"""SANTRA Unified Interaction Layer - Workspace Manager.
Provides verified, safe workspace and folder management across Windows and Ubuntu.
Guarantees:
- Safe path resolution and sandbox / system-root rejection.
- Zero-overwrite / zero-merge policy for creation and renaming.
- Interactive disambiguation when multiple folder candidates exist.
- Antecedent tracking ('that folder', 'this project').
- Verification of every filesystem operation before claiming success.
"""

import os
import re
import sys
import json
import time
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger("Santra.WorkspaceManager")


class WorkspaceManager:
    """Manages workspace and project folder resolution, creation, renaming, and recent tracking."""

    # Disallowed system-critical locations (must never be modified or targeted for project operations)
    WINDOWS_PROTECTED_ROOTS = [
        "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
        "C:\\Recovery", "C:\\System Volume Information", "C:\\$Recycle.Bin",
        "C:\\Boot", "C:\\bootmgr", "C:\\ProgramData\\Microsoft"
    ]
    LINUX_PROTECTED_ROOTS = [
        "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/sys", "/proc",
        "/dev", "/boot", "/root"
    ]

    def __init__(self, state_file: Optional[Path] = None):
        self._is_windows = sys.platform.startswith("win")
        self.state_file = state_file or (Path.home() / ".santra_recent_workspaces.json")
        self._recent_workspaces: List[str] = []
        self._last_active_folder: Optional[Path] = None
        self._load_recents()

    # -------------------------------------------------------------------------
    # Recents & Antecedent Resolution
    # -------------------------------------------------------------------------
    def _load_recents(self) -> None:
        """Loads recently accessed workspaces from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._recent_workspaces = data.get("recent", [])
                    last_str = data.get("last_active")
                    if last_str and Path(last_str).exists():
                        self._last_active_folder = Path(last_str)
            except Exception as e:
                logger.debug(f"[WORKSPACE_MANAGER] Could not read recent state: {e}")
                self._recent_workspaces = []

    def _save_recents(self) -> None:
        """Persists recently accessed workspaces."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "recent": self._recent_workspaces[:20],
                    "last_active": str(self._last_active_folder) if self._last_active_folder else None,
                    "updated_at": time.time()
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"[WORKSPACE_MANAGER] Could not save recent state: {e}")

    def track_workspace(self, folder_path: Path) -> None:
        """Records a folder as recently active for antecedent resolution."""
        resolved = folder_path.resolve()
        str_path = str(resolved)
        self._last_active_folder = resolved
        if str_path in self._recent_workspaces:
            self._recent_workspaces.remove(str_path)
        self._recent_workspaces.insert(0, str_path)
        self._recent_workspaces = self._recent_workspaces[:20]
        self._save_recents()

    def update_workspace_tracking_after_rename(self, old_path: Path, new_path: Path) -> None:
        """Atomically replaces old workspace path with new path in recents and antecedent state."""
        old_str = str(old_path.resolve())
        new_str = str(new_path.resolve())

        # Clean up old path occurrences
        while old_str in self._recent_workspaces:
            self._recent_workspaces.remove(old_str)

        # Insert new path
        if new_str in self._recent_workspaces:
            self._recent_workspaces.remove(new_str)
        self._recent_workspaces.insert(0, new_str)
        self._recent_workspaces = self._recent_workspaces[:20]

        self._last_active_folder = new_path.resolve()
        self._save_recents()
        logger.info(f"[WORKSPACE_MANAGER] Updated workspace tracking: replaced '{old_str}' with '{new_str}'")

    def snapshot_folder_contents(self, folder_path: Path) -> Dict[str, Dict[str, Any]]:
        """Takes a full recursive snapshot of folder contents, including nested and hidden files."""
        snapshot = {}
        resolved = folder_path.resolve()
        if not resolved.exists() or not resolved.is_dir():
            return snapshot

        for root, dirs, files in os.walk(resolved):
            rel_root = os.path.relpath(root, resolved)
            for d in dirs:
                rel_d = os.path.normpath(os.path.join(rel_root, d)) if rel_root != "." else d
                snapshot[rel_d] = {"is_dir": True, "size": 0}
            for f in files:
                rel_f = os.path.normpath(os.path.join(rel_root, f)) if rel_root != "." else f
                f_path = os.path.join(root, f)
                try:
                    st = os.stat(f_path)
                    snapshot[rel_f] = {"is_dir": False, "size": st.st_size}
                except Exception:
                    snapshot[rel_f] = {"is_dir": False, "size": 0}
        return snapshot

    def verify_folder_contents(self, folder_path: Path, snapshot: Dict[str, Dict[str, Any]]) -> Tuple[bool, str]:
        """Verifies that all files and directories in snapshot exist inside folder_path and match sizes."""
        resolved = folder_path.resolve()
        if not resolved.exists() or not resolved.is_dir():
            return False, f"Folder '{folder_path}' does not exist on disk."

        for rel_item, meta in snapshot.items():
            item_path = resolved / rel_item
            if not item_path.exists():
                return False, f"Item missing after rename: '{rel_item}'"
            if not meta["is_dir"]:
                try:
                    cur_size = os.path.getsize(item_path)
                    if cur_size != meta["size"]:
                        return False, f"File size mismatch for '{rel_item}': expected {meta['size']}, got {cur_size}"
                except Exception as e:
                    return False, f"Cannot verify file '{rel_item}': {e}"
        return True, "Contents intact"

    def detect_processes_referencing_path(self, folder_path: Path) -> List[Dict[str, Any]]:
        """Detects whether any running processes reference the target folder in cmdline or cwd."""
        referencing = []
        path_str = str(folder_path.resolve()).lower()
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                    cmd_str = " ".join(cmdline).lower()
                    if path_str in cmd_str:
                        referencing.append({
                            "pid": proc.info.get("pid"),
                            "name": proc.info.get("name"),
                            "cmdline": cmdline
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.debug(f"[WORKSPACE_MANAGER] Process reference check: {e}")
        return referencing

    def get_last_active_folder(self) -> Optional[Path]:
        """Returns the most recently created, opened, or modified folder."""
        if self._last_active_folder and self._last_active_folder.exists():
            return self._last_active_folder
        if self._recent_workspaces:
            for p_str in self._recent_workspaces:
                p = Path(p_str)
                if p.exists() and p.is_dir():
                    self._last_active_folder = p
                    return p
        return None

    # -------------------------------------------------------------------------
    # Path & Safety Validation
    # -------------------------------------------------------------------------
    def is_safe_path(self, target_path: Path) -> Tuple[bool, str]:
        """Validates that target path is not a system root, protected folder, or traversal escape."""
        try:
            resolved = target_path.resolve()
        except Exception as e:
            return False, f"Invalid path syntax: {e}"

        str_res = str(resolved)

        # Check drive root
        if self._is_windows:
            # C:\ or \\ or D:\ alone
            if resolved == resolved.parent:
                return False, "Cannot target a filesystem drive root directly."
            for prot in self.WINDOWS_PROTECTED_ROOTS:
                if str_res.lower().startswith(prot.lower()):
                    return False, f"Target path '{resolved}' is inside a protected Windows system directory."
        else:
            if str_res == "/" or resolved == resolved.parent:
                return False, "Cannot target root directory '/'."
            for prot in self.LINUX_PROTECTED_ROOTS:
                if str_res == prot or str_res.startswith(f"{prot}/"):
                    return False, f"Target path '{resolved}' is inside a protected Linux system directory."

        return True, "Path is safe"

    def get_standard_search_bases(self) -> List[Path]:
        """Returns standard user directories to search for projects."""
        home = Path.home()
        desktop = home / "Desktop"
        docs = home / "Documents"
        projects = home / "Projects"
        workspace_base = home / "workspace"
        current_repo = Path.cwd()

        candidates = [desktop, docs, projects, workspace_base, current_repo, home]
        existing = []
        for c in candidates:
            if c.exists() and c.is_dir() and c not in existing:
                existing.append(c)
        return existing

    # -------------------------------------------------------------------------
    # Path & Name Resolution
    # -------------------------------------------------------------------------
    def resolve_parent_location(self, parent_hint: Optional[str]) -> Path:
        """Resolves parent directory hint like 'on my desktop', 'in Documents', 'inside Projects'."""
        home = Path.home()
        if not parent_hint:
            # Default to Desktop if it exists, else user Home
            desktop = home / "Desktop"
            return desktop if desktop.exists() else home

        hint_clean = parent_hint.lower().strip()
        # Clean phrases like 'my desktop', 'on my desktop', 'on desktop'
        hint_clean = re.sub(r"^(?:on|in|inside)\s+(?:my\s+)?", "", hint_clean).strip()

        # Check if it matches an existing directory first
        matches = self.find_folders(hint_clean)
        if len(matches) == 1:
            return matches[0]

        if hint_clean in ["desktop", "the desktop"]:
            return home / "Desktop" if (home / "Desktop").exists() else home
        if hint_clean in ["documents", "my documents", "the documents"]:
            return home / "Documents" if (home / "Documents").exists() else home
        if hint_clean in ["downloads", "my downloads"]:
            return home / "Downloads" if (home / "Downloads").exists() else home
        if hint_clean in ["projects", "my projects"]:
            proj = home / "Projects"
            if not proj.exists():
                proj = home / "Desktop" / "Projects"
            return proj

        # Check if it's already an absolute or relative directory path
        p = Path(os.path.expanduser(parent_hint))
        if p.is_absolute():
            return p
        return (home / "Desktop" / p)

    def find_folders(self, folder_name: str, base_dirs: Optional[List[Path]] = None) -> List[Path]:
        """Finds folders matching folder_name across standard base directories."""
        clean_target = folder_name.lower().strip()
        if not clean_target:
            return []

        search_bases = base_dirs or self.get_standard_search_bases()
        matches: List[Path] = []
        visited = set()

        for base in search_bases:
            if not base.exists() or not base.is_dir():
                continue
            try:
                # Direct child check first (highest priority)
                direct = base / folder_name
                if direct.exists() and direct.is_dir() and str(direct.resolve()) not in visited:
                    matches.append(direct.resolve())
                    visited.add(str(direct.resolve()))

                # Case-insensitive child check
                for item in base.iterdir():
                    if item.is_dir():
                        r_item = item.resolve()
                        if str(r_item) in visited:
                            continue
                        if item.name.lower() == clean_target:
                            matches.append(r_item)
                            visited.add(str(r_item))
                        # Check 1 level deeper for 'Projects' subdirectories
                        if item.name.lower() in ["projects", "santra projects", "workspace"]:
                            try:
                                for sub in item.iterdir():
                                    if sub.is_dir() and sub.name.lower() == clean_target:
                                        r_sub = sub.resolve()
                                        if str(r_sub) not in visited:
                                            matches.append(r_sub)
                                            visited.add(str(r_sub))
                            except Exception:
                                pass
            except PermissionError:
                continue
            except Exception as e:
                logger.debug(f"[WORKSPACE_MANAGER] Search error in {base}: {e}")

        return matches

    # -------------------------------------------------------------------------
    # Core Operation 1: Folder Creation
    # -------------------------------------------------------------------------
    def create_folder(
        self,
        folder_name: str,
        parent_location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new folder safely. Never overwrites existing folders."""
        clean_name = folder_name.strip().strip("\"'").strip()
        if not clean_name:
            return {
                "success": False,
                "status": "INVALID_NAME",
                "message": "Folder name cannot be empty."
            }

        # Check for antecedent phrase: 'create a folder called X'
        parent_dir = self.resolve_parent_location(parent_location)
        target_path = (parent_dir / clean_name).resolve()

        # Validate path safety
        safe, reason = self.is_safe_path(target_path)
        if not safe:
            logger.warning(f"[WORKSPACE_MANAGER] Safe path rejection: {reason}")
            return {
                "success": False,
                "status": "UNSAFE_PATH",
                "path": str(target_path),
                "message": f"Action blocked: {reason}"
            }

        # CRITICAL CONSTRAINT: Never overwrite an existing folder or file
        if target_path.exists():
            logger.warning(f"[WORKSPACE_MANAGER] Destination exists: {target_path}")
            return {
                "success": False,
                "status": "ALREADY_EXISTS",
                "path": str(target_path),
                "exists": True,
                "message": f"A folder named '{clean_name}' already exists at {target_path.parent}. What would you like to do?"
            }

        try:
            target_path.mkdir(parents=True, exist_ok=False)
            # Physical verification
            if target_path.exists() and target_path.is_dir():
                self.track_workspace(target_path)
                logger.info(f"[WORKSPACE_MANAGER] Successfully created folder: {target_path}")
                return {
                    "success": True,
                    "status": "CREATED",
                    "folder_name": clean_name,
                    "path": str(target_path),
                    "parent": str(parent_dir),
                    "message": f"Created folder '{clean_name}' in {parent_dir.name}."
                }
            else:
                return {
                    "success": False,
                    "status": "VERIFICATION_FAILED",
                    "message": f"Attempted to create '{clean_name}', but folder could not be verified on disk."
                }
        except PermissionError:
            return {
                "success": False,
                "status": "PERMISSION_DENIED",
                "message": f"Permission denied creating folder at {parent_dir}."
            }
        except Exception as e:
            logger.error(f"[WORKSPACE_MANAGER] Error creating folder {clean_name}: {e}")
            return {
                "success": False,
                "status": "ERROR",
                "error": str(e),
                "message": f"Failed to create folder '{clean_name}': {e}"
            }

    # -------------------------------------------------------------------------
    # Core Operation 2: Folder Renaming
    # -------------------------------------------------------------------------
    def rename_folder(
        self,
        source_name: str,
        new_name: str,
        parent_location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Renames a folder safely. Never overwrites or silently merges into existing folders."""
        clean_new = new_name.strip().strip("\"'").strip()
        if not clean_new:
            return {"success": False, "status": "INVALID_NAME", "message": "New folder name cannot be empty."}

        # Check antecedent reference like 'that folder', 'this folder', 'the folder'
        source_path: Optional[Path] = None
        if source_name.lower().strip() in ["that folder", "this folder", "the folder", "that project", "it"]:
            source_path = self.get_last_active_folder()
            if not source_path:
                return {
                    "success": False,
                    "status": "ANTECEDENT_UNKNOWN",
                    "message": "I couldn't identify which folder you mean by 'that folder'. Please specify the name."
                }
        else:
            # Find matching folders
            matches = self.find_folders(source_name)
            if len(matches) == 0:
                # Check if it was provided as an absolute path
                cand = Path(source_name)
                if cand.exists() and cand.is_dir():
                    source_path = cand.resolve()
                else:
                    return {
                        "success": False,
                        "status": "FOLDER_NOT_FOUND",
                        "message": f"Could not find any folder named '{source_name}'."
                    }
            elif len(matches) > 1:
                # Ambiguous: ask user for clarification
                options = [str(p) for p in matches[:4]]
                logger.warning(f"[WORKSPACE_MANAGER] Multiple matches for '{source_name}': {options}")
                return {
                    "success": False,
                    "status": "AMBIGUOUS_MATCH",
                    "candidates": options,
                    "requires_clarification": True,
                    "message": f"Multiple folders match '{source_name}': {', '.join(options)}. Which one would you like to rename?"
                }
            else:
                source_path = matches[0]

        # Determine target destination path
        parent_dir = source_path.parent
        dest_path = (parent_dir / clean_new).resolve()

        # Validate destination safety
        safe, reason = self.is_safe_path(dest_path)
        if not safe:
            return {"success": False, "status": "UNSAFE_PATH", "message": f"Action blocked: {reason}"}

        # CRITICAL CONSTRAINT: Never overwrite or merge into an existing destination folder
        if dest_path.exists():
            logger.warning(f"[WORKSPACE_MANAGER] Rename destination already exists: {dest_path}")
            return {
                "success": False,
                "status": "DESTINATION_ALREADY_EXISTS",
                "destination_exists": True,
                "path": str(dest_path),
                "message": f"A folder named '{clean_new}' already exists in {parent_dir.name}. Stopping to prevent overwriting your data."
            }

        # Capture content snapshot before rename to verify zero data loss
        snapshot = self.snapshot_folder_contents(source_path)

        # Detect if any running process (e.g. Antigravity IDE) currently references this folder
        ref_procs = self.detect_processes_referencing_path(source_path)
        if ref_procs:
            logger.warning(f"[WORKSPACE_MANAGER] Running processes reference '{source_path}': {[p['name'] for p in ref_procs]}")

        try:
            old_display = source_path.name
            source_path.rename(dest_path)

            # Verification of physical rename
            if not dest_path.exists() or not dest_path.is_dir() or source_path.exists():
                return {
                    "success": False,
                    "status": "VERIFICATION_FAILED",
                    "message": f"Failed to verify rename of '{old_display}' to '{clean_new}'."
                }

            # Content integrity verification
            ok, reason = self.verify_folder_contents(dest_path, snapshot)
            if not ok:
                logger.error(f"[WORKSPACE_MANAGER] Content verification failed after rename: {reason}")
                return {
                    "success": False,
                    "status": "CONTENT_INTEGRITY_MISMATCH",
                    "message": f"Folder renamed, but content verification failed: {reason}"
                }

            # Update workspace tracking atomically
            self.update_workspace_tracking_after_rename(source_path, dest_path)
            logger.info(f"[WORKSPACE_MANAGER] Successfully renamed '{old_display}' -> '{clean_new}' ({len(snapshot)} items verified).")

            return {
                "success": True,
                "status": "RENAMED",
                "old_name": old_display,
                "new_name": clean_new,
                "path": str(dest_path),
                "items_verified": len(snapshot),
                "referencing_processes": ref_procs,
                "message": f"Renamed folder '{old_display}' to '{clean_new}'."
            }
        except PermissionError:
            return {
                "success": False,
                "status": "PERMISSION_DENIED",
                "message": f"Permission denied renaming '{source_path.name}'. A file inside may be locked."
            }
        except Exception as e:
            logger.error(f"[WORKSPACE_MANAGER] Error renaming folder: {e}")
            return {"success": False, "status": "ERROR", "error": str(e), "message": f"Failed to rename folder: {e}"}

    # -------------------------------------------------------------------------
    # Core Operation 3: Path Resolution & Lookup
    # -------------------------------------------------------------------------
    def resolve_workspace(self, folder_or_project_name: str) -> Dict[str, Any]:
        """Resolves the actual path for a folder or project name, handling pronouns and ambiguity."""
        clean = folder_or_project_name.lower().strip()
        if clean in ["that folder", "this folder", "the folder", "this project", "that project", "it", "current folder", "current project", "workspace", ""]:
            last = self.get_last_active_folder()
            if last:
                return {"success": True, "path": last, "name": last.name}
            # Fallback to current working directory or active project
            from pathlib import Path
            cwd = Path(os.getcwd())
            return {"success": True, "path": cwd, "name": cwd.name}

        matches = self.find_folders(folder_or_project_name)
        if len(matches) == 1:
            self.track_workspace(matches[0])
            return {"success": True, "path": matches[0], "name": matches[0].name}
        elif len(matches) > 1:
            options = [str(p) for p in matches[:4]]
            return {
                "success": False,
                "status": "AMBIGUOUS_MATCH",
                "candidates": options,
                "requires_clarification": True,
                "message": f"I found multiple folders matching '{folder_or_project_name}': {', '.join(options)}. Which one would you like?"
            }
        else:
            return {
                "success": False,
                "status": "NOT_FOUND",
                "message": f"Folder '{folder_or_project_name}' could not be found."
            }

    # -------------------------------------------------------------------------
    # Core Operation 4: Reveal / Open in Explorer
    # -------------------------------------------------------------------------
    def reveal_in_file_manager(self, folder_or_name: str) -> Dict[str, Any]:
        """Reveals folder in Windows Explorer or Linux file manager."""
        res = self.resolve_workspace(folder_or_name)
        if not res.get("success"):
            return res

        folder_path: Path = res["path"]
        try:
            if self._is_windows:
                os.startfile(str(folder_path))
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(folder_path)])
            return {
                "success": True,
                "status": "OPENED_IN_EXPLORER",
                "path": str(folder_path),
                "message": f"Opened '{folder_path.name}' in file explorer."
            }
        except Exception as e:
            return {"success": False, "status": "ERROR", "message": f"Could not open folder in file manager: {e}"}


# Global singleton
workspace_manager = WorkspaceManager()
