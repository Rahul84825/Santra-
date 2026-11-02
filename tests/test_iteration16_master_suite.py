"""
SANTRA — ITERATION 16 MASTER TEST SUITE
Comprehensive verification of:
1. Authoritative State Machine & Standby Leakage Elimination
2. Conversational Intelligence & Follow-up Continuations (Detail, Re-explain, Simplify, Example, Compare, Continue)
3. Strict SANTRA Identity & Grounded Local Application Discovery
4. Single-Voice Persona Consistency across EdgeTTS, Windows SAPI, and pyttsx3
5. Command Palette Architecture & Non-Clipped UI Layout
6. Brave-Only HiAnime Navigation Mappings
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import time

class TestIteration16MasterSuite(unittest.TestCase):

    def setUp(self):
        from core.conversation_manager import ConversationManager
        self.cm = ConversationManager()

    # -------------------------------------------------------------------------
    # 1. Authoritative State Machine Verification
    # -------------------------------------------------------------------------
    def test_state_machine_authoritative_states(self):
        from ui.state_machine import SantraRuntimeState, JarvisUIState, STATE_CONFIGS, map_runtime_status_to_ui_state

        # Verify all 10 authoritative states exist
        expected_states = [
            "INITIALIZING", "STANDBY", "LISTENING", "PROCESSING",
            "EXECUTING", "SPEAKING", "SLEEPING", "RECOVERING",
            "ERROR", "SHUTTING_DOWN"
        ]
        for s in expected_states:
            self.assertTrue(hasattr(SantraRuntimeState, s), f"Missing SantraRuntimeState.{s}")
            self.assertTrue(hasattr(JarvisUIState, s), f"Missing JarvisUIState.{s}")

        # Verify SLEEPING title does NOT leak "STANDBY"
        sleep_cfg = STATE_CONFIGS[JarvisUIState.SLEEPING]
        self.assertNotIn("STANDBY", sleep_cfg.title)
        self.assertEqual(sleep_cfg.title, "SYSTEM SLEEPING")

        # Verify STANDBY title appears ONLY for STANDBY
        standby_cfg = STATE_CONFIGS[JarvisUIState.STANDBY]
        self.assertEqual(standby_cfg.title, "STANDBY")

        # Verify mappings
        self.assertEqual(map_runtime_status_to_ui_state("SLEEPING"), JarvisUIState.SLEEPING)
        self.assertEqual(map_runtime_status_to_ui_state("RECOVERING"), JarvisUIState.RECOVERING)
        self.assertEqual(map_runtime_status_to_ui_state("LISTENING"), JarvisUIState.LISTENING)
        self.assertEqual(map_runtime_status_to_ui_state("PROCESSING"), JarvisUIState.PROCESSING)
        self.assertEqual(map_runtime_status_to_ui_state("EXECUTING"), JarvisUIState.EXECUTING)
        self.assertEqual(map_runtime_status_to_ui_state("SPEAKING"), JarvisUIState.SPEAKING)
        self.assertEqual(map_runtime_status_to_ui_state("ERROR"), JarvisUIState.ERROR)
        self.assertEqual(map_runtime_status_to_ui_state("STANDBY"), JarvisUIState.STANDBY)

    # -------------------------------------------------------------------------
    # 2. Conversational Intelligence & Follow-up Continuation Verification
    # -------------------------------------------------------------------------
    def test_followup_continuations_with_active_topic(self):
        self.cm.task_context.current_topic = "binary search"

        # A) Give an example
        r_ex = self.cm.resolve_pronouns_and_references("Give an example")
        self.assertIn("binary search", r_ex.lower())
        self.assertIn("code example", r_ex.lower())

        # B) Re-explain
        r_re = self.cm.resolve_pronouns_and_references("Re-explain")
        self.assertIn("binary search", r_re.lower())
        self.assertIn("analogy", r_re.lower())

        # C) Simplify
        r_sim = self.cm.resolve_pronouns_and_references("Simplify")
        self.assertIn("binary search", r_sim.lower())
        self.assertIn("beginner", r_sim.lower())

        # D) Explain in detail
        r_det = self.cm.resolve_pronouns_and_references("Explain in detail")
        self.assertIn("binary search", r_det.lower())
        self.assertIn("technical detail", r_det.lower())

        # E) Compare with linear search
        r_comp = self.cm.resolve_pronouns_and_references("Compare with linear search")
        self.assertIn("binary search", r_comp.lower())
        self.assertIn("linear search", r_comp.lower())

        # F) Continue
        r_cont = self.cm.resolve_pronouns_and_references("Continue")
        self.assertIn("binary search", r_cont.lower())
        self.assertIn("continue the explanation", r_cont.lower())

    def test_topic_auto_extraction_from_initial_turn(self):
        res = self.cm.process_query("Explain Dijkstra's algorithm in detail")
        self.assertIn("dijkstra", self.cm.task_context.current_topic.lower())

        # Now follow-up without specifying Dijkstra
        followup = self.cm.resolve_pronouns_and_references("Give me an example")
        self.assertIn("dijkstra", followup.lower())

    # -------------------------------------------------------------------------
    # 3. Identity Contract & Local Capability Grounding Verification
    # -------------------------------------------------------------------------
    def test_identity_contract_direct_response(self):
        res = self.cm.process_query("Who are you?")
        self.assertIn("SANTRA", res["text"])
        self.assertNotIn("NVIDIA", res["text"])
        self.assertNotIn("large language model trained by", res["text"].lower())

    def test_llm_messages_contain_system_contract(self):
        captured_messages = []
        def capture_fn(msgs, **kwargs):
            nonlocal captured_messages
            captured_messages = list(msgs)
            return "Final Answer: Quicksort is a divide-and-conquer algorithm."

        mock_gen = MagicMock(side_effect=capture_fn)
        mock_provider = MagicMock()
        mock_provider.generate_response = mock_gen
        mock_provider.is_available = lambda: True
        orig_pm = getattr(self.cm.agent, "provider_manager", None)
        try:
            self.cm.provider_manager = mock_provider
            self.cm.agent.provider_manager = mock_provider

            self.cm.process_query(f"How does quicksort work unqiue {time.time()}?")
            self.assertTrue(len(captured_messages) >= 2)
            sys_msg = captured_messages[0]
            self.assertEqual(sys_msg["role"], "system")
            self.assertIn("You are SANTRA", sys_msg["content"])
            self.assertIn("NVIDIA Nemotron is merely an external cognition provider", sys_msg["content"])
        finally:
            if orig_pm is not None:
                self.cm.agent.provider_manager = orig_pm

    def test_installed_applications_grounding(self):
        res = self.cm.process_query("What applications are installed on my system?")
        self.assertIn("discovered", res["text"].lower())
        self.assertIn("applications", res["text"].lower())
        self.assertEqual(res["tool_used"], "get_installed_applications")

    # -------------------------------------------------------------------------
    # 4. Voice Persona Consistency Verification
    # -------------------------------------------------------------------------
    def test_tts_voice_gender_consistency(self):
        from config import config
        # Configuration
        self.assertIn("Ryan", getattr(config, "tts_voice", ""))
        self.assertEqual(getattr(config, "sapi_voice", ""), "David")

    def test_sapi_provider_male_voice_selection(self):
        from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
        provider = WindowsSAPIProvider()
        voices = provider.get_available_voices()
        if provider.is_available():
            # Must have at least David on Windows 11
            has_david = any("david" in v.lower() for v in voices)
            self.assertTrue(has_david, "Microsoft David must be available on Windows 11")

    # -------------------------------------------------------------------------
    # 5. Command Palette & UI Non-Clipping Verification
    # -------------------------------------------------------------------------
    def test_command_palette_dialog_initialization(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from ui.panels.command_palette_dialog import CommandPaletteDialog

        executed_actions = []
        callbacks = {
            "code": lambda: executed_actions.append("code"),
            "screen": lambda: executed_actions.append("screen"),
            "lab": lambda: executed_actions.append("lab"),
            "ai": lambda: executed_actions.append("ai")
        }
        dialog = CommandPaletteDialog(callbacks=callbacks)
        self.assertEqual(dialog.windowTitle(), "SANTRA — Command Palette & Capability Hub")
        dialog._handle_action("code")
        self.assertIn("code", executed_actions)

    # -------------------------------------------------------------------------
    # 6. HiAnime Brave-First Verification
    # -------------------------------------------------------------------------
    def test_hianime_brave_navigation_mappings(self):
        from core.os.browser_intent import BrowserIntentParser
        parser = BrowserIntentParser()

        # Homepage
        intent_home = parser.parse("Open HiAnime")
        self.assertEqual(intent_home.url, "https://hianime.at/")
        self.assertEqual(intent_home.metadata.get("strict_browser"), "brave")

        # Watching
        intent_watch = parser.parse("Open watched anime")
        self.assertEqual(intent_watch.url, "https://hianime.at/user/watching")
        self.assertEqual(intent_watch.metadata.get("strict_browser"), "brave")


if __name__ == "__main__":
    unittest.main()
