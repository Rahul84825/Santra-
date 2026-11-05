"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Legacy Memory Bridge Module

Performs safe, idempotent, read-only synchronization from legacy SQLite databases
(memory/jarvis_memory.db) into data/santra_evolution.db without modifying or locking
the legacy database files.
"""

import os
import json
import time
import hashlib
import sqlite3
import logging
from typing import Optional, Dict, Any, Set
from core.evolution.storage import EvolutionStorage, evolution_storage

logger = logging.getLogger("Santra.Evolution.LegacyBridge")


def get_default_legacy_db_path() -> str:
    """Returns absolute path to the default legacy jarvis_memory.db."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "memory", "jarvis_memory.db")


class LegacyMemoryBridge:
    """Read-only synchronizer bridging legacy SANTRA memory into ALEE evolution store."""

    def __init__(self, storage: Optional[EvolutionStorage] = None):
        self.storage = storage or evolution_storage

    def sync_legacy_memory(
        self,
        legacy_db_path: Optional[str] = None,
        sync_experiences: bool = True,
        sync_notes: bool = True,
        sync_procedures: bool = True
    ) -> Dict[str, Any]:
        """
        Idempotently synchronizes legacy records into santra_evolution.db in read-only mode.
        Guarantees ZERO writes, zero locks, and zero WAL file creation on the legacy database.
        """
        db_path = legacy_db_path or get_default_legacy_db_path()
        if not os.path.exists(db_path):
            logger.info(f"[LEGACY_BRIDGE] Legacy database not found at '{db_path}'. Skipping sync.")
            return {
                "synced_notes": 0,
                "synced_procedures": 0,
                "synced_experiences": 0,
                "status": "NOT_FOUND"
            }

        # Safe read-only URI connection
        abs_path = os.path.abspath(db_path).replace("\\", "/")
        uri = f"file:{abs_path}?mode=ro"
        logger.info(f"[LEGACY_BRIDGE] Connecting to legacy database in read-only mode: {uri}")

        synced_notes = 0
        synced_procs = 0
        synced_exp = 0
        skipped_exp = 0

        legacy_conn = None
        try:
            legacy_conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            legacy_cursor = legacy_conn.cursor()

            # Check existing tables in legacy db
            legacy_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in legacy_cursor.fetchall()}

            # 1. Sync Knowledge Notes -> knowledge_items
            if sync_notes and "knowledge_notes" in tables:
                legacy_cursor.execute("SELECT topic, content, source, created_at FROM knowledge_notes")
                notes = legacy_cursor.fetchall()
                for topic, content, source, created_at in notes:
                    if not content or not content.strip():
                        continue
                    topic_str = str(topic or "General Note").strip()
                    content_str = str(content).strip()
                    hash_key = hashlib.sha256(f"{topic_str}:{content_str}".encode("utf-8")).hexdigest()[:16]
                    unique_key = f"legacy:note:{hash_key}"
                    formatted_content = f"[{topic_str}] {content_str}"
                    meta = {
                        "topic": topic_str,
                        "source": source or "legacy_notes",
                        "legacy_created_at": created_at
                    }
                    self.storage.upsert_knowledge(
                        key=unique_key,
                        category="legacy_notes",
                        content=formatted_content,
                        metadata=meta
                    )
                    synced_notes += 1

            # 2. Sync Learned Procedures -> skills table
            if sync_procedures and "learned_procedures" in tables:
                legacy_cursor.execute("""
                    SELECT procedure_name, intent, trigger_patterns, steps,
                           success_count, failure_count, confidence, is_active,
                           created_at, updated_at
                    FROM learned_procedures
                """)
                procs = legacy_cursor.fetchall()
                for (proc_name, intent, trigger_patterns, steps,
                     s_count, f_count, conf, is_active, c_at, u_at) in procs:
                    if not proc_name:
                        continue

                    # Parse triggers
                    triggers = []
                    if trigger_patterns:
                        try:
                            triggers = json.loads(trigger_patterns)
                        except Exception:
                            triggers = [trigger_patterns]
                    if not triggers:
                        triggers = [proc_name.replace("proc_", "").replace("_", " ")]

                    # Parse steps
                    steps_list = []
                    if steps:
                        try:
                            steps_list = json.loads(steps)
                        except Exception:
                            steps_list = []

                    # Determine status
                    confidence = float(conf or 1.0)
                    active = bool(is_active)
                    status = "VERIFIED" if (active and confidence >= 0.8) else "SANDBOX"

                    skill_dict = {
                        "skill_id": f"legacy_proc_{proc_name}",
                        "name": proc_name,
                        "trigger_phrases": triggers,
                        "description": f"Imported legacy procedure for intent '{intent or 'COMPLEX_TASK'}'",
                        "steps": steps_list,
                        "version": 1,
                        "status": status,
                        "success_count": int(s_count or 0),
                        "failure_count": int(f_count or 0),
                        "created_at": float(c_at or time.time()),
                        "updated_at": float(u_at or time.time())
                    }
                    self.storage.upsert_skill(skill_dict)
                    synced_procs += 1

            # 3. Sync Execution Experiences -> experiences table
            if sync_experiences and "execution_experiences" in tables:
                # Fetch existing timestamps in evolution store to avoid duplicates
                existing_timestamps: Set[float] = set()
                with self.storage._lock:
                    s_conn = self.storage._get_connection()
                    s_cur = s_conn.cursor()
                    s_cur.execute("SELECT timestamp FROM experiences")
                    for row in s_cur.fetchall():
                        existing_timestamps.add(round(float(row[0]), 3))
                    s_cur.close()

                legacy_cursor.execute("""
                    SELECT timestamp, user_request, normalized_intent, tool_or_procedure,
                           execution_parameters, execution_outcome, observed_failure
                    FROM execution_experiences
                """)
                exp_rows = legacy_cursor.fetchall()

                new_experiences = []
                for (ts, user_req, norm_intent, tool_proc, params, outcome, failure) in exp_rows:
                    if not user_req or not user_req.strip():
                        continue
                    ts_float = float(ts or time.time())
                    if round(ts_float, 3) in existing_timestamps:
                        skipped_exp += 1
                        continue

                    outcome_lower = str(outcome).lower()
                    success = 1 if outcome_lower in ["success", "completed", "true", "1", "independently_verified"] else 0
                    new_experiences.append((
                        ts_float,
                        user_req.strip(),
                        norm_intent or "COMMAND",
                        tool_proc or "system",
                        params or "{}",
                        success,
                        outcome or "Executed",
                        0.0,
                        failure
                    ))
                    existing_timestamps.add(round(ts_float, 3))

                if new_experiences:
                    with self.storage._lock:
                        s_conn = self.storage._get_connection()
                        s_cur = s_conn.cursor()
                        s_cur.executemany("""
                            INSERT INTO experiences (
                                timestamp, user_request, intent, action,
                                parameters_json, success, message, latency_ms, error_type
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, new_experiences)
                        s_conn.commit()
                        s_cur.close()
                    synced_exp = len(new_experiences)

            logger.info(
                f"[LEGACY_BRIDGE] Synchronization complete: {synced_notes} notes, "
                f"{synced_procs} procedures, {synced_exp} experiences synced ({skipped_exp} skipped)."
            )

        except Exception as e:
            logger.error(f"[LEGACY_BRIDGE] Error during legacy memory sync: {e}", exc_info=True)
            return {
                "synced_notes": synced_notes,
                "synced_procedures": synced_procs,
                "synced_experiences": synced_exp,
                "error": str(e)
            }
        finally:
            if legacy_conn:
                try:
                    legacy_conn.close()
                except Exception:
                    pass

        return {
            "synced_notes": synced_notes,
            "synced_procedures": synced_procs,
            "synced_experiences": synced_exp,
            "skipped_experiences": skipped_exp,
            "status": "SUCCESS"
        }


# Singleton instance
legacy_bridge = LegacyMemoryBridge()
