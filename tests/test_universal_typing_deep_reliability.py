import unittest
from unittest.mock import MagicMock, patch
from core.typing.focus_detector import FocusInfo
from core.typing.text_inserter import TextInserter, SafeClipboardManager
from core.typing.typing_coordinator import TypingCoordinator
from core.typing.punctuation_formatter import PunctuationFormatter
from core.typing.code_formatter import CodeFormatter

class TestUniversalTypingDeepReliability(unittest.TestCase):
    def setUp(self):
        self.mock_detector = MagicMock()
        self.inserter = TextInserter(detector=self.mock_detector)
        self.coordinator = TypingCoordinator(detector=self.mock_detector, inserter=self.inserter)
        self.p_formatter = PunctuationFormatter()
        self.c_formatter = CodeFormatter()

    def test_adaptive_paste_delays(self):
        self.assertEqual(self.inserter.get_adaptive_paste_delay("notepad.exe"), 0.08)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("chrome.exe"), 0.18)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("msedge.exe"), 0.18)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("code.exe"), 0.20)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("slack.exe"), 0.20)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("teams.exe"), 0.22)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("custom_editor.exe"), 0.14)

    def test_pre_insertion_focus_stability_abort(self):
        # Target HWND mismatch before insertion
        self.mock_detector.verify_focus_stable.return_value = False
        res = self.inserter.insert_text(
            "test payload",
            expected_hwnd=999,
            expected_title="Expected App"
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "target_lost")
        self.assertIn("active application changed", res["message"])

    def test_password_field_absolute_protection(self):
        pwd_focus = FocusInfo(
            hwnd=123,
            process_name="chrome.exe",
            app_name="chrome.exe",
            window_title="Sign In",
            is_editable=True,
            is_password=True
        )
        res = self.inserter.insert_text("secret_password", focus_info=pwd_focus)
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "password_field_blocked")
        self.assertIn("cannot type into password or secure fields", res["message"])

    def test_read_only_field_protection(self):
        ro_focus = FocusInfo(
            hwnd=123,
            process_name="notepad.exe",
            app_name="notepad.exe",
            window_title="Read Only Doc",
            is_editable=False,
            is_password=False
        )
        res = self.inserter.insert_text("append text", focus_info=ro_focus)
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "read_only")

    def test_spoken_punctuation_formatting(self):
        speech = "hello world comma this is santra period new line are you ready question mark"
        formatted = self.p_formatter.format_text(speech)
        self.assertEqual(formatted, "Hello world, this is santra.\nAre you ready?")

        para_speech = "first paragraph period new paragraph second paragraph exclamation point"
        para_formatted = self.p_formatter.format_text(para_speech)
        self.assertEqual(para_formatted, "First paragraph.\n\nSecond paragraph!")

    def test_code_mode_formatting(self):
        speech = "def snake case calculate total open paren x comma y close paren colon"
        code = self.c_formatter.format_code(speech, language="python")
        self.assertIn("def calculate_total(x, y):", code)

        camel_speech = "const camel case user id equals open quote admin close quote semicolon"
        camel_code = self.c_formatter.format_code(camel_speech, language="javascript")
        self.assertIn("const userId = \"admin\";", camel_code)

    def test_typing_coordinator_pause_resume_undo(self):
        self.mock_detector.get_focus_info.return_value = FocusInfo(
            hwnd=10, process_name="notepad.exe", app_name="notepad.exe", window_title="Notes", is_editable=True
        )
        self.mock_detector.verify_focus_stable.return_value = True

        with patch("pyautogui.hotkey") as mock_hotkey, \
             patch.object(self.inserter.clip_mgr, "snapshot", return_value={"has_text": False}), \
             patch.object(self.inserter.clip_mgr, "set_text", return_value=True), \
             patch.object(self.inserter.clip_mgr, "restore", return_value=True):
            # 1. Start typing session
            s_res = self.coordinator.start_typing()
            self.assertTrue(s_res["success"])

            # 2. Feed speech
            r1 = self.coordinator.feed_speech("Hello notepad full stop")
            self.assertTrue(r1["success"])

            # 3. Pause typing
            self.coordinator.pause_typing()
            r2 = self.coordinator.feed_speech("This should be blocked")
            self.assertFalse(r2["success"])
            self.assertEqual(r2["reason"], "not_active")

            # 4. Resume typing
            self.coordinator.resume_typing()
            r3 = self.coordinator.feed_speech("Now resumed")
            self.assertTrue(r3["success"])

            # 5. Undo triggers Ctrl+Z
            r4 = self.coordinator.handle_correction("undo")
            self.assertTrue(r4["success"])
            mock_hotkey.assert_any_call("ctrl", "z")

    def test_failsafe_emergency_stop_caught(self):
        self.mock_detector.get_focus_info.return_value = FocusInfo(
            hwnd=10, process_name="notepad.exe", app_name="notepad.exe", window_title="Notes", is_editable=True
        )
        self.mock_detector.verify_focus_stable.return_value = True

        from pyautogui import FailSafeException
        with patch("pyautogui.hotkey", side_effect=FailSafeException("Mouse corner")):
            res = self.inserter.insert_text("typing that triggers fail-safe")
            self.assertFalse(res["success"])
            self.assertEqual(res["reason"], "emergency_stop")

    def test_multiline_long_text_and_special_symbols(self):
        focus = FocusInfo(
            hwnd=10, process_name="notepad.exe", app_name="notepad.exe", window_title="Doc - Notepad", is_editable=True
        )
        self.mock_detector.verify_focus_stable.return_value = True

        long_payload = ("Line 1: Special symbols: $100 & {key: 'value'} \\ escape.\n"
                        "    Line 2: 4-space indent block with Unicode: 🚀 ✨ ñoño.\n") * 20
        self.assertGreater(len(long_payload), 1000)

        with patch("pyautogui.hotkey") as mock_hotkey, \
             patch.object(self.inserter.clip_mgr, "snapshot", return_value={"text": "orig", "has_text": True}), \
             patch.object(self.inserter.clip_mgr, "set_text", return_value=True) as mock_set, \
             patch.object(self.inserter.clip_mgr, "restore", return_value=True) as mock_restore:
            res = self.inserter.insert_text(long_payload, focus_info=focus)
            self.assertTrue(res["success"])
            self.assertEqual(res["method"], "clipboard_paste")
            mock_set.assert_called_with(long_payload)
            mock_hotkey.assert_called_with("ctrl", "v")
            mock_restore.assert_called_once()

    def test_post_paste_focus_shift_abort(self):
        focus = FocusInfo(
            hwnd=10, process_name="chrome.exe", app_name="chrome.exe", window_title="Web App", is_editable=True
        )
        self.mock_detector.verify_focus_stable.return_value = False

        res = self.inserter.insert_text("Target focus changed test", focus_info=focus)
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "target_lost")
        self.assertIn("Focus changed immediately prior to typing", res["message"])

    def test_host_application_status_classification(self):
        from core.os.application_resolver import application_resolver, TargetType

        # Notepad is verified on Windows
        notepad_app = application_resolver.resolve("notepad")
        self.assertEqual(notepad_app.target_type, TargetType.APPLICATION)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("notepad.exe"), 0.08)

        # Chrome is verified on Windows
        chrome_app = application_resolver.resolve("chrome")
        self.assertEqual(chrome_app.target_type, TargetType.APPLICATION)
        self.assertEqual(self.inserter.get_adaptive_paste_delay("chrome.exe"), 0.18)

        # VS Code delay
        self.assertEqual(self.inserter.get_adaptive_paste_delay("code.exe"), 0.20)

        # Non-installed check
        non_existent = application_resolver.resolve("definitely_non_existent_app_9999")
        self.assertEqual(non_existent.target_type, TargetType.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
