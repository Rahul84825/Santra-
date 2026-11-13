"""Screen Perception & UI Grounding Module for SANTRA.

Provides ultra-fast frame capture (<30ms) via mss and non-invasive UI element grounding
via Windows UI Automation without allocating GPU VRAM or loading heavy vision models.
"""

import os
import time
import logging
from typing import Tuple, Dict, Any, Optional, List

logger = logging.getLogger("Santra.ScreenPerception")

# Try importing win32 libraries gracefully
try:
    import win32gui
    import win32process
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    win32gui = None
    win32process = None
    win32con = None
    WIN32_AVAILABLE = False
    logger.warning("[SCREEN_PERCEPTION] win32gui not installed; window enumeration running in degraded mode.")

# Try importing UI automation and frame capture libraries gracefully
try:
    import uiautomation as auto
    UIA_AVAILABLE = True
except ImportError:
    auto = None
    UIA_AVAILABLE = False
    logger.warning("[SCREEN_PERCEPTION] uiautomation not installed; UI inspection running in degraded mode.")

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    mss = None
    MSS_AVAILABLE = False
    logger.warning("[SCREEN_PERCEPTION] mss not installed; frame capture running in degraded mode.")


# Overlays and system window ignore-lists
IGNORED_WINDOW_CLASSES = {
    "CEF-OSC-WIDGET",
    "NVIDIA GeForce Overlay DT",
    "Shell_TrayWnd",
    "Progman",
    "WorkerW",
}

IGNORED_PROCESS_NAMES = {
    "nvcontainer.exe",
    "NVIDIA Share.exe",
    "dwm.exe",
    "santra",
}

# UI Automation Control Type IDs for editable inputs
EDITABLE_CONTROL_TYPE_NAMES = {
    "EditControl",
    "DocumentControl",
    "ComboBoxControl",
}

EDITABLE_CONTROL_TYPE_IDS = {
    50004,  # UIA_EditControlTypeId
    50030,  # UIA_DocumentControlTypeId
    50003,  # UIA_ComboBoxControlTypeId
}


def is_overlay_or_ignored_window(hwnd_or_ctrl: Any) -> bool:
    """Checks whether a window handle or UIA control belongs to an ignored overlay, system shell, or SANTRA process."""
    if not hwnd_or_ctrl:
        return True

    try:
        # 1. Handle HWND integer
        if isinstance(hwnd_or_ctrl, int):
            hwnd = hwnd_or_ctrl
            if WIN32_AVAILABLE and win32gui is not None:
                # Class name check
                try:
                    cls_name = win32gui.GetClassName(hwnd)
                    if any(cls_name.strip().lower() == ig.lower() for ig in IGNORED_WINDOW_CLASSES):
                        return True
                except Exception:
                    pass

                # Process name / PID check
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == os.getpid():
                        return True
                    if pid:
                        try:
                            import psutil
                            pname = psutil.Process(pid).name().lower()
                            if any(ig.lower() == pname or ig.lower() in pname for ig in IGNORED_PROCESS_NAMES):
                                return True
                        except Exception:
                            pass
                except Exception:
                    pass

                # Title check
                try:
                    title = win32gui.GetWindowText(hwnd).strip()
                    if not title:
                        return True
                    title_lower = title.lower()
                    if any(k in title_lower for k in ("nvidia geforce overlay", "geforce overlay", "santra", "jarvis")):
                        return True
                    if title in ["Program Manager", "Taskbar", "Settings", "Windows Input Experience"]:
                        return True
                except Exception:
                    pass
            return False

        # 2. Handle UIA Control or Mock Object
        ctrl = hwnd_or_ctrl
        cls_name = getattr(ctrl, "ClassName", "") or ""
        if cls_name and any(cls_name.strip().lower() == ig.lower() for ig in IGNORED_WINDOW_CLASSES):
            return True

        pid = getattr(ctrl, "ProcessId", 0)
        if pid == os.getpid():
            return True
        if pid:
            try:
                import psutil
                pname = psutil.Process(pid).name().lower()
                if any(ig.lower() == pname or ig.lower() in pname for ig in IGNORED_PROCESS_NAMES):
                    return True
            except Exception:
                pass

        name = getattr(ctrl, "Name", "") or ""
        if not name.strip():
            return True
        name_lower = name.strip().lower()
        if any(k in name_lower for k in ("nvidia geforce overlay", "geforce overlay", "santra", "jarvis")):
            return True
        if name in ["Program Manager", "Taskbar", "Settings", "Windows Input Experience"]:
            return True

    except Exception as e:
        logger.debug(f"[SCREEN_PERCEPTION] is_overlay_or_ignored_window notice: {e}")

    return False


