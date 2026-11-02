"""Focus Awareness, Active Control Detection, and Password Security Guard."""

import sys
import time
import logging
from typing import Optional, Tuple, Dict, Any
from core.typing.models import FocusInfo

logger = logging.getLogger("Jarvis.FocusDetector")


class FocusDetector:
    """Detects active foreground application, focused text control, and enforces password safety."""

    def __init__(self):
        self._uia_auto = None
        self._uia_mod = None
        self._is_windows = sys.platform.startswith("win")
        if self._is_windows:
            self._init_uia()

    def _init_uia(self):
        """Initializes Windows UIAutomationCore COM interface."""
        try:
            import comtypes.client
            self._uia_mod = comtypes.client.GetModule("UIAutomationCore.dll")
            self._uia_auto = comtypes.client.CreateObject(
                self._uia_mod.CUIAutomation,
                interface=self._uia_mod.IUIAutomation
            )
            logger.debug("[FOCUS_DETECTOR] UIAutomation client initialized.")
        except Exception as e:
            logger.debug(f"[FOCUS_DETECTOR] UIAutomation unavailable: {e}")
            self._uia_auto = None
            self._uia_mod = None

    def get_focus_info(self) -> FocusInfo:
        """Captures detailed focus information and password protection status."""
        if not self._is_windows:
            return self._get_linux_focus()

        info = FocusInfo()
        hwnd = 0
        title = ""
        proc_name = "unknown"
        app_name = "unknown"

        # 1. Native Win32 Foreground Window Info
        try:
            import win32gui
            import win32process
            import psutil

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                info.hwnd = hwnd
                title = win32gui.GetWindowText(hwnd) or ""
                info.window_title = title
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid:
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                    info.process_name = proc_name
                    app_name = proc_name.lower().replace(".exe", "")
                    info.app_name = app_name
        except Exception as e:
            logger.debug(f"[FOCUS_DETECTOR] Win32 foreground inspection error: {e}")

        # 2. UIAutomation Detailed Focused Control & Password Security Inspection
        if self._uia_auto and self._uia_mod:
            try:
                focused = self._uia_auto.GetFocusedElement()
                if focused:
                    info.raw_element = focused
                    info.target_name = focused.CurrentName or ""
                    info.class_name = focused.CurrentClassName or ""
                    info.automation_id = focused.CurrentAutomationId or ""

                    # ControlType inspection (50004 = Edit, 50030 = Document, 50003 = ComboBox)
                    c_type_id = focused.CurrentControlType
                    if c_type_id == self._uia_mod.UIA_EditControlTypeId:
                        info.control_type = "edit"
                        info.is_text_field = True
                    elif c_type_id == self._uia_mod.UIA_DocumentControlTypeId:
                        info.control_type = "document"
                        info.is_text_field = True
                    elif c_type_id == self._uia_mod.UIA_ComboBoxControlTypeId:
                        info.control_type = "combobox"
                        info.is_text_field = True
                    else:
                        info.control_type = "other"
                        info.is_text_field = bool(info.class_name and any(k in info.class_name.lower() for k in ["edit", "textbox", "input", "rich", "scintilla"]))

                    # ABSOLUTE SECURITY RULE: Password Field Detection
                    # Check 1: UIAutomation native IsPassword property
                    is_pwd = bool(focused.CurrentIsPassword)

                    # Check 2: Class Name / Automation ID inspection for password markers
                    pwd_markers = ["password", "passcode", "pin", "secure", "secret", "cvv", "token"]
                    name_check = (info.target_name or "").lower()
                    id_check = (info.automation_id or "").lower()
                    class_check = (info.class_name or "").lower()

                    if any(m in name_check for m in ["enter password", "password", "pin", "security code"]):
                        is_pwd = True
                    if any(m in id_check for m in pwd_markers):
                        is_pwd = True
                    if "passwordbox" in class_check or "password" in class_check:
                        is_pwd = True

                    info.is_password = is_pwd

                    # Check Read-Only / Editable status
                    try:
                        val_pattern = focused.GetCurrentPattern(self._uia_mod.UIA_ValuePatternId)
                        if val_pattern:
                            import comtypes
                            p_val = val_pattern.QueryInterface(self._uia_mod.IUIAutomationValuePattern)
                            info.is_editable = not bool(p_val.CurrentIsReadOnly)
                    except Exception:
                        info.is_editable = True

                    info.confidence = 0.95
            except Exception as e:
                logger.debug(f"[FOCUS_DETECTOR] UIAutomation focused inspection error: {e}")

        # 3. Window & Process-Level Security Inspection (FAIL-CLOSED GUARD)
        sec_markers = [
            "password", "passcode", "pin", "credential", "security dialog",
            "windows security", "sign in", "log in", "authenticat", "keepass",
            "1password", "bitwarden", "lastpass", "dashlane", "authenticator", "totp", "otp"
        ]
        title_low = (info.window_title or "").lower()
        proc_low = (info.process_name or "").lower()

        if any(m in title_low for m in sec_markers) or any(m in proc_low for m in ["credential", "auth"]):
            info.is_password = True
            info.is_editable = False
            logger.warning(f"[SECURITY_GUARD] Fail-closed: Window '{info.window_title}' ({proc_low}) identified as security/credential interface.")

        # Fallback heuristic if UIA couldn't resolve control
        if not info.raw_element:
            info.is_text_field = not info.is_password
            info.confidence = 0.6

        return info

    def _get_linux_focus(self) -> FocusInfo:
        """Fallback focus detector for Linux environments."""
        return FocusInfo(
            app_name="linux_app",
            window_title="Linux Active Window",
            hwnd=1,
            is_text_field=True,
            is_editable=True,
            is_password=False,
            confidence=0.7
        )

    def verify_focus_stable(self, expected_hwnd: int, expected_title: str = "") -> bool:
        """Verifies that the target window has not changed unexpectedly."""
        if not expected_hwnd or not self._is_windows:
            return True
        curr = self.get_focus_info()
        if curr.hwnd != expected_hwnd:
            logger.warning(f"[FOCUS_DETECTOR] Window changed from HWND {expected_hwnd} to {curr.hwnd} ('{curr.window_title}')")
            return False
        if expected_title and curr.window_title and expected_title.lower() != curr.window_title.lower():
            logger.warning(f"[FOCUS_DETECTOR] Window title changed from '{expected_title}' to '{curr.window_title}'")
            return False
        return True


focus_detector = FocusDetector()

