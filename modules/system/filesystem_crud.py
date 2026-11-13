"""Filesystem CRUD Module for SANTRA.

Provides deterministic file and folder management with:
- Intelligent path resolution (OneDrive, Desktop, Documents, Downloads, Workspaces)
- Parent directory auto-creation
- Safe text reading with runaway protection (size/line budgets)
- Automatic .bak backup creation on modification
- Recycle Bin protection via send2trash (NO unrecoverable os.remove / rmtree)
- Seamless ALEE rule configuration integration
"""

import os
import re
import time
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger("Santra.FilesystemCrud")

try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    send2trash = None
    SEND2TRASH_AVAILABLE = False
    logger.warning("[FILESYSTEM_CRUD] send2trash not available; recycle bin protection degraded.")


# Workspace root directory
BASE_WORKSPACE = Path(__file__).parent.parent.parent.resolve()


def get_desktop_dir() -> Path:
    """Accurately locates the user's active Desktop, respecting OneDrive redirection and Windows registry."""
    # 1. Windows Registry HKCU User Shell Folders (Primary source of truth on Windows)
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            val, _ = winreg.QueryValueEx(key, "Desktop")
            reg_d = Path(os.path.expandvars(val)).resolve()
            if reg_d.exists():
                return reg_d
        except Exception:
            pass

    # 2. Check OneDrive environment variable
    one_drive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or os.environ.get("OneDriveCommercial")
    if one_drive:
        od_path = Path(one_drive)
        # Check Attachments/Desktop (active on this machine)
        od_att_desktop = od_path / "Attachments" / "Desktop"
        if od_att_desktop.exists():
            return od_att_desktop.resolve()
        od_desktop = od_path / "Desktop"
        if od_desktop.exists():
            return od_desktop.resolve()

    # 3. Platform Manager
    try:
        from core.platform import platform_manager
        if platform_manager:
            return platform_manager.get_folder_path("desktop").resolve()
    except Exception:
        pass

    # 4. Standard user home fallback
    return (Path.home() / "Desktop").resolve()


def get_known_folder_dir(folder_key: str) -> Path:
    """Resolves standard user folders (desktop, documents, downloads, etc.)."""
    fk = folder_key.lower().strip()
    if fk == "desktop":
        return get_desktop_dir()

    if fk == "workspace":
        return BASE_WORKSPACE

    # Platform Manager check
    try:
        from core.platform import platform_manager
        if platform_manager:
            return platform_manager.get_folder_path(fk).resolve()
    except Exception:
        pass

    one_drive = os.environ.get("OneDrive")
    if one_drive:
        od_sub = Path(one_drive) / fk.capitalize()
        if od_sub.exists():
            return od_sub.resolve()

    return (Path.home() / fk.capitalize()).resolve()


def extract_name_and_destination(raw_text: str) -> tuple[str, Optional[str]]:
    """Extracts clean entity name and destination target from natural language strings.
    E.g. "create a folder called Project, on my desktop" -> ("Project", "desktop")
         "Project, on my desktop" -> ("Project", "desktop")
         "Project on desktop" -> ("Project", "desktop")
         "Project" -> ("Project", None)
    """
    if not raw_text:
        return "", None

    txt = str(raw_text).strip()
    # Strip leading command preambles if present
    txt = re.sub(r"^(?:create|make)\s+(?:a\s+)?(?:folder|directory|file)\s+(?:called|named|with\s+(?:the\s+)?name|by\s+(?:the\s+)?name|name)?\s*", "", txt, flags=re.IGNORECASE).strip()

    # Match trailing destination phrase: ", on my desktop", " on desktop", " in documents", etc.
    dest_match = re.search(
        r"^(.*?)(?:\s*,\s*|\s+)+(?:in|on|at)\s+(?:my\s+|the\s+)?(desktop|documents|downloads|music|videos|pictures|workspace|home)\s*$",
        txt,
        re.IGNORECASE
    )
    if dest_match:
        name_part = dest_match.group(1).strip().strip(" ,'\"")
        name_part = re.sub(r"^(?:called|named|with\s+(?:the\s+)?name|by\s+(?:the\s+)?name|name)\s+", "", name_part, flags=re.IGNORECASE).strip(" ,'\"")
        dest_part = dest_match.group(2).lower()
        if name_part:
            return name_part, dest_part

    clean = re.sub(r"^(?:called|named|with\s+(?:the\s+)?name|by\s+(?:the\s+)?name|name)\s+", "", txt, flags=re.IGNORECASE).strip(" ,'\"")
    return clean, None


