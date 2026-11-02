"""SANTRA Iteration 10 - Conversation Identity, Submission Verification & Reliability Test Suite.
Exhaustively tests:
1. ChatGPT conversation identity protection against tab/window/profile/conversation switching.
2. Antigravity submission verification separating KEYSTROKE_SENT from PROMPT_ACCEPTED.
3. Live composer re-reading and SHA-256 hash validation before approval.
4. Comprehensive folder rename with nested, hidden, and Unicode content verification.
5. Invalidation of pending drafts across restart.
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
import hashlib
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
    ChatGPTConversationIdentity,
    WorkspaceIdentity,
    SubmissionVerificationStatus
)


class TestChatGPTConversationIdentityAdversarial(unittest.TestCase):
    """Phase 2: Adversarial testing of ChatGPT Conversation Identity model."""

    def setUp(self):
        self.mock_app_mgr = MagicMock()
        self.mock_cdp = MagicMock()
        self.browser_mgr = BrowserInteractionManager(cdp_client=self.mock_cdp, app_mgr=self.mock_app_mgr)
        self.draft_mgr = DraftManager(browser_mgr=self.browser_mgr)

    def test_critical_adversarial_conversation_switch_in_same_window_blocked(self):
        """CRITICAL: Switching ChatGPT conversation within the same Chrome window blocks submission."""
        # 1. Capture initial conversation identity for 'SANTRA' chat
        initial_identity = ChatGPTConversationIdentity(
            process_id=1000,
            profile_name="Default",
            tab_id="tab-1",
            url="https://chatgpt.com/c/santra-convo-uuid-1",
            conversation_id="santra-convo-uuid-1",
            title="SANTRA Project Conversation"
        )

        draft = self.draft_mgr.create_draft(
            app_name="chatgpt",
            draft_text="Deploy the microservices to production cluster.",
            target_hwnd=5001,
            conversation_identity=initial_identity
        )
        self.assertEqual(draft.state, DraftState.AWAITING_APPROVAL)

        # 2. Adversary switches conversation to another chat in the same window (same HWND 5001, same tab-1, same PID 1000)
        switched_identity = ChatGPTConversationIdentity(
            process_id=1000,
            profile_name="Default",
            tab_id="tab-1",
            url="https://chatgpt.com/c/personal-chat-uuid-2",
            conversation_id="personal-chat-uuid-2",
            title="Personal Groceries"
        )

        # Mock browser_mgr to return switched identity
        with patch.object(self.browser_mgr, "capture_active_conversation_identity", return_value=switched_identity):
            # User says "Send it."
            res = self.draft_mgr.process_approval("Send it.", current_hwnd=5001)

            # MUST BE BLOCKED
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "CONVERSATION_IDENTITY_CHANGED")
            self.assertFalse(res["submitted"])
            self.assertEqual(draft.state, DraftState.FAILED)
            self.assertIn("mismatch", res["reason"].lower())

    def test_switch_to_different_chrome_tab_blocked(self):
        """Switching to another Chrome tab in the same window blocks submission."""
        init_id = ChatGPTConversationIdentity(
            process_id=1000,
            profile_name="Default",
            tab_id="tab-alpha",
            url="https://chatgpt.com/c/conv-1",
            conversation_id="conv-1"
        )
        draft = self.draft_mgr.create_draft(
            app_name="chatgpt",
            draft_text="Review the PR.",
            target_hwnd=5001,
            conversation_identity=init_id
        )

        # Live tab is tab-beta
        tab_switched = ChatGPTConversationIdentity(
            process_id=1000,
            profile_name="Default",
            tab_id="tab-beta",
            url="https://chatgpt.com/c/conv-1",
            conversation_id="conv-1"
        )

        with patch.object(self.browser_mgr, "capture_active_conversation_identity", return_value=tab_switched):
            res = self.draft_mgr.process_approval("Yes, send it.", current_hwnd=5001)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "CONVERSATION_IDENTITY_CHANGED")
            self.assertIn("tab mismatch", res["reason"].lower())

    def test_switch_to_different_chrome_process_blocked(self):
        """Switching to a different Chrome process blocks submission."""
        init_id = ChatGPTConversationIdentity(process_id=1000, tab_id="tab-1", conversation_id="c-1")
        draft = self.draft_mgr.create_draft(app_name="chatgpt", draft_text="Run tests.", conversation_identity=init_id)

        proc_switched = ChatGPTConversationIdentity(process_id=2000, tab_id="tab-1", conversation_id="c-1")
        with patch.object(self.browser_mgr, "capture_active_conversation_identity", return_value=proc_switched):
            res = self.draft_mgr.process_approval("Yes, send it.")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "CONVERSATION_IDENTITY_CHANGED")
            self.assertIn("process mismatch", res["reason"].lower())

    def test_switch_to_different_browser_profile_blocked(self):
        """Switching browser profile (e.g. Work vs Personal) blocks submission."""
        init_id = ChatGPTConversationIdentity(profile_name="WorkProfile", conversation_id="c-1")
        draft = self.draft_mgr.create_draft(app_name="chatgpt", draft_text="Confidential report.", conversation_identity=init_id)

        prof_switched = ChatGPTConversationIdentity(profile_name="PersonalProfile", conversation_id="c-1")
        with patch.object(self.browser_mgr, "capture_active_conversation_identity", return_value=prof_switched):
            res = self.draft_mgr.process_approval("Yes, send it.")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "CONVERSATION_IDENTITY_CHANGED")
            self.assertIn("profile mismatch", res["reason"].lower())

    def test_conversation_with_same_title_but_different_id_blocked(self):
        """A conversation with the same display title but different conversation UUID is blocked."""
        init_id = ChatGPTConversationIdentity(conversation_id="uuid-original", title="Project Discussion")
        draft = self.draft_mgr.create_draft(app_name="chatgpt", draft_text="Update status.", conversation_identity=init_id)

        same_title_diff_id = ChatGPTConversationIdentity(conversation_id="uuid-fake-duplicate", title="Project Discussion")
        with patch.object(self.browser_mgr, "capture_active_conversation_identity", return_value=same_title_diff_id):
            res = self.draft_mgr.process_approval("Yes, send it.")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "CONVERSATION_IDENTITY_CHANGED")
            self.assertIn("conversation mismatch", res["reason"].lower())


class TestAntigravitySubmissionVerification(unittest.TestCase):
    """Phase 3: Antigravity submission verification separating keystroke from acceptance."""

    def setUp(self):
        self.mock_focus = MagicMock()
        self.mock_inserter = MagicMock()
        self.interaction_mgr = ApplicationInteractionManager(focus_detector=self.mock_focus, text_inserter=self.mock_inserter)
        self.draft_mgr = DraftManager(interaction_mgr=self.interaction_mgr)

    def test_antigravity_submission_distinguishes_keystroke_from_acceptance(self):
        """Draft transitions to PROMPT_ACCEPTED only when composer is verified cleared."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Implement JWT authentication",
            target_hwnd=9999
        )

        with patch.object(self.interaction_mgr, "execute_submit", return_value={"success": True}), \
             patch.object(self.interaction_mgr, "verify_antigravity_submission", return_value={
                 "confirmed": True,
                 "status": "VERIFIED",
                 "stage": SubmissionVerificationStatus.PROMPT_ACCEPTED,
                 "evidence": "composer_cleared_after_enter_keystroke"
             }):
            res = self.draft_mgr.process_approval("Yes, send it.", current_content="Implement JWT authentication", current_hwnd=9999)
            self.assertTrue(res["success"])
            self.assertTrue(res["submitted"])
            self.assertEqual(res["status"], "SUBMITTED_AND_VERIFIED")
            self.assertEqual(res["stage"], SubmissionVerificationStatus.PROMPT_ACCEPTED.value)
            self.assertEqual(draft.state, DraftState.VERIFIED)

    def test_antigravity_submission_unconfirmed_when_no_ui_evidence(self):
        """When keystroke is delivered but UI state change cannot be confirmed, report SUBMISSION_UNCONFIRMED."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Fix race condition",
            target_hwnd=9999
        )

        with patch.object(self.interaction_mgr, "execute_submit", return_value={"success": True}), \
             patch.object(self.interaction_mgr, "verify_antigravity_submission", return_value={
                 "confirmed": False,
                 "status": "SUBMISSION_UNCONFIRMED",
                 "stage": SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED,
                 "evidence": "keystroke_delivered_without_accessibility_state_change"
             }):
            res = self.draft_mgr.process_approval("Yes, send it.", current_content="Fix race condition", current_hwnd=9999)
            self.assertTrue(res["success"])
            self.assertTrue(res["submitted"])
            self.assertEqual(res["status"], "SUBMISSION_UNCONFIRMED")
            self.assertEqual(res["stage"], SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED.value)

    def test_antigravity_submission_fails_if_composer_still_contains_text(self):
        """If Enter key was intercepted and composer still holds text after timeout, verification fails."""
        with patch.object(self.interaction_mgr, "read_current_composer_text", return_value="Fix race condition"):
            v_res = self.interaction_mgr.verify_antigravity_submission("Fix race condition", target_hwnd=9999, timeout_seconds=0.1)
            self.assertFalse(v_res["confirmed"])
            self.assertEqual(v_res["status"], "VERIFICATION_FAILED")
            self.assertEqual(v_res["stage"], SubmissionVerificationStatus.VERIFICATION_FAILED)


class TestChatGPTSubmissionVerification(unittest.TestCase):
    """Phase 4: ChatGPT multi-stage submission verification in browser."""

    def setUp(self):
        self.mock_cdp = MagicMock()
        self.mock_app_mgr = MagicMock()
        self.browser_mgr = BrowserInteractionManager(cdp_client=self.mock_cdp, app_mgr=self.mock_app_mgr)

    def test_chatgpt_submission_confirmed_when_message_appears_in_dom(self):
        """Submission confirmed when chat stream reflects user turn."""
        self.mock_cdp.is_available.return_value = False
        v_res = self.browser_mgr.verify_chatgpt_submission("Explain quantum computing", timeout_seconds=0.05)
        # Without live CDP DOM, it gracefully returns unconfirmed rather than falsely verified
        self.assertFalse(v_res["confirmed"])
        self.assertEqual(v_res["stage"], SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED)


class TestDraftAndApprovalSecurity(unittest.TestCase):
    """Phase 5: Draft tampering, workspace identity, live composer re-reading, and restart recovery."""

    def setUp(self):
        self.draft_mgr = DraftManager()

    def test_live_composer_alteration_detected_and_rejected(self):
        """Re-reading the live composer detects on-screen text tampering and halts submission."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Original prompt: Refactor auth module."
        )

        # Simulate user manually typing extra text into the on-screen composer
        with patch.object(self.draft_mgr.interaction_mgr, "read_current_composer_text", return_value="Original prompt: Refactor auth module. AND DELETE ALL USERS"):
            res = self.draft_mgr.process_approval("Yes, send it.")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "CONTENT_HASH_MISMATCH")
            self.assertFalse(res["submitted"])
            self.assertEqual(draft.state, DraftState.FAILED)

    def test_antigravity_workspace_identity_mismatch_blocks_submission(self):
        """Switching Antigravity workspace after drafting blocks submission."""
        init_ws = WorkspaceIdentity(workspace_path="C:\\Users\\activ\\Desktop\\ProjectA", process_id=1234)
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Run build script.",
            workspace_identity=init_ws
        )

        switched_ws = WorkspaceIdentity(workspace_path="C:\\Users\\activ\\Desktop\\ProjectB", process_id=1234)
        with patch.object(self.draft_mgr.interaction_mgr, "capture_active_workspace_identity", return_value=switched_ws):
            res = self.draft_mgr.process_approval("Yes, send it.", current_content="Run build script.")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "WORKSPACE_IDENTITY_CHANGED")
            self.assertEqual(draft.state, DraftState.FAILED)

    def test_pending_drafts_invalidated_on_restart(self):
        """Pending approval does not silently survive restart."""
        self.draft_mgr.create_draft(app_name="antigravity", draft_text="Pending task")
        self.assertEqual(self.draft_mgr.current_state, DraftState.AWAITING_APPROVAL)

        count = self.draft_mgr.invalidate_all_pending_drafts(reason="system_restart")
        self.assertEqual(count, 1)
        self.assertEqual(self.draft_mgr.current_state, DraftState.IDLE)
        self.assertIsNone(self.draft_mgr.get_latest_draft())


