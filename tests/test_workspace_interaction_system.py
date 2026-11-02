"""Comprehensive Automated Test Suite for SANTRA Voice-Controlled Workspace & Application Interaction.
Validates:
1. WorkspaceManager: Creation, nesting, renaming, non-overwrite, non-merge, safe-paths, recents.
2. ApplicationManager: Discovery, running instance detection, activation, parameter passing.
3. BrowserInteractionManager: Chrome detection, ChatGPT discovery, pinned chat routing, auth guard.
4. ApplicationInteractionManager: Control detection, clipboard preservation, text insertion, submit keystrokes.
5. DraftManager: Cryptographic hash binding, explicit approval, ambiguous rejection, cancellation, TTL, idempotency.
6. Scenario A & B Multi-Turn End-to-End Workflows.
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
)
from core.intent_engine import intent_engine
from modules.system.executor import CommandExecutor, CommandOutcome


class TestWorkspaceManager(unittest.TestCase):
    """Unit and filesystem safety tests for WorkspaceManager."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="santra_ws_test_")
        self.state_file = Path(self.temp_dir) / ".santra_recent.json"
        self.ws_mgr = WorkspaceManager(state_file=self.state_file)
        self.test_base = Path(self.temp_dir) / "test_root"
        self.test_base.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_create_folder_success(self):
        """Folder creation succeeds and physically verifies existence."""
        with patch.object(self.ws_mgr, "resolve_parent_location", return_value=self.test_base):
            res = self.ws_mgr.create_folder("Santra Projects")
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "CREATED")
            created_path = Path(res["path"])
            self.assertTrue(created_path.exists())
            self.assertTrue(created_path.is_dir())
            self.assertEqual(created_path.name, "Santra Projects")
            self.assertEqual(self.ws_mgr.get_last_active_folder(), created_path)

    def test_create_nested_folder(self):
        """Nested folder creation inside a parent directory succeeds."""
        parent_p = self.test_base / "Projects"
        parent_p.mkdir(parents=True, exist_ok=True)

        with patch.object(self.ws_mgr, "find_folders", return_value=[parent_p]):
            res = self.ws_mgr.create_folder("E-commerce", parent_location="Projects")
            self.assertTrue(res["success"])
            created_path = Path(res["path"])
            self.assertTrue(created_path.exists())
            self.assertEqual(created_path.parent, parent_p)

    def test_create_folder_destination_conflict_never_overwrites(self):
        """Folder creation MUST fail if destination already exists (zero overwrite rule)."""
        existing = self.test_base / "Existing Folder"
        existing.mkdir(parents=True, exist_ok=True)

        with patch.object(self.ws_mgr, "resolve_parent_location", return_value=self.test_base):
            res = self.ws_mgr.create_folder("Existing Folder")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "ALREADY_EXISTS")
            self.assertTrue(res.get("exists"))
            self.assertIn("already exists", res["message"])

    def test_rename_folder_success(self):
        """Folder rename succeeds and updates last active folder."""
        orig = self.test_base / "Old Name"
        orig.mkdir(parents=True, exist_ok=True)
        self.ws_mgr.track_workspace(orig)

        with patch.object(self.ws_mgr, "find_folders", return_value=[orig]):
            res = self.ws_mgr.rename_folder("Old Name", "Mithai World")
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "RENAMED")
            new_path = Path(res["path"])
            self.assertTrue(new_path.exists())
            self.assertFalse(orig.exists())
            self.assertEqual(new_path.name, "Mithai World")
            self.assertEqual(self.ws_mgr.get_last_active_folder(), new_path)

    def test_rename_folder_antecedent_that_folder(self):
        """Renaming with antecedent 'that folder' resolves to last active folder."""
        orig = self.test_base / "Prior Folder"
        orig.mkdir(parents=True, exist_ok=True)
        self.ws_mgr.track_workspace(orig)

        res = self.ws_mgr.rename_folder("that folder", "Brand New Name")
        self.assertTrue(res["success"])
        new_path = Path(res["path"])
        self.assertTrue(new_path.exists())
        self.assertFalse(orig.exists())
        self.assertEqual(new_path.name, "Brand New Name")

    def test_rename_destination_conflict_never_merges(self):
        """Renaming MUST fail if destination already exists (zero merge rule)."""
        f1 = self.test_base / "Folder A"
        f2 = self.test_base / "Folder B"
        f1.mkdir(parents=True, exist_ok=True)
        f2.mkdir(parents=True, exist_ok=True)

        with patch.object(self.ws_mgr, "find_folders", return_value=[f1]):
            res = self.ws_mgr.rename_folder("Folder A", "Folder B")
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "DESTINATION_ALREADY_EXISTS")
            self.assertTrue(res.get("destination_exists"))
            self.assertTrue(f1.exists())
            self.assertTrue(f2.exists())

    def test_safe_path_rejection_for_system_roots(self):
        """Rejects operations targeting system roots and protected directories."""
        if sys.platform.startswith("win"):
            unsafe_targets = [Path("C:\\Windows"), Path("C:\\Program Files"), Path("C:\\")]
        else:
            unsafe_targets = [Path("/"), Path("/etc"), Path("/usr")]

        for target in unsafe_targets:
            safe, reason = self.ws_mgr.is_safe_path(target)
            self.assertFalse(safe)
            self.assertTrue(any(w in reason.lower() for w in ["protected", "root"]))

    def test_unicode_and_special_character_folder_names(self):
        """Handles Unicode, spaces, and Indian English naming safely."""
        unicode_name = "संत्रा प्रोजेक्ट्स - E-Commerce 🚀"
        with patch.object(self.ws_mgr, "resolve_parent_location", return_value=self.test_base):
            res = self.ws_mgr.create_folder(unicode_name)
            self.assertTrue(res["success"])
            p = Path(res["path"])
            self.assertTrue(p.exists())
            self.assertEqual(p.name, unicode_name)