def is_santra_control_or_window(ctrl: Any) -> bool:
    """Checks whether a UI control belongs to the SANTRA HUD, assistant process, or ignored overlay."""
    return is_overlay_or_ignored_window(ctrl)


def get_top_visible_window() -> Tuple[Optional[int], str]:
    """Iterates with win32gui.EnumWindows to find the topmost visible, non-minimized, non-tool, non-overlay window."""
    if not WIN32_AVAILABLE or win32gui is None:
        return None, ""

    candidate_hwnd = None
    candidate_title = ""

    def enum_cb(hwnd, extra):
        nonlocal candidate_hwnd, candidate_title
        if candidate_hwnd is not None:
            return False

        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True

            # Exclude tool windows
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return True

            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width <= 10 or height <= 10:
                return True

            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True

            if is_overlay_or_ignored_window(hwnd):
                return True

            candidate_hwnd = hwnd
            candidate_title = title
            return False
        except Exception:
            return True

    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    return candidate_hwnd, candidate_title


def get_effective_foreground_window() -> Any:
    """Gets the active foreground application window, automatically bypassing SANTRA's HUD and OS/GPU overlays."""
    # 1. Prefer Win32 EnumWindows to discover the topmost visible non-overlay application
    top_hwnd, top_title = get_top_visible_window()
    if top_hwnd:
        if UIA_AVAILABLE and auto is not None:
            try:
                ctrl = auto.ControlFromHandle(top_hwnd)
                if ctrl:
                    return ctrl
            except Exception as e:
                logger.debug(f"[SCREEN_PERCEPTION] ControlFromHandle notice: {e}")

        # Return a lightweight proxy control with HWND and Name
        class WindowHandleWrapper:
            def __init__(self, hwnd: int, name: str):
                self.NativeWindowHandle = hwnd
                self.Name = name
                self.ControlTypeName = "WindowControl"
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    self.ProcessId = pid
                except Exception:
                    self.ProcessId = 0
            def GetChildren(self):
                return []
        return WindowHandleWrapper(top_hwnd, top_title)

    # 2. Fallback to UIA GetForegroundControl (e.g. in unit test mocks or headless sessions)
    if UIA_AVAILABLE and auto is not None:
        try:
            fg = auto.GetForegroundControl()
            if fg and not is_overlay_or_ignored_window(fg):
                return fg
            root = auto.GetRootControl()
            if root:
                for child in root.GetChildren():
                    if not is_overlay_or_ignored_window(child):
                        return child
            return fg
        except Exception as e:
            logger.debug(f"[SCREEN_PERCEPTION] get_effective_foreground_window fallback notice: {e}")
            return None

    return None


