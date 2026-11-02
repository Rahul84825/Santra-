"""SANTRA Iteration 11 - Real Antigravity Prompt Acceptance Suite.
Tests live Antigravity IDE state, decoupling keystroke dispatch from prompt acceptance,
background window handling, modal dialog interference, long prompts, and duplicate approval guards.
"""

import unittest
import time
from unittest.mock import patch, MagicMock

from core.workspace_interaction.interaction_models import (
    WorkspaceIdentity,
    SubmissionVerificationStatus
)
from core.workspace_interaction.application_interaction_manager import (
    ApplicationInteractionManager
)
from core.workspace_interaction.draft_manager import DraftManager, DraftState
from core.workspace_interaction.application_manager import application_manager


class TestRealAntigravityPromptAcceptance(unittest.TestCase):
    """Phase 4 Verification Suite for Antigravity IDE interaction."""

    def setUp(self):
        self.app_interaction = ApplicationInteractionManager()
        self.draft_mgr = DraftManager(interaction_mgr=self.app_interaction)

    def test_live_antigravity_detection_on_host(self):
        """Validates that real running Antigravity IDE on host is detected with HWND and PID."""
        ag_windows = application_manager.get_application_windows("antigravity")
        self.assertIsInstance(ag_windows, list)
        if ag_windows:
            win = ag_windows[0]
            self.assertIn("hwnd", win)
            self.assertIn("pid", win)
            self.assertIn("title", win)
            self.assertGreater(win["hwnd"], 0)
            self.assertGreater(win["pid"], 0)
            print(f"\n[HOST ANTIGRAVITY DETECTED] HWND: {win['hwnd']}, PID: {win['pid']}, Title: '{win['title']}'")

    def test_background_window_focus_shift_prevents_keystroke_leak(self):
        """When Antigravity is in the background and foreground shifts to another window,

        approval must be blocked with FOCUS_CHANGED_BEFORE_SEND.
        """
        target_hwnd = 67074  # Live Antigravity HWND
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Fix race condition in background tasks",
            target_hwnd=target_hwnd
        )

        # Simulate foreground window being different (e.g. Chrome or Terminal)
        different_hwnd = 132300
        with patch.object(self.app_interaction, "verify_workspace_identity", return_value=(True, "Verified")):
            res = self.draft_mgr.process_approval(
                "Yes, send it",
                draft_id=draft.draft_id,
                current_hwnd=different_hwnd
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FOCUS_CHANGED_BEFORE_SEND")
            self.assertIn("Focus shifted away", res["message"])
            self.assertNotEqual(draft.state, DraftState.APPROVED)

    def test_disabled_composer_detects_verification_failure(self):
        """When Antigravity composer is disabled/busy and prompt text is NOT consumed,

        verify_antigravity_submission must return VERIFICATION_FAILED.
        """
        prompt = "Run comprehensive unit test suite"
        # Mock read_current_composer_text returning the unchanged prompt after timeout
        with patch.object(self.app_interaction, "read_current_composer_text", return_value=prompt):
            res = self.app_interaction.verify_antigravity_submission(
                expected_text=prompt,
                target_hwnd=67074,
                timeout_seconds=0.2
            )
            self.assertFalse(res["confirmed"])
            self.assertEqual(res["status"], "VERIFICATION_FAILED")
            self.assertEqual(res["stage"], SubmissionVerificationStatus.VERIFICATION_FAILED)
            self.assertEqual(res["evidence"], "composer_still_contains_prompt_after_timeout")

    def test_keystroke_decoupling_from_prompt_acceptance(self):
        """Verifies that keystroke delivery does not prematurely claim prompt acceptance."""
        prompt = "Refactor interaction manager"
        # When composer clears, prompt is accepted
        with patch.object(self.app_interaction, "read_current_composer_text", side_effect=["", ""]):
            res = self.app_interaction.verify_antigravity_submission(
                expected_text=prompt,
                target_hwnd=67074,
                timeout_seconds=0.5
            )
            self.assertTrue(res["confirmed"])
            self.assertEqual(res["status"], "VERIFIED")
            self.assertEqual(res["stage"], SubmissionVerificationStatus.PROMPT_ACCEPTED)
            self.assertEqual(res["evidence"], "composer_cleared_after_enter_keystroke")

    def test_duplicate_approval_idempotency_guard(self):
        """Approving an already submitted or verified draft must be rejected immediately."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Review security posture",
            target_hwnd=67074
        )
        # Manually mark as submitted
        draft.state = DraftState.SUBMITTED
        draft.submitted = True

        res = self.draft_mgr.process_approval("Yes, send it", draft_id=draft.draft_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "ALREADY_SUBMITTED")
        self.assertIn("already been submitted", res["message"])

    def test_long_prompt_cryptographic_integrity(self):
        """Drafts with large technical content (>4000 characters) maintain exact SHA-256 integrity."""
        large_code_prompt = """
        def generate_report():
            data = {"metric": 42, "status": "nominal"}
            for i in range(500):
                data[f"key_{i}"] = i * 2.5
            return data
        """ * 25  # ~5000 characters

        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text=large_code_prompt,
            target_hwnd=67074
        )
        self.assertEqual(draft.state, DraftState.AWAITING_APPROVAL)
        self.assertEqual(len(draft.draft_text), len(large_code_prompt.strip()))
        self.assertTrue(draft.verify_hash(large_code_prompt.strip()))

        # Modify single character at end -> hash mismatch triggers invalidation
        tampered = large_code_prompt.strip() + " # unauthorized comment"
        self.assertFalse(draft.verify_hash(tampered))


if __name__ == "__main__":
    unittest.main()