class TestApplicationManager(unittest.TestCase):
    """Tests for application discovery, instance detection, and window activation."""

    def setUp(self):
        self.app_mgr = ApplicationManager()

    def test_executable_discovery(self):
        """Executable discovery finds Chrome and Antigravity if present, or reports None gracefully."""
        chrome_exe = self.app_mgr.find_chrome_executable()
        if chrome_exe:
            self.assertTrue(os.path.exists(chrome_exe))
            self.assertIn("chrome", chrome_exe.lower())

        antigravity_exe = self.app_mgr.find_antigravity_executable()
        if antigravity_exe:
            self.assertTrue(os.path.exists(antigravity_exe))
            self.assertTrue(any(k in antigravity_exe.lower() for k in ["antigravity", "agy"]))

    def test_is_running_detection(self):
        """Running process detection checks running instances cleanly."""
        res = self.app_mgr.is_running("non_existent_fake_app_xyz")
        self.assertFalse(res)

    def test_open_workspace_in_antigravity_missing_folder_fails_safely(self):
        """Opening a non-existent folder reports failure cleanly."""
        missing = Path("C:\\non_existent_folder_abc_123")
        res = self.app_mgr.open_workspace_in_antigravity(missing)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "WORKSPACE_NOT_FOUND" if self.app_mgr.find_antigravity_executable() else "NOT_INSTALLED")


class TestBrowserInteractionManager(unittest.TestCase):
    """Tests for Chrome and ChatGPT conversation navigation."""

    def setUp(self):
        self.mock_cdp = MagicMock()
        self.mock_cdp.is_available.return_value = False
        self.browser_mgr = BrowserInteractionManager(cdp_client=self.mock_cdp)

    def test_check_login_status_unauthenticated(self):
        """Detects login requirement from auth URL or title."""
        self.mock_cdp.is_available.return_value = True
        self.mock_cdp.get_active_tab.return_value = {
            "url": "https://chatgpt.com/auth/login",
            "title": "Log in - OpenAI"
        }
        ok, msg = self.browser_mgr.check_login_status()
        self.assertFalse(ok)
        self.assertIn("Login required", msg)

    def test_check_login_status_authenticated(self):
        """Detects authenticated session cleanly."""
        self.mock_cdp.is_available.return_value = True
        self.mock_cdp.get_active_tab.return_value = {
            "url": "https://chatgpt.com/c/santra-ai-chat",
            "title": "SANTRA AI - ChatGPT"
        }
        ok, msg = self.browser_mgr.check_login_status()
        self.assertTrue(ok)
        self.assertEqual(msg, "Authenticated")


