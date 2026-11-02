"""Unit tests for The Ask-Before-Send Conversation Workflow Engine."""

import time
import unittest
from unittest.mock import MagicMock, patch
from core.interaction.message_workflow import MessageWorkflowManager, MessageWorkflowState


class TestMessageWorkflowAskBeforeSend(unittest.TestCase):
    """Verifies that draft creation never sends automatically and requires explicit approval."""

    def setUp(self):
        self.workflow = MessageWorkflowManager()

    @patch("core.interaction.text_entry_service.text_entry_service.enter_text")
    @patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context")
    def test_prepare_message_does_not_send(self, mock_context, mock_enter):
        mock_ctx = MagicMock()
        mock_ctx.foreground_app = "ChatGPT"
        mock_ctx.window_title = "ChatGPT — Mozilla Firefox"
        mock_context.return_value = mock_ctx
        mock_enter.return_value = {"success": True, "target": "ChatGPT Prompt Box"}

        res = self.workflow.prepare_message("Explain quantum computing in simple terms", target_app="ChatGPT")

        self.assertTrue(res["success"])
        self.assertEqual(res["state"], MessageWorkflowState.AWAITING_SEND_APPROVAL.value)
        self.assertTrue(res["requires_approval"])
        self.assertIn("Should I send it?", res["message"])
        self.assertEqual(self.workflow.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)

    @patch("pyautogui.press")
    @patch("core.interaction.text_entry_service.text_entry_service.enter_text")
    @patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context")
    def test_explicit_approval_sends_chat(self, mock_context, mock_enter, mock_press):
        mock_ctx = MagicMock()
        mock_ctx.foreground_app = "ChatGPT"
        mock_ctx.window_title = "ChatGPT"
        mock_context.return_value = mock_ctx
        mock_enter.return_value = {"success": True, "target": "ChatGPT Prompt Box"}

        self.workflow.prepare_message("Hello from user", target_app="ChatGPT")
        self.assertEqual(self.workflow.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)

        res = self.workflow.process_approval_response("Yes, send it")
        self.assertTrue(res["success"])
        self.assertTrue(res["sent"])
        self.assertEqual(res["state"], MessageWorkflowState.SENT.value)
        self.assertEqual(self.workflow.state, MessageWorkflowState.SENT)
        # In chat interface, Enter is pressed
        mock_press.assert_called_with("enter")

    @patch("pyautogui.hotkey")
    @patch("core.interaction.text_entry_service.text_entry_service.enter_text")
    @patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context")
    def test_explicit_approval_sends_email_with_ctrl_enter(self, mock_context, mock_enter, mock_hotkey):
        mock_ctx = MagicMock()
        mock_ctx.foreground_app = "Outlook"
        mock_ctx.window_title = "Inbox - Outlook"
        mock_context.return_value = mock_ctx
        mock_enter.return_value = {"success": True, "target": "Email Body"}

        self.workflow.prepare_message("Meeting confirmation attached.", target_app="Outlook")

        res = self.workflow.process_approval_response("Send the message")
        self.assertTrue(res["success"])
        self.assertTrue(res["sent"])
        self.assertEqual(self.workflow.state, MessageWorkflowState.SENT)
        # In email client, Ctrl+Enter is used
        mock_hotkey.assert_called_with("ctrl", "enter")

    @patch("pyautogui.press")
    @patch("pyautogui.hotkey")
    @patch("core.interaction.text_entry_service.text_entry_service.enter_text")
    @patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context")
    def test_ambiguous_responses_withhold_permission(self, mock_context, mock_enter, mock_hotkey, mock_press):
        ambiguous_utterances = [
            "looks good",
            "okay",
            "that's fine",
            "nice",
            "cool",
            "perfect"
        ]

        for utterance in ambiguous_utterances:
            mock_press.reset_mock()
            mock_hotkey.reset_mock()
            mock_ctx = MagicMock()
            mock_ctx.foreground_app = "WhatsApp"
            mock_ctx.window_title = "WhatsApp"
            mock_context.return_value = mock_ctx
            mock_enter.return_value = {"success": True, "target": "Message input"}

            self.workflow.prepare_message("Draft text", target_app="WhatsApp")
            res = self.workflow.process_approval_response(utterance)

            self.assertTrue(res["success"])
            self.assertFalse(res["sent"])
            self.assertTrue(res.get("requires_explicit_approval"))
            self.assertEqual(self.workflow.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)
            # Ensure no send key was pressed
            mock_press.assert_not_called()
            mock_hotkey.assert_not_called()

    @patch("pyautogui.press")
    @patch("pyautogui.hotkey")
    @patch("core.interaction.text_entry_service.text_entry_service.enter_text")
    @patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context")
    def test_explicit_rejections_cancel_sending(self, mock_context, mock_enter, mock_hotkey, mock_press):
        rejections = [
            "don't send it",
            "dont send",
            "leave it as a draft",
            "cancel",
            "no"
        ]

        for rejection in rejections:
            mock_press.reset_mock()
            mock_hotkey.reset_mock()
            mock_ctx = MagicMock()
            mock_ctx.foreground_app = "Discord"
            mock_ctx.window_title = "Discord"
            mock_context.return_value = mock_ctx
            mock_enter.return_value = {"success": True, "target": "Discord message"}

            self.workflow.prepare_message("Draft text", target_app="Discord")
            res = self.workflow.process_approval_response(rejection)

            self.assertTrue(res["success"])
            self.assertFalse(res["sent"])
            self.assertEqual(self.workflow.state, MessageWorkflowState.CANCELLED)
            mock_press.assert_not_called()
            mock_hotkey.assert_not_called()

    def test_approval_without_pending_draft(self):
        self.workflow.state = MessageWorkflowState.IDLE
        res = self.workflow.process_approval_response("Yes, send it")
        self.assertFalse(res["success"])
        self.assertIn("no pending message draft", res["message"].lower())

    def test_draft_expiration(self):
        self.workflow.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
        self.workflow.target_app = "ChatGPT"
        self.workflow.current_draft = "Hello"
        # Set created_at to 200 seconds ago (exceeding 180s TTL)
        self.workflow.created_at = time.time() - 200.0

        res = self.workflow.process_approval_response("Yes, send it")
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "draft_expired")
        self.assertEqual(self.workflow.state, MessageWorkflowState.CANCELLED)

    def test_low_confidence_rejection(self):
        self.workflow.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
        self.workflow.target_app = "ChatGPT"
        self.workflow.current_draft = "Hello"
        self.workflow.created_at = time.time()

        res = self.workflow.process_approval_response("send it", confidence=0.45)
        self.assertTrue(res["success"])
        self.assertFalse(res["sent"])
        self.assertTrue(res.get("requires_explicit_approval"))
        self.assertIn("low audio confidence", res["message"].lower())
        self.assertEqual(self.workflow.state, MessageWorkflowState.AWAITING_SEND_APPROVAL)

    @patch("core.interaction.desktop_context_service.desktop_context_service.get_current_context")
    def test_target_app_changed_withholds_send(self, mock_context):
        self.workflow.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
        self.workflow.target_app = "chatgpt"
        self.workflow.current_draft = "Sensitive message"
        self.workflow.created_at = time.time()

        # Foreground window changed to Windows Terminal!
        mock_ctx = MagicMock()
        mock_ctx.foreground_app = "Windows Terminal"
        mock_context.return_value = mock_ctx

        res = self.workflow.process_approval_response("Yes, send it")
        self.assertFalse(res["success"])
        self.assertFalse(res["sent"])
        self.assertEqual(res["reason"], "target_app_changed")
        self.assertIn("active window changed", res["message"].lower())


if __name__ == "__main__":
    unittest.main()
