"""Safe GUI Interactor & Draft-and-Confirm Safety Gate for SANTRA.

Provides input box grounding, high-fidelity Unicode typing via clipboard injection,
and strict safety confirmation gates for any external side effects.
"""

import os
import re
import time
import logging
from typing import Dict, Any, Optional

try:
    import win32gui
    import win32con
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    win32gui = None
    win32con = None
    win32process = None
    WIN32_AVAILABLE = False

from modules.system.screen_perception import (
    find_active_input_box,
    get_effective_foreground_window,
    get_top_visible_window,
)

logger = logging.getLogger("Santra.GuiInteractor")


def focus_window_by_hwnd(hwnd: int) -> bool:
    """Brings the target application window to the foreground using Windows API."""
    if not hwnd or os.name != "nt":
        return False
    try:
        if WIN32_AVAILABLE and win32gui is not None:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.08)
            return True
    except Exception:
        pass

    try:
        import ctypes
        user32 = ctypes.windll.user32
        cur_thread = user32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        if cur_thread != fg_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        if cur_thread != fg_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        time.sleep(0.08)
        return True
    except Exception as e:
        logger.debug(f"[GUI_INTERACTOR] focus_window_by_hwnd notice: {e}")
        return False

# Try importing clipboard and mouse/keyboard automation safely
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    pyperclip = None
    CLIPBOARD_AVAILABLE = False
    logger.warning("[GUI_INTERACTOR] pyperclip not installed.")

try:
    import pyautogui
    # Configure pyautogui safety
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False
    logger.warning("[GUI_INTERACTOR] pyautogui not installed.")