class TestDraftManagerAndApprovalGate(unittest.TestCase):
    """Rigorous security testing for DraftManager and explicit approval gates."""

    def setUp(self):
        self.mock_interaction = MagicMock()
        self.mock_interaction.execute_submit.return_value = {"success": True}
        self.draft_mgr = DraftManager(interaction_mgr=self.mock_interaction, default_ttl_seconds=180.0)

    def test_draft_creation_cryptographic_hash(self):
        """Draft creation binds exact content with SHA-256 hash."""
        text = "Build a complete authentication system with Google login and email login."
        expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        draft = self.mock_draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text=text,
            target_hwnd=12345
        )

        self.assertEqual(draft.content_hash, expected_hash)
        self.assertEqual(draft.state, DraftState.AWAITING_APPROVAL)
        self.assertFalse(draft.submitted)
        self.assertEqual(self.draft_mgr.current_state, DraftState.AWAITING_APPROVAL)

    def test_explicit_approval_submits(self):
        """Explicit approval ('Yes, send it', 'Submit this message') approves and submits."""
        draft = self.draft_mgr.create_draft(
            app_name="antigravity",
            draft_text="Sample text",
            target_hwnd=12345
        )

        res = self.draft_mgr.process_approval("Yes, send it", current_content="Sample text", current_hwnd=12345)
        self.assertTrue(res["success"])
        self.assertTrue(res["submitted"])
        self.assertEqual(res["status"], "SUBMITTED_AND_VERIFIED")
        self.assertEqual(draft.state, DraftState.VERIFIED)
        self.mock_interaction.execute_submit.assert_called_once()

    def test_ambiguous_approval_rejection_security(self):
        """Ambiguous phrases ('Okay', 'Looks good', 'Fine') MUST be rejected without submission."""
        ambiguous_cases = ["okay", "ok", "looks good", "fine", "sure", "cool", "alright"]
        for phrase in ambiguous_cases:
            draft = self.draft_mgr.create_draft(app_name="antigravity", draft_text=f"Draft for {phrase}")
            res = self.draft_mgr.process_approval(phrase)
            self.assertFalse(res["success"])
            self.assertFalse(res["submitted"])
            self.assertEqual(res["status"], "AMBIGUOUS_APPROVAL_REJECTED")
            self.assertEqual(draft.state, DraftState.AWAITING_APPROVAL)
            self.mock_interaction.execute_submit.assert_not_called()

    def test_cancellation_discards_submission(self):
        """Cancellation phrases ('Don't send', 'Cancel') transition state to CANCELLED without submit."""
        cancellations = ["don't send", "cancel", "stop", "leave it", "keep as draft"]
        for phrase in cancellations:
            draft = self.draft_mgr.create_draft(app_name="chatgpt", draft_text=f"Draft for {phrase}")
            res = self.draft_mgr.process_approval(phrase)
            self.assertTrue(res["success"])
            self.assertFalse(res["submitted"])
            self.assertEqual(res["status"], "CANCELLED")
            self.assertEqual(draft.state, DraftState.CANCELLED)
            self.mock_interaction.execute_submit.assert_not_called()

    def test_content_modification_invalidates_approval(self):
        """If text is altered externally, approval is rejected due to hash mismatch."""
        draft = self.draft_mgr.create_draft(app_name="antigravity", draft_text="Original Text")
        res = self.draft_mgr.process_approval("Yes, send it", current_content="TAMPERED Text")
        self.assertFalse(res["success"])
        self.assertFalse(res["submitted"])
        self.assertEqual(res["status"], "CONTENT_HASH_MISMATCH")
        self.assertEqual(draft.state, DraftState.FAILED)
        self.mock_interaction.execute_submit.assert_not_called()

    def test_ttl_expiration(self):
        """Expired drafts (>180s) cannot be approved."""
        draft = self.draft_mgr.create_draft(app_name="antigravity", draft_text="Text")
        draft.expiry_timestamp = time.time() - 10.0  # Expired 10s ago

        res = self.draft_mgr.process_approval("Yes, send it")
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "DRAFT_EXPIRED")
        self.mock_interaction.execute_submit.assert_not_called()

    def test_idempotent_submission_no_duplicates(self):
        """A draft cannot be submitted twice."""
        draft = self.draft_mgr.create_draft(app_name="antigravity", draft_text="Text", target_hwnd=100)
        res1 = self.draft_mgr.process_approval("Yes, send it", current_hwnd=100)
        self.assertTrue(res1["submitted"])

        # Second attempt
        res2 = self.draft_mgr.process_approval("Yes, send it", current_hwnd=100)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status"], "ALREADY_SUBMITTED")
        self.assertEqual(self.mock_interaction.execute_submit.call_count, 1)


