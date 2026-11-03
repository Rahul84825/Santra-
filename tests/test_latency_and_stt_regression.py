"""
tests/test_latency_and_stt_regression.py
Master Regression Suite for Latency, STT Integrity, Routing, and AI Provider Reliability.
"""

import unittest
import time
from unittest.mock import MagicMock, patch

from core.transcript_validator import (
    transcript_validator,
    ValidationStatus,
    ValidationResult
)
from core.ai.intelligence_router import (
    intelligence_router,
    MODE_FAST_LOCAL,
    MODE_QUESTION,
    MODE_REASONING
)
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from core.ai.agent_brain import agent_brain
from ui.state_machine import JarvisUIState, map_runtime_status_to_ui_state, STATE_CONFIGS


class TestSTTValidationRegression(unittest.TestCase):
    """Verifies Whisper hallucination filters and transcript validation."""

    def test_repetitive_wakeword_hallucination_loop(self):
        """Whisper looping 'Santra' 75 times ending in 'Sant' must be rejected."""
        loop_text = " ".join(["santra"] * 75) + " sant"
        res = transcript_validator.validate(loop_text)
        self.assertFalse(res.is_valid, "75x wake-word loop must not be considered valid")
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_high_compression_ratio_rejection(self):
        """Metadata compression_ratio > 2.4 must be rejected even if text looks short."""
        res = transcript_validator.validate("Hello world hello world hello world", compression_ratio=3.8)
        self.assertFalse(res.is_valid, "compression_ratio > 2.4 must be rejected")
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_low_info_fragment_rejection(self):
        """Trailing fragments like 'And else.' or 'Or else.' must be rejected."""
        for frag in ["And else.", "Or else.", "Else.", "Then.", "And."]:
            res = transcript_validator.validate(frag)
            self.assertFalse(res.is_valid, f"Fragment '{frag}' must be rejected")
            self.assertEqual(res.status, ValidationStatus.FRAGMENT)

    def test_pure_wakeword_address_rejection(self):
        """Stand-alone wake-word addresses should not trigger conversation/AI loop."""
        for address in ["Santra", "Hey Santra", "Samtra", "Jarvis"]:
            res = transcript_validator.validate(address)
            self.assertFalse(res.is_valid, f"Pure wake-word '{address}' must be rejected")
            self.assertEqual(res.status, ValidationStatus.WAKEWORD_ONLY)

    def test_valid_knowledge_queries_pass(self):
        """Valid queries must pass cleanly with status VALID."""
        queries = [
            "Explain how gradient descent works in detail",
            "What is the capital of France?",
            "Open Chrome and search for machine learning papers",
            "What time is it right now?"
        ]
        for q in queries:
            res = transcript_validator.validate(q)
            self.assertTrue(res.is_valid, f"Query '{q}' must pass validation")
            self.assertEqual(res.status, ValidationStatus.VALID)


class TestRoutingLatencyAndLayerRegression(unittest.TestCase):
    """Verifies zero-overhead routing (<100ms) and correct layer targeting."""

    @classmethod
    def setUpClass(cls):
        # Warm up lazy modules (COM UIAutomation, DomainManager, AppDiscovery)
        intelligence_router.route("warmup router")

    def test_local_commands_remain_local_under_100ms(self):
        """OS commands must route to Layer 1/2 deterministic in <100ms."""
        local_commands = [
            "open chrome",
            "set volume to 50",
            "take a screenshot",
            "what time is it",
            "open notepad"
        ]
        for cmd in local_commands:
            t0 = time.perf_counter()
            req = intelligence_router.route(cmd)
            duration_ms = (time.perf_counter() - t0) * 1000

            self.assertLess(duration_ms, 100.0, f"Routing '{cmd}' took {duration_ms:.2f}ms (target < 100ms)")
            self.assertIn(req.layer, [1, 2], f"Local command '{cmd}' routed to Layer {req.layer}")
            self.assertNotEqual(req.mode, MODE_REASONING)

    def test_informational_explanation_routes_to_conversational(self):
        """Explanation requests must route to Layer 2 Conversational, not Layer 3 OS automation."""
        query = "Explain quicksort in detail."
        t0 = time.perf_counter()
        req = intelligence_router.route(query)
        duration_ms = (time.perf_counter() - t0) * 1000

        self.assertLess(duration_ms, 100.0, f"Routing '{query}' took {duration_ms:.2f}ms (target < 100ms)")
        self.assertEqual(req.layer, 2, "Explanation must route to Layer 2")
        self.assertEqual(req.mode, MODE_QUESTION)
        self.assertIn("quicksort", req.target.lower())