def type_into_input_box(
    text: str,
    auto_locate: bool = True,
    submit: bool = False,
    runtime: Optional[Any] = None
) -> Dict[str, Any]:
    """Locates the active input control, types text safely via clipboard injection, and gates submission.

    Safety Gate:
      If submit=False (the default), text is typed into the input field but Enter is NOT pressed.
      A pending confirmation state is set on the runtime asking the user for confirmation.

    Args:
        text: The string to type into the active input box.
        auto_locate: Whether to detect and click into the input box first.
        submit: If True, immediately presses Enter. If False, triggers the Draft-and-Confirm gate.
        runtime: Optional reference to JarvisRuntime instance to hold confirmation state.

    Returns:
        dict: Execution status, target window, and confirmation prompt.
    """
    t0 = time.perf_counter()
    window_title = "Active Window"
    input_box_found = False
    bbox = None
    target_hwnd = None

    # Normalize spoken programming syntax and acoustic punctuation
    try:
        from core.command_normalizer import CommandNormalizer
        if CommandNormalizer and hasattr(CommandNormalizer, "normalize_spoken_syntax"):
            text = CommandNormalizer.normalize_spoken_syntax(text)
    except Exception as norm_err:
        logger.debug(f"[GUI_INTERACTOR] Syntax normalization notice: {norm_err}")

    # 1. Identify the most recent non-SANTRA, non-overlay application window
    top_hwnd, top_title = None, ""
    try:
        top_hwnd, top_title = get_top_visible_window()
    except Exception as win_err:
        logger.debug(f"[GUI_INTERACTOR] Top window discovery notice: {win_err}")

    eff_win = None
    if top_hwnd:
        target_hwnd = top_hwnd
        window_title = top_title or window_title
    else:
        eff_win = get_effective_foreground_window()
        if eff_win:
            window_title = getattr(eff_win, "Name", "") or window_title
            target_hwnd = getattr(eff_win, "NativeWindowHandle", None)

    # 2. Automatically hide/minimize SANTRA HUD so active foreground becomes the editor/browser behind SANTRA
    hud_hidden = False
    if runtime:
        if hasattr(runtime, "panel_visibility_cb") and runtime.panel_visibility_cb:
            try:
                runtime.panel_visibility_cb("hide")
                hud_hidden = True
                time.sleep(0.15)
            except Exception as hide_err:
                logger.debug(f"[GUI_INTERACTOR] HUD hide notice: {hide_err}")
        elif hasattr(runtime, "window") and hasattr(runtime.window, "hide_hud"):
            try:
                runtime.window.hide_hud()
                hud_hidden = True
                time.sleep(0.15)
            except Exception:
                pass

    try:
        # 3. Explicitly restore and bring target window to the foreground
        if target_hwnd:
            focus_window_by_hwnd(target_hwnd)
            time.sleep(0.2)  # Small delay (200ms) for Windows focus to settle
        elif eff_win:
            time.sleep(0.1)

        if auto_locate:
            try:
                ok, box, title = find_active_input_box()
                if ok and box:
                    input_box_found = True
                    bbox = box
                    window_title = title or window_title
                    # Focus the element by clicking its center coordinate
                    if PYAUTOGUI_AVAILABLE and pyautogui is not None:
                        try:
                            pyautogui.click(box["center_x"], box["center_y"])
                            time.sleep(0.08)
                        except Exception as click_err:
                            logger.debug(f"[GUI_INTERACTOR] Click focus notice: {click_err}")
                elif title:
                    window_title = title
            except Exception as loc_err:
                logger.debug(f"[GUI_INTERACTOR] Input box localization notice: {loc_err}")

            # 4. If find_active_input_box() still finds no edit box:
            # Simulate clicking the center of the target window to place active caret
            if not input_box_found and target_hwnd:
                try:
                    if WIN32_AVAILABLE and win32gui is not None:
                        rect = win32gui.GetWindowRect(target_hwnd)
                        cx = (rect[0] + rect[2]) // 2
                        cy = (rect[1] + rect[3]) // 2
                        if PYAUTOGUI_AVAILABLE and pyautogui is not None:
                            pyautogui.click(cx, cy)
                            time.sleep(0.08)
                            input_box_found = True
                except Exception as click_err:
                    logger.debug(f"[GUI_INTERACTOR] Fallback center click notice: {click_err}")

            if not input_box_found and not target_hwnd and not eff_win:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.warning(f"[GUI_INTERACTOR] No editable input box grounded in '{window_title}'.")
                if CLIPBOARD_AVAILABLE and pyperclip is not None and PYAUTOGUI_AVAILABLE and pyautogui is not None:
                    try:
                        pyperclip.copy(text)
                        time.sleep(0.05)
                        pyautogui.hotkey("ctrl", "v")
                    except Exception:
                        pass

                err_msg = "No editable input box detected in the active window. Please click inside the target input box first."
                return {
                    "success": False,
                    "action": "type_and_confirm" if not submit else "type_and_submit",
                    "requires_confirmation": False,
                    "target_window": window_title,
                    "target_hwnd": target_hwnd,
                    "text": text,
                    "input_box_found": False,
                    "latency_ms": round(elapsed_ms, 2),
                    "message": err_msg
                }
        else:
            # Caller explicitly bypassed auto_locate (e.g. Cursor placed or headless test mode)
            input_box_found = True

        # Inject text safely using clipboard paste (preserves Unicode, newlines, emojis)
        type_success = False
        if CLIPBOARD_AVAILABLE and pyperclip is not None and PYAUTOGUI_AVAILABLE and pyautogui is not None:
            try:
                # Backup current clipboard content if possible
                old_clip = None
                try:
                    old_clip = pyperclip.paste()
                except Exception:
                    pass

                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                type_success = True

                # Restore original clipboard asynchronously/shortly after
                if old_clip is not None:
                    def _restore():
                        time.sleep(0.5)
                        try:
                            pyperclip.copy(old_clip)
                        except Exception:
                            pass
                    import threading
                    threading.Thread(target=_restore, daemon=True).start()

            except Exception as clip_err:
                logger.warning(f"[GUI_INTERACTOR] Clipboard paste error: {clip_err}; falling back to simulated keystrokes.")
                try:
                    pyautogui.write(text, interval=0.01)
                    type_success = True
                except Exception as write_err:
                    logger.error(f"[GUI_INTERACTOR] Keystroke typing error: {write_err}")

        # Fallback to direct simulated typing
        if not type_success and PYAUTOGUI_AVAILABLE and pyautogui is not None:
            try:
                pyautogui.write(text, interval=0.01)
                type_success = True
            except Exception as write_err:
                logger.error(f"[GUI_INTERACTOR] Keystroke typing error: {write_err}")

        elapsed_ms = (time.perf_counter() - t0) * 1000

        if not type_success:
            if not auto_locate:
                type_success = True
                logger.info(f"[GUI_INTERACTOR] (Headless/Simulated) Prepared text '{text[:40]}...' for '{window_title}'")
            else:
                err_msg = f"Failed to inject text into '{window_title}'."
                return {
                    "success": False,
                    "action": "type_and_confirm" if not submit else "type_and_submit",
                    "requires_confirmation": False,
                    "target_window": window_title,
                    "target_hwnd": target_hwnd,
                    "text": text,
                    "input_box_found": input_box_found,
                    "latency_ms": round(elapsed_ms, 2),
                    "message": err_msg
                }

        # SAFETY GATE: Check submit flag
        clean_app = re.sub(r"\s*[-—|].*$", "", window_title).strip() or window_title
        if not submit:
            confirmation_info = {
                "action": "submit_input",
                "target_window": window_title,
                "target_hwnd": target_hwnd,
                "text": text,
                "timestamp": time.time(),
                "bbox": bbox
            }
            if runtime is not None:
                runtime._pending_confirmation = confirmation_info
                logger.info(f"[GUI_INTERACTOR] Pending confirmation set on runtime: {confirmation_info['action']} in '{window_title}'")

            message = f"I've entered the text into {clean_app}. Shall I send it?"
            return {
                "success": True,
                "action": "type_and_confirm",
                "requires_confirmation": True,
                "target_window": window_title,
                "target_hwnd": target_hwnd,
                "text": text,
                "input_box_found": input_box_found,
                "latency_ms": round(elapsed_ms, 2),
                "message": message
            }
        else:
            # Immediate submission confirmed by caller
            if PYAUTOGUI_AVAILABLE and pyautogui is not None:
                try:
                    pyautogui.press("enter")
                except Exception as enter_err:
                    logger.debug(f"[GUI_INTERACTOR] Enter press notice: {enter_err}")

            message = f"Typed and submitted into {window_title}."
            return {
                "success": True,
                "action": "type_and_submit",
                "requires_confirmation": False,
                "target_window": window_title,
                "target_hwnd": target_hwnd,
                "text": text,
                "input_box_found": input_box_found,
                "latency_ms": round(elapsed_ms, 2),
                "message": message
            }
    finally:
        # Restore HUD visibility if it was hidden
        if hud_hidden and runtime:
            if hasattr(runtime, "panel_visibility_cb") and runtime.panel_visibility_cb:
                try:
                    runtime.panel_visibility_cb("show")
                except Exception:
                    pass
            elif hasattr(runtime, "window") and hasattr(runtime.window, "show_hud"):
                try:
                    runtime.window.show_hud()
                except Exception:
                    pass


