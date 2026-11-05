"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Stage 5 Verification Suite: Controlled Evolution Pipeline, Approval Manager & Versioned Rollbacks
"""

import os
import sys
import time
import json
import sqlite3
import tempfile
import unittest

from core.evolution.storage import EvolutionStorage
from core.evolution.collector import ExperienceCollector
from core.evolution.evaluator import PerformanceEvaluator
from core.evolution.skill_developer import SkillDeveloper
from core.evolution.evolution_manager import EvolutionManager
from core.evolution.scheduler import EvolutionScheduler


class TestALEEStage5(unittest.TestCase):
    """Rigorous Stage 5 verification under hardware, zero-VRAM, and isolation constraints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.temp_dir.name, "test_evolution_s5.db")
        self.storage = EvolutionStorage(db_path=self.test_db_path)
        self.collector = ExperienceCollector(storage=self.storage)
        self.evaluator = PerformanceEvaluator(storage=self.storage, collector=self.collector)
        self.skill_dev = SkillDeveloper(storage=self.storage, collector=self.collector)
        self.evo_mgr = EvolutionManager(
            storage=self.storage,
            evaluator=self.evaluator,
            skill_dev=self.skill_dev,
            collector=self.collector
        )

    def tearDown(self):
        self.collector.shutdown()
        self.storage.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ==========================================
    # TEST 1: AUTOMATED PROPOSAL GENERATION
    # ==========================================
    def test_01_proposal_generation(self):
        """Verifies proposals drafted from failing intents, unpromoted aliases, and sandbox skills."""
        # 1. Insert failing experiences for an intent
        now = time.time()
        for i in range(5):
            self.storage.record_experience(
                user_request=f"launch tool {i}",
                intent="LAUNCH_TOOL",
                action="launch_tool",
                success=False,
                error_type="MissingExecutable",
                timestamp=now - (i * 10)
            )

        # 2. Insert unpromoted alias with confidence >= 2
        with self.storage._lock:
            conn = self.storage._get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO phonetic_aliases (misheard_phrase, intended_phrase, confidence_count, auto_apply, last_seen)
                VALUES ('doc ker', 'docker', 3, 0, ?)
            """, (now,))
            conn.commit()
            cur.close()

        # 3. Insert candidate skill in SANDBOX status
        safe_skill = {
            "skill_id": "skill_safe_calc",
            "name": "open calculator",
            "trigger_phrases": ["open calculator", "launch calc"],
            "description": "Safe utility launching calc",
            "steps": [{"tool": "open_application", "args": {"app_name": "calc"}}],
            "status": "SANDBOX"
        }
        self.storage.upsert_skill(safe_skill)

        # Generate proposals
        proposals = self.evo_mgr.generate_proposals()
        self.assertGreaterEqual(len(proposals), 3)

        types = {p["proposal_type"] for p in proposals}
        self.assertIn("INTENT_RULE", types)
        self.assertIn("ALIAS_PROMOTION", types)
        self.assertIn("SKILL_PROMOTION", types)

        for p in proposals:
            self.assertEqual(p["status"], "PENDING")
            self.assertIsNotNone(p["reason"])
            self.assertGreater(p["evidence_count"], 0)

        # Idempotency check: running again produces identical count without duplicates
        proposals_again = self.evo_mgr.generate_proposals()
        self.assertEqual(len(proposals), len(proposals_again))

    # ==========================================
    # TEST 2: L3 APPROVAL GATE & SNAPSHOT RECORDING
    # ==========================================
    def test_02_approval_gate_and_snapshot(self):
        """Verifies Level 3 approval records audit snapshot and applies state with benchmark verification."""
        # Create unpromoted alias proposal
        now = time.time()
        with self.storage._lock:
            conn = self.storage._get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO phonetic_aliases (misheard_phrase, intended_phrase, confidence_count, auto_apply, last_seen)
                VALUES ('pi thon', 'python', 4, 0, ?)
            """, (now,))
            conn.commit()
            cur.close()

        prop_id = self.storage.upsert_proposal({
            "proposal_id": "prop_alias_pi_thon",
            "proposal_type": "ALIAS_PROMOTION",
            "target_key": "pi thon",
            "proposed_value": {"auto_apply": 1},
            "reason": "Verified alias",
            "evidence_count": 4,
            "status": "PENDING"
        })

        # Approve proposal
        approved, msg = self.evo_mgr.approve_proposal(prop_id)
        self.assertTrue(approved, f"Approval failed: {msg}")

        # Check proposal status updated
        prop = self.storage.get_proposal(prop_id)
        self.assertEqual(prop["status"], "APPROVED")
        self.assertIsNotNone(prop["reviewed_at"])

        # Check snapshot recorded
        snap = self.storage.get_snapshot_for_proposal(prop_id)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["proposal_id"], prop_id)
        self.assertEqual(snap["previous_state"].get("auto_apply"), 0)
        self.assertEqual(snap["new_state"].get("auto_apply"), 1)
        self.assertGreaterEqual(snap["benchmark_score_before"], 90.0)
        self.assertGreaterEqual(snap["benchmark_score_after"], 90.0)

        # Check target state applied
        with self.storage._lock:
            conn = self.storage._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT auto_apply FROM phonetic_aliases WHERE misheard_phrase = 'pi thon'")
            auto_val = cur.fetchone()[0]
            cur.close()
        self.assertEqual(auto_val, 1)

    # ==========================================
    # TEST 3: AUTO-ROLLBACK GUARD ON REGRESSION
    # ==========================================
    def test_03_auto_rollback_on_regression(self):
        """Ensures that changes degrading benchmark performance trigger instant automatic rollback."""
        # Create a candidate skill proposal
        skill = {
            "skill_id": "skill_revert_test",
            "name": "revert test skill",
            "trigger_phrases": ["test revert"],
            "steps": [{"tool": "open_application", "args": {"app_name": "notepad"}}],
            "status": "SANDBOX"
        }
        self.storage.upsert_skill(skill)

        prop_id = self.storage.upsert_proposal({
            "proposal_id": "prop_skill_revert_test",
            "proposal_type": "SKILL_PROMOTION",
            "target_key": "skill_revert_test",
            "proposed_value": {"target_status": "VERIFIED"},
            "reason": "Test regression guard",
            "evidence_count": 1,
            "status": "PENDING"
        })

        # Attempt approval with simulated post-change regression score (e.g. 50% vs 100%)
        approved, msg = self.evo_mgr.approve_proposal(prop_id, simulated_regression_score=50.0)
        self.assertFalse(approved)
        self.assertIn("Regression detected", msg)

        # Verify proposal marked FAILED
        prop = self.storage.get_proposal(prop_id)
        self.assertEqual(prop["status"], "FAILED")

        # Verify skill was automatically reverted to SANDBOX
        sk_after = self.storage.get_skill("skill_revert_test")
        self.assertEqual(sk_after["status"], "SANDBOX")

        # Verify no approved snapshot was created
        snap = self.storage.get_snapshot_for_proposal(prop_id)
        self.assertIsNone(snap)

    # ==========================================
    # TEST 4: MANUAL VERSIONED ROLLBACK
    # ==========================================
    def test_04_manual_rollback(self):
        """Verifies manual rollback restores prior state and updates snapshot audit status."""
        # 1. Setup and approve a skill proposal
        skill = {
            "skill_id": "skill_rollback_demo",
            "name": "rollback demo skill",
            "trigger_phrases": ["demo rollback trigger"],
            "steps": [{"tool": "open_application", "args": {"app_name": "calc"}}],
            "status": "SANDBOX"
        }
        self.storage.upsert_skill(skill)

        prop_id = self.storage.upsert_proposal({
            "proposal_id": "prop_skill_rollback_demo",
            "proposal_type": "SKILL_PROMOTION",
            "target_key": "skill_rollback_demo",
            "proposed_value": {"target_status": "VERIFIED"},
            "reason": "Test manual rollback",
            "evidence_count": 1,
            "status": "PENDING"
        })

        ok, msg = self.evo_mgr.approve_proposal(prop_id)
        self.assertTrue(ok)
        self.assertEqual(self.storage.get_skill("skill_rollback_demo")["status"], "VERIFIED")

        # 2. Execute rollback
        rb_ok, rb_msg = self.evo_mgr.rollback_proposal(prop_id)
        self.assertTrue(rb_ok)
        self.assertIn("rolled back successfully", rb_msg)

        # 3. Verify state restored to SANDBOX
        self.assertEqual(self.storage.get_skill("skill_rollback_demo")["status"], "SANDBOX")

        # 4. Verify proposal status updated
        prop = self.storage.get_proposal(prop_id)
        self.assertEqual(prop["status"], "ROLLED_BACK")

        # 5. Verify snapshot marked with rolled_back_at
        snap = self.storage.get_snapshot_for_proposal(prop_id)
        self.assertIsNotNone(snap["rolled_back_at"])

    # ==========================================
    # TEST 5: VOICE DIAGNOSTIC SKILLS & FAST MATCHING (< 1ms)
    # ==========================================
    def test_05_voice_proposals_skills(self):
        """Verifies voice proposal inspection and approval triggers execute under 1.0 ms."""
        triggers = [
            ("what are your evolution proposals", "list evolution proposals"),
            ("list evolution proposals", "list evolution proposals"),
            ("show failing intents", "list evolution proposals"),
            ("pending improvements", "list evolution proposals"),
            ("approve evolution proposals", "approve evolution proposals"),
            ("approve pending proposals", "approve evolution proposals")
        ]

        for query, expected_name in triggers:
            t0 = time.perf_counter()
            match = self.skill_dev.match_trigger(query)
            dt_ms = (time.perf_counter() - t0) * 1000

            self.assertIsNotNone(match, f"Failed matching '{query}'")
            self.assertEqual(match["name"], expected_name)
            self.assertLess(dt_ms, 1.0, f"Trigger matching latency {dt_ms:.4f}ms exceeded 1.0ms")

        # Execute list proposals skill
        m_list = self.skill_dev.match_trigger("what are your evolution proposals")
        res_list = self.skill_dev.execute_skill(m_list, speak=False)
        self.assertTrue(res_list["success"])
        self.assertIn("ALEE has", res_list["message"])
        self.assertIn("pending evolution proposals", res_list["message"])

        # Execute approve proposals skill
        m_app = self.skill_dev.match_trigger("approve pending proposals")
        res_app = self.skill_dev.execute_skill(m_app, speak=False)
        self.assertTrue(res_app["success"])
        self.assertIn("Processed pending evolution proposals", res_app["message"])

    # ==========================================
    # TEST 6: SCHEDULER & PYQT6 HUD PROPOSAL TELEMETRY
    # ==========================================
    def test_06_scheduler_and_hud_telemetry(self):
        """Verifies EvolutionScheduler writes proposal telemetry and MainWindow updates badge."""
        report_file = os.path.join(self.temp_dir.name, "health_report_s5.json")
        scheduler = EvolutionScheduler(
            storage=self.storage,
            collector=self.collector,
            report_path=report_file
        )

        report = scheduler.run_maintenance_now()
        self.assertIn("pending_proposals_count", report)
        self.assertIn("approved_improvements_count", report)
        self.assertIn("proposals_summary", report)
        self.assertTrue(os.path.exists(report_file))

        # Test UI telemetry slot
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()

        self.assertTrue(hasattr(window, "lbl_evo_proposals"))
        window.sig_evolution_updated.emit(report)
        self.assertIn("Proposals:", window.lbl_evo_proposals.text())


if __name__ == "__main__":
    unittest.main()

