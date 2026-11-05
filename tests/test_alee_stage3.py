"""
ALEE Stage 3 Verification Suite
Tests Conversational FTS5 Recall, Actionable Weakness Detection,
Fast Deterministic Self-Benchmarks (<50ms, 100% pass), and PyQt6 Telemetry Bridge.
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
from core.evolution.collector import ExperienceCollector
from core.evolution.knowledge_explorer import KnowledgeExplorer
from core.evolution.evaluator import PerformanceEvaluator
from core.evolution.scheduler import EvolutionScheduler


class TestALEEStage3(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_stage3_evolution.db")
        cls.report_path = os.path.join(cls.temp_dir.name, "health_report.json")

        cls.storage = EvolutionStorage(db_path=cls.db_path)
        cls.collector = ExperienceCollector(storage=cls.storage)
        cls.explorer = KnowledgeExplorer(storage=cls.storage)
        cls.evaluator = PerformanceEvaluator(
            storage=cls.storage,
            explorer=cls.explorer,
            collector=cls.collector
        )

        # Ingest docs/architecture.md into isolated storage
        arch_path = os.path.join(BASE_DIR, "docs", "architecture.md")
        if os.path.exists(arch_path):
            cls.explorer.ingest_local_file(arch_path, category="architecture_docs")

    @classmethod
    def tearDownClass(cls):
        cls.collector.shutdown()
        cls.storage.close()
        cls.temp_dir.cleanup()

    def test_01_conversational_fts5_recall_and_budget(self):
        """Verifies conversational queries with stopwords match architecture.md and enforce max_chars budget."""
        queries = [
            "How does SANTRA handle background resource limits?",
            "What is the voice pipeline for speech listening?",
            "Tell me about the layers in intelligence routing"
        ]

        for q in queries:
            results = self.explorer.retrieve_relevant_knowledge(q, top_k=3, max_chars=1200)
            self.assertGreaterEqual(len(results), 1, f"Failed recall for conversational query: '{q}'")
            top_hit = results[0]
            self.assertEqual(top_hit["category"], "architecture_docs")
            self.assertIn("metadata", top_hit)

            # Verify character budget
            total_chars = sum(len(r.get("content", "")) for r in results)
            self.assertLessEqual(total_chars, 1200, f"Character budget exceeded: {total_chars} > 1200")

    def test_02_actionable_weakness_detection(self):
        """Verifies detection of failing intents, slow operations, and pending aliases."""
        now = time.time()

        # Seed 1: Failing intent (3 runs: 2 failed, 1 success -> 33% success rate)
        self.storage.record_experience(
            user_request="run cmd script",
            intent="terminal_execute",
            action="terminal_exec",
            success=False,
            message="Access denied to system file",
            latency_ms=45.0,
            timestamp=now - 100
        )
        self.storage.record_experience(
            user_request="run cmd script 2",
            intent="terminal_execute",
            action="terminal_exec",
            success=False,
            message="Access denied to system file",
            latency_ms=50.0,
            timestamp=now - 80
        )
        self.storage.record_experience(
            user_request="run cmd echo",
            intent="terminal_execute",
            action="terminal_exec",
            success=True,
            message="Echo completed",
            latency_ms=30.0,
            timestamp=now - 50
        )

        # Seed 2: Slow operation (avg latency > 1500ms)
        self.storage.record_experience(
            user_request="scrape heavy page",
            intent="web_crawl",
            action="heavy_crawl",
            success=True,
            message="Crawled successfully",
            latency_ms=2400.0,
            timestamp=now - 40
        )

        # Seed 3: Normal fast operation (should not be flagged)
        for i in range(4):
            self.storage.record_experience(
                user_request=f"launch app {i}",
                intent="application.launch",
                action="open_app",
                success=True,
                message="App launched",
                latency_ms=18.0,
                timestamp=now - 20
            )

        # Seed 4: Pending alias candidate (confidence < 3, auto_apply = 0)
        self.storage.upsert_alias("samtra_pending", "santra", delta=1, auto_apply=0)

        # Analyze weaknesses
        analysis = self.evaluator.analyze_weaknesses()

        self.assertIn("failing_intents", analysis)
        self.assertIn("slow_operations", analysis)
        self.assertIn("pending_aliases", analysis)
        self.assertIn("overall_metrics", analysis)

        # Verify failing intent identified
        failing_ops = [x["operation"] for x in analysis["failing_intents"]]
        self.assertIn("terminal_exec", failing_ops)
        fail_record = next(x for x in analysis["failing_intents"] if x["operation"] == "terminal_exec")
        self.assertEqual(fail_record["most_common_error"], "Access denied to system file")
        self.assertLess(fail_record["success_rate"], 80.0)

        # Verify slow operation identified
        slow_ops = [x["operation"] for x in analysis["slow_operations"]]
        self.assertIn("heavy_crawl", slow_ops)

        # Verify pending alias identified
        pending_names = [x["misheard_phrase"] for x in analysis["pending_aliases"]]
        self.assertIn("samtra_pending", pending_names)

        # Verify overall metrics calculated
        metrics = analysis["overall_metrics"]
        self.assertGreaterEqual(metrics["total_commands_all_time"], 8)
        self.assertGreater(metrics["latency_p95_ms"], 0.0)

    def test_03_regression_benchmarks_pass_rate_and_speed(self):
        """Verifies offline regression benchmarks execute in < 50ms with 100% score."""
        # Ensure pre-seeded aliases are loaded in memory collector
        self.collector._alias_cache["ballorant"] = "valorant"
        self.collector._alias_cache["anti gravity"] = "antigravity"
        self.collector._alias_cache["vs code"] = "vscode"
        self.collector._alias_cache["samtra"] = "santra"
        self.collector._alias_cache["nemo tron"] = "nemotron"
        self.collector._rebuild_regex()

        # Run benchmark suite
        bench = self.evaluator.run_regression_benchmarks()

        self.assertIn("passed", bench)
        self.assertIn("score", bench)
        self.assertIn("total_benchmark_time_ms", bench)
        self.assertIn("benchmarks", bench)

        print(f"\n[BENCHMARK] ALEE Regression Suite Time: {bench['total_benchmark_time_ms']:.2f} ms | Score: {bench['score']}%")

        self.assertTrue(bench["passed"], f"Benchmarks failed: {bench}")
        self.assertEqual(bench["score"], 100.0)
        self.assertLess(bench["total_benchmark_time_ms"], 50.0, "Benchmark exceeded 50ms budget!")

        sub_benchmarks = bench["benchmarks"]
        self.assertTrue(sub_benchmarks["alias_resolution"]["passed"])
        self.assertLess(sub_benchmarks["alias_resolution"]["latency_ms"], 1.0)
        self.assertTrue(sub_benchmarks["bm25_retrieval"]["passed"])
        self.assertLess(sub_benchmarks["bm25_retrieval"]["latency_ms"], 5.0)
        self.assertTrue(sub_benchmarks["safety_defense"]["passed"])

    def test_04_ui_evolution_telemetry_signal(self):
        """Verifies MainWindow receives sig_evolution_updated and updates telemetry badges."""
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        # Reuse or create QApplication instance
        app = QApplication.instance() or QApplication(sys.argv)

        window = MainWindow()
        self.assertTrue(hasattr(window, "sig_evolution_updated"))
        self.assertTrue(hasattr(window, "lbl_evo_aliases"))
        self.assertTrue(hasattr(window, "lbl_evo_score"))

        test_payload = {
            "active_aliases_count": 14,
            "database_stats": {"total_knowledge_items": 3},
            "benchmarks": {"score": 100.0},
            "system_resources": {"can_run": True, "game_detected": None}
        }

        # Emit signal to test slot
        window.sig_evolution_updated.emit(test_payload)

        self.assertEqual(window.lbl_evo_aliases.text(), "Aliases: 14")
        self.assertEqual(window.lbl_evo_knowledge.text(), "Docs: 3")
        self.assertEqual(window.lbl_evo_score.text(), "Score: 100% PASS")
        self.assertEqual(window.lbl_evo_guard.text(), "LEARNING IDLE")


if __name__ == "__main__":
    unittest.main()

