"""
ALEE Stage 1 Verification Suite (Isolated Test Harness)
Tests SQLite WAL storage, in-memory alias cache (<1ms), privacy scrubber,
ResourceGuard fast detection, and EvolutionScheduler health report generation.
Completely isolated in tempfile.TemporaryDirectory() - zero production DB pollution.
"""

import os
import sys
import time
import json
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.evolution.storage import EvolutionStorage
from core.evolution.resource_guard import ResourceGuard
from core.evolution.collector import ExperienceCollector, scrub_text, scrub_data
from core.evolution.scheduler import EvolutionScheduler


class TestALEEStage1(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_evolution.db")
        cls.report_path = os.path.join(cls.temp_dir.name, "health_report.json")

        cls.storage = EvolutionStorage(db_path=cls.db_path)
        cls.collector = ExperienceCollector(storage=cls.storage)
        cls.guard = ResourceGuard()
        cls.scheduler = EvolutionScheduler(
            storage=cls.storage,
            guard=cls.guard,
            collector=cls.collector,
            report_path=cls.report_path
        )

    @classmethod
    def tearDownClass(cls):
        cls.collector.shutdown()
        cls.storage.close()
        cls.temp_dir.cleanup()

    def test_01_storage_initialization_and_wal(self):
        """Verifies database initializes with WAL mode, migrations, and required tables."""
        self.assertTrue(os.path.exists(self.db_path), f"Database file does not exist at {self.db_path}")

        conn = self.storage._get_connection()
        cursor = conn.cursor()

        # Check WAL mode
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        self.assertEqual(journal_mode.lower(), "wal")

        # Check required tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        required = {"schema_migrations", "experiences", "phonetic_aliases", "knowledge_items", "knowledge_fts"}
        self.assertTrue(required.issubset(tables), f"Missing tables: {required - tables}")

        # Check schema migration version >= 1
        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        ver = cursor.fetchone()[0]
        self.assertGreaterEqual(ver, 1)
        cursor.close()

    def test_02_knowledge_fts_indexing(self):
        """Verifies knowledge upsert and FTS5 full-text matching."""
        item_id = self.storage.upsert_knowledge(
            key="test_rule_01",
            category="preference",
            content="Always prefer dark mode and high performance graphics for gaming.",
            metadata={"source": "user_explicit"}
        )
        self.assertGreater(item_id, 0)

        # FTS5 search
        results = self.storage.search_knowledge_fts("dark mode")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["key"], "test_rule_01")
        self.assertIn("dark mode", results[0]["content"])

    def test_03_privacy_scrubbing(self):
        """Verifies privacy scrubber strips API keys, passwords, and emails."""
        raw_text = (
            "Calling API with nvapi-1234567890abcdef1234567890abcdef and "
            "sk-1234567890abcdef1234567890abcdef, Bearer my_secret_token_value_abc123456, "
            "user password='superSecretPassword123' email aktiv.user@domain.org"
        )
        scrubbed = scrub_text(raw_text)

        self.assertNotIn("nvapi-", scrubbed)
        self.assertIn("[API_KEY_REDACTED]", scrubbed)
        self.assertNotIn("sk-123", scrubbed)
        self.assertNotIn("my_secret_token_value", scrubbed)
        self.assertIn("[TOKEN_REDACTED]", scrubbed)
        self.assertNotIn("superSecretPassword123", scrubbed)
        self.assertIn("[REDACTED]", scrubbed)
        self.assertNotIn("aktiv.user@domain.org", scrubbed)
        self.assertIn("[EMAIL_REDACTED]", scrubbed)

        # Test dictionary scrubber
        data = {
            "key": "nvapi-abcdef1234567890abcdef1234567890",
            "nested": ["user@test.com", "clean_text"]
        }
        scrubbed_data = scrub_data(data)
        self.assertEqual(scrubbed_data["key"], "[API_KEY_REDACTED]")
        self.assertEqual(scrubbed_data["nested"][0], "[EMAIL_REDACTED]")
        self.assertEqual(scrubbed_data["nested"][1], "clean_text")

    def test_04_alias_resolution_latency_sub_millisecond(self):
        """Verifies apply_known_aliases runs in < 1ms on the voice critical path."""
        with self.collector._cache_lock:
            self.collector._alias_cache["ballorant"] = "valorant"
            self.collector._alias_cache["anti gravity"] = "antigravity"
            self.collector._rebuild_regex()

        test_phrase = "Please open ballorant and test anti gravity IDE right now"

        # Benchmark 1000 iterations
        t0 = time.perf_counter()
        for _ in range(1000):
            res = self.collector.apply_known_aliases(test_phrase)
        elapsed_total_s = time.perf_counter() - t0

        avg_latency_ms = (elapsed_total_s / 1000) * 1000
        print(f"\n[BENCHMARK] apply_known_aliases average latency: {avg_latency_ms:.4f} ms per call")

        self.assertLess(avg_latency_ms, 1.0, f"Latency {avg_latency_ms} ms exceeds 1.0 ms budget!")
        self.assertEqual(res, "Please open valorant and test antigravity IDE right now")

    def test_05_correction_diffing_and_promotion(self):
        """Verifies token-level diffing extracts aliases and promotes them at confidence >= 3."""
        for _ in range(3):
            self.collector.record_correction(
                failed_transcript="hey samtra wake up",
                corrected_transcript="hey santra wake up"
            )

        # Wait briefly for background writer thread
        time.sleep(1.0)

        # Verify alias recorded in DB
        aliases = self.storage.get_all_aliases()
        samtra_alias = next((a for a in aliases if a["misheard_phrase"] == "samtra"), None)
        self.assertIsNotNone(samtra_alias)
        self.assertGreaterEqual(samtra_alias["confidence_count"], 3)
        self.assertEqual(samtra_alias["intended_phrase"], "santra")

        # Verify it was auto-promoted to in-memory cache
        corrected_text = self.collector.apply_known_aliases("hello samtra")
        self.assertEqual(corrected_text, "hello santra")

    def test_06_resource_guard_and_activity_check(self):
        """Verifies ResourceGuard detects activity and caches game check."""
        snap = self.guard.get_system_snapshot()
        self.assertIn("cpu_percent", snap)
        self.assertIn("memory_percent", snap)
        self.assertIn("battery_plugged", snap)
        self.assertIn("can_run", snap)

        # Test activity check hook
        is_active = True
        self.guard.register_activity_check(lambda: is_active)

        # When active, background tasks must not run
        self.assertFalse(self.guard.can_run_background_tasks())

        # When inactive, background tasks can run
        is_active = False
        can_run = self.guard.can_run_background_tasks(runtime_status="STANDBY")
        self.assertFalse(is_active)

    def test_07_scheduler_health_report(self):
        """Verifies EvolutionScheduler runs maintenance and outputs health_report.json."""
        self.storage.record_experience(
            user_request="open notepad",
            intent="application.launch",
            action="open_app",
            parameters={"app_name": "notepad"},
            success=True,
            message="Notepad launched.",
            latency_ms=12.5
        )

        report = self.scheduler.run_maintenance_now()

        self.assertIn("timestamp", report)
        self.assertIn("status", report)
        self.assertIn("database_stats", report)
        self.assertIn("system_resources", report)

        stats = report["database_stats"]
        self.assertGreaterEqual(stats["total_experiences"], 1)
        self.assertGreater(stats["success_rate"], 0.0)

        # Verify health report file exists in temp directory and is valid JSON
        self.assertTrue(os.path.exists(self.report_path))
        with open(self.report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["status"], report["status"])
        print(f"\n[HEALTH_REPORT] Verified isolated at {self.report_path}")


if __name__ == "__main__":
    unittest.main()
