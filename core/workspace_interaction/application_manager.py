"""SANTRA Unified Interaction Layer - Application Manager.
Handles dynamic executable discovery, running instance detection, window activation,
and parameter passing for desktop applications (Antigravity IDE, Google Chrome, etc.).
"""

import os
import sys
import time
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger("Santra.ApplicationManager")


class ApplicationManager:
    """Manages discovery, launching, instance detection, and window activation for desktop apps."""

    def __init__(self):
        self._is_windows = sys.platform.startswith("win")
        self._executable_cache: Dict[str, str] = {}
        self._discover_known_apps()

    # -------------------------------------------------------------------------
    # Application Executable Discovery
    # -------------------------------------------------------------------------
    def _discover_known_apps(self) -> None:
        """Dynamically locates executables for supported applications."""
        self.find_antigravity_executable()
        self.find_chrome_executable()

    def find_antigravity_executable(self) -> Optional[str]:
        """Locates the Antigravity IDE executable on the host system."""
        if "antigravity" in self._executable_cache:
            p = self._executable_cache["antigravity"]
            if os.path.exists(p):
                return p

        # 1. System PATH lookup
        path_which = shutil.which("antigravity") or shutil.which("Antigravity IDE") or shutil.which("agy")
        if path_which and os.path.exists(path_which):
            self._executable_cache["antigravity"] = path_which
            return path_which

        # 2. Windows-specific standard directories
        if self._is_windows:
            user_local = Path(os.environ.get("LOCALAPPDATA", ""))
            prog_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
            prog_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))

            candidates = [
                user_local / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe",
                user_local / "Programs" / "antigravity" / "antigravity.exe",
                prog_files / "Antigravity IDE" / "Antigravity IDE.exe",
                prog_files / "Google" / "Antigravity" / "antigravity.exe",
                prog_files_x86 / "Antigravity IDE" / "Antigravity IDE.exe",
            ]
            for cand in candidates:
                if cand.exists():
                    self._executable_cache["antigravity"] = str(cand)
                    logger.info(f"[APP_MANAGER] Discovered Antigravity at: {cand}")
                    return str(cand)

        # 3. Ubuntu / Linux paths
        else:
            linux_cands = [
                "/usr/bin/antigravity",
                "/usr/local/bin/antigravity",
                "/opt/antigravity/antigravity",
                str(Path.home() / ".local" / "bin" / "antigravity")
            ]
            for cand in linux_cands:
                if os.path.exists(cand):
                    self._executable_cache["antigravity"] = cand
                    return cand

        # Fallback inspection of running processes if already running
        running = self.find_running_process(["antigravity ide", "antigravity"])
        if running and running.get("exe") and os.path.exists(running["exe"]):
            self._executable_cache["antigravity"] = running["exe"]
            return running["exe"]

        return None

    def find_chrome_executable(self) -> Optional[str]:
        """Locates the Google Chrome executable on the host system."""
        if "chrome" in self._executable_cache:
            p = self._executable_cache["chrome"]
            if os.path.exists(p):
                return p

        # 1. System PATH lookup
        path_which = shutil.which("chrome") or shutil.which("google-chrome")
        if path_which and os.path.exists(path_which):
            self._executable_cache["chrome"] = path_which
            return path_which

        # 2. Windows paths
        if self._is_windows:
            prog_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
            prog_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))
            user_local = Path(os.environ.get("LOCALAPPDATA", ""))

            candidates = [
                prog_files / "Google" / "Chrome" / "Application" / "chrome.exe",
                prog_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
                user_local / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
            for cand in candidates:
                if cand.exists():
                    self._executable_cache["chrome"] = str(cand)
                    logger.info(f"[APP_MANAGER] Discovered Chrome at: {cand}")
                    return str(cand)
        else:
            linux_cands = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium-browser"]
            for cand in linux_cands:
                if os.path.exists(cand):
                    self._executable_cache["chrome"] = cand
                    return cand

        # Fallback inspection of running processes
        running = self.find_running_process(["chrome"])
        if running and running.get("exe") and os.path.exists(running["exe"]):
            self._executable_cache["chrome"] = running["exe"]
            return running["exe"]

        return None

    # -------------------------------------------------------------------------
    # Running Instance & Window Detection
    # -------------------------------------------------------------------------
    def find_running_process(self, process_names: List[str]) -> Optional[Dict[str, Any]]:
        """Finds running process matching any name in process_names."""
        try:
            import psutil
            targets = [n.lower() for n in process_names]
            for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if any(t in name for t in targets):
                        return {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "exe": proc.info.get("exe"),
                            "cmdline": proc.info.get("cmdline") or []
                        }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.debug(f"[APP_MANAGER] Process search error: {e}")
        return None

    def is_running(self, app_name: str) -> bool:
        """Checks if the application is currently running."""
        clean = app_name.lower().strip()
        if "antigravity" in clean:
            return self.find_running_process(["antigravity ide", "antigravity"]) is not None
        elif "chrome" in clean:
            return self.find_running_process(["chrome"]) is not None
        else:
            return self.find_running_process([clean]) is not None

    def get_application_windows(self, app_name: str) -> List[Dict[str, Any]]:
        """Enumerates visible top-level windows for the application."""
        if not self._is_windows:
            return []

        clean = app_name.lower().strip()
        search_terms = []
        if "antigravity" in clean:
            search_terms = ["antigravity ide", "antigravity"]
        elif "chrome" in clean:
            search_terms = ["chrome"]
        else:
            search_terms = [clean]

        windows: List[Dict[str, Any]] = []
        try:
            import ctypes
            import ctypes.wintypes
            import psutil

            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            def check_win(hwnd):
                if user32.IsWindowVisible(hwnd):
                    try:
                        pid = ctypes.wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value:
                            p_name = psutil.Process(pid.value).name().lower()
                            if any(t in p_name for t in search_terms):
                                length = user32.GetWindowTextLengthW(hwnd)
                                buff = ctypes.create_unicode_buffer(length + 1)
                                user32.GetWindowTextW(hwnd, buff, length + 1)
                                title = buff.value or ""
                                windows.append({
                                    "hwnd": hwnd,
                                    "pid": pid.value,
                                    "title": title,
                                    "process_name": p_name
                                })
                    except Exception:
                        pass

            cb_func = WNDENUMPROC(lambda h, l: (check_win(h), True)[1])

            # 1. Try standard EnumWindows on current desktop
            try:
                user32.EnumWindows(cb_func, 0)
            except Exception:
                pass

            # 2. If no windows found (e.g. running in isolated desktop session), inspect Default interactive desktop
            if not windows:
                try:
                    hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                    if hdesk:
                        user32.EnumDesktopWindows(hdesk, cb_func, 0)
                        user32.CloseDesktop(hdesk)
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"[APP_MANAGER] Window enumeration error: {e}")

        return windows

    # -------------------------------------------------------------------------
    # Window Activation
    # -------------------------------------------------------------------------
    def activate_window(self, hwnd: int) -> bool:
        """Brings an existing window to the foreground."""
        if not self._is_windows or not hwnd:
            return False

        try:
            import win32gui
            import win32con

            # Restore if minimized
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)
            # Set to foreground
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            return True
        except Exception as e:
            logger.debug(f"[APP_MANAGER] Window activation error for HWND {hwnd}: {e}")
            return False

    def activate_application(self, app_name: str) -> Dict[str, Any]:
        """Activates an existing running instance of the application if present."""
        wins = self.get_application_windows(app_name)
        if not wins:
            # Running process check
            proc = self.find_running_process(["antigravity ide" if "antigravity" in app_name.lower() else "chrome"])
            if proc:
                return {
                    "success": True,
                    "running": True,
                    "window_found": False,
                    "pid": proc["pid"],
                    "message": f"{app_name.title()} is running (PID: {proc['pid']})."
                }
            return {
                "success": False,
                "running": False,
                "window_found": False,
                "message": f"{app_name.title()} is not currently running."
            }

        # Select the best window (with meaningful title, or the first)
        best_win = None
        for w in wins:
            if w.get("title") and len(w["title"].strip()) > 1:
                best_win = w
                break
        if not best_win:
            best_win = wins[0]

        hwnd = best_win["hwnd"]
        activated = self.activate_window(hwnd)

        return {
            "success": True,
            "running": True,
            "window_found": True,
            "hwnd": hwnd,
            "title": best_win.get("title", ""),
            "activated": activated,
            "message": f"Activated {app_name.title()} window ('{best_win.get('title', '')}')."
        }

    # -------------------------------------------------------------------------
    # Launch or Open Workspace
    # -------------------------------------------------------------------------
    def open_workspace_in_antigravity(self, workspace_path: Path) -> Dict[str, Any]:
        """Opens a workspace folder in Antigravity IDE, launching it or activating existing instance."""
        exe = self.find_antigravity_executable()
        if not exe:
            return {
                "success": False,
                "status": "NOT_INSTALLED",
                "message": "Antigravity IDE executable could not be found on this system."
            }

        target_str = str(workspace_path.resolve())
        if not os.path.exists(target_str):
            return {
                "success": False,
                "status": "WORKSPACE_NOT_FOUND",
                "message": f"Folder '{target_str}' does not exist on disk."
            }

        try:
            # Launch with target workspace argument
            logger.info(f"[APP_MANAGER] Launching Antigravity IDE with workspace: {target_str}")
            proc = subprocess.Popen([exe, target_str], shell=False)

            # Give process a moment to initialize or attach
            time.sleep(0.5)

            return {
                "success": True,
                "status": "OPENED",
                "application": "Antigravity IDE",
                "executable": exe,
                "workspace": target_str,
                "pid": proc.pid,
                "message": f"Opened workspace '{workspace_path.name}' in Antigravity IDE."
            }
        except Exception as e:
            logger.error(f"[APP_MANAGER] Failed to launch Antigravity: {e}")
            return {
                "success": False,
                "status": "LAUNCH_FAILED",
                "error": str(e),
                "message": f"Failed to launch Antigravity IDE: {e}"
            }

    def open_chatgpt_in_chrome(self, prompt_url: str = "https://chatgpt.com") -> Dict[str, Any]:
        """Opens ChatGPT in the user's Google Chrome session."""
        exe = self.find_chrome_executable()
        if not exe:
            return {
                "success": False,
                "status": "NOT_INSTALLED",
                "message": "Google Chrome executable could not be found."
            }

        # Check if Chrome is already running
        chrome_running = self.is_running("chrome")
        try:
            if self._is_windows:
                # Open URL in existing browser instance without creating a separate profile
                logger.info(f"[APP_MANAGER] Opening URL in Chrome: {prompt_url}")
                proc = subprocess.Popen([exe, prompt_url], shell=False)
            else:
                proc = subprocess.Popen(["google-chrome", prompt_url])

            time.sleep(0.5)
            return {
                "success": True,
                "status": "OPENED",
                "application": "Google Chrome",
                "url": prompt_url,
                "existing_session_active": chrome_running,
                "message": f"Opened ChatGPT in Chrome."
            }
        except Exception as e:
            logger.error(f"[APP_MANAGER] Failed to open Chrome: {e}")
            return {"success": False, "status": "LAUNCH_FAILED", "error": str(e), "message": f"Failed to open Chrome: {e}"}


# Global singleton
application_manager = ApplicationManager()

