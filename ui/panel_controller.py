"""
Unified Panel Visibility Controller for Santra.
Thread-safe, idempotent, and resilient controller for managing the PyQt6 HUD
panel lifecycle across voice commands, system tray actions, global shortcuts,
and single-instance IPC activations on Windows 11.
"""

import sys
import logging
from typing import Optional, Callable
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QGuiApplication

logger = logging.getLogger("Jarvis.PanelController")


class PanelVisibilityController(QObject):
    """Coordinates HUD visibility and window management on the Qt main GUI thread.
    
    Accepts visibility commands from background threads (voice runtime, hotkey thread,
    single-instance IPC server) via Qt signal queueing, guaranteeing safe GUI access.
    """

    sig_request_action = pyqtSignal(str)

    def __init__(self, window: Optional[QObject] = None, on_exit: Optional[Callable[[], None]] = None):
        super().__init__()
        self.window = window
        self.on_exit_cb = on_exit

        # Connect the action request signal to our main-thread slot
        self.sig_request_action.connect(self._handle_action_queued, Qt.ConnectionType.QueuedConnection)

    def set_window(self, window: QObject):
        """Sets or updates the managed window instance."""
        self.window = window

    def request_action(self, action: str):
        """Thread-safe entry point. Can be invoked from any thread safely."""
        self.sig_request_action.emit(action)

    @pyqtSlot(str)
    def _handle_action_queued(self, action: str):
        """Executes window lifecycle changes strictly on the Qt main GUI thread."""
        act = (action or "").lower().strip()
        logger.debug(f"[PANEL_CONTROLLER] Handling visibility action: '{act}'")

        if act in ("show", "show_panel", "restore", "restore_hud", "open", "open_panel", "show_santra", "open_santra"):
            self.show_panel()
        elif act in ("hide", "hide_panel", "minimize", "send_to_tray"):
            self.hide_panel()
        elif act in ("toggle", "toggle_panel"):
            self.toggle_panel()
        elif act in ("exit", "exit_assistant", "shutdown", "quit"):
            if self.on_exit_cb:
                self.on_exit_cb()
        else:
            logger.warning(f"[PANEL_CONTROLLER] Unrecognized visibility action: '{action}'")

    def show_panel(self):
        """Restores and displays the existing HUD panel idempotently.
        - Restores minimized state if minimized.
        - Rescues window if positioned off-screen.
        - Raises and activates window in Windows 11 foreground hierarchy.
        """
        if not self.window:
            logger.error("[PANEL_CONTROLLER] Cannot show panel: MainWindow reference is None.")
            return

        try:
            # 1. Verify and repair screen geometry if moved off-screen
            self._ensure_onscreen_geometry()

            # 2. Clear Minimized state explicitly (Win32 + Qt quirk workaround)
            state = self.window.windowState()
            if state & Qt.WindowState.WindowMinimized:
                self.window.setWindowState((state & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)

            self.window.showNormal()
            self.window.show()

            # 3. Windows 11 Foreground & Z-Order assert
            if sys.platform == "win32":
                try:
                    import ctypes
                    hwnd = int(self.window.winId())
                    # SW_RESTORE = 9, SW_SHOW = 5
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception as win_err:
                    logger.debug(f"[PANEL_CONTROLLER] Win32 ShowWindow/SetForegroundWindow: {win_err}")

            # 4. Qt Desktop Window Manager (DWM) bring-to-front pulse
            self.window.setWindowFlags(self.window.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.window.show()
            self.window.setWindowFlags(self.window.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.window.show()

            self.window.raise_()
            self.window.activateWindow()
            logger.info("[PANEL_CONTROLLER] Santra HUD panel successfully restored and activated.")
        except Exception as e:
            logger.error(f"[PANEL_CONTROLLER] Failed to show panel: {e}", exc_info=True)

    def hide_panel(self):
        """Hides the panel to tray without destroying state or terminating the assistant."""
        if not self.window:
            return

        try:
            if self.window.isVisible():
                self.window.hide()
                logger.info("[PANEL_CONTROLLER] Santra HUD panel hidden to tray.")
        except Exception as e:
            logger.error(f"[PANEL_CONTROLLER] Failed to hide panel: {e}", exc_info=True)

    def toggle_panel(self):
        """Toggles between visible/active and hidden states idempotently."""
        if not self.window:
            return

        if self.window.isVisible() and not self.window.isMinimized():
            self.hide_panel()
        else:
            self.show_panel()

    def _ensure_onscreen_geometry(self):
        """Detects if window coordinates are off-screen and recenters if needed."""
        try:
            screens = QGuiApplication.screens()
            if not screens:
                return

            geom = self.window.frameGeometry()
            is_visible_on_any = any(s.availableGeometry().intersects(geom) for s in screens)

            if not is_visible_on_any or geom.isEmpty() or geom.width() < 100 or geom.height() < 100:
                primary = QGuiApplication.primaryScreen()
                if primary:
                    avail = primary.availableGeometry()
                    w = max(self.window.width(), 960)
                    h = max(self.window.height(), 620)
                    x = avail.x() + max(0, (avail.width() - w) // 2)
                    y = avail.y() + max(0, (avail.height() - h) // 2)
                    self.window.setGeometry(x, y, w, h)
                    logger.info(f"[PANEL_CONTROLLER] Repositioned off-screen panel onto primary screen at ({x}, {y}, {w}, {h}).")
        except Exception as ge:
            logger.debug(f"[PANEL_CONTROLLER] Geometry check exception: {ge}")