def get_active_rule_config() -> Dict[str, Any]:
    """Queries ALEE active configuration for filesystem CRUD parameters."""
    try:
        from core.evolution.evolution_manager import evolution_manager
        rule = evolution_manager.get_active_rule("filesystem_crud")
        if rule and isinstance(rule, dict):
            return rule
    except Exception as e:
        logger.debug(f"[FILESYSTEM_CRUD] Evolution rule lookup notice: {e}")
    return {}


def resolve_path(path_input: Union[str, Path, None], destination: Optional[str] = None) -> Path:
    """Standardizes paths across OneDrive-redirected folders and relative project paths."""
    if not path_input:
        if destination:
            return get_known_folder_dir(destination)
        return BASE_WORKSPACE

    p_str = str(path_input).strip()
    p_lower = p_str.lower()

    # If destination explicitly passed
    if destination:
        base = get_known_folder_dir(destination)
        clean_name, _ = extract_name_and_destination(p_str)
        return base / (clean_name or p_str)

    # Check for natural language destination phrases inside path_input (e.g. "Project, on my desktop")
    clean_name, extracted_dest = extract_name_and_destination(p_str)
    if extracted_dest:
        base = get_known_folder_dir(extracted_dest)
        return base / clean_name

    # Try platform manager for known folders first
    try:
        from core.platform import platform_manager
    except Exception:
        platform_manager = None

    # Handle named folder aliases
    for folder_key in ["desktop", "documents", "downloads", "music", "videos", "pictures"]:
        prefix_patterns = [
            f"{folder_key}:",
            f"{folder_key}/",
            f"{folder_key}\\"
        ]
        for pref in prefix_patterns:
            if p_lower.startswith(pref):
                sub = p_str[len(pref):].lstrip("/\\")
                base = get_known_folder_dir(folder_key)
                return (base / sub).resolve()

        if p_lower == folder_key:
            return get_known_folder_dir(folder_key)

    # Handle ~ expansion
    if p_str.startswith("~"):
        return Path(p_str).expanduser().resolve()

    # Handle absolute paths
    p_obj = Path(p_str)
    if p_obj.is_absolute():
        return p_obj.resolve()

    # Check ALEE rule override for default root
    rule_cfg = get_active_rule_config()
    default_root = rule_cfg.get("default_root")
    if default_root and os.path.exists(default_root):
        return (Path(default_root) / p_str).resolve()

    # Relative to project workspace root
    return (BASE_WORKSPACE / p_str).resolve()


# Global tracking for entity context memory (most recent folder/file created or operated on)
_LAST_FILESYSTEM_TARGET: Optional[Path] = None


def get_last_filesystem_target() -> Optional[Path]:
    """Retrieves the most recently created or accessed filesystem path, consulting SQLite working_memory."""
    global _LAST_FILESYSTEM_TARGET
    if _LAST_FILESYSTEM_TARGET is not None and _LAST_FILESYSTEM_TARGET.exists():
        return _LAST_FILESYSTEM_TARGET

    # Fallback to persistent SQLite working_memory
    try:
        from core.evolution.storage import evolution_storage
        if evolution_storage:
            mem = evolution_storage.get_entity_memory("last_filesystem_target")
            if mem and mem.get("value"):
                p = Path(mem["value"])
                if p.exists():
                    _LAST_FILESYSTEM_TARGET = p
                    return p
    except Exception as e:
        logger.debug(f"[FILESYSTEM_CRUD] Working memory query notice: {e}")

    return _LAST_FILESYSTEM_TARGET


