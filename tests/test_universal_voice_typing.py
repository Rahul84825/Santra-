"""Unit tests for Universal Voice Typing Engine and Dictation Formatting."""

import unittest
from unittest.mock import MagicMock, patch
from core.typing.models import TypingMode, TypingState, FocusInfo, DictationSegment, TypingSession
from core.typing.punctuation_formatter import punctuation_formatter
from core.typing.code_formatter import code_formatter
from core.typing.focus_detector import FocusDetector
from core.typing.text_inserter import TextInserter
from core.typing.typing_coordinator import TypingCoordinator


class TestPunctuationFormatter(unittest.TestCase):
    """Verifies spoken punctuation translation, formatting, and capitalization."""

    def test_basic_punctuation(self):
        text = "hello comma how are you question mark"
        result = punctuation_formatter.format_text(text)
        self.assertEqual(result, "Hello, how are you?")

    def test_sentence_capitalization(self):
        text = "first sentence period second sentence exclamation mark third sentence"
        result = punctuation_formatter.format_text(text)
        self.assertEqual(result, "First sentence. Second sentence! Third sentence")

    def test_newlines_and_paragraphs(self):
        text = "dear sir colon new line thank you for your email period new paragraph best regards comma"
        result = punctuation_formatter.format_text(text)
        self.assertIn(":\nThank", result)
        self.assertIn(".\n\nBest regards,", result)

    def test_quotes_and_brackets(self):
        text = "he said open quote welcome close quote in open parenthesis 2026 close parenthesis"
        result = punctuation_formatter.format_text(text)
        self.assertIn('"welcome"', result)
        self.assertIn("(2026)", result)

    def test_empty_input(self):
        self.assertEqual(punctuation_formatter.format_text(""), "")
        self.assertEqual(punctuation_formatter.format_text("   "), "")


class TestCodeFormatter(unittest.TestCase):
    """Verifies code dictation mode syntax, identifiers, and symbols."""

    def test_case_transformations(self):
        camel = code_formatter.format_code("camel case user profile service")
        self.assertIn("userProfileService", camel)

        snake = code_formatter.format_code("snake case calculate final score")
        self.assertIn("calculate_final_score", snake)

        screaming = code_formatter.format_code("constant default timeout seconds")
        self.assertIn("DEFAULT_TIMEOUT_SECONDS", screaming)

    def test_code_keywords_and_symbols(self):
        code = code_formatter.format_code("def add open paren self comma a comma b close paren colon")
        self.assertIn("def add(self, a, b):", code)

        code2 = code_formatter.format_code("if x double equals y arrow return true")
        self.assertIn("if x == y -> return True", code2)

    def test_indentation(self):
        indented = code_formatter.format_code("indent return true")
        self.assertTrue(indented.startswith("    return True"))