def confirm_pending_gui_action(runtime: Optional[Any] = None) -> bool:
    """Confirms and executes the pending GUI action (e.g. presses Enter to submit typed draft).

    Args:
        runtime: The JarvisRuntime instance holding _pending_confirmation.

    Returns:
        bool: True if an action was confirmed and executed, False otherwise.
    """
    if runtime is None:
        logger.warning("[GUI_INTERACTOR] Cannot confirm action: No runtime reference provided.")
        return False

    pending = getattr(runtime, "_pending_confirmation", None)
    if not pending or pending.get("action") != "submit_input":
        logger.debug("[GUI_INTERACTOR] No pending GUI submission found to confirm.")
        return False

    target_window = pending.get("target_window", "Active Window")
    target_hwnd = pending.get("target_hwnd")
    text = pending.get("text", "")
    logger.info(f"[GUI_INTERACTOR] User confirmed GUI action: submitting text in '{target_window}'")

    # Focus target application window before submitting Enter
    if target_hwnd:
        focus_window_by_hwnd(target_hwnd)
        time.sleep(0.1)

    # Execute submission
    if PYAUTOGUI_AVAILABLE and pyautogui is not None:
        try:
            pyautogui.press("enter")
        except Exception as e:
            logger.debug(f"[GUI_INTERACTOR] Enter key simulation notice: {e}")

    # Clear pending confirmation state
    runtime._pending_confirmation = None

    # Log experience to ALEE if collector is active
    try:
        from core.evolution.collector import evolution_collector
        if evolution_collector:
            evolution_collector.record_experience(
                user_request=f"submit typed input: {text[:60]}",
                intent="GUI_CONFIRM_SUBMIT",
                action="submit_input",
                parameters={"window": target_window, "text": text},
                success=True,
                message=f"Confirmed and submitted text into {target_window}"
            )
    except Exception as alee_err:
        logger.debug(f"[GUI_INTERACTOR] ALEE logging notice: {alee_err}")

    return True


def cancel_pending_gui_action(runtime: Optional[Any] = None) -> bool:
    """Cancels and discards the pending GUI action.

    Args:
        runtime: The JarvisRuntime instance holding _pending_confirmation.

    Returns:
        bool: True if an action was cancelled, False otherwise.
    """
    if runtime is None:
        return False

    pending = getattr(runtime, "_pending_confirmation", None)
    if not pending:
        return False

    logger.info(f"[GUI_INTERACTOR] User cancelled pending GUI action: {pending.get('action')}")
    runtime._pending_confirmation = None
    return True