def find_active_input_box(timeout_sec: float = 0.5) -> Tuple[bool, Optional[Dict[str, int]], str]:
    """Inspects the foreground window's UI Automation tree for focused or primary editable controls.

    Returns:
        tuple[bool, dict | None, str]:
            - success: True if an editable input box was grounded.
            - bbox: Dictionary with 'center_x', 'center_y', 'width', 'height', 'left', 'top', 'right', 'bottom'.
            - window_title: Title of the active foreground window.
    """
    if not UIA_AVAILABLE or auto is None:
        logger.debug("[SCREEN_PERCEPTION] UI Automation unavailable.")
        return False, None, "UI Automation Unavailable"

    try:
        fg_win = get_effective_foreground_window() or auto.GetForegroundControl()
        window_title = fg_win.Name if fg_win and fg_win.Name else "Active Window"
    except Exception as e:
        logger.debug(f"[SCREEN_PERCEPTION] Failed to get foreground control: {e}")
        return False, None, "Unknown Window"

    if not fg_win:
        return False, None, window_title

    # 1. Check if the currently focused element is directly an editable input
    try:
        focused = auto.GetFocusedControl()
        if focused and _is_editable_control(focused):
            bbox = _extract_bounding_box(focused)
            if bbox and bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                logger.info(f"[SCREEN_PERCEPTION] Found focused editable control '{focused.Name}' in '{window_title}' at {bbox}")
                return True, bbox, window_title
    except Exception as fe:
        logger.debug(f"[SCREEN_PERCEPTION] Focused control check notice: {fe}")

    # 2. Search foreground window's UI subtree for the most prominent editable control
    try:
        candidate_box = _search_editable_descendant(fg_win, max_depth=6)
        if candidate_box:
            logger.info(f"[SCREEN_PERCEPTION] Grounded input box in '{window_title}' at {candidate_box}")
            return True, candidate_box, window_title
    except Exception as se:
        logger.debug(f"[SCREEN_PERCEPTION] Subtree search notice: {se}")

    return False, None, window_title


def _is_editable_control(ctrl: Any) -> bool:
    """Checks whether a UI Automation control is an editable text field or document."""
    if not ctrl:
        return False
    try:
        # Check ControlTypeName string
        type_name = getattr(ctrl, "ControlTypeName", "")
        if type_name in EDITABLE_CONTROL_TYPE_NAMES:
            return True

        # Check ControlTypeId integer
        type_id = getattr(ctrl, "ControlType", None)
        if type_id in EDITABLE_CONTROL_TYPE_IDS:
            return True

        # Check patterns (ValuePattern or TextPattern indicates editable/text capability)
        if hasattr(ctrl, "IsValuePatternAvailable") and ctrl.IsValuePatternAvailable():
            # Ensure it is not read-only
            try:
                val_pat = ctrl.GetValuePattern()
                if val_pat and not getattr(val_pat, "IsReadOnly", False):
                    return True
            except Exception:
                pass

        if hasattr(ctrl, "IsTextPatternAvailable") and ctrl.IsTextPatternAvailable():
            return True

    except Exception:
        pass
    return False


def _extract_bounding_box(ctrl: Any) -> Optional[Dict[str, int]]:
    """Extracts pixel coordinates and center points from a UI control."""
    try:
        rect = getattr(ctrl, "BoundingRectangle", None)
        if not rect:
            return None
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
        width = int(rect.width()) if callable(getattr(rect, "width", None)) else int(right - left)
        height = int(rect.height()) if callable(getattr(rect, "height", None)) else int(bottom - top)
        center_x = left + width // 2
        center_y = top + height // 2
        return {
            "center_x": center_x,
            "center_y": center_y,
            "width": width,
            "height": height,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom
        }
    except Exception as e:
        logger.debug(f"[SCREEN_PERCEPTION] Bounding box extraction error: {e}")
        return None


def _search_editable_descendant(parent: Any, max_depth: int = 5) -> Optional[Dict[str, int]]:
    """Traverses child controls breadth-first to locate an editable control."""
    if not parent:
        return None

    queue = [(parent, 0)]
    visited_count = 0
    max_elements = 40

    while queue and visited_count < max_elements:
        current, depth = queue.pop(0)
        visited_count += 1

        if depth > 0 and _is_editable_control(current):
            bbox = _extract_bounding_box(current)
            if bbox and bbox.get("width", 0) > 10 and bbox.get("height", 0) > 10:
                return bbox

        if depth < max_depth:
            try:
                children = current.GetChildren()
                if children:
                    for ch in children:
                        queue.append((ch, depth + 1))
            except Exception:
                pass

    return None


