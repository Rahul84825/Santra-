"""Comprehensive Unit & Regression Tests for Round 3 Live Fixes.

Verifies:
1. Bug 1: Non-blocking detached subprocess execution for OPEN_IN_IDE via subprocess.Popen without hanging.
2. Bug 2: Persistent SQLite working_memory schema migration v5 and cross-instance recovery.
3. Bug 3: Spoken programming punctuation normalization ("console.log, bracket,") and safe typing focus with HUD hiding.
"""

import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.command_normalizer import CommandNormalizer, normalize_spoken_syntax
from core.evolution.storage import EvolutionStorage
from modules.system import filesystem_crud, gui_interactor


class TestBug1NonBlockingIDE(unittest.TestCase):
    """Test suite for Bug 1: Non-blocking detached process launch for IDE commands."""

    def test_01_open_in_ide_popen_non_blocking(self):
        """Verifies that OPEN_IN_IDE launches using subprocess.Popen with detached flags without blocking."""
        from core.jarvis_runtime import JarvisRuntime

        with patch("core.jarvis_runtime.TTSManager"), \
             patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory"):
            runtime = JarvisRuntime()

        temp_folder = Path(tempfile.gettempdir()) / "test_ide_project"
        temp_folder.mkdir(parents=True, exist_ok=True)
        runtime._last_filesystem_target = temp_folder

        with patch("shutil.which", return_value="C:\\Programs\\VSCode\\code.cmd"), \
             patch("subprocess.Popen") as mock_popen:

            intent_node = {
                "intent": "open_in_ide",
                "ide": "vscode",
                "target": "it",
                "pronoun": True
            }

            res = runtime._execute_intent(intent_node, speak=False, utterance_id="test-uid-1")

            self.assertTrue(res["success"])
            self.assertIn("Opened test_ide_project in VS Code", res["message"])
            self.assertEqual(runtime.current_status, "STANDBY")

            # Verify subprocess.Popen called with non-blocking detached flags
            mock_popen.assert_called_once()
            call_args, call_kwargs = mock_popen.call_args
            self.assertEqual(call_args[0], ["C:\\Programs\\VSCode\\code.cmd", str(temp_folder.resolve())])
            expected_flags = 0x00000008 | 0x00000200
            self.assertEqual(call_kwargs.get("creationflags"), expected_flags)
            self.assertTrue(call_kwargs.get("close_fds"))

    def test_02_open_in_ide_missing_binary_no_hang(self):
        """Verifies that missing IDE binary returns graceful error immediately and resets status to STANDBY."""
        from core.jarvis_runtime import JarvisRuntime

        with patch("core.jarvis_runtime.TTSManager"), \
             patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory"):
            runtime = JarvisRuntime()

        temp_folder = Path(tempfile.gettempdir()) / "test_missing_ide_project"
        temp_folder.mkdir(parents=True, exist_ok=True)
        runtime._last_filesystem_target = temp_folder

        with patch("shutil.which", return_value=None):

            intent_node = {
                "intent": "open_in_ide",
                "ide": "custom_editor",
                "target": "it",
                "pronoun": True
            }

            res = runtime._execute_intent(intent_node, speak=False, utterance_id="test-uid-2")

            self.assertFalse(res["success"])
            self.assertIn("Could not locate the executable", res["message"])
            self.assertEqual(runtime.current_status, "STANDBY")


