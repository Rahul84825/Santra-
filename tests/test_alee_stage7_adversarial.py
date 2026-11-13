"""
SANTRA ALEE Stage 7 - Adversarial Security, Lifecycle & Controlled Autonomy Suite
Verifies:
1. Malicious skill payload rejection (path traversal, attempted shell injection, unauthorized tools).
2. Skills cannot elevate their own state to VERIFIED (must stop at DRY_RUN_PASSED unless confirmed by user).
3. Alias collision defense ('visual studio code' remains intact and does not mangle into 'vscode code').
4. Startup maintenance deferral under simulated high RAM/CPU conditions.
Strictly isolated using tempfile.TemporaryDirectory().
"""

import os
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.evolution.storage import EvolutionStorage
from core.evolution.collector import ExperienceCollector
from core.evolution.skill_developer import SkillDeveloper
from core.evolution.evolution_manager import EvolutionManager
from core.evolution.scheduler import EvolutionScheduler
from core.evolution.resource_guard import ResourceGuard


class TestAleeStage7Adversarial(unittest.TestCase):
    """Adversarial security, skill lifecycle boundaries, and collision hardening tests."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "adv_evolution.db")
        self.report_path = os.path.join(self.tmpdir.name, "health_report.json")
        self.storage = EvolutionStorage(db_path=self.db_path)
        self.collector = ExperienceCollector(storage=self.storage)
        self.skill_dev = SkillDeveloper(storage=self.storage, collector=self.collector)

    def tearDown(self):
        self.collector.shutdown()
        self.storage.close()
        self.tmpdir.cleanup()

    # ==========================================
    # 1. MALICIOUS SKILL PAYLOAD REJECTION
    # ==========================================
    def test_01_malicious_tool_and_shell_rejection(self):
        """Rejects unauthorized tools, shell execution attempts, and prohibited commands."""
        # A. Prohibited tool: system_command
        spec_sys_cmd = {
            "name": "Malicious System Command",
            "trigger_phrases": ["run system command"],
            "steps": [{"tool": "system_command", "args": {"command": "dir"}}]
        }
        valid, reason = self.skill_dev.validate_skill_spec(spec_sys_cmd)
        self.assertFalse(valid)
        self.assertIn("not in allowed tools", reason)

        # B. Prohibited tool: autonomous proposal approve
        spec_approve = {
            "name": "Auto Approve Everything",
            "trigger_phrases": ["auto approve proposals"],
            "steps": [{"tool": "evolution_proposals_approve", "args": {}}]
        }
        valid, reason = self.skill_dev.validate_skill_spec(spec_approve)
        self.assertFalse(valid)
        self.assertIn("not in allowed tools", reason)

        # C. Shell metacharacters in open_application
        spec_shell_injection = {
            "name": "Shell Injection Attempt",
            "trigger_phrases": ["inject shell"],
            "steps": [{"tool": "open_application", "args": {"app_name": "notepad & whoami"}}]
        }
        valid, reason = self.skill_dev.validate_skill_spec(spec_shell_injection)
        self.assertFalse(valid)
        self.assertIn("prohibited characters", reason)

        # D. Dangerous executable script extension
        spec_script = {
            "name": "Script Execution Attempt",
            "trigger_phrases": ["run script"],
            "steps": [{"tool": "open_application", "args": {"app_name": "payload.bat"}}]
        }
        valid, reason = self.skill_dev.validate_skill_spec(spec_script)
        self.assertFalse(valid)
        self.assertIn("Prohibited executable/script target extension", reason)

        # E. Path traversal attack
        spec_traversal = {
            "name": "Path Traversal",
            "trigger_phrases": ["traverse path"],
            "steps": [{"tool": "open_application", "args": {"app_name": "../../Windows/System32/cmd"}}]
        }
        valid, reason = self.skill_dev.validate_skill_spec(spec_traversal)
        self.assertFalse(valid)
        self.assertIn("Directory traversal pattern", reason)

        # F. Invalid URL scheme (javascript/data URI)
        spec_js_url = {
            "name": "XSS Script URL",
            "trigger_phrases": ["open bad url"],
            "steps": [{"tool": "open_url", "args": {"url": "javascript:alert(1)"}}]
        }
        valid, reason = self.skill_dev.validate_skill_spec(spec_js_url)
        self.assertFalse(valid)
        self.assertIn("requires http:// or https:// scheme", reason)

    # ==========================================
    # 2. HONEST SKILL LIFECYCLE & EXECUTION BOUNDARIES
    # ==========================================
    def test_02_skill_cannot_self_promote_to_verified(self):
        """A sandbox skill undergoing dry run can only reach DRY_RUN_PASSED, not VERIFIED."""
        skill_spec = {
            "skill_id": "candidate_open_docs",
            "name": "Open Documentation",
            "trigger_phrases": ["open documentation portal"],
            "description": "Safe utility skill to launch docs.",
            "steps": [
                {"tool": "open_url", "args": {"url": "https://example.com/docs"}},
                {"tool": "speak", "args": {"text": "Documentation portal opened."}}
            ],
            "version": 1,
            "status": "SANDBOX",
            "created_at": 1700000000.0,
            "updated_at": 1700000000.0
        }
        self.storage.upsert_skill(skill_spec)

        # Execute sandbox dry run
        dry_run_ok = self.skill_dev.test_skill_in_sandbox("candidate_open_docs")
        self.assertTrue(dry_run_ok)

        # Inspect status: must be DRY_RUN_PASSED, NEVER VERIFIED!
        saved_skill = self.storage.get_skill("candidate_open_docs")
        self.assertEqual(saved_skill["status"], "DRY_RUN_PASSED")

        # In-memory trigger cache must NOT execute DRY_RUN_PASSED skills
        matched = self.skill_dev.match_trigger("open documentation portal")
        self.assertIsNone(matched, "DRY_RUN_PASSED skills must not be executable via fast trigger cache.")

        # Attempt promote without human confirmation: must fail
        ok, msg = self.skill_dev.promote_skill_to_verified("candidate_open_docs", confirmed_by_user=False)
        self.assertFalse(ok)
        self.assertIn("explicit user confirmation", msg)

        # Promote with human confirmation: succeeds
        ok, msg = self.skill_dev.promote_skill_to_verified("candidate_open_docs", confirmed_by_user=True)
        self.assertTrue(ok)
        promoted = self.storage.get_skill("candidate_open_docs")
        self.assertEqual(promoted["status"], "VERIFIED")

        # Now it is executable via fast trigger cache
        matched_after = self.skill_dev.match_trigger("open documentation portal")
        self.assertIsNotNone(matched_after)
        self.assertEqual(matched_after["skill_id"], "candidate_open_docs")

    # ==========================================
    # 3. SEMANTIC COLLISION & ALIAS SAFETY
    # ==========================================
    def test_03_alias_collision_defense_visual_studio_code(self):
        """Ensures 'visual studio code' remains intact and does NOT mangle into 'vscode code'."""
        # Case A: Alias cache contains ONLY ('visual studio' -> 'vscode')
        # Without protection, 'open visual studio code' would become 'open vscode code'
        collector = ExperienceCollector(storage=self.storage)
        with collector._cache_lock:
            collector._alias_cache = {
                "visual studio": "vscode",
                "ballorant": "valorant"
            }
            collector._rebuild_regex()

        # Query referring to Visual Studio Code
        result = collector.apply_known_aliases("open visual studio code")
        # Must NOT mangle into 'open vscode code'
        self.assertNotIn("vscode code", result.lower())
        self.assertTrue(
            result.lower() in ("open visual studio code", "open vscode"),
            f"Expected 'open visual studio code' or 'open vscode', got '{result}'"
        )

        # Standalone 'visual studio' should still map to 'vscode'
        result_standalone = collector.apply_known_aliases("open visual studio")
        self.assertEqual(result_standalone.lower(), "open vscode")

        # Case B: Alias cache contains BOTH ('visual studio code' -> 'vscode') and ('visual studio' -> 'vscode')
        with collector._cache_lock:
            collector._alias_cache = {
                "visual studio code": "vscode",
                "visual studio": "vscode"
            }
            collector._rebuild_regex()

        result_compound = collector.apply_known_aliases("please open visual studio code now")
        self.assertEqual(result_compound.lower(), "please open vscode now")
        self.assertNotIn("vscode code", result_compound.lower())

        collector.shutdown()

    # ==========================================
    # 4. STARTUP RESOURCE GUARD MAINTENANCE DEFERRAL
    # ==========================================
    def test_04_startup_maintenance_deferral_under_high_load(self):
        """Under high CPU or RAM load, scheduler gracefully defers heavy tasks without throwing."""
        guard = ResourceGuard()
        # Mock high CPU (65% > 30% max threshold)
        with patch.object(guard, "get_system_snapshot") as mock_snap:
            mock_snap.return_value = {
                "can_run": False,
                "cpu_percent": 65.0,
                "memory_percent": 75.0,
                "battery_plugged": True,
                "battery_percent": 80,
                "game_detected": None,
                "voice_active": False,
                "reasons": ["CPU high (65.0% > 30.0%)"]
            }

            scheduler = EvolutionScheduler(
                storage=self.storage,
                guard=guard,
                collector=self.collector,
                report_path=self.report_path
            )

            # run_maintenance_now without force
            report = scheduler.run_maintenance_now(force=False)

            # Status should reflect PAUSED_HIGH_LOAD
            self.assertEqual(report["status"], "PAUSED_HIGH_LOAD")
            # Heavy workloads (benchmarks, proposals_summary) should be empty/deferred
            self.assertEqual(report["benchmarks"], {})
            self.assertEqual(report["proposals_summary"], {})

            # Health report file was written cleanly
            self.assertTrue(os.path.exists(self.report_path))

    # ==========================================
    # 5. CONTROLLED AUTONOMY APPROVAL GATES
    # ==========================================
    def test_05_medium_high_risk_proposals_require_user_confirmation(self):
        """Proposals in INTENT_RULE, SKILL_PROMOTION, and RUNTIME_CONFIG reject automated approval."""
        evo_mgr = EvolutionManager(storage=self.storage, collector=self.collector)

        # Create an INTENT_RULE proposal (HIGH risk)
        prop_id = self.storage.upsert_proposal({
            "proposal_id": "prop_test_high_risk",
            "proposal_type": "INTENT_RULE",
            "target_key": "custom_intent",
            "proposed_value": {"strategy": "retry_3x"},
            "reason": "Test high risk rule",
            "evidence_count": 5,
            "status": "PENDING"
        })

        # Attempt approval without user confirmation: must be rejected
        ok, msg = evo_mgr.approve_proposal(prop_id, confirmed_by_user=False)
        self.assertFalse(ok)
        self.assertIn("Explicit user confirmation is required", msg)

        # Batch approval without confirmation: skips high risk proposal
        batch_res = evo_mgr.approve_all_pending(confirmed_by_user=False)
        self.assertEqual(batch_res["approved_count"], 0)
        self.assertEqual(batch_res["failed_count"], 1)

        # Proposal with confirmed_by_user=True: approved successfully
        ok, msg = evo_mgr.approve_proposal(prop_id, confirmed_by_user=True)
        self.assertTrue(ok)
        self.assertIn("Approved and verified", msg)


if __name__ == "__main__":
    unittest.main()

