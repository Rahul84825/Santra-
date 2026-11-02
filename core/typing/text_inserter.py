"""Safe Text Insertion Engine with Clipboard Preservation and Security Guards."""

import sys
import time
import logging
from typing import Optional, Dict, Any
from core.typing.models import FocusInfo
from core.typing.focus_detector import focus_detector

logger = logging.getLogger("Jarvis.TextInserter")


class SafeClipboardManager:
    """Manages clipboard snapshots, format enumeration, and safe restoration."""

    @staticmethod
    def snapshot() -> Dict[str, Any]:
        """Captures existing clipboard contents and available formats."""
        res = {"text": "", "formats": [], "has_text": False}
        try:
            import win32clipboard
            import win32con
            for _ in range(5):
                try:
                    win32clipboard.OpenClipboard(0)
                    break
                except Exception:
                    time.sleep(0.02)
            else:
                raise RuntimeError("Could not open clipboard after 5 attempts.")

            try:
                f = win32clipboard.EnumClipboardFormats(0)
                while f != 0:
                    res["formats"].append(f)
                    f = win32clipboard.EnumClipboardFormats(f)

                if win32con.CF_UNICODETEXT in res["formats"]:
                    res["text"] = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
                    res["has_text"] = True
            finally:
                win32clipboard.CloseClipboard()
            return res
        except Exception:
            pass

        try:
            import pyperclip
            txt = pyperclip.paste()
            return {"text": txt, "formats": [], "has_text": bool(txt)}
        except Exception:
            return res

    @staticmethod
    def set_text(text: str) -> bool:
        """Sets clipboard text with retries."""
        try:
            import win32clipboard
            import win32con
            for _ in range(5):
                try:
                    win32clipboard.OpenClipboard(0)
                    break
                except Exception:
                    time.sleep(0.02)
            else:
                raise RuntimeError("Could not open clipboard for write.")

            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            pass

        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except Exception:
            return False

    @classmethod
    def restore(cls, snapshot: Dict[str, Any], paste_delay: float = 0.12) -> bool:
        """Waits for application to process paste event, then restores clipboard."""
        time.sleep(paste_delay)
        if snapshot.get("has_text"):
            return cls.set_text(snapshot.get("text", ""))
        return True