class TestTextInserterAndSecurity(unittest.TestCase):
    """Verifies safe text insertion, focus stability, and password security guard."""

    def setUp(self):
        self.mock_detector = MagicMock(spec=FocusDetector)
        self.mock_detector._uia_mod = None
        self.inserter = TextInserter(detector=self.mock_detector)

    def test_password_field_absolute_block(self):
        focus = FocusInfo(
            hwnd=1234,
            app_name="Chrome",
            window_title="Login - Bank",
            is_password=True,
            is_editable=True
        )
        self.mock_detector.get_focus_info.return_value = focus

        result = self.inserter.insert_text("secret_password", focus_info=focus)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "password_field_blocked")
        self.assertIn("password", result["message"].lower())

    def test_credential_window_fail_closed(self):
        detector = FocusDetector()
        with patch("win32gui.GetForegroundWindow", return_value=999), \
             patch("win32gui.GetWindowText", return_value="Windows Security - Enter Network Password"), \
             patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234)), \
             patch("psutil.Process") as mock_proc:
            mock_proc.return_value.name.return_value = "CredentialUIBroker.exe"
            detector._uia_auto = None  # Simulate UIA element unavailable or failing
            focus = detector.get_focus_info()
            self.assertTrue(focus.is_password)
            self.assertFalse(focus.is_editable)

    def test_read_only_field_block(self):
        focus = FocusInfo(
            hwnd=1234,
            app_name="Acrobat",
            window_title="Readonly PDF",
            is_password=False,
            is_editable=False
        )
        result = self.inserter.insert_text("hello", focus_info=focus)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "read_only")

    def test_window_stability_guard(self):
        self.mock_detector.verify_focus_stable.return_value = False
        focus = FocusInfo(hwnd=5678, app_name="Notepad", window_title="Notes")
        self.mock_detector.get_focus_info.return_value = focus

        result = self.inserter.insert_text("text", expected_hwnd=1234, expected_title="Old Window")
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "target_lost")

    @patch("pyautogui.hotkey")
    def test_clipboard_preservation(self, mock_hotkey):
        focus = FocusInfo(hwnd=100, app_name="Notepad", window_title="Untitled - Notepad", is_editable=True)
        self.mock_detector.get_focus_info.return_value = focus
        self.mock_detector.verify_focus_stable.return_value = True

        with patch.object(self.inserter.clip_mgr, "snapshot", return_value={"text": "ORIGINAL_DATA", "formats": [13], "has_text": True}), \
             patch.object(self.inserter.clip_mgr, "set_text") as mock_set, \
             patch.object(self.inserter.clip_mgr, "restore") as mock_restore:
            res = self.inserter.insert_text("Dictated text", focus_info=focus)
            self.assertTrue(res["success"])
            self.assertEqual(res["method"], "clipboard_paste")
            mock_set.assert_called_with("Dictated text")
            mock_restore.assert_called_once()

    @patch("pyautogui.hotkey")
    def test_emergency_stop_failsafe(self, mock_hotkey):
        import pyautogui
        mock_hotkey.side_effect = pyautogui.FailSafeException("Mouse in corner")
        focus = FocusInfo(hwnd=100, app_name="Notepad", window_title="Untitled - Notepad", is_editable=True)
        self.mock_detector.get_focus_info.return_value = focus
        self.mock_detector.verify_focus_stable.return_value = True

        res = self.inserter.insert_text("Text", focus_info=focus)
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "emergency_stop")
        self.assertIn("emergency stop", res["message"].lower())


class TestTypingCoordinator(unittest.TestCase):
    """Verifies typing coordinator states, spoken corrections, and mode transitions."""

    def setUp(self):
        self.mock_detector = MagicMock(spec=FocusDetector)
        self.mock_detector.get_focus_info.return_value = FocusInfo(
            hwnd=1001,
            app_name="Word",
            window_title="Document 1 - Word",
            target_name="Page 1",
            is_editable=True,
            is_password=False
        )
        self.mock_detector.verify_focus_stable.return_value = True
        self.mock_inserter = MagicMock(spec=TextInserter)
        self.mock_inserter.insert_text.return_value = {"success": True, "method": "clipboard_paste"}

        self.coordinator = TypingCoordinator(detector=self.mock_detector, inserter=self.mock_inserter)

    def test_start_pause_resume_stop(self):
        res = self.coordinator.start_typing(mode="continuous")
        self.assertTrue(res["success"])
        self.assertEqual(self.coordinator.state, TypingState.LISTENING)

        res_pause = self.coordinator.pause_typing()
        self.assertTrue(res_pause["success"])
        self.assertEqual(self.coordinator.state, TypingState.PAUSED)

        res_resume = self.coordinator.resume_typing()
        self.assertTrue(res_resume["success"])
        self.assertEqual(self.coordinator.state, TypingState.LISTENING)

        res_stop = self.coordinator.stop_typing()
        self.assertTrue(res_stop["success"])
        self.assertEqual(self.coordinator.state, TypingState.INACTIVE)

    def test_spoken_undo_correction(self):
        self.coordinator.start_typing(mode="draft")
        self.coordinator.process_dictation("This is an error")
        self.assertIn("error", self.coordinator.get_draft_text())

        undo_res = self.coordinator.process_correction("undo that")
        self.assertTrue(undo_res["success"])
        self.assertEqual(self.coordinator.get_draft_text(), "")

    def test_clear_draft(self):
        self.coordinator.start_typing(mode="draft")
        self.coordinator.process_dictation("Draft sentence one")
        self.coordinator.process_dictation("Draft sentence two")
        self.assertTrue(len(self.coordinator.get_draft_text()) > 0)

        clear_res = self.coordinator.process_correction("clear draft")
        self.assertTrue(clear_res["success"])
        self.assertEqual(self.coordinator.get_draft_text(), "")


if __name__ == "__main__":
    unittest.main()