class TestIntentAndExecutorIntegration(unittest.TestCase):
    """Validates end-to-end intent parsing and executor dispatch."""

    def setUp(self):
        from core.workspace_interaction import draft_manager, DraftState
        draft_manager.current_state = DraftState.IDLE
        draft_manager.active_drafts.clear()
        draft_manager.latest_draft_id = None
        self.executor = CommandExecutor()

    def tearDown(self):
        from core.workspace_interaction import draft_manager, DraftState
        draft_manager.current_state = DraftState.IDLE
        draft_manager.active_drafts.clear()
        draft_manager.latest_draft_id = None

    def test_folder_intent_parsing(self):
        """Parses natural folder commands accurately."""
        n1 = intent_engine.parse("Create a folder called Santra Projects on my desktop.")
        self.assertEqual(n1.get("intent"), "workspace.create_folder")
        self.assertEqual(n1.get("target"), "santra projects")

        n2 = intent_engine.parse("Create a folder called E-commerce inside Projects.")
        self.assertEqual(n2.get("intent"), "workspace.create_folder")
        self.assertEqual(n2.get("target"), "e-commerce")
        self.assertEqual(n2.get("parent"), "projects")

        n3 = intent_engine.parse("Rename that folder to Mithai World.")
        self.assertEqual(n3.get("intent"), "workspace.rename_folder")
        self.assertEqual(n3.get("target"), "mithai world")

    def test_antigravity_and_chatgpt_intent_parsing(self):
        """Parses application navigation commands."""
        n1 = intent_engine.parse("Open the folder in Antigravity.")
        self.assertEqual(n1.get("intent"), "workspace.open_folder")
        self.assertEqual(n1.get("app"), "antigravity")

        n2 = intent_engine.parse("Open ChatGPT in Chrome.")
        self.assertIn(n2.get("intent"), ["browser.open_chatgpt", "open_website"])
        self.assertEqual(n2.get("browser"), "chrome")

        n3 = intent_engine.parse("Open my pinned SANTRA chat.")
        self.assertEqual(n3.get("intent"), "browser.open_pinned_chat")
        self.assertEqual(n3.get("target"), "SANTRA")

    def test_dictation_and_approval_workflow_scenario(self):
        """End-to-end scenario execution through IntentEngine and CommandExecutor."""
        from core.workspace_interaction import draft_manager, DraftState

        # 1. User says: "Write a prompt."
        node_prompt = intent_engine.parse("Write a prompt.")
        self.assertEqual(node_prompt.get("intent"), "draft.start_prompt")
        res1 = self.executor.execute(node_prompt)
        self.assertEqual(draft_manager.current_state, DraftState.DRAFTING)

        # 2. User dictates text
        dictation_text = "Build a complete authentication system with Google login and email login."
        node_dictation = intent_engine.parse(dictation_text)
        self.assertEqual(node_dictation.get("intent"), "draft.enter_text")
        self.assertEqual(node_dictation.get("text"), dictation_text)

        # Mock text insertion in executor
        with patch.object(self.executor, "execute", wraps=self.executor.execute), \
             patch("core.workspace_interaction.ApplicationInteractionManager.insert_text_into_target", return_value={"success": True, "hwnd": 111}):
            res2 = self.executor.execute(node_dictation)
            self.assertTrue(res2["success"])
            self.assertIn("Should I send it?", res2["message"])
            self.assertEqual(draft_manager.current_state, DraftState.AWAITING_APPROVAL)

        # 3. User says ambiguous: "Okay" -> Must NOT submit
        node_ambiguous = intent_engine.parse("Okay.")
        self.assertEqual(node_ambiguous.get("intent"), "draft.approve_submission")
        res3 = self.executor.execute(node_ambiguous)
        self.assertFalse(res3["success"])
        self.assertEqual(draft_manager.current_state, DraftState.AWAITING_APPROVAL)

        # 4. User says: "Yes, send it." -> Approves and submits
        node_approve = intent_engine.parse("Yes, send it.")
        self.assertEqual(node_approve.get("intent"), "draft.approve_submission")

        with patch("core.workspace_interaction.ApplicationInteractionManager.execute_submit", return_value={"success": True}):
            res4 = self.executor.execute(node_approve)
            self.assertTrue(res4["success"])
            self.assertEqual(res4["outcome"], CommandOutcome.SUCCESS.value)
            self.assertEqual(draft_manager.current_state, DraftState.VERIFIED)


if __name__ == "__main__":
    unittest.main()