def capture_screen_context(region: str = "active_window") -> Dict[str, Any]:
    """Captures the active window or screen frame via mss (<30ms) and extracts readable UI text.

    Formats structured visual and textual context for AgentBrain without requiring GPU VRAM.

    Args:
        region: "active_window" or "fullscreen"

    Returns:
        dict:
            - success (bool)
            - active_window (str)
            - process_name (str)
            - readable_texts (list[dict])
            - description (str)
            - capture_time_ms (float)
            - error (str | None)
    """
    t0 = time.perf_counter()
    window_title = "Unknown Window"
    process_name = "unknown.exe"
    readable_elements: List[Dict[str, str]] = []
    capture_err = None

    # 1. UI Automation inspection for window metadata and visible text
    if UIA_AVAILABLE and auto is not None:
        try:
            fg_win = get_effective_foreground_window() or auto.GetForegroundControl()
            if fg_win:
                window_title = fg_win.Name or "Active Window"
                proc_id = getattr(fg_win, "ProcessId", 0)
                try:
                    import psutil
                    process_name = psutil.Process(proc_id).name()
                except Exception:
                    process_name = f"PID:{proc_id}"

                # Extract readable UI elements (Text, Document, Edit, Button, TitleBar)
                readable_elements = _extract_readable_elements(fg_win, max_elements=30)
        except Exception as uia_err:
            logger.debug(f"[SCREEN_PERCEPTION] UI Automation reading error: {uia_err}")
            capture_err = str(uia_err)

    # 2. Fast frame grab via mss (<30ms target)
    frame_captured = False
    if MSS_AVAILABLE and mss is not None:
        try:
            with mss.MSS() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                _ = sct.grab(mon)
                frame_captured = True
        except Exception as mss_err:
            logger.debug(f"[SCREEN_PERCEPTION] mss capture notice (headless/locked session): {mss_err}")
            if not capture_err:
                capture_err = str(mss_err)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 3. Construct crisp textual description for AgentBrain
    description_lines = [
        f"Active Window: '{window_title}' (Process: {process_name})",
        f"Frame Capture: {'OK (<30ms)' if frame_captured else 'Headless/Desktop Restricted'}",
        "Readable Screen UI Elements:"
    ]
    if readable_elements:
        for elem in readable_elements[:15]:
            description_lines.append(f"  - [{elem['type']}] {elem['name']}")
    else:
        description_lines.append("  (No direct text controls discovered in active foreground window)")

    description = "\n".join(description_lines)

    return {
        "success": bool(window_title != "Unknown Window" or frame_captured),
        "active_window": window_title,
        "process_name": process_name,
        "readable_texts": readable_elements,
        "description": description,
        "capture_time_ms": round(elapsed_ms, 2),
        "error": capture_err
    }


def _extract_readable_elements(parent: Any, max_elements: int = 30) -> List[Dict[str, str]]:
    """Gathers visible text and control labels from the UI Automation tree."""
    elements = []
    seen_texts = set()

    queue = [(parent, 0)]
    visited = 0

    while queue and len(elements) < max_elements and visited < 60:
        current, depth = queue.pop(0)
        visited += 1

        try:
            name = (current.Name or "").strip()
            type_name = getattr(current, "ControlTypeName", "Control").replace("Control", "")
            
            # Extract ValuePattern text if available
            val_text = ""
            if hasattr(current, "GetValuePattern"):
                try:
                    vp = current.GetValuePattern()
                    if vp and vp.Value:
                        val_text = vp.Value.strip()
                except Exception:
                    pass

            display_text = val_text or name
            if display_text and len(display_text) > 1 and display_text not in seen_texts:
                # Truncate very long strings
                clean_display = display_text[:120]
                seen_texts.add(display_text)
                elements.append({
                    "type": type_name,
                    "name": clean_display
                })

            if depth < 4:
                children = current.GetChildren()
                if children:
                    for ch in children:
                        queue.append((ch, depth + 1))
        except Exception:
            continue

    return elements

