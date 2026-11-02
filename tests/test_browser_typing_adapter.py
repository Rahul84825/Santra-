import unittest
from unittest.mock import MagicMock, patch
from core.typing.browser_typing_adapter import BrowserTypingAdapter, BrowserSubmissionOutcome
from core.interaction.message_workflow import MessageWorkflowManager, MessageWorkflowState

class TestBrowserTypingAdapter(unittest.TestCase):
    def setUp(self):
        self.workflow_mgr = MessageWorkflowManager()
        self.mock_cdp = MagicMock()
        self.mock_cdp.is_available.return_value = False
        self.adapter = BrowserTypingAdapter(cdp_client=self.mock_cdp, workflow_mgr=self.workflow_mgr)

    @patch("win32gui.GetForegroundWindow", return_value=1234)
    @patch("win32gui.GetWindowText", return_value="ChatGPT - Google Chrome")
    @patch("win32process.GetWindowThreadProcessId", return_value=(1, 5678))
    @patch("psutil.Process")
    def test_identify_active_browser_chrome(self, mock_proc_cls, mock_win_pid, mock_win_text, mock_fg):
        mock_proc = MagicMock()
        mock_proc.name.return_value = "chrome.exe"
        mock_proc_cls.return_value = mock_proc

        info = self.adapter.identify_active_browser()
        self.assertTrue(info["is_browser"])
        self.assertEqual(info["browser_type"], "chrome")
        self.assertEqual(info["hwnd"], 1234)

    def test_identify_active_tab_chatgpt_gemini_claude(self):
        # ChatGPT
        b_info = {"is_browser": True, "title": "New Chat - ChatGPT — Mozilla Firefox", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        self.assertTrue(tab["is_ai_app"])
        self.assertEqual(tab["service_name"], "chatgpt")

        # Gemini
        b_info = {"is_browser": True, "title": "Gemini - Chat with Google AI - Google Chrome", "hwnd": 22}
        tab = self.adapter.identify_active_tab(b_info)
        self.assertTrue(tab["is_ai_app"])
        self.assertEqual(tab["service_name"], "gemini")

        # Claude
        b_info = {"is_browser": True, "title": "Claude 3.5 Sonnet - Anthropic", "hwnd": 33}
        tab = self.adapter.identify_active_tab(b_info)
        self.assertTrue(tab["is_ai_app"])
        self.assertEqual(tab["service_name"], "claude")

    def test_unauthenticated_blocked_status(self):
        # Test auth check on login URL
        b_info = {"is_browser": True, "title": "Log in to ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        tab["url"] = "https://auth0.openai.com/u/login"

        is_auth, msg = self.adapter.check_authentication_status(tab)
        self.assertFalse(is_auth)
        self.assertIn("BLOCKED", msg)

        # Full workflow on unauthenticated tab must return status="BLOCKED"
        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab):
            res = self.adapter.execute_browser_typing_workflow("Hello ChatGPT!")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "BLOCKED")
            self.assertEqual(res["reason"], "unauthenticated")

    def test_password_field_blocked(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value={"found": True, "is_password": True, "is_editable": False}):
            res = self.adapter.execute_browser_typing_workflow("My super secret")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "BLOCKED")
            self.assertEqual(res["reason"], "password_field")

    def test_draft_insertion_and_approval_workflow(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {"found": True, "is_password": False, "is_editable": True, "method": "ui_automation"}

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.text_inserter.text_inserter.insert_text", return_value={"success": True}):
            res = self.adapter.execute_browser_typing_workflow("Explain quantum computing in one sentence.")
            self.assertTrue(res["success"])
            self.assertTrue(res["draft_inserted"])
            self.assertEqual(res["status"], "AWAITING_APPROVAL")
            approval_id = res["approval_id"]

            # 1. Ambiguous response withholding send permission
            appr_res1 = self.adapter.process_send_approval(approval_id, "okay sounds good")
            self.assertFalse(appr_res1["approved"])
            self.assertTrue(appr_res1["requires_explicit_approval"])

            # 2. Explicit approval sends message (delivery unconfirmed via keyboard simulation)
            with patch("pyautogui.press") as mock_press, \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res2 = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertTrue(appr_res2["approved"])
                self.assertTrue(appr_res2["submitted"])
                self.assertEqual(appr_res2["outcome"], "SUBMISSION_TRIGGERED")
                self.assertEqual(appr_res2["verification"], "DELIVERY_UNCONFIRMED")
                mock_press.assert_called_with("enter")

    def test_auth_check_across_chatgpt_gemini_claude(self):
        # 1. Gemini login wall
        b_gemini = {"is_browser": True, "title": "Sign in - Google Accounts", "hwnd": 22}
        tab_gemini = self.adapter.identify_active_tab(b_gemini)
        tab_gemini["url"] = "https://accounts.google.com/signin/v2/identifier"
        tab_gemini["service_name"] = "gemini"
        from core.os.website_adapters import GeminiAdapter
        tab_gemini["adapter"] = GeminiAdapter()

        is_auth, msg = self.adapter.check_authentication_status(tab_gemini)
        self.assertFalse(is_auth)
        self.assertIn("BLOCKED", msg)

        # 2. Claude login wall
        b_claude = {"is_browser": True, "title": "Log in to Claude", "hwnd": 33}
        tab_claude = self.adapter.identify_active_tab(b_claude)
        tab_claude["url"] = "https://claude.ai/login"
        tab_claude["service_name"] = "claude"
        from core.os.website_adapters import ClaudeAdapter
        tab_claude["adapter"] = ClaudeAdapter()

        is_auth_c, msg_c = self.adapter.check_authentication_status(tab_claude)
        self.assertFalse(is_auth_c)
        self.assertIn("BLOCKED", msg_c)

    def test_dom_verified_submission_outcome(self):
        # Test CDP DOM clearance verification produces outcome="DELIVERY_VERIFIED"
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {
            "found": True,
            "is_password": False,
            "is_editable": True,
            "method": "cdp_dom",
            "selector": "#prompt-textarea",
            "ws_url": "ws://127.0.0.1:9222/devtools/page/test"
        }

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.browser_typing_adapter.LightweightCDPWebSocket") as mock_ws_cls:
            mock_ws = MagicMock()
            mock_ws.connect.return_value = True
            
            def cdp_eval_mock(cmd, params):
                expr = params.get("expression", "")
                if "return currentVal.includes" in expr:
                    return {"result": {"result": {"value": True}}}
                elif "return el ? (el.value || el.innerText" in expr:
                    return {"result": {"result": {"value": "Summarize relativity."}}}
                elif "return !el || !(el.value" in expr:
                    return {"result": {"result": {"value": True}}}
                return {"result": {"result": {"value": {
                    "fieldCleared": True,
                    "errorDetected": False,
                    "errorText": "",
                    "messageVisible": False,
                    "responseGenerated": False
                }}}}

            mock_ws.send_cdp_command.side_effect = cdp_eval_mock
            mock_ws_cls.return_value = mock_ws

            res = self.adapter.execute_browser_typing_workflow("Summarize relativity.")
            self.assertTrue(res["success"])
            approval_id = res["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertTrue(appr_res["approved"])
                self.assertEqual(appr_res["outcome"], BrowserSubmissionOutcome.APPLICATION_ACCEPTED.value)
                self.assertEqual(appr_res["verification"], "DELIVERY_VERIFIED")

    def test_message_visible_and_response_generated_outcomes(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {
            "found": True,
            "is_password": False,
            "is_editable": True,
            "method": "cdp_dom",
            "selector": "#prompt-textarea",
            "ws_url": "ws://127.0.0.1:9222/devtools/page/test"
        }

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.browser_typing_adapter.LightweightCDPWebSocket") as mock_ws_cls:
            mock_ws = MagicMock()
            mock_ws.connect.return_value = True

            # Helper for CDP dispatch
            def make_cdp_mock(content_text, evidence_dict):
                def _mock(cmd, params):
                    expr = params.get("expression", "")
                    if "currentVal.includes" in expr:
                        return {"result": {"result": {"value": True}}}
                    elif "return el ? (el.value || el.innerText" in expr:
                        return {"result": {"result": {"value": content_text}}}
                    return {"result": {"result": {"value": evidence_dict}}}
                return _mock

            # 1. Test MESSAGE_VISIBLE
            msg1 = "Hello visible message"
            mock_ws.send_cdp_command.side_effect = make_cdp_mock(msg1, {
                "fieldCleared": True,
                "errorDetected": False,
                "errorText": "",
                "messageVisible": True,
                "responseGenerated": False
            })
            mock_ws_cls.return_value = mock_ws

            res = self.adapter.execute_browser_typing_workflow(msg1)
            approval_id = res["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertTrue(appr_res["approved"])
                self.assertEqual(appr_res["outcome"], BrowserSubmissionOutcome.MESSAGE_VISIBLE.value)

            # 2. Test RESPONSE_GENERATED
            msg2 = "Hello response generated"
            mock_ws.send_cdp_command.side_effect = make_cdp_mock(msg2, {
                "fieldCleared": True,
                "errorDetected": False,
                "errorText": "",
                "messageVisible": True,
                "responseGenerated": True
            })

            res2 = self.adapter.execute_browser_typing_workflow(msg2)
            approval_id2 = res2["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res2 = self.adapter.process_send_approval(approval_id2, "yes send it")
                self.assertTrue(appr_res2["approved"])
                self.assertEqual(appr_res2["outcome"], BrowserSubmissionOutcome.RESPONSE_GENERATED.value)

    def test_error_detected_returns_failed_outcome(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {
            "found": True,
            "is_password": False,
            "is_editable": True,
            "method": "cdp_dom",
            "selector": "#prompt-textarea",
            "ws_url": "ws://127.0.0.1:9222/devtools/page/test"
        }

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.browser_typing_adapter.LightweightCDPWebSocket") as mock_ws_cls:
            mock_ws = MagicMock()
            mock_ws.connect.return_value = True

            err_msg = "Will encounter network error"
            def make_cdp_mock(cmd, params):
                expr = params.get("expression", "")
                if "currentVal.includes" in expr:
                    return {"result": {"result": {"value": True}}}
                elif "return el ? (el.value || el.innerText" in expr:
                    return {"result": {"result": {"value": err_msg}}}
                return {"result": {"result": {"value": {
                    "fieldCleared": False,
                    "errorDetected": True,
                    "errorText": "Network error, please retry",
                    "messageVisible": False,
                    "responseGenerated": False
                }}}}

            mock_ws.send_cdp_command.side_effect = make_cdp_mock
            mock_ws_cls.return_value = mock_ws

            res = self.adapter.execute_browser_typing_workflow(err_msg)
            approval_id = res["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertFalse(appr_res["success"])
                self.assertEqual(appr_res["outcome"], BrowserSubmissionOutcome.FAILED.value)
                self.assertIn("Network error", appr_res["verification"])

    def test_duplicate_approval_rejected(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {"found": True, "is_password": False, "is_editable": True, "method": "ui_automation"}

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.text_inserter.text_inserter.insert_text", return_value={"success": True}):
            res = self.adapter.execute_browser_typing_workflow("No double sends allowed")
            approval_id = res["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                # First approval succeeds
                appr1 = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertTrue(appr1["approved"])
                self.assertTrue(appr1["submitted"])

                # Second approval on already sent draft is rejected
                appr2 = self.adapter.process_send_approval(approval_id, "yes send it again")
                self.assertFalse(appr2["approved"])
                self.assertEqual(appr2["reason"], "already_sent")

    def test_complex_multiline_unicode_code_prompts(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {"found": True, "is_password": False, "is_editable": True, "method": "ui_automation"}

        complex_text = "Here is Python code:\n```python\ndef greet(name: str) -> str:\n    return f'Hello, {name}! 🌟 café ñ'\n```\nPlease review it."

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.text_inserter.text_inserter.insert_text") as mock_insert:
            mock_insert.return_value = {"success": True}

            res = self.adapter.execute_browser_typing_workflow(complex_text)
            self.assertTrue(res["success"])
            self.assertTrue(res["draft_inserted"])
            mock_insert.assert_called_once()
            inserted_arg = mock_insert.call_args[0][0]
            self.assertEqual(inserted_arg, complex_text)

    def test_rapid_focus_shift_protection(self):
        # Foreground application changes between start and approval
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {"found": True, "is_password": False, "is_editable": True, "method": "ui_automation"}

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.text_inserter.text_inserter.insert_text", return_value={"success": True}):
            res = self.adapter.execute_browser_typing_workflow("Focus shift prompt")
            approval_id = res["approval_id"]

            # User shifted focus to Discord (HWND 999) before approving
            with patch("ctypes.windll.user32.GetForegroundWindow", return_value=999):
                appr_res = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertFalse(appr_res["approved"])
                self.assertEqual(appr_res["reason"], "target_hwnd_changed")

    def test_response_started_and_completed_outcomes(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {
            "found": True,
            "is_password": False,
            "is_editable": True,
            "method": "cdp_dom",
            "selector": "#prompt-textarea",
            "ws_url": "ws://127.0.0.1:9222/devtools/page/test"
        }

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.browser_typing_adapter.LightweightCDPWebSocket") as mock_ws_cls:
            mock_ws = MagicMock()
            mock_ws.connect.return_value = True

            # Helper for CDP dispatch
            def make_cdp_mock(content_text, evidence_dict):
                def _mock(cmd, params):
                    expr = params.get("expression", "")
                    if "currentVal.includes" in expr:
                        return {"result": {"result": {"value": True}}}
                    elif "return el ? (el.value || el.innerText" in expr:
                        return {"result": {"result": {"value": content_text}}}
                    return {"result": {"result": {"value": evidence_dict}}}
                return _mock

            # 1. Test RESPONSE_STARTED (active streaming with stop button visible)
            msg1 = "Stream this response"
            mock_ws.send_cdp_command.side_effect = make_cdp_mock(msg1, {
                "fieldCleared": True,
                "errorDetected": False,
                "errorText": "",
                "messageVisible": True,
                "responseStarted": True,
                "responseCompleted": False,
                "responseGenerated": True
            })
            mock_ws_cls.return_value = mock_ws

            res1 = self.adapter.execute_browser_typing_workflow(msg1)
            approval_id1 = res1["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res1 = self.adapter.process_send_approval(approval_id1, "yes send it")
                self.assertTrue(appr_res1["approved"])
                self.assertEqual(appr_res1["outcome"], BrowserSubmissionOutcome.RESPONSE_STARTED.value)

            # 2. Test RESPONSE_COMPLETED (streaming finished, response fully rendered)
            msg2 = "Complete this response"
            mock_ws.send_cdp_command.side_effect = make_cdp_mock(msg2, {
                "fieldCleared": True,
                "errorDetected": False,
                "errorText": "",
                "messageVisible": True,
                "responseStarted": False,
                "responseCompleted": True,
                "responseGenerated": True
            })

            res2 = self.adapter.execute_browser_typing_workflow(msg2)
            approval_id2 = res2["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res2 = self.adapter.process_send_approval(approval_id2, "yes send it")
                self.assertTrue(appr_res2["approved"])
                self.assertEqual(appr_res2["outcome"], BrowserSubmissionOutcome.RESPONSE_COMPLETED.value)

    def test_delivery_unconfirmed_on_empty_evidence(self):
        b_info = {"is_browser": True, "title": "ChatGPT", "hwnd": 11}
        tab = self.adapter.identify_active_tab(b_info)
        field = {
            "found": True,
            "is_password": False,
            "is_editable": True,
            "method": "cdp_dom",
            "selector": "#prompt-textarea",
            "ws_url": "ws://127.0.0.1:9222/devtools/page/test"
        }

        with patch.object(self.adapter, "identify_active_browser", return_value=b_info), \
             patch.object(self.adapter, "identify_active_tab", return_value=tab), \
             patch.object(self.adapter, "check_authentication_status", return_value=(True, "Authenticated")), \
             patch.object(self.adapter, "locate_and_verify_prompt_field", return_value=field), \
             patch("core.typing.browser_typing_adapter.LightweightCDPWebSocket") as mock_ws_cls:
            mock_ws = MagicMock()
            mock_ws.connect.return_value = True

            msg = "Unconfirmed prompt"
            def _mock(cmd, params):
                expr = params.get("expression", "")
                if "currentVal.includes" in expr:
                    return {"result": {"result": {"value": True}}}
                elif "return el ? (el.value || el.innerText" in expr:
                    return {"result": {"result": {"value": msg}}}
                # All indicators false (e.g. network stall before page update)
                return {"result": {"result": {"value": {
                    "fieldCleared": False,
                    "errorDetected": False,
                    "errorText": "",
                    "messageVisible": False,
                    "responseStarted": False,
                    "responseCompleted": False,
                    "responseGenerated": False
                }}}}

            mock_ws.send_cdp_command.side_effect = _mock
            mock_ws_cls.return_value = mock_ws

            res = self.adapter.execute_browser_typing_workflow(msg)
            approval_id = res["approval_id"]

            with patch("pyautogui.press"), \
                 patch("ctypes.windll.user32.GetForegroundWindow", return_value=11), \
                 patch.object(self.workflow_mgr.context_service, "get_current_context") as mock_ctx:
                mock_ctx.return_value.foreground_app = "chatgpt"
                appr_res = self.adapter.process_send_approval(approval_id, "yes send it")
                self.assertTrue(appr_res["approved"])
                self.assertEqual(appr_res["outcome"], BrowserSubmissionOutcome.DELIVERY_UNCONFIRMED.value)


if __name__ == "__main__":
    unittest.main()

