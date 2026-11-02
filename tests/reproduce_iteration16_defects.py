"""
Defect Reproduction Script for Iteration 16.
Validates the presence of the 6 key defects prior to remediation:
1. Standby indicator present during SLEEP state.
2. TTS male/female voice mismatch between EdgeTTS (Ryan) and SAPI (Zira).
3. Follow-up topic loss ("Explain in detail", "Re-explain", "Give an example") in ConversationManager.
4. Missing canonical SANTRA identity contract in ConversationManager messages sent to LLM.
5. Lack of grounding for "What applications are installed on my system?" causing hallucination.
6. Bottom button layout crowding in MainWindow resulting in label clipping.
"""

import unittest
import json
from pathlib import Path

class TestIteration16DefectReproduction(unittest.TestCase):

    def test_defect_1_standby_label_in_sleeping_state(self):
        """Defect 1: Standby label appears when UI is in SLEEPING state."""
        from ui.state_machine import STATE_CONFIGS, JarvisUIState
        sleep_cfg = STATE_CONFIGS.get(JarvisUIState.SLEEPING)
        self.assertIsNotNone(sleep_cfg)
        # Bug: sleep_cfg.title has "STANDBY" in it ("SLEEP MODE // STANDBY")
        print(f"[REPRO 1] Sleep config title: '{sleep_cfg.title}'")
        self.assertIn("STANDBY", sleep_cfg.title, "Confirmed: SLEEPING state displays STANDBY")

    def test_defect_2_tts_voice_mismatch(self):
        """Defect 2: EdgeTTS is male (Ryan) but SAPI is female (Zira)."""
        from config import config
        edge_voice = getattr(config, "tts_voice", "")
        sapi_voice = getattr(config, "sapi_voice", "")
        print(f"[REPRO 2] Config tts_voice='{edge_voice}', sapi_voice='{sapi_voice}'")
        self.assertIn("Ryan", edge_voice, "EdgeTTS is configured with Ryan (male)")
        self.assertIn("Zira", sapi_voice, "SAPI is configured with Zira (female), causing gender flip on fallback!")

    def test_defect_3_followup_topic_loss(self):
        """Defect 3: Follow-up phrases like 'Give an example' or 'Re-explain' lose topic context."""
        from core.conversation_manager import ConversationManager
        cm = ConversationManager()
        # Set a topic manually or simulate a prior turn
        cm.task_context.current_topic = "binary search"
        
        # 'Give an example' does not contain 'it', 'this', or 'that'
        res1 = cm.resolve_pronouns_and_references("Give an example")
        print(f"[REPRO 3] 'Give an example' resolved to: '{res1}'")
        self.assertEqual(res1, "Give an example", "Confirmed: 'Give an example' is NOT resolved to 'binary search'")

        res2 = cm.resolve_pronouns_and_references("Re-explain")
        print(f"[REPRO 3] 'Re-explain' resolved to: '{res2}'")
        self.assertEqual(res2, "Re-explain", "Confirmed: 'Re-explain' is NOT resolved to 'binary search'")

        res3 = cm.resolve_pronouns_and_references("Explain in detail")
        print(f"[REPRO 3] 'Explain in detail' resolved to: '{res3}'")
        self.assertEqual(res3, "Explain in detail", "Confirmed: 'Explain in detail' is NOT resolved to 'binary search'")

    def test_defect_4_missing_santra_system_prompt_in_conversation_messages(self):
        """Defect 4: ConversationManager passes raw user message without SANTRA identity system prompt."""
        from core.conversation_manager import ConversationManager
        from unittest.mock import MagicMock
        cm = ConversationManager()
        mock_provider = MagicMock()
        captured_messages = []
        def mock_gen(msgs, **kwargs):
            nonlocal captured_messages
            captured_messages = list(msgs)
            return "I am a language model trained by NVIDIA."
        mock_provider.generate_response = mock_gen
        cm.provider_manager = mock_provider

        cm.process_query("Who are you?")
        print(f"[REPRO 4] Messages sent to LLM: {captured_messages}")
        # Check if system message exists
        has_sys = any(m.get("role") == "system" for m in captured_messages)
        self.assertFalse(has_sys, "Confirmed: No system prompt defining SANTRA identity is sent in conversation_manager!")

    def test_defect_5_application_discovery_not_wired_to_query(self):
        """Defect 5: 'What applications are installed on my system' does not query ApplicationDiscovery."""
        from core.ai.agent_brain import AgentBrain
        brain = AgentBrain()
        # If offline fallback is run for this query:
        res = brain._handle_offline_reasoning("what applications are installed on my system", 0.0)
        print(f"[REPRO 5] Brain response to 'what applications are installed': {res['text']}")
        # Currently falls back to: "I cannot perform AI reasoning while offline..." instead of listing discovered apps!
        self.assertIn("cannot perform AI reasoning", res["text"])

if __name__ == "__main__":
    unittest.main()