def set_last_filesystem_target(target: Optional[Union[str, Path]]) -> None:
    """Sets and persists the most recently created or accessed filesystem path in SQLite."""
    global _LAST_FILESYSTEM_TARGET
    if target is None:
        _LAST_FILESYSTEM_TARGET = None
        try:
            from core.evolution.storage import evolution_storage
            if evolution_storage:
                evolution_storage.clear_entity_memory("last_filesystem_target")
        except Exception:
            pass
    else:
        resolved = Path(target).resolve()
        _LAST_FILESYSTEM_TARGET = resolved
        try:
            from core.evolution.storage import evolution_storage
            if evolution_storage:
                evolution_storage.set_entity_memory(
                    "last_filesystem_target",
                    str(resolved),
                    {"name": resolved.name, "is_dir": resolved.is_dir()}
                )
        except Exception as e:
            logger.debug(f"[FILESYSTEM_CRUD] Working memory set notice: {e}")


def clean_entity_name(name: str) -> str:
    """Strips trailing and embedded generic entity nouns (folder, directory, file) and command verbs."""
    if not name:
        return ""
    txt = str(name).strip()
    txt = re.sub(r"^(?:can\s+you\s+|please\s+|could\s+you\s+)?(?:trash|recycle|delete|remove|open|create|make)\s+(?:the\s+|a\s+)?", "", txt, flags=re.IGNORECASE).strip()
    txt = re.sub(r"^(?:folder|directory|file)\s+(?:called|named|with\s+(?:the\s+)?name|by\s+(?:the\s+)?name|name)?\s*", "", txt, flags=re.IGNORECASE).strip()
    txt = re.sub(r"^(?:called|named|with\s+(?:the\s+)?name|by\s+(?:the\s+)?name|name)\s+", "", txt, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(folder|directory|file)\b", "", txt, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" ,'\"")
    return cleaned


def find_or_resolve_target(
    target: Union[str, Path],
    runtime: Optional[Any] = None
) -> Optional[Path]:
    """Resolves target names or pronouns using universal search and Entity Context Memory.

    Search Order:
      1. Entity Context: Check runtime._last_filesystem_target or _LAST_FILESYSTEM_TARGET
         (if target is a pronoun 'it', 'this', 'that', or matches the last target's name/stem).
      2. Direct path: If target is already an existing path (absolute or relative to current dir).
      3. Desktop / target (OneDrive Desktop and local user Desktop).
      4. Documents / target.
      5. Workspace / cwd / target.
    """
    last_t = getattr(runtime, "_last_filesystem_target", None) or get_last_filesystem_target()

    if not target:
        if last_t and Path(last_t).exists():
            return Path(last_t)
        return None

    target_str = str(target).strip()
    clean_name = clean_entity_name(target_str)

    # 1. Check Entity Context Memory (pronouns or exact match with last target)
    pronoun_tokens = {"it", "this", "that", "the", "the folder", "the file", "the directory", "the item", ""}
    if target_str.lower() in pronoun_tokens or clean_name.lower() in pronoun_tokens:
        if last_t and Path(last_t).exists():
            return Path(last_t)

    if last_t and Path(last_t).exists():
        if clean_name.lower() in [last_t.name.lower(), last_t.stem.lower()]:
            return Path(last_t)

    # 2. Check if clean_name or target_str directly exists
    for candidate in [clean_name, target_str]:
        if candidate:
            p = Path(candidate)
            if p.is_absolute() and p.exists():
                return p
            if (BASE_WORKSPACE / p).exists():
                return BASE_WORKSPACE / p
            if p.exists():
                return p.resolve()

    # 3. Check Desktop (OneDrive & local)
    desktop_dir = get_desktop_dir()
    for name_candidate in [clean_name, target_str]:
        if not name_candidate:
            continue
        p_desk = desktop_dir / name_candidate
        if p_desk.exists():
            return p_desk
        p_home_desk = Path.home() / "Desktop" / name_candidate
        if p_home_desk.exists():
            return p_home_desk
        if "." not in name_candidate:
            for ext in [".txt", ".py", ".json", ".log", ".md"]:
                if (desktop_dir / f"{name_candidate}{ext}").exists():
                    return desktop_dir / f"{name_candidate}{ext}"
                if (p_home_desk.parent / f"{name_candidate}{ext}").exists():
                    return p_home_desk.parent / f"{name_candidate}{ext}"

    # 4. Check Documents
    docs_dir = get_known_folder_dir("documents")
    for name_candidate in [clean_name, target_str]:
        if not name_candidate:
            continue
        p_docs = docs_dir / name_candidate
        if p_docs.exists():
            return p_docs
        p_home_docs = Path.home() / "Documents" / name_candidate
        if p_home_docs.exists():
            return p_home_docs
        if "." not in name_candidate:
            for ext in [".txt", ".py", ".json", ".log", ".md"]:
                if (docs_dir / f"{name_candidate}{ext}").exists():
                    return docs_dir / f"{name_candidate}{ext}"

    # 5. Check BASE_WORKSPACE / current dir
    for name_candidate in [clean_name, target_str]:
        if not name_candidate:
            continue
        p_ws = BASE_WORKSPACE / name_candidate
        if p_ws.exists():
            return p_ws
        if "." not in name_candidate:
            for ext in [".txt", ".py", ".json", ".log", ".md"]:
                if (BASE_WORKSPACE / f"{name_candidate}{ext}").exists():
                    return BASE_WORKSPACE / f"{name_candidate}{ext}"

    # Fallback: resolve canonical path even if it doesn't currently exist
    return resolve_path(clean_name or target_str)


def create_folder(path: Union[str, Path], destination: Optional[str] = None) -> Dict[str, Any]:
    """Creates directories recursively (mkdir(parents=True, exist_ok=True))."""
    t0 = time.perf_counter()
    try:
        target = resolve_path(path, destination=destination)
        target.mkdir(parents=True, exist_ok=True)
        set_last_filesystem_target(target)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        msg = f"Created directory '{target.name}' at {target}."
        logger.info(f"[FILESYSTEM_CRUD] {msg} ({elapsed_ms:.2f}ms)")
        return {
            "success": True,
            "path": str(target),
            "latency_ms": round(elapsed_ms, 2),
            "message": msg
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        err_msg = f"Failed to create directory '{path}': {e}"
        logger.error(f"[FILESYSTEM_CRUD] {err_msg}")
        return {
            "success": False,
            "path": str(path),
            "latency_ms": round(elapsed_ms, 2),
            "message": err_msg
        }


def create_file(
    path: Union[str, Path],
    content: str = "",
    allow_overwrite: bool = True
) -> Dict[str, Any]:
    """Creates a file with parent directory auto-creation and UTF-8 encoding."""
    t0 = time.perf_counter()
    try:
        target = resolve_path(path)
        if target.exists() and not allow_overwrite:
            return {
                "success": False,
                "path": str(target),
                "message": f"File '{target.name}' already exists and allow_overwrite=False."
            }

        # Ensure parent directories exist
        target.parent.mkdir(parents=True, exist_ok=True)

        target.write_text(content, encoding="utf-8")
        set_last_filesystem_target(target)
        bytes_written = len(content.encode("utf-8"))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        msg = f"Created file '{target.name}' ({bytes_written} bytes) at {target}."
        logger.info(f"[FILESYSTEM_CRUD] {msg} ({elapsed_ms:.2f}ms)")
        return {
            "success": True,
            "path": str(target),
            "bytes_written": bytes_written,
            "latency_ms": round(elapsed_ms, 2),
            "message": msg
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        err_msg = f"Failed to create file '{path}': {e}"
        logger.error(f"[FILESYSTEM_CRUD] {err_msg}")
        return {
            "success": False,
            "path": str(path),
            "bytes_written": 0,
            "latency_ms": round(elapsed_ms, 2),
            "message": err_msg
        }


def read_file(
    path: Union[str, Path],
    max_lines: int = 200,
    max_bytes: int = 500_000
) -> Dict[str, Any]:
    """Reads text safely, preventing runaway reads of massive files or binary crashes."""
    t0 = time.perf_counter()
    rule_cfg = get_active_rule_config()
    max_lines = rule_cfg.get("max_read_lines", max_lines)
    max_bytes = rule_cfg.get("max_read_bytes", max_bytes)

    try:
        target = resolve_path(path)
        if not target.exists():
            return {
                "success": False,
                "path": str(target),
                "content": "",
                "message": f"File '{target.name}' does not exist."
            }

        if target.is_dir():
            return {
                "success": False,
                "path": str(target),
                "content": "",
                "message": f"Path '{target.name}' is a directory, not a file."
            }

        # Check file size
        file_size = target.stat().st_size
        truncated = False

        lines = []
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    truncated = True
                    break
                lines.append(line)

        content = "".join(lines)
        if len(content.encode("utf-8")) > max_bytes:
            content = content[:max_bytes]
            truncated = True

        elapsed_ms = (time.perf_counter() - t0) * 1000
        msg = f"Read {len(lines)} lines from '{target.name}'" + (" (truncated)" if truncated else "") + "."
        return {
            "success": True,
            "path": str(target),
            "content": content,
            "total_lines": len(lines),
            "file_size_bytes": file_size,
            "truncated": truncated,
            "latency_ms": round(elapsed_ms, 2),
            "message": msg
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        err_msg = f"Failed to read file '{path}': {e}"
        logger.error(f"[FILESYSTEM_CRUD] {err_msg}")
        return {
            "success": False,
            "path": str(path),
            "content": "",
            "total_lines": 0,
            "truncated": False,
            "latency_ms": round(elapsed_ms, 2),
            "message": err_msg
        }


def list_directory(
    path: Union[str, Path, None] = None,
    pattern: str = "*",
    max_items: int = 100
) -> Dict[str, Any]:
    """Lists files and folders with sizes, counts, and last modified timestamps."""
    t0 = time.perf_counter()
    try:
        target = resolve_path(path)
        if not target.exists() or not target.is_dir():
            return {
                "success": False,
                "path": str(target),
                "items": [],
                "total_items": 0,
                "files_count": 0,
                "dirs_count": 0,
                "message": f"Directory '{target}' does not exist."
            }

        items = []
        files_count = 0
        dirs_count = 0

        # Scan directory
        for entry in target.glob(pattern):
            if len(items) >= max_items:
                break
            try:
                stat = entry.stat()
                is_dir = entry.is_dir()
                if is_dir:
                    dirs_count += 1
                else:
                    files_count += 1

                items.append({
                    "name": entry.name,
                    "is_dir": is_dir,
                    "size_bytes": 0 if is_dir else stat.st_size,
                    "modified_time": stat.st_mtime,
                    "path": str(entry)
                })
            except Exception:
                continue

        elapsed_ms = (time.perf_counter() - t0) * 1000
        msg = f"Found {len(items)} items ({files_count} files, {dirs_count} folders) in '{target.name}'."
        return {
            "success": True,
            "path": str(target),
            "items": items,
            "total_items": len(items),
            "files_count": files_count,
            "dirs_count": dirs_count,
            "latency_ms": round(elapsed_ms, 2),
            "message": msg
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        err_msg = f"Failed to list directory '{path}': {e}"
        logger.error(f"[FILESYSTEM_CRUD] {err_msg}")
        return {
            "success": False,
            "path": str(path),
            "items": [],
            "total_items": 0,
            "files_count": 0,
            "dirs_count": 0,
            "latency_ms": round(elapsed_ms, 2),
            "message": err_msg
        }


def modify_file(
    path: Union[str, Path],
    content: str,
    mode: str = "append"
) -> Dict[str, Any]:
    """Updates file contents with automatic .bak backup creation before writing.

    Args:
        path: Path to target file.
        content: String content to append or overwrite.
        mode: 'append' or 'overwrite'.

    Returns:
        dict: Execution status, backup path, and bytes written.
    """
    t0 = time.perf_counter()
    mode = mode.lower().strip()
    if mode not in ["append", "overwrite"]:
        mode = "append"

    try:
        target = resolve_path(path)
        backup_path_str = None

        # If file exists, create backup copy first
        if target.exists() and target.is_file():
            bak_path = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, bak_path)
            backup_path_str = str(bak_path)
            logger.info(f"[FILESYSTEM_CRUD] Created backup '{bak_path.name}' before {mode}.")
        else:
            # Auto-create parent directory if new file
            target.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            target.write_text(content, encoding="utf-8")

        bytes_written = len(content.encode("utf-8"))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        msg = f"Modified file '{target.name}' ({mode}, {bytes_written} bytes written)."
        return {
            "success": True,
            "path": str(target),
            "backup_path": backup_path_str,
            "bytes_written": bytes_written,
            "mode": mode,
            "latency_ms": round(elapsed_ms, 2),
            "message": msg
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        err_msg = f"Failed to modify file '{path}': {e}"
        logger.error(f"[FILESYSTEM_CRUD] {err_msg}")
        return {
            "success": False,
            "path": str(path),
            "backup_path": None,
            "bytes_written": 0,
            "mode": mode,
            "latency_ms": round(elapsed_ms, 2),
            "message": err_msg
        }


def trash_item(path: Union[str, Path], runtime: Optional[Any] = None) -> Dict[str, Any]:
    """Uses send2trash to safely move files or folders to the Windows Recycle Bin.

    NEVER permanently deletes via os.remove or rmtree without explicit recovery fallback.
    """
    t0 = time.perf_counter()
    try:
        resolved = find_or_resolve_target(path, runtime=runtime)
        if not resolved or not resolved.exists():
            target_display = str(path)
            clean_display = clean_entity_name(target_display)
            return {
                "success": False,
                "path": str(resolved) if resolved else target_display,
                "message": f"Item '{clean_display or Path(target_display).name}' does not exist to trash."
            }

        target = resolved
        target_str = str(target)
        if SEND2TRASH_AVAILABLE and send2trash is not None:
            send2trash.send2trash(target_str)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            msg = f"Moved '{target.name}' from {target_str} to Recycle Bin."
            logger.info(f"[FILESYSTEM_CRUD] {msg} ({elapsed_ms:.2f}ms)")
            if get_last_filesystem_target() == target:
                set_last_filesystem_target(None)
            if runtime and getattr(runtime, "_last_filesystem_target", None) == target:
                runtime._last_filesystem_target = None
            return {
                "success": True,
                "path": target_str,
                "recycled": True,
                "latency_ms": round(elapsed_ms, 2),
                "message": msg
            }
        else:
            # Fallback to local .trash quarantine directory instead of permanent destruction
            quarantine_dir = BASE_WORKSPACE / ".recycle_quarantine"
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            dest = quarantine_dir / f"{target.name}_{int(time.time())}"
            shutil.move(target_str, str(dest))
            elapsed_ms = (time.perf_counter() - t0) * 1000
            msg = f"Moved '{target.name}' from {target_str} to safe quarantine folder (send2trash unavailable)."
            logger.warning(f"[FILESYSTEM_CRUD] {msg}")
            if get_last_filesystem_target() == target:
                set_last_filesystem_target(None)
            if runtime and getattr(runtime, "_last_filesystem_target", None) == target:
                runtime._last_filesystem_target = None
            return {
                "success": True,
                "path": target_str,
                "quarantine_path": str(dest),
                "recycled": False,
                "latency_ms": round(elapsed_ms, 2),
                "message": msg
            }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        err_msg = f"Failed to trash item '{path}': {e}"
        logger.error(f"[FILESYSTEM_CRUD] {err_msg}")
        return {
            "success": False,
            "path": str(path),
            "latency_ms": round(elapsed_ms, 2),
            "message": err_msg
        }

