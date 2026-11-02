"""
Unit and integration tests for Panel Visibility Controller:
- Show a hidden panel
- Restore a minimized panel
- Repeated show/hide requests (idempotence)
- Voice, tray, hotkey, and IPC entry points
- Screen geometry bounds check and recovery
- Thread-safe signal dispatch
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt, QRect, QObject
from PyQt6.QtWidgets import QApplication, QWidget

# Ensure QApplication instance exists for PyQt6 testing
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from ui.panel_controller import PanelVisibilityController


class DummyWindow(QWidget):
    """Minimal test window simulating MainWindow visibility methods and state."""
    def __init__(self):
        super().__init__()
        self.resize(1180, 780)
        self._minimized = False

    def isMinimized(self):
        return self._minimized or bool(self.windowState() & Qt.WindowState.WindowMinimized)

    def showMinimized(self):
        self._minimized = True
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMinimized)

    def showNormal(self):
        self._minimized = False
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        super().showNormal()


class TestPanelRecovery(unittest.TestCase):
    """Validates the reliability, idempotency, and geometry handling of PanelVisibilityController."""

    def setUp(self):
        self.window = DummyWindow()
        self.exit_mock = MagicMock()
        self.controller = PanelVisibilityController(window=self.window, on_exit=self.exit_mock)

    def tearDown(self):
        self.window.close()

    def test_show_hidden_panel(self):
        """Hidden panel should become visible and normal."""
        self.window.hide()
        self.assertFalse(self.window.isVisible())

        self.controller.show_panel()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.isMinimized())

    def test_restore_minimized_panel(self):
        """Minimized panel should restore to normal window state and become visible."""
        self.window.showMinimized()
        self.assertTrue(self.window.isMinimized())

        self.controller.show_panel()
        self.assertFalse(self.window.isMinimized())
        self.assertTrue(self.window.isVisible())

    def test_repeated_show_requests_are_idempotent(self):
        """Calling show_panel multiple times consecutively should not fail or corrupt state."""
        self.controller.show_panel()
        self.assertTrue(self.window.isVisible())

        self.controller.show_panel()
        self.assertTrue(self.window.isVisible())

        self.controller.show_panel()
        self.assertTrue(self.window.isVisible())

    def test_hide_and_repeated_hide_are_idempotent(self):
        """Calling hide_panel multiple times consecutively should be an idempotent no-op."""
        self.controller.show_panel()
        self.assertTrue(self.window.isVisible())

        self.controller.hide_panel()
        self.assertFalse(self.window.isVisible())

        self.controller.hide_panel()
        self.assertFalse(self.window.isVisible())

    def test_toggle_panel(self):
        """Toggle should alternately hide visible panel and show hidden panel."""
        self.window.hide()
        self.assertFalse(self.window.isVisible())

        self.controller.toggle_panel()
        self.assertTrue(self.window.isVisible())

        self.controller.toggle_panel()
        self.assertFalse(self.window.isVisible())

    def test_offscreen_geometry_recovery(self):
        """Window placed at invalid off-screen coordinates should be recentered on primary screen."""
        # Move window far off-screen
        self.window.setGeometry(-5000, -5000, 1180, 780)
        self.assertEqual(self.window.x(), -5000)

        self.controller.show_panel()
        # Should now be on-screen with positive coordinates
        self.assertGreaterEqual(self.window.x(), 0)
        self.assertGreaterEqual(self.window.y(), 0)

    def test_handle_action_queued(self):
        """Various string actions should route to correct visibility operations."""
        self.window.hide()
        self.controller._handle_action_queued("show_panel")
        self.assertTrue(self.window.isVisible())

        self.controller._handle_action_queued("hide_panel")
        self.assertFalse(self.window.isVisible())

        self.controller._handle_action_queued("open")
        self.assertTrue(self.window.isVisible())

        self.controller._handle_action_queued("minimize")
        self.assertFalse(self.window.isVisible())

        self.controller._handle_action_queued("toggle")
        self.assertTrue(self.window.isVisible())

        self.controller._handle_action_queued("exit_assistant")
        self.exit_mock.assert_called_once()

    def test_thread_safe_request_action(self):
        """request_action should emit signal safely and process via Qt event loop."""
        self.window.hide()
        self.controller.request_action("show")
        app.processEvents()
        self.assertTrue(self.window.isVisible())


if __name__ == "__main__":
    unittest.main()
