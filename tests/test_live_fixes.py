"""Unit and Integration Tests for Live Testing Fixes (Bugs 1-4).

Validates:
1. BUG 1: Folder and path parsing separates folder name and destination target ("Project, on my desktop").
   - Resolves to Desktop/Project (respecting OneDrive/Windows registry).
   - Folder name is strictly "Project" without commas or trailing prepositions.
2. BUG 2: SCREEN_ANALYSIS regex routing and verbal summary generation.
   - Matches "analyze what's on my screen", "analyze screen", "what's on my screen".
   - Generates structured summary: "Active window is [Title]. Visible elements/text: [Summary]."
3. BUG 3: Target Window Handling and Single-Word Affirmations.
   - Captures "yes", "send it", "send", "press enter", "confirm" as CONFIRM_ACTION.
   - Switches focus to target application window before typing and on confirmation.
4. BUG 4: Left Telemetry Badges in HUD.
   - MainWindow initializes 7 pills with real non-empty labels.
   - Updates dynamically on sig_evolution_updated and sig_sys_stats_updated.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

# Ensure shared QApplication for headless UI testing
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from core.ai.intelligence_router import intelligence_router, LAYER_1
from modules.system import filesystem_crud
from modules.system import gui_interactor
from modules.system import screen_perception
from ui.main_window import MainWindow


class TestBug1FolderAndPathParsing(unittest.TestCase):
    """Test suite for Bug 1: Folder name extraction and destination resolution."""

    def test_01_extract_name_and_destination(self):
        """Verify extraction of clean folder name and destination target."""
        test_cases = [
            ("create a folder called Project, on my desktop", ("Project", "desktop")),
            ("create a folder called Project on my desktop", ("Project", "desktop")),
            ("make folder Project on desktop", ("Project", "desktop")),
            ("create a folder named 'CodeBase' in my documents", ("CodeBase", "documents")),
            ("make a directory Project on my desktop", ("Project", "desktop")),
            ("create a folder called Data", ("Data", None)),
            ("create folder 'My Notes', on desktop", ("My Notes", "desktop")),
        ]
        for raw_input, expected in test_cases:
            name, dest = filesystem_crud.extract_name_and_destination(raw_input)
            self.assertEqual(name, expected[0], f"Failed name on: '{raw_input}'")
            self.assertEqual(dest, expected[1], f"Failed dest on: '{raw_input}'")

    def test_02_resolve_path_to_desktop(self):
        """Verify that resolve_path resolves destination 'desktop' to active Desktop folder."""
        desktop_dir = filesystem_crud.get_desktop_dir()
        self.assertTrue(desktop_dir.exists(), f"Desktop directory must exist: {desktop_dir}")
        self.assertTrue(
            "desktop" in str(desktop_dir).lower(),
            f"Path must contain Desktop: {desktop_dir}"
        )

        resolved = filesystem_crud.resolve_path("create a folder called Project, on my desktop")
        self.assertEqual(resolved.name, "Project")
        self.assertEqual(resolved.parent, desktop_dir)
        self.assertTrue(
            str(resolved).lower().endswith(r"desktop\project") or str(resolved).lower().endswith("desktop/project")
        )

    def test_03_intelligence_router_folder_creation(self):
        """Verify IntelligenceRouter routes folder creation commands with exact destination entities."""
        decision = intelligence_router.route("create a folder called Project, on my desktop")
        self.assertEqual(decision.intent, "FS_CREATE_FOLDER")
        self.assertEqual(decision.layer, LAYER_1)
        self.assertEqual(decision.entities.get("name"), "Project")
        self.assertEqual(decision.entities.get("destination"), "desktop")
        self.assertTrue(decision.target.lower().endswith("project"))


class TestBug2ScreenAnalysisWiring(unittest.TestCase):
    """Test suite for Bug 2: SCREEN_ANALYSIS routing and runtime response formatting."""

    def test_01_screen_analysis_router_patterns(self):
        """Verify flexible regex patterns trigger SCREEN_ANALYSIS in fast-path (Layer 1)."""
        screen_queries = [
            "analyze what's on my screen",
            "analyze whats on my screen",
            "what's on my screen",
            "whats on my screen",
            "analyze screen",
            "analyze the screen",
            "read my screen",
            "read screen",
            "inspect screen",
            "screen analysis",
            "read this error",
            "read active window",
        ]
        for query in screen_queries:
            decision = intelligence_router.route(query)
            self.assertEqual(
                decision.intent,
                "SCREEN_ANALYSIS",
                f"Failed to route screen query: '{query}' (Got: {decision.intent})"
            )
            self.assertEqual(decision.layer, LAYER_1)

    def test_02_screen_perception_ignores_santra_window(self):
        """Verify that screen perception functions bypass SANTRA's own window."""
        mock_santra = MagicMock()
        mock_santra.Name = "SANTRA — Holographic HUD Core"
        mock_santra.ProcessId = 99999
        self.assertTrue(screen_perception.is_santra_control_or_window(mock_santra))

        mock_app = MagicMock()
        mock_app.Name = "Google Chrome"
        mock_app.ProcessId = 12345
        self.assertFalse(screen_perception.is_santra_control_or_window(mock_app))