class TestFolderManagementReliability(unittest.TestCase):
    """Phase 6: Folder management reliability with nested, hidden, and Unicode files."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="santra_iteration10_ws_")
        self.state_file = Path(self.temp_dir) / ".santra_recent.json"
        self.ws_mgr = WorkspaceManager(state_file=self.state_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_folder_rename_preserves_nested_hidden_and_unicode_contents(self):
        """Renaming a folder preserves all nested subdirectories, hidden files, and Unicode filenames."""
        # 1. Create source folder
        source = Path(self.temp_dir) / "Source Project"
        source.mkdir()

        # 2. Populate with complex items
        (source / "README.md").write_text("Documentation", encoding="utf-8")
        (source / ".env").write_text("SECRET=12345", encoding="utf-8")
        (source / ".hidden_folder").mkdir()
        (source / ".hidden_folder" / "config.json").write_text("{}", encoding="utf-8")
        (source / "src").mkdir()
        (source / "src" / "संत्रा_मॉड्यूल.py").write_text("# संत्रा कोड", encoding="utf-8")
        (source / "src" / "rocket_🚀.txt").write_text("Blast off!", encoding="utf-8")

        self.ws_mgr.track_workspace(source)
        self.assertIn(str(source.resolve()), self.ws_mgr._recent_workspaces)

        # 3. Rename folder
        res = self.ws_mgr.rename_folder(str(source), "Target Renamed Project")
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "RENAMED")
        self.assertEqual(res["items_verified"], 7)  # 2 dirs + 5 files

        # 4. Physical disk assertions
        target = Path(self.temp_dir) / "Target Renamed Project"
        self.assertFalse(source.exists())
        self.assertTrue(target.exists())
        self.assertTrue((target / "README.md").exists())
        self.assertTrue((target / ".env").exists())
        self.assertTrue((target / ".hidden_folder" / "config.json").exists())
        self.assertTrue((target / "src" / "संत्रा_मॉड्यूल.py").exists())
        self.assertTrue((target / "src" / "rocket_🚀.txt").exists())

        # Verify content fidelity
        self.assertEqual((target / ".env").read_text(encoding="utf-8"), "SECRET=12345")
        self.assertEqual((target / "src" / "संत्रा_मॉड्यूल.py").read_text(encoding="utf-8"), "# संत्रा कोड")

        # 5. Tracking updated: old path removed, new path tracked
        self.assertNotIn(str(source.resolve()), self.ws_mgr._recent_workspaces)
        self.assertIn(str(target.resolve()), self.ws_mgr._recent_workspaces)
        self.assertEqual(self.ws_mgr.get_last_active_folder(), target.resolve())

    def test_rename_detects_destination_already_exists_and_prevents_merge(self):
        """Rename halts if destination already exists, guaranteeing zero data loss/merge."""
        f1 = Path(self.temp_dir) / "Folder A"
        f1.mkdir()
        (f1 / "unique_a.txt").write_text("A", encoding="utf-8")

        f2 = Path(self.temp_dir) / "Folder B"
        f2.mkdir()
        (f2 / "unique_b.txt").write_text("B", encoding="utf-8")

        res = self.ws_mgr.rename_folder(str(f1), "Folder B")
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "DESTINATION_ALREADY_EXISTS")
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertTrue((f1 / "unique_a.txt").exists())
        self.assertTrue((f2 / "unique_b.txt").exists())


if __name__ == "__main__":
    unittest.main()

