"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Stage 4 Verification Suite: Autonomous Skill Registry, Legacy DB Bridge & Voice Diagnostics
"""

import os
import time
import json
import sqlite3
import tempfile
import unittest

from core.evolution.storage import EvolutionStorage
from core.evolution.collector import ExperienceCollector
from core.evolution.skill_developer import SkillDeveloper
from core.evolution.legacy_bridge import LegacyMemoryBridge


class TestALEEStage4(unittest.TestCase):
    """Rigorous Stage 4 verification under strict hardware and isolation constraints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.temp_dir.name, "test_evolution_s4.db")
        self.storage = EvolutionStorage(db_path=self.test_db_path)
        self.collector = ExperienceCollector(storage=self.storage)
        self.skill_dev = SkillDeveloper(storage=self.storage, collector=self.collector)

    def tearDown(self):
        self.collector.shutdown()
        self.storage.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ==========================================
    # TEST 1: SAFETY GOVERNOR REJECTION
    # ==========================================
    def test_safety_governor_rejects_malicious_skills(self):
        """Ensures arbitrary shell execution, file deletion, and core file attacks are blocked."""
        malicious_specs = [
            {
                "name": "malicious_shell_injection",
                "trigger_phrases": ["destroy everything"],
                "steps": [
                    {"tool": "open_application", "args": {"app_name": "cmd.exe && del /f /q *"}}
                ]
            },
            {
                "name": "prohibited_tool_eval",
                "trigger_phrases": ["eval python"],
                "steps": [
                    {"tool": "eval", "args": {"code": "import os; os.system('rm -rf /')"}}
                ]
            },
            {
                "name": "prohibited_os_system",
                "trigger_phrases": ["nuke files"],
                "steps": [
                    {"tool": "open_app", "args": {"app_name": "notepad", "extra": "os.system('del c:')"}}
                ]
            },
            {
                "name": "core_code_tampering",
                "trigger_phrases": ["edit core"],
                "steps": [
                    {"tool": "open_application", "args": {"app_name": "notepad core/jarvis_runtime.py"}}
                ]
            },
            {
                "name": "invalid_url_scheme",
                "trigger_phrases": ["launch file url"],
                "steps": [
                    {"tool": "open_url", "args": {"url": "file:///c:/windows/system32/cmd.exe"}}
                ]
            }
        ]

        for spec in malicious_specs:
            valid, reason = self.skill_dev.validate_skill_spec(spec)
            self.assertFalse(valid, f"Malicious spec '{spec['name']}' should have been rejected!")
            self.assertIn("Safety Governor violation", reason)

            # Attempting sandbox execution should mark as BLOCKED
            spec["status"] = "SANDBOX"
            skill_id = self.storage.upsert_skill(spec)
            promoted = self.skill_dev.test_skill_in_sandbox(skill_id)
            self.assertFalse(promoted)
            db_skill = self.storage.get_skill(skill_id)
            self.assertEqual(db_skill["status"], "BLOCKED")

    # ==========================================
    # TEST 2: DRY-RUN SANDBOX PROMOTION
    # ==========================================
    def test_sandbox_dry_run_promotion(self):
        """Verifies safe candidate skills pass dry-run testing and promote to VERIFIED."""
        safe_spec = {
            "name": "launch dev docs",
            "trigger_phrases": ["open python docs", "show python documentation"],
            "description": "Safe utility skill launching official python docs.",
            "steps": [
                {"tool": "open_url", "args": {"url": "https://docs.python.org/3/"}},
                {"tool": "speak", "args": {"text": "Opening Python documentation."}}
            ],
            "status": "SANDBOX"
        }

        skill_id = self.storage.upsert_skill(safe_spec)
        self.assertEqual(self.storage.get_skill(skill_id)["status"], "SANDBOX")

        # Dry-run test should pass and promote
        passed = self.skill_dev.test_skill_in_sandbox(skill_id)
        self.assertTrue(passed, "Safe skill must pass sandbox testing")

        promoted = self.storage.get_skill(skill_id)
        self.assertEqual(promoted["status"], "VERIFIED")

        # Must now be active in memory trigger cache
        match = self.skill_dev.match_trigger("open python docs")
        self.assertIsNotNone(match)
        self.assertEqual(match["name"], "launch dev docs")

    # ==========================================
    # TEST 3: SUB-MILLISECOND TRIGGER MATCHING (< 1ms)
    # ==========================================
    def test_sub_millisecond_trigger_matching(self):
        """Confirms in-memory skill trigger matching runs in strictly under 1.0 ms."""
        # Ensure pre-seeded skills are loaded
        verified = self.storage.get_verified_skills()
        self.assertGreaterEqual(len(verified), 2)

        triggers_to_test = [
            "dev workspace mode",
            "developer mode",
            "evolution status",
            "santra evolution report",
            "evolution self report"
        ]

        for trig in triggers_to_test:
            t0 = time.perf_counter()
            match = self.skill_dev.match_trigger(trig)
            dt_ms = (time.perf_counter() - t0) * 1000

            self.assertIsNotNone(match, f"Failed to match trigger '{trig}'")
            self.assertLess(dt_ms, 1.0, f"Trigger matching took {dt_ms:.4f} ms (must be < 1.0 ms)")

    # ==========================================
    # TEST 4: WORKFLOW MINING FROM EXPERIENCES
    # ==========================================
    def test_workflow_mining_from_experiences(self):
        """Verifies repeated sequential command pairs are discovered and proposed in SANDBOX."""
        base_t = time.time() - 3600

        # Simulate user running "open code" followed by "open localhost" twice within 30s
        for offset in [0, 1800]:
            self.storage.record_experience(
                user_request="open code",
                intent="OPEN_APPLICATION",
                action="open_app",
                parameters={"app_name": "code"},
                success=True,
                timestamp=base_t + offset
            )
            self.storage.record_experience(
                user_request="open localhost",
                intent="OPEN_URL",
                action="open_url",
                parameters={"url": "http://localhost:3000"},
                success=True,
                timestamp=base_t + offset + 15.0  # 15s later
            )

        proposed = self.skill_dev.propose_skills_from_experiences(window_seconds=60.0, min_occurrences=2)
        self.assertGreaterEqual(len(proposed), 1)

        candidate = proposed[0]
        self.assertEqual(candidate["status"], "SANDBOX")
        self.assertIn("open code and open localhost", candidate["trigger_phrases"][0])
        self.assertEqual(len(candidate["steps"]), 2)

    # ==========================================
    # TEST 5: LEGACY DB BRIDGE (READ-ONLY & IDEMPOTENT)
    # ==========================================
    def test_legacy_bridge_idempotent_read_only(self):
        """Verifies legacy bridge synchronizes without altering or locking legacy files."""
        # 1. Create a dummy legacy jarvis_memory.db
        legacy_path = os.path.join(self.temp_dir.name, "legacy_jarvis_memory.db")
        conn = sqlite3.connect(legacy_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE knowledge_notes (
                id INTEGER PRIMARY KEY,
                topic TEXT,
                content TEXT,
                source TEXT,
                created_at REAL
            )
        """)
        cur.execute("""
            CREATE TABLE learned_procedures (
                id INTEGER PRIMARY KEY,
                procedure_name TEXT,
                intent TEXT,
                trigger_patterns TEXT,
                steps TEXT,
                success_count INTEGER,
                failure_count INTEGER,
                confidence REAL,
                is_active INTEGER,
                created_at REAL,
                updated_at REAL
            )
        """)
        cur.execute("""
            CREATE TABLE execution_experiences (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                user_request TEXT,
                normalized_intent TEXT,
                tool_or_procedure TEXT,
                execution_parameters TEXT,
                execution_outcome TEXT,
                observed_failure TEXT
            )
        """)

        # Insert dummy records
        cur.execute("INSERT INTO knowledge_notes VALUES (1, 'Preference', 'Prefers dark mode', 'user', 1700000000.0)")
        cur.execute("INSERT INTO learned_procedures VALUES (1, 'proc_backup', 'BACKUP', '[\"run backup\"]', '[{\"tool\": \"speak\", \"args\": {\"text\": \"done\"}}]', 5, 0, 0.95, 1, 1700000000.0, 1700000000.0)")
        cur.execute("INSERT INTO execution_experiences VALUES (1, 1700000100.0, 'check weather', 'WEATHER', 'get_weather', '{}', 'success', NULL)")
        conn.commit()
        conn.close()

        # Capture file stat before sync
        stat_before = os.stat(legacy_path)

        # Execute Bridge Sync
        bridge = LegacyMemoryBridge(storage=self.storage)
        res1 = bridge.sync_legacy_memory(legacy_db_path=legacy_path)
        self.assertEqual(res1["synced_notes"], 1)
        self.assertEqual(res1["synced_procedures"], 1)
        self.assertEqual(res1["synced_experiences"], 1)

        # Verify second sync is idempotent
        res2 = bridge.sync_legacy_memory(legacy_db_path=legacy_path)
        self.assertEqual(res2["synced_experiences"], 0)
        self.assertEqual(res2["skipped_experiences"], 1)

        # Verify legacy file was untouched
        stat_after = os.stat(legacy_path)
        self.assertEqual(stat_before.st_mtime, stat_after.st_mtime)
        self.assertEqual(stat_before.st_size, stat_after.st_size)

    # ==========================================
    # TEST 6: VOICE SELF-DIAGNOSTICS EXECUTION
    # ==========================================
    def test_voice_evolution_status_response(self):
        """Verifies 'evolution self report' generates comprehensive voice telemetry."""
        skill = self.skill_dev.match_trigger("evolution status")
        self.assertIsNotNone(skill)

        res = self.skill_dev.execute_skill(skill, speak=False)
        self.assertTrue(res["success"])
        msg = res["message"]
        self.assertIn("ALEE system is", msg)
        self.assertIn("benchmark pass score", msg)
        self.assertIn("phonetic domain aliases", msg)
        self.assertIn("verified autonomous skills", msg)


if __name__ == "__main__":
    unittest.main()
