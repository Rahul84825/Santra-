"""SANTRA Iteration 11 - Live Chrome ChatGPT Conversation Switch & Submission Verification.
Tests conversation identity binding across tabs, windows, profiles, and URL switches within the SAME HWND.
Verifies multi-stage submission status and honest epistemic reporting when CDP is unattached.
"""

import unittest
import time
from unittest.mock import patch

from core.workspace_interaction.interaction_models import (
    ChatGPTConversationIdentity,
    SubmissionVerificationStatus
)
from core.workspace_interaction.browser_interaction_manager import (
    BrowserInteractionManager
)
from core.workspace_interaction.draft_manager import DraftManager, DraftState
from core.workspace_interaction.application_manager import application_manager


class TestLiveChromeChatGPTConversationSwitch(unittest.TestCase):
    """Phase 2 & Phase 3 Verification Suite."""

    def setUp(self):
        self.browser_mgr = BrowserInteractionManager()
        self.draft_mgr = DraftManager(browser_mgr=self.browser_mgr)

    def test_live_chrome_detection_on_host(self):
        """Validates that real running Chrome on the host is detected with HWND and PID."""
        chrome_windows = application_manager.get_application_windows("chrome")
        self.assertIsInstance(chrome_windows, list)
        if chrome_windows:
            win = chrome_windows[0]
            self.assertIn("hwnd", win)
            self.assertIn("pid", win)
            self.assertIn("title", win)
            self.assertGreater(win["hwnd"], 0)
            self.assertGreater(win["pid"], 0)
            safe_title = win["title"].encode("ascii", "replace").decode("ascii")
            print(f"\n[HOST CHROME DETECTED] HWND: {win['hwnd']}, PID: {win['pid']}, Title: '{safe_title}'")

    def test_conversation_identity_switch_in_same_window_blocked(self):
        """Scenario: User has draft bound to Conv A. Conversation is switched in SAME window (same HWND).

        Approval MUST be blocked with CONVERSATION_IDENTITY_CHANGED.
        """
        initial_conv_uuid = "3a9f01e2-bca4-4f40-8b17-104958102394"
        switched_conv_uuid = "7f8a9b0c-1122-3344-5566-778899aabbcc"

        # Capture original identity
        orig_identity = ChatGPTConversationIdentity(
            process_id=12312,
            profile_name="Default",
            tab_id="tab-1",
            url=f"https://chatgpt.com/c/{initial_conv_uuid}",
            conversation_id=initial_conv_uuid,
            title="SANTRA Architecture - ChatGPT",
            composer_selector="#prompt-textarea"
        )

        draft = self.draft_mgr.create_draft(
            app_name="chatgpt",
            draft_text="Explain multi-agent verification protocols",
            target_hwnd=132300,
            conversation_identity=orig_identity
        )
        self.assertIsNotNone(draft)
        self.assertEqual(draft.state, DraftState.AWAITING_APPROVAL)

        # Simulate user switching conversation within the exact same window (same HWND 132300, same PID 12312)
        switched_identity = ChatGPTConversationIdentity(
            process_id=12312,
            profile_name="Default",
            tab_id="tab-1",
            url=f"https://chatgpt.com/c/{switched_conv_uuid}",
            conversation_id=switched_conv_uuid,
            title="Random Cooking Recipes - ChatGPT",
            composer_selector="#prompt-textarea"
        )

        # Active browser now reports switched identity
        self.browser_mgr.active_conversation_identity = switched_identity

        # User attempts to approve previous draft
        res = self.draft_mgr.process_approval("Yes, send it", draft_id=draft.draft_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "CONVERSATION_IDENTITY_CHANGED")
        self.assertIn("CONVERSATION_IDENTITY_CHANGED", res["message"])
        self.assertIn("ChatGPT conversation mismatch", res["reason"])

        # Draft must not be approved
        self.assertNotEqual(draft.state, DraftState.APPROVED)
        self.assertEqual(draft.state, DraftState.FAILED)

    def test_return_to_original_conversation_and_reapproval(self):
        """Scenario: After switch is blocked, user returns to original conversation.

        Identity matches, but prior approval was not granted, requiring fresh explicit approval.
        """
        conv_uuid = "3a9f01e2-bca4-4f40-8b17-104958102394"
        orig_identity = ChatGPTConversationIdentity(
            process_id=12312,
            profile_name="Default",
            tab_id="tab-1",
            url=f"https://chatgpt.com/c/{conv_uuid}",
            conversation_id=conv_uuid,
            title="SANTRA Architecture - ChatGPT",
            composer_selector="#prompt-textarea"
        )

        draft = self.draft_mgr.create_draft(
            app_name="chatgpt",
            draft_text="Deploy verification harness",
            target_hwnd=132300,
            conversation_identity=orig_identity
        )

        # 1. Switch away
        self.browser_mgr.active_conversation_identity = ChatGPTConversationIdentity(
            process_id=12312,
            url="https://chatgpt.com/c/other-uuid",
            conversation_id="other-uuid"
        )
        res1 = self.draft_mgr.process_approval("Yes, send it", draft_id=draft.draft_id)
        self.assertFalse(res1["success"])

        # 2. Return to original conversation - recreate fresh draft with explicit approval requirement
        self.browser_mgr.active_conversation_identity = orig_identity

        # 3. Verify identity re-validation passes
        ok, reason = self.browser_mgr.verify_conversation_identity(orig_identity)
        self.assertTrue(ok)
        self.assertEqual(reason, "Identity verified")

        fresh_draft = self.draft_mgr.create_draft(
            app_name="chatgpt",
            draft_text="Deploy verification harness",
            target_hwnd=132300,
            conversation_identity=orig_identity
        )

        # 4. Fresh explicit verbal approval allows submission
        with patch.object(self.browser_mgr, "verify_chatgpt_submission") as mock_verify:
            mock_verify.return_value = {
                "confirmed": True,
                "status": "VERIFIED",
                "stage": SubmissionVerificationStatus.PROMPT_ACCEPTED,
                "evidence": "user_turn_confirmed_in_chat_stream",
                "message": "Message confirmed in ChatGPT conversation."
            }
            res2 = self.draft_mgr.process_approval("Yes, send it", draft_id=fresh_draft.draft_id)
            self.assertTrue(res2["success"])
            self.assertIn(fresh_draft.state, [DraftState.SUBMITTED, DraftState.VERIFIED])

    def test_cdp_unattached_honest_epistemic_reporting(self):
        """When CDP is unattached, submission verification must report SUBMISSION_UNCONFIRMED, never falsely claiming VERIFIED."""
        # CDP is not connected on physical host
        self.assertFalse(self.browser_mgr.cdp.is_available())

        res = self.browser_mgr.verify_chatgpt_submission("Test prompt without CDP", timeout_seconds=0.1)
        self.assertFalse(res["confirmed"])
        self.assertEqual(res["status"], "SUBMISSION_UNCONFIRMED")
        self.assertEqual(res["stage"], SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED)
        self.assertIn("could not be independently confirmed", res["message"])

    def test_multi_stage_status_transitions(self):
        """Validates the explicit stages of submission lifecycle."""
        stages = [
            SubmissionVerificationStatus.IDLE,
            SubmissionVerificationStatus.KEYSTROKE_SENT,
            SubmissionVerificationStatus.PROMPT_ACCEPTED,
            SubmissionVerificationStatus.AGENT_PROCESSING,
            SubmissionVerificationStatus.RESPONSE_STARTED,
            SubmissionVerificationStatus.RESPONSE_COMPLETED,
            SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED,
            SubmissionVerificationStatus.VERIFICATION_FAILED
        ]
        self.assertEqual(len(stages), 8)
        self.assertEqual(stages[1].value, "KEYSTROKE_SENT")
        self.assertEqual(stages[2].value, "PROMPT_ACCEPTED")
        self.assertEqual(stages[6].value, "SUBMISSION_UNCONFIRMED")


if __name__ == "__main__":
    unittest.main()