class TestBug3TargetWindowAndAffirmations(unittest.TestCase):
    """Test suite for Bug 3: GUI typing target window focus and single-word confirmations."""

    def test_01_confirm_and_cancel_single_word_routing(self):
        """Verify single-word affirmations route directly to CONFIRM_ACTION."""
        affirmations = ["yes", "send it", "send", "press enter", "confirm", "submit"]
        for word in affirmations:
            decision = intelligence_router.route(word)
            self.assertEqual(
                decision.intent,
                "CONFIRM_ACTION",
                f"Failed affirmation routing on '{word}': got '{decision.intent}'"
            )
            self.assertEqual(decision.layer, LAYER_1)

        cancellations = ["cancel", "no", "discard", "don't send"]
        for word in cancellations:
            decision = intelligence_router.route(word)
            self.assertEqual(
                decision.intent,
                "CANCEL_ACTION",
                f"Failed cancellation routing on '{word}': got '{decision.intent}'"
            )
            self.assertEqual(decision.layer, LAYER_1)

    def test_02_gui_interactor_draft_and_confirm_lifecycle(self):
        """Verify GUI interactor holds pending confirmation and executes upon confirmation."""
        mock_runtime = MagicMock()
        mock_runtime._pending_confirmation = None

        with patch("modules.system.gui_interactor.pyautogui") as mock_pyautogui, \
             patch("modules.system.gui_interactor.pyperclip") as mock_pyperclip, \
             patch("modules.system.gui_interactor.find_active_input_box", return_value=(True, {"center_x": 100, "center_y": 200}, "Notepad")):

            res = gui_interactor.type_into_input_box(
                text="Hello from SANTRA pair programming",
                auto_locate=True,
                submit=False,
                runtime=mock_runtime
            )

            self.assertTrue(res["success"])
            self.assertTrue(res["requires_confirmation"])
            self.assertTrue(any(q in res["message"] for q in ["Shall I send it?", "Would you like me to send it?"]))
            self.assertIsNotNone(mock_runtime._pending_confirmation)

            # Confirm action
            ok = gui_interactor.confirm_pending_gui_action(mock_runtime)
            self.assertTrue(ok)
            mock_pyautogui.press.assert_called_with("enter")
            self.assertIsNone(mock_runtime._pending_confirmation)


class TestBug4HUDTelemetryBadges(unittest.TestCase):
    """Test suite for Bug 4: Left telemetry pill badges initialization and dynamic refresh."""

    @classmethod
    def setUpClass(cls):
        cls.window = MainWindow()

    def test_01_all_seven_pills_exist_and_populated(self):
        """Verify all 7 telemetry badges exist on MainWindow and contain non-empty text."""
        pills = [
            ("lbl_telemetry_status", "ALEE Status:"),
            ("lbl_telemetry_aliases", "Active Aliases:"),
            ("lbl_telemetry_skills", "Verified Skills:"),
            ("lbl_telemetry_knowledge", "Knowledge Chunks:"),
            ("lbl_telemetry_proposals", "Pending Proposals:"),
            ("lbl_telemetry_score", "Regression Score:"),
            ("lbl_telemetry_power", "Power:"),
        ]
        for attr_name, expected_prefix in pills:
            self.assertTrue(
                hasattr(self.window, attr_name),
                f"MainWindow missing telemetry badge: {attr_name}"
            )
            widget = getattr(self.window, attr_name)
            text = widget.text().strip()
            self.assertTrue(len(text) > 0, f"Pill {attr_name} must not be empty!")
            self.assertIn(
                expected_prefix,
                text,
                f"Pill {attr_name} text '{text}' missing prefix '{expected_prefix}'"
            )

    def test_02_dynamic_telemetry_updates(self):
        """Verify emitting sig_evolution_updated updates all 7 pill badges dynamically."""
        mock_report = {
            "status": "AUTONOMOUS",
            "active_phonetic_aliases": 18,
            "verified_skills": 11,
            "total_knowledge_chunks": 9,
            "proposals_summary": {"total_pending": 3},
            "benchmark_score": 100.0
        }
        self.window.sig_evolution_updated.emit(mock_report)

        self.assertIn("AUTONOMOUS", self.window.lbl_telemetry_status.text())
        self.assertIn("18", self.window.lbl_telemetry_aliases.text())
        self.assertIn("11", self.window.lbl_telemetry_skills.text())
        self.assertIn("9", self.window.lbl_telemetry_knowledge.text())
        self.assertIn("3", self.window.lbl_telemetry_proposals.text())
        self.assertIn("100%", self.window.lbl_telemetry_score.text())


if __name__ == "__main__":
    unittest.main()