class TextInserter:
    """Safely inserts text into focused controls across applications."""

    APPLICATION_PASTE_DELAYS = {
        "notepad": 0.08,
        "wordpad": 0.09,
        "winword": 0.12,
        "chrome": 0.18,
        "msedge": 0.18,
        "firefox": 0.18,
        "code": 0.20,
        "slack": 0.20,
        "discord": 0.20,
        "teams": 0.22,
        "whatsapp": 0.18
    }

    def __init__(self, detector=None):
        self.detector = detector or focus_detector
        self.clip_mgr = SafeClipboardManager()

    def get_adaptive_paste_delay(self, app_name: Optional[str] = None) -> float:
        """Determines optimal paste consumption delay based on application architecture."""
        clean_app = (app_name or "").lower().strip()
        for key, delay in self.APPLICATION_PASTE_DELAYS.items():
            if key in clean_app:
                return delay
        return 0.14  # Default balanced delay

    def insert_text(
        self,
        text: str,
        focus_info: Optional[FocusInfo] = None,
        expected_hwnd: int = 0,
        expected_title: str = "",
        mode: str = "append",  # 'append', 'insert', 'replace'
        focus_context: Optional[FocusInfo] = None
    ) -> Dict[str, Any]:
        """Inserts text into verified target element with strict safety guards."""
        if not text:
            return {"success": False, "reason": "empty_text", "message": "No text provided to insert."}

        # 1. Capture current focus if not supplied
        current_focus = focus_info or focus_context or self.detector.get_focus_info()

        # 2. Window Stability Guard
        if expected_hwnd and not self.detector.verify_focus_stable(expected_hwnd, expected_title):
            return {
                "success": False,
                "reason": "target_lost",
                "message": "The active application changed, so I paused typing to avoid typing into the wrong window.",
                "current_app": current_focus.app_name,
                "current_window": current_focus.window_title
            }

        # 3. ABSOLUTE SECURITY GUARD: Never type into password/secure fields
        if current_focus.is_password:
            logger.warning(f"[SECURITY_GUARD] Blocked typing into password field in '{current_focus.window_title}'")
            return {
                "success": False,
                "reason": "password_field_blocked",
                "message": "I cannot type into password or secure fields for your security."
            }

        # 4. Check if field is read-only
        if not current_focus.is_editable:
            return {
                "success": False,
                "reason": "read_only",
                "message": f"The target field in '{current_focus.window_title}' is read-only."
            }

        # 5. Method 1: UIAutomation ValuePattern (Direct Accessibility Injection)
        if current_focus.raw_element:
            try:
                raw_el = current_focus.raw_element
                if self.detector._uia_mod:
                    val_pattern = raw_el.GetCurrentPattern(self.detector._uia_mod.UIA_ValuePatternId)
                    if val_pattern:
                        import comtypes
                        pattern = val_pattern.QueryInterface(self.detector._uia_mod.IUIAutomationValuePattern)
                        if mode == "append":
                            existing = pattern.CurrentValue or ""
                            # If existing text ends without space, add one
                            sep = " " if existing and not existing.endswith((" ", "\n")) and not text.startswith((" ", "\n", ",", ".", "!", "?", ";", ":")) else ""
                            new_val = f"{existing}{sep}{text}"
                            pattern.SetValue(new_val)
                        elif mode == "replace":
                            pattern.SetValue(text)
                        else:
                            # Default insert
                            pattern.SetValue(text)

                        logger.info(f"[TEXT_INSERTER] Inserted text via UIAutomation ValuePattern into '{current_focus.target_name or current_focus.app_name}'.")
                        return {
                            "success": True,
                            "method": "uia_value_pattern",
                            "target": current_focus.target_name or current_focus.app_name,
                            "app": current_focus.app_name,
                            "message": f"Text inserted into {current_focus.app_name}."
                        }
            except Exception as e:
                logger.debug(f"[TEXT_INSERTER] UIA ValuePattern failed ({e}); falling back to clipboard paste.")

        # Re-verify window focus immediately before desktop input
        if current_focus.hwnd and not self.detector.verify_focus_stable(current_focus.hwnd, current_focus.window_title):
            return {
                "success": False,
                "reason": "target_lost",
                "message": "Focus changed immediately prior to typing. Aborted to avoid typing into wrong window."
            }

        # 6. Method 2: Safe Clipboard Paste with Strict Preservation & Emergency Stop
        clip_snap = self.clip_mgr.snapshot()
        try:
            import pyautogui
            old_failsafe = getattr(pyautogui, "FAILSAFE", True)
            try:
                # In automated / background environments, cursor rests at (0, 0).
                # Nudge cursor if possible, or disable failsafe if stuck at (0, 0)
                pyautogui.FAILSAFE = False
                pos = pyautogui.position()
                if pos != (0, 0):
                    pyautogui.FAILSAFE = old_failsafe
                else:
                    try:
                        pyautogui.moveTo(50, 50)
                        if pyautogui.position() != (0, 0):
                            pyautogui.FAILSAFE = old_failsafe
                    except Exception:
                        pass

                # Step B: If replace mode, select all first
                if mode == "replace":
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.03)

                # Step C: Copy dictated text and paste via Ctrl+V
                self.clip_mgr.set_text(text)
                time.sleep(0.02)
                pyautogui.hotkey("ctrl", "v")

                # Step D: Wait for app consumption and safely restore clipboard
                adaptive_delay = self.get_adaptive_paste_delay(current_focus.app_name)
                self.clip_mgr.restore(clip_snap, paste_delay=adaptive_delay)

                target_disp = current_focus.target_name or current_focus.app_name or "active window"
                logger.info(f"[TEXT_INSERTER] Inserted text via clipboard paste into {target_disp}.")
                return {
                    "success": True,
                    "method": "clipboard_paste",
                    "target": target_disp,
                    "app": current_focus.app_name,
                    "clipboard_preserved": clip_snap.get("has_text", False),
                    "message": f"Text typed into {target_disp}."
                }
            finally:
                pyautogui.FAILSAFE = old_failsafe
        except Exception as e:
            # Check for PyAutoGUI fail-safe emergency stop
            if "FailSafeException" in type(e).__name__:
                logger.critical("[EMERGENCY_STOP] Hardware fail-safe triggered by mouse corner gesture. Aborting all typing.")
                self.clip_mgr.restore(clip_snap, paste_delay=0.01)
                return {
                    "success": False,
                    "reason": "emergency_stop",
                    "message": "Emergency stop activated. Typing cancelled."
                }
            logger.debug(f"[TEXT_INSERTER] Clipboard paste failed ({e}); falling back to keyboard type.")

        # 7. Method 3: Keyboard Type Fallback
        try:
            import pyautogui
            pyautogui.write(text, interval=0.01)
            return {
                "success": True,
                "method": "keyboard_simulation",
                "target": current_focus.app_name,
                "app": current_focus.app_name,
                "message": f"Text typed into {current_focus.app_name}."
            }
        except Exception as e:
            if "FailSafeException" in type(e).__name__:
                logger.critical("[EMERGENCY_STOP] Hardware fail-safe triggered during keyboard write.")
                return {
                    "success": False,
                    "reason": "emergency_stop",
                    "message": "Emergency stop activated."
                }
            logger.error(f"[TEXT_INSERTER] All text insertion methods failed: {e}")
            return {
                "success": False,
                "reason": "all_methods_failed",
                "message": f"Failed to type text: {e}"
            }


text_inserter = TextInserter()
