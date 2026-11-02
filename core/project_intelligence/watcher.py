"""Lightweight Project File System Watcher for Incremental Indexing."""

import os
import time
import threading
import logging
from pathlib import Path
from typing import Dict, Set, Optional, Callable

from core.project_intelligence.scanner import project_scanner

logger = logging.getLogger("Jarvis.ProjectWatcher")


class ProjectWatcher:
    """Monitors watched project directories and triggers incremental indexing callbacks."""

    def __init__(self, check_interval_sec: float = 2.0):
        self.check_interval_sec = check_interval_sec
        self.watched_paths: Set[str] = set()
        self._file_mtimes: Dict[str, float] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_change_callbacks: list[Callable[[str, str], None]] = []

    def add_watch(self, directory_path: str):
        """Adds a project directory to monitor."""
        p = str(Path(directory_path).resolve())
        self.watched_paths.add(p)
        self._snapshot_directory(p)
        logger.info(f"[PROJECT_WATCHER] Watching directory '{p}'")

    def remove_watch(self, directory_path: str):
        """Removes a directory from monitoring."""
        p = str(Path(directory_path).resolve())
        self.watched_paths.discard(p)

    def on_file_changed(self, cb: Callable[[str, str], None]):
        """Registers a callback function `cb(file_path, change_type)`."""
        self._on_change_callbacks.append(cb)

    def _snapshot_directory(self, root_dir: str):
        """Records initial modification timestamps for all non-excluded files."""
        excludes = project_scanner.DEFAULT_EXCLUDES
        for current_root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in excludes and not d.startswith(".")]
            for f in files:
                f_path = os.path.join(current_root, f)
                try:
                    self._file_mtimes[f_path] = os.path.getmtime(f_path)
                except Exception:
                    pass

    def start(self):
        """Starts background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ProjectWatcherThread")
        self._thread.start()

    def stop(self):
        """Stops background monitoring loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _monitor_loop(self):
        """Polls file modification times incrementally."""
        while self._running:
            time.sleep(self.check_interval_sec)
            self.check_changes_once()

    def check_changes_once(self):
        """Executes a single synchronous polling pass to detect created, modified, and deleted files."""
        for root_dir in list(self.watched_paths):
            if not os.path.exists(root_dir):
                continue
            excludes = project_scanner.DEFAULT_EXCLUDES
            for current_root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if d not in excludes and not d.startswith(".")]
                for f in files:
                    f_path = os.path.join(current_root, f)
                    try:
                        mtime = os.path.getmtime(f_path)
                        prev_mtime = self._file_mtimes.get(f_path)
                        if prev_mtime is None:
                            self._file_mtimes[f_path] = mtime
                            self._notify(f_path, "created")
                        elif mtime > prev_mtime:
                            self._file_mtimes[f_path] = mtime
                            self._notify(f_path, "modified")
                    except Exception:
                        pass

            # Check for deleted files
            for f_path in list(self._file_mtimes.keys()):
                if f_path.startswith(root_dir) and not os.path.exists(f_path):
                    del self._file_mtimes[f_path]
                    self._notify(f_path, "deleted")

    def _notify(self, file_path: str, change_type: str):
        logger.debug(f"[PROJECT_WATCHER] Change detected ({change_type}): '{file_path}'")
        for cb in self._on_change_callbacks:
            try:
                cb(file_path, change_type)
            except Exception as e:
                logger.debug(f"[PROJECT_WATCHER] Callback error: {e}")


project_watcher = ProjectWatcher()

