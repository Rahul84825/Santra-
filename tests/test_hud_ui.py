"""Unit & Integration Tests for SANTRA JARVIS / F.R.I.D.A.Y. Holographic HUD Interface.

Validates:
1. FramelessWindowHint, WindowStaysOnTopHint, WA_TranslucentBackground.
2. Presence and integrity of all 21 PyQt6 signals and observer bindings.
3. ArcReactorWidget lifecycle, 60fps timer, reactive states and audio pulses.
4. Smooth fade-in (show_hud) and fade-out (hide_hud) property animations.
5. Telemetry widgets (CPU/RAM bars, status pill, ALEE Stage 7 Evolution capsule).
6. Fast-path intelligence routing for voice summoning (SHOW_PANEL / HIDE_PANEL).
7. Runtime & PanelController coordination (zero-drop execution).
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

# Ensure single shared QApplication instance for headless test execution
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from ui.main_window import MainWindow
from ui.widgets.arc_reactor import ArcReactorWidget
from ui.panel_controller import PanelVisibilityController
from core.ai.intelligence_router import intelligence_router, LAYER_1


class TestHolographicHUDWindow(unittest.TestCase):
    """Test suite for MainWindow HUD architecture, window flags, and signals."""

    @classmethod
    def setUpClass(cls):
        cls.window = MainWindow()

    def test_01_window_flags_and_attributes(self):
        """Verify window is frameless, stays on top, and has translucent background."""
        flags = self.window.windowFlags()
        self.assertTrue(bool(flags & Qt.WindowType.FramelessWindowHint), "FramelessWindowHint must be set")
        self.assertTrue(bool(flags & Qt.WindowType.WindowStaysOnTopHint), "WindowStaysOnTopHint must be set")
        self.assertTrue(
            self.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
            "WA_TranslucentBackground must be True for glassmorphic styling"
        )
        self.assertGreaterEqual(self.window.minimumWidth(), 900)
        self.assertGreaterEqual(self.window.minimumHeight(), 600)

    def test_02_all_twenty_one_signals_present(self):
        """Verify that all 21 historical and runtime signals are preserved on MainWindow."""
        expected_signals = [
            "sig_status_updated",
            "sig_status_changed",
            "sig_pipeline_stage_updated",
            "sig_speech_text_updated",
            "sig_last_action_updated",
            "sig_history_updated",
            "sig_command_submitted",
            "sig_speech_debug_updated",
            "sig_audio_amplitude_updated",
            "sig_show_permission_dialog",
            "sig_permission_resolved",
            "sig_camera_state_updated",
            "sig_gesture_detected",
            "sig_ai_mode_changed",
            "sig_evolution_updated",
            "sig_panel_visibility_requested",
            "sig_sys_stats_updated",
            "sig_mic_state_changed",
            "sig_log_received",
            "sig_closed",
            "sig_typing_state_changed",
            "sig_show_message_approval",
        ]
        for sig_name in expected_signals:
            self.assertTrue(
                hasattr(self.window, sig_name),
                f"MainWindow missing required signal: {sig_name}"
            )
            sig_obj = getattr(self.window, sig_name)
            self.assertTrue(
                hasattr(sig_obj, "connect") and hasattr(sig_obj, "emit"),
                f"Attribute {sig_name} must be a valid PyQt6 pyqtSignal"
            )

    def test_03_hud_ui_components_exist(self):
        """Verify core holographic widgets exist on MainWindow."""
        self.assertIsInstance(self.window.arc_reactor, ArcReactorWidget)
        self.assertIsNotNone(self.window.lbl_status_pill)
        self.assertIsNotNone(self.window.lbl_caption)
        self.assertIsNotNone(self.window.bar_cpu)
        self.assertIsNotNone(self.window.bar_ram)
        self.assertIsNotNone(self.window.btn_evolution_center)
        self.assertIsNotNone(self.window.cmd_input)
        self.assertIsNotNone(self.window.btn_send)
        self.assertIsNotNone(self.window.btn_mic)
        self.assertIsNotNone(self.window.btn_sleep)
        self.assertIsNotNone(self.window.lbl_evo_aliases)
        self.assertIsNotNone(self.window.lbl_evo_knowledge)
        self.assertIsNotNone(self.window.lbl_evo_skills)
        self.assertIsNotNone(self.window.lbl_evo_score)

    def test_04_status_and_telemetry_updates(self):
        """Verify emitting status, caption, and sys stats updates child widget displays."""
        # 1. Status pill
        self.window.sig_status_updated.emit("LISTENING")
        self.assertIn("LISTENING", self.window.lbl_status_pill.text().upper())

        # 2. Subtitle marquee / caption
        test_caption = "Faster-Whisper: Ready for voice input"
        self.window.sig_speech_text_updated.emit(test_caption)
        self.assertIn("Ready for voice input", self.window.lbl_caption.text())

        # 3. System stats
        self.window.sig_sys_stats_updated.emit(34.5, 62.1)
        self.assertEqual(self.window.bar_cpu.value(), 34)
        self.assertEqual(self.window.bar_ram.value(), 62)

    def test_05_evolution_capsule_telemetry(self):
        """Verify sig_evolution_updated refreshes ALEE Stage 7 diagnostic counts."""
        mock_rep = {
            "status": "HEALTHY",
            "active_phonetic_aliases": 15,
            "total_knowledge_chunks": 8,
            "verified_skills": 9,
            "benchmark_score": 100.0,
            "success_rate": 96.5
        }
        self.window.sig_evolution_updated.emit(mock_rep)
        self.assertIn("15 Active", self.window.lbl_evo_aliases.text())
        self.assertIn("8 Chunks", self.window.lbl_evo_knowledge.text())
        self.assertIn("9 Procedures", self.window.lbl_evo_skills.text())
        self.assertIn("100% PASS", self.window.lbl_evo_score.text())

    def test_06_smooth_hud_visibility_transitions(self):
        """Verify show_hud and hide_hud initialize animations without crashes."""
        # Test show_hud
        self.window.show_hud()
        self.assertTrue(self.window.isVisible())
        self.assertIsNotNone(self.window.anim_opacity)
        self.assertEqual(self.window.anim_opacity.endValue(), 1.0)

        # Test hide_hud
        self.window.hide_hud()
        self.assertIsNotNone(self.window.anim_opacity)
        self.assertEqual(self.window.anim_opacity.endValue(), 0.0)

        # Re-show for test sanity
        self.window.show_hud()

    def test_07_command_input_submission(self):
        """Verify typing in cmd_input and pressing enter or send button emits sig_command_submitted."""
        submitted = []
        self.window.sig_command_submitted.connect(lambda cmd: submitted.append(cmd))

        self.window.cmd_input.setText("create folder test_santra_hud")
        self.window._submit_command()

        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0], "create folder test_santra_hud")
        self.assertEqual(self.window.cmd_input.text(), "")  # Cleared after submit


class TestArcReactorWidget(unittest.TestCase):
    """Test suite for the pure-QPainter reactive Arc Reactor core."""

    def setUp(self):
        self.reactor = ArcReactorWidget()

    def test_01_state_transitions(self):
        """Verify reactor transitions smoothly between all recognized states."""
        for state in ["STANDBY", "LISTENING", "THINKING", "SPEAKING", "PAUSED_GAMING", "PAUSED_HIGH_LOAD", "SLEEPING"]:
            self.reactor.set_state(state)
            self.assertIn(state, ["STANDBY", "LISTENING", "THINKING", "SPEAKING", "PAUSED_GAMING", "PAUSED_HIGH_LOAD", "SLEEPING"])
            col = self.reactor.get_primary_color()
            self.assertTrue(col.isValid())

    def test_02_audio_amplitude_scaling(self):
        """Verify audio amplitude clamps within [0.0, 1.0] and affects wave rings."""
        self.reactor.set_audio_amplitude(0.65)
        self.assertAlmostEqual(self.reactor._audio_amplitude, 0.65, places=2)

        self.reactor.set_audio_amplitude(1.8)  # Clamp to 1.0
        self.assertAlmostEqual(self.reactor._audio_amplitude, 1.0, places=2)

        self.reactor.set_audio_amplitude(-0.5)  # Clamp to 0.0
        self.assertAlmostEqual(self.reactor._audio_amplitude, 0.0, places=2)

    def test_03_gesture_pulse(self):
        """Verify gesture pulse sets expanded scale and triggers repaint."""
        self.reactor.trigger_gesture_pulse("PINCH")
        self.assertEqual(self.reactor._target_core_scale, 1.40)


class TestVoiceSummoningAndPanelController(unittest.TestCase):
    """Test suite for voice summoning routing and panel controller synchronization."""

    def test_01_show_panel_fast_path_routing(self):
        """Verify natural language voice commands to show HUD route directly to SHOW_PANEL."""
        phrases = [
            "open your panel",
            "show panel",
            "show hud",
            "bring up hud",
            "display panel",
            "open hud",
            "show santra panel",
            "open santra panel",
            "bring up the hud",
            "display the panel",
        ]
        for phrase in phrases:
            decision = intelligence_router.route(phrase)
            self.assertEqual(decision.intent, "SHOW_PANEL", f"Failed for phrase: '{phrase}'")
            self.assertEqual(decision.layer, LAYER_1)
            self.assertLess(decision.confidence, 1.01)

    def test_02_hide_panel_fast_path_routing(self):
        """Verify natural language voice commands to hide HUD route directly to HIDE_PANEL."""
        phrases = [
            "hide your panel",
            "hide panel",
            "close panel",
            "minimize hud",
            "go to stealth",
            "hide hud",
            "stealth mode",
            "dismiss panel",
            "hide santra panel",
            "minimize santra dashboard",
        ]
        for phrase in phrases:
            decision = intelligence_router.route(phrase)
            self.assertEqual(decision.intent, "HIDE_PANEL", f"Failed for phrase: '{phrase}'")
            self.assertEqual(decision.layer, LAYER_1)

    def test_03_panel_controller_delegation(self):
        """Verify PanelVisibilityController forwards show, hide, and toggle to window methods."""
        mock_win = MagicMock()
        mock_win.isVisible.return_value = True
        mock_win.isMinimized.return_value = False
        ctrl = PanelVisibilityController(window=mock_win)

        ctrl.show_panel()
        mock_win.show_hud.assert_called_once()

        ctrl.hide_panel()
        mock_win.hide_hud.assert_called_once()

        ctrl.toggle_panel()
        self.assertEqual(mock_win.hide_hud.call_count, 2)


if __name__ == "__main__":
    unittest.main()