class TestBug2WorkingMemoryPersistence(unittest.TestCase):
    """Test suite for Bug 2: Persistent SQLite working_memory schema migration v5 and cross-instance recovery."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_evolution.db")
        self.storage = None

    def tearDown(self):
        if self.storage:
            try:
                self.storage.close()
            except Exception:
                pass
            self.storage = None
        self.temp_dir.cleanup()

    def test_01_working_memory_schema_and_crud(self):
        """Verifies working_memory table creation and set/get/clear operations."""
        self.storage = EvolutionStorage(db_path=self.db_path)

        ok = self.storage.set_entity_memory(
            key="last_filesystem_target",
            value="C:\\Users\\Test\\Desktop\\ProjectAlpha",
            metadata={"type": "folder", "name": "ProjectAlpha"}
        )
        self.assertTrue(ok)

        rec = self.storage.get_entity_memory("last_filesystem_target")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["key"], "last_filesystem_target")
        self.assertEqual(rec["value"], "C:\\Users\\Test\\Desktop\\ProjectAlpha")
        self.assertEqual(rec["metadata"].get("name"), "ProjectAlpha")
        self.assertIsInstance(rec["updated_at"], float)

        # Clear key
        cleared = self.storage.clear_entity_memory("last_filesystem_target")
        self.assertTrue(cleared)
        self.assertIsNone(self.storage.get_entity_memory("last_filesystem_target"))

        self.storage.close()
        self.storage = None

    def test_02_working_memory_cross_instance_persistence(self):
        """Verifies persistent entity retrieval across distinct storage instances."""
        storage1 = EvolutionStorage(db_path=self.db_path)
        storage1.set_entity_memory(
            key="last_filesystem_target",
            value="C:\\Shared\\PersistentWorkspace"
        )
        storage1.close()

        # Second fresh instance opening the same SQLite file
        storage2 = EvolutionStorage(db_path=self.db_path)
        rec = storage2.get_entity_memory("last_filesystem_target")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["value"], "C:\\Shared\\PersistentWorkspace")
        storage2.close()

    def test_03_filesystem_crud_persists_and_queries_working_memory(self):
        """Verifies filesystem_crud set_last_filesystem_target persists into SQLite and recovers on in-memory loss."""
        self.storage = EvolutionStorage(db_path=self.db_path)
        sample_folder = Path(self.temp_dir.name) / "PersistentFolder"
        sample_folder.mkdir(parents=True, exist_ok=True)

        try:
            with patch("core.evolution.storage.evolution_storage", self.storage):
                # Set target
                filesystem_crud.set_last_filesystem_target(sample_folder)

                # Invalidate in-memory reference to simulate app reload / fresh session
                filesystem_crud._LAST_FILESYSTEM_TARGET = None

                # Retrieve target - must query SQLite working_memory
                recovered = filesystem_crud.get_last_filesystem_target()
                self.assertEqual(recovered, sample_folder.resolve())
        finally:
            self.storage.close()
            self.storage = None


class TestBug3AcousticPunctuationAndTyping(unittest.TestCase):
    """Test suite for Bug 3: Spoken programming punctuation normalization and safe typing focus."""

    def test_01_normalize_spoken_syntax_rules(self):
        """Verifies spoken punctuation tokens are normalized to canonical code characters."""
        cases = [
            ("console.log, bracket,", "console.log("),
            ("open bracket", "("),
            ("close bracket", ")"),
            ("dot", "."),
            ("comma", ","),
            ("semicolon", ";"),
            ("quotes", "'"),
            ("quote", "'"),
            ("console dot log bracket quote hello quote close bracket semicolon", "console.log('hello');"),
            ("print open bracket quote status ok quote close bracket", "print('status ok')"),
        ]
        for spoken, expected in cases:
            res = CommandNormalizer.normalize_spoken_syntax(spoken)
            self.assertEqual(res, expected, f"Failed syntax normalization for: '{spoken}'")

    def test_02_typing_normalizes_spoken_syntax(self):
        """Verifies type_into_input_box normalizes spoken syntax before injecting text."""
        with patch("modules.system.gui_interactor.pyperclip.copy") as mock_clip_copy, \
             patch("modules.system.gui_interactor.pyperclip.paste", return_value=""), \
             patch("modules.system.gui_interactor.pyautogui.hotkey"):

            res = gui_interactor.type_into_input_box(
                text="console.log, bracket,",
                auto_locate=False,
                submit=False
            )

            self.assertTrue(res["success"])
            self.assertEqual(res["text"], "console.log(")
            mock_clip_copy.assert_called_with("console.log(")

    def test_03_typing_hides_and_restores_hud(self):
        """Verifies type_into_input_box temporarily hides SANTRA HUD for 150ms and restores it."""
        mock_runtime = MagicMock()
        mock_runtime.panel_visibility_cb = MagicMock()

        mock_win = MagicMock()
        mock_win.Name = "Visual Studio Code"
        mock_win.NativeWindowHandle = 12345

        with patch("modules.system.gui_interactor.get_effective_foreground_window", return_value=mock_win), \
             patch("modules.system.gui_interactor.focus_window_by_hwnd", return_value=True), \
             patch("modules.system.gui_interactor.find_active_input_box", return_value=(True, {"center_x": 100, "center_y": 100}, "Visual Studio Code")), \
             patch("modules.system.gui_interactor.pyperclip.copy"), \
             patch("modules.system.gui_interactor.pyperclip.paste", return_value=""), \
             patch("modules.system.gui_interactor.pyautogui.click"), \
             patch("modules.system.gui_interactor.pyautogui.hotkey"):

            res = gui_interactor.type_into_input_box(
                text="hello world",
                auto_locate=True,
                submit=False,
                runtime=mock_runtime
            )

            self.assertTrue(res["success"])
            mock_runtime.panel_visibility_cb.assert_any_call("hide")
            mock_runtime.panel_visibility_cb.assert_any_call("show")


if __name__ == "__main__":
    unittest.main()
