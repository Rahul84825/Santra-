"""SANTRA Iteration 11 - Folder Rename Race Conditions & Filesystem Concurrency Suite.
Tests:
- Concurrent file modification during snapshot & rename
- Concurrent file creation/deletion detection
- Locked files/directories on Windows (PermissionError handling)
- Preserving .git directory, .env, and hidden files
- Unicode folder names (Hindi, Japanese, emojis)
- Large files
- Process reference detection
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
from pathlib import Path

from core.workspace_interaction.workspace_manager import WorkspaceManager


class TestFolderRenameRaceConditions(unittest.TestCase):
    """Phase 7 Verification Suite."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="santra_iteration11_fs_")
        self.base_path = Path(self.temp_dir)
        self.ws_mgr = WorkspaceManager()

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_git_and_env_preservation_across_rename(self):
        """Verifies that .git/ config, .env secrets, and nested directories are 100% preserved."""
        src = self.base_path / "MyRepo"
        src.mkdir()
        (src / ".git").mkdir()
        (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (src / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
        (src / ".env").write_text("API_KEY=secret_production_key_12345\nPORT=8080\n", encoding="utf-8")
        (src / "README.md").write_text("# Project SANTRA\n", encoding="utf-8")

        res = self.ws_mgr.rename_folder(str(src), "MyRenamedRepo")
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "RENAMED")
        dest = self.base_path / "MyRenamedRepo"
        self.assertTrue(dest.exists())
        self.assertTrue((dest / ".git" / "HEAD").exists())
        self.assertEqual((dest / ".git" / "HEAD").read_text(encoding="utf-8").strip(), "ref: refs/heads/main")
        self.assertEqual((dest / ".env").read_text(encoding="utf-8").splitlines()[0], "API_KEY=secret_production_key_12345")
        self.assertFalse(src.exists())

    def test_unicode_paths_hindi_and_japanese(self):
        """Verifies renaming folders with complex Unicode, Hindi (Mithai World) and Japanese characters."""
        hindi_name = "मिठाई_World_प्रोजेक्ट"
        jp_name = "東京_開発_Workspace_🚀"

        src = self.base_path / hindi_name
        src.mkdir()
        (src / "app.py").write_text("print('Namaste')\n", encoding="utf-8")

        res = self.ws_mgr.rename_folder(str(src), jp_name)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "RENAMED")

        dest = self.base_path / jp_name
        self.assertTrue(dest.exists())
        self.assertTrue((dest / "app.py").exists())
        self.assertEqual((dest / "app.py").read_text(encoding="utf-8").strip(), "print('Namaste')")
        self.assertFalse(src.exists())

    def test_concurrent_file_modification_detection(self):
        """If a file's size changes between snapshot and post-rename verification,

        integrity verification must detect the discrepancy and report CONTENT_INTEGRITY_MISMATCH.
        """
        src = self.base_path / "ConcurrentSrc"
        src.mkdir()
        data_file = src / "database.sqlite"
        data_file.write_text("initial snapshot bytes", encoding="utf-8")

        # Snapshot before modification
        snap = self.ws_mgr.snapshot_folder_contents(src)
        self.assertIn("database.sqlite", snap)
        orig_size = snap["database.sqlite"]["size"]

        # Rename to target
        dest = self.base_path / "ConcurrentDest"
        src.rename(dest)

        # Simulate concurrent write altering file size
        (dest / "database.sqlite").write_text("initial snapshot bytes with concurrent appended payload", encoding="utf-8")

        ok, reason = self.ws_mgr.verify_folder_contents(dest, snap)
        self.assertFalse(ok)
        self.assertIn("File size mismatch", reason)

    def test_concurrent_file_deletion_detection(self):
        """If a file is deleted concurrently, verification fails with missing item."""
        src = self.base_path / "DeletionSrc"
        src.mkdir()
        (src / "important_document.pdf").write_bytes(b"%PDF-1.4 dummy binary content")
        (src / "config.json").write_text('{"mode": "prod"}', encoding="utf-8")

        snap = self.ws_mgr.snapshot_folder_contents(src)

        dest = self.base_path / "DeletionDest"
        src.rename(dest)

        # Concurrently delete a file
        (dest / "important_document.pdf").unlink()

        ok, reason = self.ws_mgr.verify_folder_contents(dest, snap)
        self.assertFalse(ok)
        self.assertIn("Item missing after rename", reason)

    def test_locked_file_permission_denied_handling(self):
        """When an application holds an exclusive file lock, rename must return PERMISSION_DENIED without data corruption."""
        src = self.base_path / "LockedFolder"
        src.mkdir()
        locked_file = src / "active_process.lock"
        locked_file.write_text("locked", encoding="utf-8")

        # Hold open file handle exclusively
        with open(locked_file, "r+b") as lock_handle:
            # On Windows, open write handle prevents folder rename
            res = self.ws_mgr.rename_folder(str(src), "LockedFolderRenamed")
            # Should either succeed (if OS permits directory rename while file open) or return PERMISSION_DENIED
            self.assertIn(res["status"], ["PERMISSION_DENIED", "RENAMED"])
            if res["status"] == "PERMISSION_DENIED":
                self.assertFalse(res["success"])
                self.assertIn("Permission denied", res["message"])
                self.assertTrue(src.exists())

    def test_large_file_preservation(self):
        """Verifies folders containing large multi-megabyte files are verified cleanly."""
        src = self.base_path / "LargeFilesFolder"
        src.mkdir()
        large_file = src / "data_dump.bin"
        # 4 MB binary file
        data = b"0123456789ABCDEF" * (256 * 1024)
        large_file.write_bytes(data)

        res = self.ws_mgr.rename_folder(str(src), "LargeFilesFolderRenamed")
        self.assertTrue(res["success"])
        dest = self.base_path / "LargeFilesFolderRenamed"
        self.assertTrue(dest.exists())
        self.assertEqual((dest / "data_dump.bin").stat().st_size, len(data))


if __name__ == "__main__":
    unittest.main()