class TestAIProviderLatencyAndReliability(unittest.TestCase):
    """Verifies timeout behavior, error attribution, and cancellation in NvidiaNemotronProvider."""

    def setUp(self):
        self.provider = NvidiaNemotronProvider(api_key="nvapi-mock-test-key", model="nvidia/nemotron-3.5-bolt-e4b")

    def test_read_timeout_does_not_blame_credentials(self):
        """A ReadTimeout must result in AI_PROVIDER_TIMEOUT, never CREDENTIALS_INVALID."""
        import requests
        with patch("requests.post", side_effect=requests.exceptions.ReadTimeout("Read timed out")):
            res = self.provider.generate_response([{"role": "user", "content": "Test prompt"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "AI_PROVIDER_TIMEOUT")
            self.assertNotEqual(self.provider.get_last_error_code(), "CREDENTIALS_INVALID")

    def test_401_results_in_credentials_invalid(self):
        """HTTP 401 must properly attribute CREDENTIALS_INVALID."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized: Invalid API key"
        with patch("requests.post", return_value=mock_resp):
            res = self.provider.generate_response([{"role": "user", "content": "Test prompt"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "CREDENTIALS_INVALID")

    def test_prompt_cancellation_aborts_immediately(self):
        """A cancelled request must abort before or during processing with CANCELLED code."""
        res = self.provider.generate_response([{"role": "user", "content": "Test prompt"}], is_cancelled=lambda: True)
        self.assertIsNone(res)
        self.assertEqual(self.provider.get_last_error_code(), "CANCELLED")

    def test_agent_brain_truthful_timeout_error_message(self):
        """AgentBrain must formulate a truthful timeout message rather than generic credentials error."""
        with patch.object(agent_brain.provider_manager, "get_last_error_code", return_value="AI_PROVIDER_TIMEOUT"):
            with patch.object(agent_brain.provider_manager, "generate_response", return_value=None):
                result = agent_brain.reason_and_execute("Explain general relativity")
                text = result["text"].lower()
                self.assertTrue("time limit" in text or "timed out" in text, f"Expected timeout explanation, got: {result['text']}")
                self.assertNotIn("verify your credentials", text)

    def test_reasoning_and_thought_tags_stripped(self):
        """Thinking tags like <thought>...</thought> and 'Here's a thinking process:' must be stripped."""
        raw_output = "<thought>Thinking about the question...</thought>The speed of light is 299,792,458 m/s."
        cleaned = self.provider._clean_reasoning_from_content(raw_output)
        self.assertEqual(cleaned, "The speed of light is 299,792,458 m/s.")

        raw_output2 = "Here's a thinking process:\n\n1. Analyze question\n\n**Final Answer:** 42"
        cleaned2 = self.provider._clean_reasoning_from_content(raw_output2)
        self.assertEqual(cleaned2, "42")


class TestUIStateMachineTransitions(unittest.TestCase):
    """Verifies that new granular states are recognized and configured."""

    def test_granular_states_in_ui_state_enum(self):
        """JarvisUIState must contain the new granular latency states."""
        self.assertTrue(hasattr(JarvisUIState, "WAITING_FOR_NVIDIA"))
        self.assertTrue(hasattr(JarvisUIState, "STREAMING_RESPONSE"))
        self.assertTrue(hasattr(JarvisUIState, "ROUTING"))
        self.assertTrue(hasattr(JarvisUIState, "VALIDATING_INPUT"))
        self.assertTrue(hasattr(JarvisUIState, "TIMED_OUT"))
        self.assertTrue(hasattr(JarvisUIState, "COMPLETED"))

    def test_map_runtime_status_mapping(self):
        """map_runtime_status_to_ui_state must map status strings to authoritative enum."""
        self.assertEqual(map_runtime_status_to_ui_state("WAITING_FOR_NVIDIA"), JarvisUIState.WAITING_FOR_NVIDIA)
        self.assertEqual(map_runtime_status_to_ui_state("STREAMING_RESPONSE"), JarvisUIState.STREAMING_RESPONSE)
        self.assertEqual(map_runtime_status_to_ui_state("ROUTING"), JarvisUIState.ROUTING)
        self.assertEqual(map_runtime_status_to_ui_state("VALIDATING_INPUT"), JarvisUIState.VALIDATING_INPUT)
        self.assertEqual(map_runtime_status_to_ui_state("TIMED_OUT"), JarvisUIState.TIMED_OUT)
        self.assertEqual(map_runtime_status_to_ui_state("COMPLETED"), JarvisUIState.COMPLETED)

    def test_visual_configs_exist_for_all_states(self):
        """Every JarvisUIState must have an entry in STATE_CONFIGS."""
        for state in JarvisUIState:
            self.assertIn(state, STATE_CONFIGS, f"Missing STATE_CONFIGS entry for {state}")


if __name__ == "__main__":
    unittest.main()
