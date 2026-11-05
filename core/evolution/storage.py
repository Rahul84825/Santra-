"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Evolution Storage Module

Provides versioned SQLite storage for experiences, phonetic aliases, and knowledge items
with native FTS5 full-text indexing, WAL mode, and OneDrive lock protection.
"""

import os
import json
import time
import sqlite3
import logging
import threading
from typing import Dict, List, Optional, Any

logger = logging.getLogger("Santra.Evolution.Storage")

CURRENT_SCHEMA_VERSION = 2


class EvolutionStorage:
    """Thread-safe SQLite + FTS5 storage for ALEE."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "santra_evolution.db")
        else:
            self.db_path = db_path
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_connection()
        self._apply_migrations()

    def _init_connection(self):
        """Initializes SQLite connection with OneDrive WAL lock resilience."""
        with self._lock:
            # 10.0s busy timeout and cross-thread access enabled
            self._conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._init_connection()
        return self._conn

    def _apply_migrations(self):
        """Applies versioned migrations up to CURRENT_SCHEMA_VERSION."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """)
            conn.commit()

            cursor.execute("SELECT MAX(version) FROM schema_migrations")
            row = cursor.fetchone()
            current_ver = row[0] if (row and row[0] is not None) else 0

            if current_ver < 1:
                logger.info("[MIGRATION] Applying ALEE schema version 1...")
                # 1. Experiences Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS experiences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        user_request TEXT NOT NULL,
                        intent TEXT,
                        action TEXT,
                        parameters_json TEXT,
                        success INTEGER NOT NULL,
                        message TEXT,
                        latency_ms REAL DEFAULT 0.0,
                        error_type TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_intent ON experiences(intent);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_success ON experiences(success);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_timestamp ON experiences(timestamp);")

                # 2. Phonetic Aliases Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS phonetic_aliases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        misheard_phrase TEXT UNIQUE NOT NULL,
                        intended_phrase TEXT NOT NULL,
                        confidence_count INTEGER DEFAULT 1,
                        last_seen REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_misheard ON phonetic_aliases(misheard_phrase);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_conf ON phonetic_aliases(confidence_count);")

                # 3. Knowledge Items Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata_json TEXT,
                        updated_at REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_know_cat ON knowledge_items(category);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_know_key ON knowledge_items(key);")

                # 4. Knowledge FTS5 Virtual Table & Sync Triggers
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                        key,
                        category,
                        content,
                        content=knowledge_items,
                        content_rowid=id
                    )
                """)

                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS trg_know_ai AFTER INSERT ON knowledge_items BEGIN
                        INSERT INTO knowledge_fts(rowid, key, category, content)
                        VALUES (new.id, new.key, new.category, new.content);
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS trg_know_ad AFTER DELETE ON knowledge_items BEGIN
                        INSERT INTO knowledge_fts(knowledge_fts, rowid, key, category, content)
                        VALUES ('delete', old.id, old.key, old.category, old.content);
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS trg_know_au AFTER UPDATE ON knowledge_items BEGIN
                        INSERT INTO knowledge_fts(knowledge_fts, rowid, key, category, content)
                        VALUES ('delete', old.id, old.key, old.category, old.content);
                        INSERT INTO knowledge_fts(rowid, key, category, content)
                        VALUES (new.id, new.key, new.category, new.content);
                    END;
                """)

                cursor.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (1, "Initial ALEE schema: experiences, phonetic_aliases, knowledge_items, knowledge_fts")
                )
                conn.commit()
                logger.info("[MIGRATION] ALEE schema version 1 applied successfully.")

            if current_ver < 2:
                logger.info("[MIGRATION] Applying ALEE schema version 2 (Stage 1.5 domain pre-seeding & auto_apply)...")
                # Add auto_apply column if not present
                cursor.execute("PRAGMA table_info(phonetic_aliases)")
                columns = [col[1] for col in cursor.fetchall()]
                if "auto_apply" not in columns:
                    cursor.execute("ALTER TABLE phonetic_aliases ADD COLUMN auto_apply INTEGER DEFAULT 1;")

                preseeded_aliases = [
                    ("ballorant", "valorant", 5, 1),
                    ("valorent", "valorant", 5, 1),
                    ("velorant", "valorant", 5, 1),
                    ("anti gravity", "antigravity", 5, 1),
                    ("ante gravity", "antigravity", 5, 1),
                    ("samtra", "santra", 5, 1),
                    ("sandra", "santra", 5, 1),
                    ("santa", "santra", 5, 1),
                    ("nemo tron", "nemotron", 5, 1),
                    ("vs code", "vscode", 5, 1),
                    ("visual studio", "vscode", 5, 1),
                ]
                now = time.time()
                for misheard, intended, conf, auto in preseeded_aliases:
                    cursor.execute("""
                        INSERT INTO phonetic_aliases (misheard_phrase, intended_phrase, confidence_count, auto_apply, last_seen)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(misheard_phrase) DO UPDATE SET
                            intended_phrase=excluded.intended_phrase,
                            confidence_count=MAX(phonetic_aliases.confidence_count, excluded.confidence_count),
                            auto_apply=excluded.auto_apply,
                            last_seen=excluded.last_seen
                    """, (misheard, intended, conf, auto, now))

                cursor.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (2, "Stage 1.5 domain pre-seeding and auto_apply column")
                )
                conn.commit()
                logger.info("[MIGRATION] ALEE schema version 2 applied successfully.")

            if current_ver < 3:
                logger.info("[MIGRATION] Applying ALEE schema version 3 (Autonomous Skills Registry)...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS skills (
                        skill_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        trigger_phrases TEXT NOT NULL,
                        description TEXT,
                        steps_json TEXT NOT NULL,
                        version INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'SANDBOX',
                        success_count INTEGER DEFAULT 0,
                        failure_count INTEGER DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);")

                cursor.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (3, "Stage 4 autonomous skills table")
                )
                conn.commit()
                logger.info("[MIGRATION] ALEE schema version 3 applied successfully.")

            if current_ver < 4:
                logger.info("[MIGRATION] Applying ALEE schema version 4 (Controlled Evolution Proposals & Snapshots)...")
                # 1. Evolution Proposals Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evolution_proposals (
                        proposal_id TEXT PRIMARY KEY,
                        proposal_type TEXT NOT NULL,
                        target_key TEXT NOT NULL,
                        proposed_value_json TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        evidence_count INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'PENDING',
                        created_at REAL NOT NULL,
                        reviewed_at REAL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_prop_status ON evolution_proposals(status);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_prop_type ON evolution_proposals(proposal_type);")

                # 2. Evolution Snapshots (Audit & Rollback Log) Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evolution_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        proposal_id TEXT NOT NULL,
                        previous_state_json TEXT NOT NULL,
                        new_state_json TEXT NOT NULL,
                        benchmark_score_before REAL DEFAULT 100.0,
                        benchmark_score_after REAL DEFAULT 100.0,
                        applied_at REAL NOT NULL,
                        rolled_back_at REAL,
                        FOREIGN KEY (proposal_id) REFERENCES evolution_proposals(proposal_id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_proposal ON evolution_snapshots(proposal_id);")

                cursor.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (4, "Stage 5 evolution proposals and versioned snapshots tables")
                )
                conn.commit()
                logger.info("[MIGRATION] ALEE schema version 4 applied successfully.")

            cursor.close()

    # ==========================================
    # EXPERIENCES API
    # ==========================================
    def record_experience(
        self,
        user_request: str,
        intent: Optional[str] = None,
        action: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        message: Optional[str] = None,
        latency_ms: float = 0.0,
        error_type: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> int:
        """Inserts an execution experience record."""
        ts = timestamp or time.time()
        param_str = json.dumps(parameters or {}, default=str)
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO experiences (
                    timestamp, user_request, intent, action,
                    parameters_json, success, message, latency_ms, error_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                user_request,
                intent or "",
                action or "",
                param_str,
                1 if success else 0,
                message or "",
                float(latency_ms),
                error_type or ("" if success else "EXECUTION_ERROR")
            ))
            exp_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            return exp_id

    # ==========================================
    # PHONETIC ALIASES API
    # ==========================================
    def upsert_alias(
        self,
        misheard_phrase: str,
        intended_phrase: str,
        delta: int = 1,
        auto_apply: int = 1
    ) -> Dict[str, Any]:
        """
        Inserts or increments an alias. Returns the updated alias dict.
        """
        misheard = misheard_phrase.strip().lower()
        intended = intended_phrase.strip()
        now = time.time()

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, confidence_count, auto_apply FROM phonetic_aliases WHERE misheard_phrase = ?",
                (misheard,)
            )
            row = cursor.fetchone()
            if row:
                alias_id = row["id"]
                new_conf = row["confidence_count"] + delta
                cursor.execute("""
                    UPDATE phonetic_aliases
                    SET intended_phrase = ?, confidence_count = ?, auto_apply = ?, last_seen = ?
                    WHERE id = ?
                """, (intended, new_conf, auto_apply, now, alias_id))
            else:
                new_conf = max(1, delta)
                cursor.execute("""
                    INSERT INTO phonetic_aliases (misheard_phrase, intended_phrase, confidence_count, auto_apply, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                """, (misheard, intended, new_conf, auto_apply, now))
                alias_id = cursor.lastrowid
            conn.commit()
            cursor.close()

            return {
                "id": alias_id,
                "misheard_phrase": misheard,
                "intended_phrase": intended,
                "confidence_count": new_conf,
                "auto_apply": auto_apply,
                "last_seen": now
            }

    def get_active_aliases(self, min_confidence: int = 3) -> Dict[str, str]:
        """
        Retrieves all aliases that meet min_confidence or have auto_apply=1.
        Returns a dict of {misheard_phrase: intended_phrase}.
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT misheard_phrase, intended_phrase
                FROM phonetic_aliases
                WHERE confidence_count >= ? OR auto_apply = 1
            """, (min_confidence,))
            rows = cursor.fetchall()
            cursor.close()
            return {row["misheard_phrase"]: row["intended_phrase"] for row in rows}

    def get_all_aliases(self) -> List[Dict[str, Any]]:
        """Returns all aliases regardless of confidence."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM phonetic_aliases ORDER BY confidence_count DESC, last_seen DESC")
            rows = cursor.fetchall()
            cursor.close()
            return [dict(r) for r in rows]

    # ==========================================
    # KNOWLEDGE & FTS5 API
    # ==========================================
    def upsert_knowledge(
        self,
        key: str,
        category: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Upserts a knowledge item and synchronizes full-text search."""
        now = time.time()
        meta_str = json.dumps(metadata or {}, default=str)
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO knowledge_items (key, category, content, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    category=excluded.category,
                    content=excluded.content,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
            """, (key, category, content, meta_str, now))
            item_id = cursor.lastrowid
            if not item_id or item_id == 0:
                cursor.execute("SELECT id FROM knowledge_items WHERE key = ?", (key,))
                row = cursor.fetchone()
                item_id = row[0] if row else 0
            conn.commit()
            cursor.close()
            return item_id

    def search_knowledge_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Performs full-text search against knowledge_items via FTS5."""
        clean_query = query.strip().replace('"', '""')
        if not clean_query:
            return []
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT k.id, k.key, k.category, k.content, k.metadata_json, k.updated_at
                    FROM knowledge_items k
                    JOIN knowledge_fts f ON k.id = f.rowid
                    WHERE knowledge_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (clean_query, limit))
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    item = dict(r)
                    if item.get("metadata_json"):
                        try:
                            item["metadata"] = json.loads(item["metadata_json"])
                        except Exception:
                            item["metadata"] = {}
                    results.append(item)
                return results
            except Exception as e:
                logger.warning(f"[FTS5] Search error for '{query}': {e}")
                return []
            finally:
                cursor.close()

    def search_knowledge_bm25(
        self,
        query: str,
        limit: int = 3,
        allowed_statuses: tuple = ("VERIFIED", "UNVERIFIED")
    ) -> List[Dict[str, Any]]:
        """
        Fast BM25 retrieval against knowledge_fts.
        Returns top results ranked by bm25 score in < 5ms.
        """
        import re
        if " OR " in query or '"' in query:
            fts_match_expr = query
        else:
            raw_tokens = [re.sub(r"[^\w\-_]", "", t) for t in query.split()]
            raw_tokens = [t for t in raw_tokens if len(t) >= 2]
            stopwords = {
                "what", "is", "the", "how", "does", "can", "you", "tell", "me", "about",
                "in", "on", "for", "with", "to", "of", "a", "an", "my", "please", "sir",
                "do", "did", "are", "was", "were", "be", "been", "being", "have", "has",
                "had", "it", "its", "this", "that", "these", "those", "i", "we", "they",
                "them", "he", "she", "him", "her", "and", "or", "but", "if", "so", "as",
                "at", "by", "from", "up", "into", "over", "after", "then", "just", "now",
                "there", "here", "where", "which", "who", "whom", "why", "all", "any"
            }
            meaningful = [t for t in raw_tokens if t.lower() not in stopwords]
            tokens_to_use = meaningful if meaningful else raw_tokens
            if not tokens_to_use:
                return []
            fts_match_expr = " OR ".join(f'"{t}"' for t in tokens_to_use)
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT k.id, k.key, k.category, k.content, k.metadata_json, k.updated_at,
                           bm25(knowledge_fts) AS bm25_score
                    FROM knowledge_items k
                    JOIN knowledge_fts f ON k.id = f.rowid
                    WHERE knowledge_fts MATCH ?
                    ORDER BY bm25_score ASC
                    LIMIT ?
                """, (fts_match_expr, limit * 3))
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    item = dict(r)
                    metadata = {}
                    if item.get("metadata_json"):
                        try:
                            metadata = json.loads(item["metadata_json"])
                        except Exception:
                            metadata = {}
                    status = metadata.get("verification_status", "VERIFIED")
                    if status in allowed_statuses:
                        item["metadata"] = metadata
                        item["verification_status"] = status
                        item["source_url"] = metadata.get("source_url", "")
                        results.append(item)
                    if len(results) >= limit:
                        break
                return results
            except Exception as e:
                logger.warning(f"[BM25] Search error for '{query}': {e}")
                return []
            finally:
                cursor.close()

    def optimize_fts(self):
        """Runs FTS5 table optimization during idle maintenance."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('optimize');")
                conn.commit()
                cursor.close()
                logger.debug("[FTS5] FTS index optimized successfully.")
            except Exception as e:
                logger.warning(f"[FTS5] Index optimization error: {e}")

    # ==========================================
    # SKILLS API (STAGE 4)
    # ==========================================
    def upsert_skill(self, skill: Dict[str, Any]) -> str:
        """Inserts or updates an autonomous skill definition."""
        skill_id = skill.get("skill_id") or f"skill_{int(time.time() * 1000)}"
        name = skill.get("name", "unnamed_skill")
        triggers = skill.get("trigger_phrases", [])
        if isinstance(triggers, list):
            triggers_json = json.dumps(triggers)
        else:
            triggers_json = str(triggers)

        description = skill.get("description", "")
        steps = skill.get("steps", skill.get("steps_json", []))
        if isinstance(steps, list):
            steps_json = json.dumps(steps)
        else:
            steps_json = str(steps)

        version = int(skill.get("version", 1))
        status = skill.get("status", "SANDBOX")
        success_count = int(skill.get("success_count", 0))
        failure_count = int(skill.get("failure_count", 0))
        now = time.time()
        created_at = float(skill.get("created_at", now))
        updated_at = float(skill.get("updated_at", now))

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO skills (
                    skill_id, name, trigger_phrases, description, steps_json,
                    version, status, success_count, failure_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    name=excluded.name,
                    trigger_phrases=excluded.trigger_phrases,
                    description=excluded.description,
                    steps_json=excluded.steps_json,
                    version=excluded.version,
                    status=excluded.status,
                    success_count=MAX(skills.success_count, excluded.success_count),
                    failure_count=MAX(skills.failure_count, excluded.failure_count),
                    updated_at=excluded.updated_at
            """, (
                skill_id, name, triggers_json, description, steps_json,
                version, status, success_count, failure_count, created_at, updated_at
            ))
            conn.commit()
            cursor.close()

        return skill_id

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single skill by ID."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT skill_id, name, trigger_phrases, description, steps_json,
                       version, status, success_count, failure_count, created_at, updated_at
                FROM skills WHERE skill_id = ?
            """, (skill_id,))
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return None

            try:
                triggers = json.loads(row[2])
            except Exception:
                triggers = [row[2]]
            try:
                steps = json.loads(row[4])
            except Exception:
                steps = []

            return {
                "skill_id": row[0],
                "name": row[1],
                "trigger_phrases": triggers,
                "description": row[3],
                "steps": steps,
                "version": row[5],
                "status": row[6],
                "success_count": row[7],
                "failure_count": row[8],
                "created_at": row[9],
                "updated_at": row[10]
            }

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """Retrieves all registered skills."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT skill_id, name, trigger_phrases, description, steps_json,
                       version, status, success_count, failure_count, created_at, updated_at
                FROM skills ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            cursor.close()

            skills = []
            for row in rows:
                try:
                    triggers = json.loads(row[2])
                except Exception:
                    triggers = [row[2]]
                try:
                    steps = json.loads(row[4])
                except Exception:
                    steps = []
                skills.append({
                    "skill_id": row[0],
                    "name": row[1],
                    "trigger_phrases": triggers,
                    "description": row[3],
                    "steps": steps,
                    "version": row[5],
                    "status": row[6],
                    "success_count": row[7],
                    "failure_count": row[8],
                    "created_at": row[9],
                    "updated_at": row[10]
                })
            return skills

    def get_verified_skills(self) -> List[Dict[str, Any]]:
        """Retrieves all verified and active skills."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT skill_id, name, trigger_phrases, description, steps_json,
                       version, status, success_count, failure_count, created_at, updated_at
                FROM skills WHERE status = 'VERIFIED'
                ORDER BY success_count DESC
            """)
            rows = cursor.fetchall()
            cursor.close()

            skills = []
            for row in rows:
                try:
                    triggers = json.loads(row[2])
                except Exception:
                    triggers = [row[2]]
                try:
                    steps = json.loads(row[4])
                except Exception:
                    steps = []
                skills.append({
                    "skill_id": row[0],
                    "name": row[1],
                    "trigger_phrases": triggers,
                    "description": row[3],
                    "steps": steps,
                    "version": row[5],
                    "status": row[6],
                    "success_count": row[7],
                    "failure_count": row[8],
                    "created_at": row[9],
                    "updated_at": row[10]
                })
            return skills

    def update_skill_status(self, skill_id: str, status: str) -> bool:
        """Updates the operational status of a skill ('SANDBOX', 'VERIFIED', 'DEPRECATED', 'BLOCKED')."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE skills SET status = ?, updated_at = ? WHERE skill_id = ?
            """, (status, time.time(), skill_id))
            affected = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return affected

    def record_skill_execution(self, skill_id: str, success: bool) -> bool:
        """Updates skill execution counts based on success/failure."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if success:
                cursor.execute("""
                    UPDATE skills SET success_count = success_count + 1, updated_at = ? WHERE skill_id = ?
                """, (time.time(), skill_id))
            else:
                cursor.execute("""
                    UPDATE skills SET failure_count = failure_count + 1, updated_at = ? WHERE skill_id = ?
                """, (time.time(), skill_id))
            affected = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return affected

    # ==========================================
    # PROPOSALS & SNAPSHOTS API (STAGE 5)
    # ==========================================
    def upsert_proposal(self, proposal: Dict[str, Any]) -> str:
        """Inserts or updates an evolution proposal."""
        prop_type = proposal.get("proposal_type", "INTENT_RULE")
        prop_id = proposal.get("proposal_id") or f"prop_{prop_type.lower()}_{int(time.time() * 1000)}"
        target_key = proposal.get("target_key", "")
        p_val = proposal.get("proposed_value_json", proposal.get("proposed_value", {}))
        val_json = json.dumps(p_val) if isinstance(p_val, (dict, list)) else str(p_val)
        reason = proposal.get("reason", "")
        evidence_count = int(proposal.get("evidence_count", 1))
        status = proposal.get("status", "PENDING")
        now = time.time()
        created_at = float(proposal.get("created_at", now))
        reviewed_at = proposal.get("reviewed_at")

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO evolution_proposals (
                    proposal_id, proposal_type, target_key, proposed_value_json,
                    reason, evidence_count, status, created_at, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    proposed_value_json=excluded.proposed_value_json,
                    reason=excluded.reason,
                    evidence_count=MAX(evolution_proposals.evidence_count, excluded.evidence_count),
                    status=CASE WHEN evolution_proposals.status = 'APPROVED' THEN evolution_proposals.status ELSE excluded.status END,
                    reviewed_at=CASE WHEN evolution_proposals.status = 'APPROVED' THEN evolution_proposals.reviewed_at ELSE excluded.reviewed_at END
            """, (
                prop_id, prop_type, target_key, val_json,
                reason, evidence_count, status, created_at, reviewed_at
            ))
            conn.commit()
            cursor.close()

        return prop_id

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single proposal by ID."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT proposal_id, proposal_type, target_key, proposed_value_json,
                       reason, evidence_count, status, created_at, reviewed_at
                FROM evolution_proposals WHERE proposal_id = ?
            """, (proposal_id,))
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return None

            try:
                p_val = json.loads(row[3])
            except Exception:
                p_val = row[3]

            return {
                "proposal_id": row[0],
                "proposal_type": row[1],
                "target_key": row[2],
                "proposed_value": p_val,
                "reason": row[4],
                "evidence_count": row[5],
                "status": row[6],
                "created_at": row[7],
                "reviewed_at": row[8]
            }

    def get_pending_proposals(self) -> List[Dict[str, Any]]:
        """Retrieves all pending proposals awaiting approval."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT proposal_id, proposal_type, target_key, proposed_value_json,
                       reason, evidence_count, status, created_at, reviewed_at
                FROM evolution_proposals WHERE status = 'PENDING'
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            cursor.close()

            proposals = []
            for row in rows:
                try:
                    p_val = json.loads(row[3])
                except Exception:
                    p_val = row[3]
                proposals.append({
                    "proposal_id": row[0],
                    "proposal_type": row[1],
                    "target_key": row[2],
                    "proposed_value": p_val,
                    "reason": row[4],
                    "evidence_count": row[5],
                    "status": row[6],
                    "created_at": row[7],
                    "reviewed_at": row[8]
                })
            return proposals

    def get_all_proposals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves proposals ordered by creation date."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT proposal_id, proposal_type, target_key, proposed_value_json,
                       reason, evidence_count, status, created_at, reviewed_at
                FROM evolution_proposals
                ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            cursor.close()

            proposals = []
            for row in rows:
                try:
                    p_val = json.loads(row[3])
                except Exception:
                    p_val = row[3]
                proposals.append({
                    "proposal_id": row[0],
                    "proposal_type": row[1],
                    "target_key": row[2],
                    "proposed_value": p_val,
                    "reason": row[4],
                    "evidence_count": row[5],
                    "status": row[6],
                    "created_at": row[7],
                    "reviewed_at": row[8]
                })
            return proposals

    def update_proposal_status(self, proposal_id: str, status: str, reviewed_at: Optional[float] = None) -> bool:
        """Updates the status of a proposal ('PENDING', 'APPROVED', 'REJECTED', 'ROLLED_BACK', 'FAILED')."""
        rev_t = reviewed_at if reviewed_at is not None else time.time()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE evolution_proposals SET status = ?, reviewed_at = ? WHERE proposal_id = ?
            """, (status, rev_t, proposal_id))
            affected = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return affected

    def record_snapshot(
        self,
        proposal_id: str,
        previous_state: Dict[str, Any],
        new_state: Dict[str, Any],
        score_before: float,
        score_after: float
    ) -> str:
        """Records a versioned audit snapshot for reversible rollbacks."""
        snapshot_id = f"snap_{int(time.time() * 1000)}"
        prev_json = json.dumps(previous_state)
        new_json = json.dumps(new_state)
        now = time.time()

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO evolution_snapshots (
                    snapshot_id, proposal_id, previous_state_json, new_state_json,
                    benchmark_score_before, benchmark_score_after, applied_at, rolled_back_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """, (
                snapshot_id, proposal_id, prev_json, new_json,
                float(score_before), float(score_after), now
            ))
            conn.commit()
            cursor.close()

        return snapshot_id

    def get_snapshot_for_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the latest audit snapshot for a given proposal."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT snapshot_id, proposal_id, previous_state_json, new_state_json,
                       benchmark_score_before, benchmark_score_after, applied_at, rolled_back_at
                FROM evolution_snapshots WHERE proposal_id = ?
                ORDER BY applied_at DESC LIMIT 1
            """, (proposal_id,))
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return None

            try:
                prev_st = json.loads(row[2])
            except Exception:
                prev_st = {}
            try:
                new_st = json.loads(row[3])
            except Exception:
                new_st = {}

            return {
                "snapshot_id": row[0],
                "proposal_id": row[1],
                "previous_state": prev_st,
                "new_state": new_st,
                "benchmark_score_before": row[4],
                "benchmark_score_after": row[5],
                "applied_at": row[6],
                "rolled_back_at": row[7]
            }

    def mark_snapshot_rolled_back(self, snapshot_id: str) -> bool:
        """Marks a snapshot as rolled back with a timestamp."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE evolution_snapshots SET rolled_back_at = ? WHERE snapshot_id = ?
            """, (time.time(), snapshot_id))
            affected = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return affected

    # ==========================================
    # TELEMETRY & STATS
    # ==========================================
    def get_stats(self) -> Dict[str, Any]:
        """Compiles summary statistics of the evolution store."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*), SUM(success) FROM experiences")
            row = cursor.fetchone()
            total_exp = row[0] or 0
            success_exp = row[1] or 0
            fail_exp = total_exp - success_exp
            success_rate = (success_exp / total_exp) if total_exp > 0 else 1.0

            cursor.execute("SELECT COUNT(*) FROM phonetic_aliases")
            total_aliases = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM phonetic_aliases WHERE confidence_count >= 3")
            active_aliases = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM knowledge_items")
            total_knowledge = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM skills")
            total_skills = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM skills WHERE status = 'VERIFIED'")
            verified_skills = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM evolution_proposals WHERE status = 'PENDING'")
            pending_props = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM evolution_proposals WHERE status = 'APPROVED'")
            approved_props = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM evolution_proposals")
            total_props = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM evolution_snapshots")
            total_snaps = cursor.fetchone()[0] or 0

            cursor.close()

            return {
                "total_experiences": total_exp,
                "successful_experiences": success_exp,
                "failed_experiences": fail_exp,
                "success_rate": round(success_rate, 4),
                "total_aliases": total_aliases,
                "active_aliases": active_aliases,
                "total_knowledge_items": total_knowledge,
                "total_skills": total_skills,
                "verified_skills": verified_skills,
                "pending_proposals_count": pending_props,
                "approved_proposals_count": approved_props,
                "total_proposals": total_props,
                "total_snapshots": total_snaps
            }

    def close(self):
        """Cleanly closes database connection."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None


# Singleton instance
evolution_storage = EvolutionStorage()
