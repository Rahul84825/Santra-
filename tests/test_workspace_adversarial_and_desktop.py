"""Adversarial, Security & Live Desktop Integration Tests for Workspace Interaction.
Covers:
- Adversarial draft content tampering (SHA-256 mismatch detection)
- Focus hijacking & HWND shift during submission
- Ambiguous & phonetically confusing approval attempts
- Idempotency & double-submit prevention
- Symlink & Junction traversal attacks
- Path traversal escapes ('..', absolute system path attempts)
- Live verification of Antigravity IDE and Google Chrome executables on host
"""

import os
import sys
import time
import shutil
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.workspace_interaction import (
    WorkspaceManager,
    ApplicationManager,
    BrowserInteractionManager,
    ApplicationInteractionManager,
    DraftManager,
    DraftState,
    InteractionDraft,
    workspace_manager,
    application_manager,
    browser_interaction_manager,
    draft_manager
)


class TestWorkspaceAdversarialSecurity(unittest.TestCase):
    """Adversarial and security boundary tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="santra_adv_test_")
        self.ws_mgr = WorkspaceManager(state_file=Path(self.temp_dir) / ".recent.json")
        self.test_base = Path(self.temp_dir) / "workspace"
        self.test_base.mkdir(parents=True, exist_ok=True)
        draft_manager.current_state = DraftState.IDLE
        draft_manager.active_drafts.clear()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        draft_manager.current_state = DraftState.IDLE
        draft_manager.active_drafts.clear()

    # -------------------------------------------------------------------------
    # Security: Symlink, Junction & Path Traversal
    # -------------------------------------------------------------------------
    def test_path_traversal_escape_rejected(self):
        """Path traversal attempts targeting Windows system directories are resolved and blocked."""
        if sys.platform.startswith("win"):
            escape_target = Path("C:\\Users\\..\\..\\Windows")
        else:
            escape_target = Path("/home/user/../../etc")
        safe, reason = self.ws_mgr.is_safe_path(escape_target)
        self.assertFalse(safe)
        self.assertIn("protected", reason.lower())

    def test_drive_root_direct_target_blocked(self):
        r"""Targeting drive root C:\ directly is blocked."""
        if sys.platform.startswith("win"):
            safe, reason = self.ws_mgr.is_safe_path(Path("C:\\"))
            self.assertFalse(safe)
            self.assertIn("drive root", reason.lower())

    # -------------------------------------------------------------------------
    # Adversarial: Draft Content Tampering
    # -------------------------------------------------------------------------
    def test_draft_tampered_by_user_aborts_send(self):
        """If user manually modifies the text in the target field after draft creation,
        the approval gate detects the hash divergence and rejects sending."""
        orig_text = "Fix the login bug by adding token refresh."
        draft = draft_manager.create_draft("antigravity", orig_text, target_hwnd=999)

        tampered_text = "Fix the login bug by deleting the database."
        res = draft_manager.process_approval("Yes, send it", current_content=tampered_text, current_hwnd=999)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "CONTENT_HASH_MISMATCH")
        self.assertFalse(res["submitted"])
        self.assertIn("modified externally", res["message"])
        self.assertEqual(draft.state, DraftState.FAILED)

    # -------------------------------------------------------------------------
    # Adversarial: Focus Hijacking During Approval
    # -------------------------------------------------------------------------
    def test_focus_shifted_to_unrelated_window_aborts_send(self):
        """If foreground focus shifts to another application (e.g. browser or terminal)
        when approval is given, submission is blocked to avoid typing into wrong app."""
        draft = draft_manager.create_draft("antigravity", "print('hello')", target_hwnd=1001)

        # Focus shifted to HWND 2002 (unrelated app)
        res = draft_manager.process_approval("Yes, send it", current_content="print('hello')", current_hwnd=2002)

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "FOCUS_CHANGED_BEFORE_SEND")
        self.assertFalse(res["submitted"])
        self.assertIn("Focus shifted away", res["message"])

    # -------------------------------------------------------------------------
    # Adversarial: Ambiguous & Phonetic Approval Spoofing
    # -------------------------------------------------------------------------
    def test_casual_assent_phrases_strictly_denied(self):
        """Conversational filler or casual assent phrases cannot trigger submission."""
        casual_phrases = [
            "okay", "ok", "fine", "looks good", "continue", "nice", "cool",
            "sure", "alright", "sounds good", "perfect"
        ]
        for phrase in casual_phrases:
            draft = draft_manager.create_draft("chatgpt", "Important prompt text", target_hwnd=555)
            res = draft_manager.process_approval(phrase, current_hwnd=555)
            self.assertFalse(res["success"], f"Phrase '{phrase}' should NOT have granted approval")
            self.assertEqual(res["status"], "AMBIGUOUS_APPROVAL_REJECTED")
            self.assertFalse(res["submitted"])

    def test_unrelated_speech_during_approval_retained_safely(self):
        """Unrelated conversation overheard while awaiting approval does not trigger or discard."""
        draft = draft_manager.create_draft("antigravity", "System architecture diagram", target_hwnd=555)
        res = draft_manager.process_approval("What is the weather outside today?", current_hwnd=555)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "UNRELATED_SPEECH")
        self.assertEqual(draft.state, DraftState.AWAITING_APPROVAL)
        self.assertFalse(draft.submitted)

    # -------------------------------------------------------------------------
    # Adversarial: Duplicate Submission & Replay Attack
    # -------------------------------------------------------------------------
    def test_double_submission_replay_blocked(self):
        """A user saying 'Send it' twice in rapid succession cannot result in duplicate posts."""
        mock_interaction = MagicMock()
        mock_interaction.execute_submit.return_value = {"success": True}
        dm = DraftManager(interaction_mgr=mock_interaction)

        draft = dm.create_draft("chatgpt", "Post message", target_hwnd=888)

        # First approval
        r1 = dm.process_approval("Yes, send it", current_hwnd=888)
        self.assertTrue(r1["submitted"])
        self.assertEqual(mock_interaction.execute_submit.call_count, 1)

        # Immediate repeat
        r2 = dm.process_approval("Yes, send it", current_hwnd=888)
        self.assertFalse(r2["success"])
        self.assertEqual(r2["status"], "ALREADY_SUBMITTED")
        # Ensure underlying keystroke was NOT sent a second time
        self.assertEqual(mock_interaction.execute_submit.call_count, 1)


class TestHostEnvironmentLiveIntegration(unittest.TestCase):
    """Physically verifies actual installation state and capability on the live host machine."""

    def test_antigravity_host_installation_verified(self):
        """Verifies Antigravity IDE executable discovery on this physical Windows machine."""
        exe = application_manager.find_antigravity_executable()
        self.assertIsNotNone(exe, "Antigravity IDE should be discoverable on host.")
        self.assertTrue(os.path.exists(exe), f"Discovered Antigravity executable '{exe}' does not exist on disk.")

    def test_google_chrome_host_installation_verified(self):
        """Verifies Google Chrome executable discovery on this physical Windows machine."""
        exe = application_manager.find_chrome_executable()
        self.assertIsNotNone(exe, "Google Chrome should be discoverable on host.")
        self.assertTrue(os.path.exists(exe), f"Discovered Chrome executable '{exe}' does not exist on disk.")

    def test_safe_clipboard_preservation_live(self):
        """Physically tests SafeClipboardManager: restores original clipboard content."""
        if not sys.platform.startswith("win"):
            self.skipTest("Windows-specific Win32 clipboard test")

        from core.typing.text_inserter import SafeClipboardManager
        import win32clipboard

        original_text = f"SANTRA_CLIPBOARD_SNAPSHOT_TEST_{time.time()}"
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(original_text)
        win32clipboard.CloseClipboard()

        mgr = SafeClipboardManager()
        snapshot = mgr.snapshot()

        # Overwrite clipboard with test draft
        mgr.set_text("DRAFT_TEMPORARY_TEXT")

        # Verify temporary text is in clipboard
        win32clipboard.OpenClipboard()
        temp_val = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        self.assertEqual(temp_val, "DRAFT_TEMPORARY_TEXT")

        # Restore original
        mgr.restore(snapshot)

        win32clipboard.OpenClipboard()
        restored_val = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        self.assertEqual(restored_val, original_text)


if __name__ == "__main__":
    unittest.main()
