import unittest
from unittest.mock import MagicMock, patch
import time
from core.interaction.message_workflow import (
    MessageWorkflowManager,
    MessageWorkflowState,
    PendingApproval
)

class TestMessageApprovalSecurityDeep(unittest.TestCase):
    def setUp(self):
        self.mgr = MessageWorkflowManager()

    def test_draft_creation_and_hash_binding(self):
        draft = self.mgr.create_draft("TestApp", "Hello, this is a secret draft.", target_hwnd=12345)
        self.assertIsNotNone(draft.draft_id)
        self.assertEqual(draft.target_app, "TestApp")
        self.assertEqual(draft.target_hwnd, 12345)
        self.assertEqual(self.mgr.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)
        self.assertEqual(len(draft.content_hash), 64) # SHA-256 hex length
        self.assertTrue(self.mgr.verify_draft_unaltered(draft.draft_id, "Hello, this is a secret draft."))
        self.assertFalse(self.mgr.verify_draft_unaltered(draft.draft_id, "Hello, this is a MODIFIED draft."))

    def test_low_stt_confidence_blocks_send(self):
        draft = self.mgr.create_draft("TestApp", "Send test draft.")
        res = self.mgr.process_approval_response("Yes send it", confidence=0.45, draft_id=draft.draft_id)
        self.assertFalse(res["sent"])
        self.assertTrue(res.get("requires_explicit_approval"))
        self.assertIn("low audio confidence", res["message"])
        self.assertEqual(self.mgr.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)

    def test_ambiguous_response_blocks_send(self):
        draft = self.mgr.create_draft("TestApp", "Draft awaiting approval.")
        for phrase in ["looks good", "ok", "fine", "nice"]:
            res = self.mgr.process_approval_response(phrase, confidence=0.95, draft_id=draft.draft_id)
            self.assertFalse(res["sent"])
            self.assertTrue(res.get("requires_explicit_approval"))
            self.assertIn("leave it as a draft", res["message"])
            self.assertEqual(self.mgr.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)

    def test_explicit_rejection_cancels(self):
        draft = self.mgr.create_draft("TestApp", "Draft awaiting approval.")
        res = self.mgr.process_approval_response("don't send", confidence=0.95, draft_id=draft.draft_id)
        self.assertFalse(res["sent"])
        self.assertEqual(self.mgr.state, MessageWorkflowState.CANCELLED)
        self.assertIn("leave the draft there", res["message"])

    def test_draft_content_tampering_aborts(self):
        draft = self.mgr.create_draft("TestApp", "Original content.")
        res = self.mgr.process_approval_response(
            "yes send it",
            confidence=0.95,
            draft_id=draft.draft_id,
            current_content="Tampered content!"
        )
        self.assertFalse(res["sent"])
        self.assertEqual(res.get("reason"), "draft_content_changed")

    def test_duplicate_send_prevention(self):
        draft = self.mgr.create_draft("TestApp", "Send once only.")
        with patch("pyautogui.press") as mock_press, \
             patch("ctypes.windll.user32.GetForegroundWindow", return_value=0):
            res1 = self.mgr.process_approval_response("yes send it", confidence=0.95, draft_id=draft.draft_id)
            self.assertTrue(res1["sent"])
            self.assertEqual(self.mgr.state, MessageWorkflowState.SENT)

            res2 = self.mgr.process_approval_response("yes send it", confidence=0.95, draft_id=draft.draft_id)
            self.assertFalse(res2["sent"])
            self.assertEqual(res2.get("reason"), "already_sent")

    def test_ttl_expiration(self):
        draft = self.mgr.create_draft("TestApp", "Expired message.")
        draft.created_at = time.time() - 200 # older than 180s TTL
        res = self.mgr.process_approval_response("yes send it", confidence=0.95, draft_id=draft.draft_id)
        self.assertFalse(res["sent"])
        self.assertEqual(res.get("reason"), "draft_expired")
        self.assertEqual(self.mgr.state, MessageWorkflowState.CANCELLED)

    def test_hwnd_mismatch_aborts_send(self):
        draft = self.mgr.create_draft("Chrome", "Browser draft", target_hwnd=99999)
        with patch("ctypes.windll.user32.GetForegroundWindow", return_value=11111):
            res = self.mgr.process_approval_response("yes send it", confidence=0.95, draft_id=draft.draft_id)
            self.assertFalse(res["sent"])
            self.assertEqual(res.get("reason"), "target_hwnd_changed")
            self.assertEqual(self.mgr.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)

    def test_email_uses_ctrl_enter(self):
        draft = self.mgr.create_draft("Outlook", "Email body", target_hwnd=555)
        with patch("pyautogui.hotkey") as mock_hotkey, \
             patch("ctypes.windll.user32.GetForegroundWindow", return_value=555), \
             patch.object(self.mgr.context_service, "get_current_context") as mock_ctx:
            mock_ctx.return_value.foreground_app = "Outlook"
            res = self.mgr.process_approval_response("send it", confidence=0.95, draft_id=draft.draft_id)
            self.assertTrue(res["sent"])
            self.assertEqual(res.get("method"), "ctrl_enter_email")
            mock_hotkey.assert_called_with("ctrl", "enter")

    def test_chat_uses_enter(self):
        draft = self.mgr.create_draft("ChatGPT", "AI Prompt", target_hwnd=777)
        with patch("pyautogui.press") as mock_press, \
             patch("ctypes.windll.user32.GetForegroundWindow", return_value=777), \
             patch.object(self.mgr.context_service, "get_current_context") as mock_ctx:
            mock_ctx.return_value.foreground_app = "ChatGPT"
            res = self.mgr.process_approval_response("send", confidence=0.95, draft_id=draft.draft_id)
            self.assertTrue(res["sent"])
            self.assertEqual(res.get("method"), "enter_chat")
            mock_press.assert_called_with("enter")

if __name__ == "__main__":
    unittest.main()

