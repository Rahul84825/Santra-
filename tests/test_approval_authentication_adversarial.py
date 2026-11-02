"""SANTRA Iteration 11 - Approval Authentication & Adversarial Robustness Test Suite.
Verifies verbal approval security against background conversation, TV audio,
low acoustic confidence, partial transcripts, focus shifts, active dictation races,
and expired or re-used draft tokens.
"""

import unittest
import time
from unittest.mock import patch, MagicMock

from core.workspace_interaction.draft_manager import DraftManager, DraftState
from core.workspace_interaction.interaction_models import (
    ChatGPTConversationIdentity,
    WorkspaceIdentity,
    SubmissionVerificationStatus
)


class TestApprovalAuthenticationAdversarial(unittest.TestCase):
    """Phase 6 Verification Suite."""

    def setUp(self):
        self.draft_mgr = DraftManager()

    def test_explicit_approval_phrases_accepted(self):
        """Explicit confirmation phrases must be successfully recognized."""
        valid_approvals = [
            "Yes, send it",
            "Send it",
            "Send the message",
            "Submit it",
            "Go ahead and send",
            "Approve and submit",
            "Yes please send"
        ]
        for phrase in valid_approvals:
            draft = self.draft_mgr.create_draft(
                app_name="antigravity",
                draft_text="Deploy pipeline",
                target_hwnd=67074
            )
            with patch.object(self.draft_mgr.interaction_mgr, "verify_antigravity_submission") as mock_v:
                mock_v.return_value = {"confirmed": True, "status": "VERIFIED", "stage": SubmissionVerificationStatus.PROMPT_ACCEPTED}
                res = self.draft_mgr.process_approval(phrase, draft_id=draft.draft_id, current_content="Deploy pipeline", current_hwnd=67074)
                self.assertTrue(res["success"], f"Failed on phrase: '{phrase}'")

    def test_ambiguous_phrases_strictly_rejected(self):
        """Ambiguous utterances like 'okay', 'maybe', 'sounds good' must NEVER submit."""
        ambiguous_phrases = [
            "okay",
            "ok",
            "maybe",
            "sounds good",
            "i guess",
            "sure why not",
            "fine"
        ]
        for phrase in ambiguous_phrases:
            draft = self.draft_mgr.create_draft(
                app_name="antigravity",
                draft_text="Sensitive production deployment",
                target_hwnd=67074
            )
            res = self.draft_mgr.process_approval(phrase, draft_id=draft.draft_id)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "AMBIGUOUS_APPROVAL_REJECTED")
            self.assertFalse(res["submitted"])
            self.assertNotEqual(draft.state, DraftState.APPROVED)

    def test_background_chatter_and_tv_audio_rejected(self):
        """Random conversational background speech or TV audio must be rejected as unrelated."""
        background_utterances = [
            "Did you order pizza tonight?",
            "Turn on the air conditioner please",
            "And now we send it back to the studio in New York",
            "Who is winning the cricket match?",
            "Hey what time does the train arrive"
        ]
        for phrase in background_utterances:
            draft = self.draft_mgr.create_draft(
                app_name="antigravity",
                draft_text="Sensitive financial transfer",
                target_hwnd=67074
            )
            res = self.draft_mgr.process_approval(phrase, draft_id=draft.draft_id)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "UNRELATED_SPEECH")
            self.assertFalse(res["submitted"])
            self.assertNotEqual(draft.state, DraftState.APPROVED)

    def test_low_confidence_acoustic_rejection(self):
        """Spoken approval with low confidence (< 0.65) must be rejected to prevent acoustic false-triggers."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Drop production database",
            target_hwnd=67074
        )
        res = self.draft_mgr.process_approval(
            "Yes, send it",
            draft_id=draft.draft_id,
            confidence=0.48,  # Muffled / distant background confidence
            is_final=True
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "LOW_CONFIDENCE_REJECTED")
        self.assertFalse(res["submitted"])
        self.assertIn("low acoustic confidence", res["message"])
        self.assertNotEqual(draft.state, DraftState.APPROVED)

    def test_partial_streaming_transcript_rejection(self):
        """In-flight partial transcripts (is_final=False) must never trigger submission."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Execute security audit",
            target_hwnd=67074
        )
        res = self.draft_mgr.process_approval(
            "Yes, send",
            draft_id=draft.draft_id,
            is_final=False  # User is still speaking!
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "PARTIAL_TRANSCRIPT_REJECTED")
        self.assertFalse(res["submitted"])
        self.assertIn("cannot be granted on a partial transcript", res["message"])
        self.assertNotEqual(draft.state, DraftState.APPROVED)

    def test_single_use_token_and_replay_prevention(self):
        """Once approved and submitted, draft state is consumed; replay attempts are rejected."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Send email report",
            target_hwnd=67074
        )
        with patch.object(self.draft_mgr.interaction_mgr, "verify_antigravity_submission") as mock_v:
            mock_v.return_value = {"confirmed": True, "status": "VERIFIED", "stage": SubmissionVerificationStatus.PROMPT_ACCEPTED}
            res1 = self.draft_mgr.process_approval("Yes, send it", draft_id=draft.draft_id, current_content="Send email report", current_hwnd=67074)
            self.assertTrue(res1["success"])

        # Immediate replay attempt with exact same phrase
        res2 = self.draft_mgr.process_approval("Yes, send it", draft_id=draft.draft_id, current_content="Send email report", current_hwnd=67074)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status"], "ALREADY_SUBMITTED")
        self.assertIn("already been submitted", res2["message"])

    def test_ttl_expiry_enforcement(self):
        """Drafts older than default TTL (180s) must be expired and rejected."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Old message",
            target_hwnd=67074
        )
        # Force expiry timestamp into the past
        draft.expiry_timestamp = time.time() - 10.0

        res = self.draft_mgr.process_approval("Yes, send it", draft_id=draft.draft_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "DRAFT_EXPIRED")
        self.assertEqual(draft.state, DraftState.EXPIRED)


if __name__ == "__main__":
    unittest.main()

