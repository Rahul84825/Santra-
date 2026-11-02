import unittest
import time
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.ai.intelligence_router import (
    IntelligenceRouter,
    StructuredRequest,
    MODE_FAST_LOCAL,
    MODE_CONTEXT,
    MODE_REASONING,
    MODE_QUESTION,
    LAYER_1,
    LAYER_2,
    LAYER_3
)
from core.intent_engine import IntentEngine
from core.conversation_manager import ConversationManager
from core.jarvis_runtime import JarvisRuntime
from ui.state_machine import JarvisUIState

class TestZeroDelayRouting(unittest.TestCase):
    """End-to-End Latency, Fast Routing & Regression Verification Suite.
    Validates zero artificial 'understanding...' delay, fast deterministic execution,
    accurate educational answers, and streaming TTS delivery.
    """

    @classmethod
    def setUpClass(cls):
        cls.router = IntelligenceRouter()
        cls.intent_engine = IntentEngine()
        # Warmup router & intent engine
        cls.router.route("warm up jarvis")
        cls.router.route("What is my battery percentage?")
        cls.router.route("Open Chrome.")

    def setUp(self):
        self.runtime = JarvisRuntime()
        self.observed_states = []
        def _on_status_change(status):
            self.observed_states.append(status)
        self.runtime.register_observers(on_status_change=_on_status_change)

    def tearDown(self):
        try:
            self.runtime.shutdown()
        except Exception:
            pass

    # =========================================================================
    # 1. GREETINGS & SMALL TALK: "Hi Santra."
    # =========================================================================
    def test_scenario_1_greeting_hi_santra(self):
        """'Hi Santra.' -> Respond naturally and promptly without LLM tool analysis."""
        t0 = time.perf_counter()
        req = self.router.route("Hi Santra.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "GREETING")
        self.assertLess(route_ms, 35.0, f"Greeting routing exceeded 35ms ({route_ms:.2f}ms)")

        # Verify runtime execution does not trigger UNDERSTANDING state
        t_exec0 = time.perf_counter()
        res = self.runtime._process_single_command("Hi Santra.", speak=False)
        total_ms = (time.perf_counter() - t_exec0) * 1000

        self.assertTrue(res.get("success"))
        self.assertTrue(any(w in res.get("message", "") for w in ["Hello", "SANTRA", "Sir", "standing by"]))
        self.assertNotIn("UNDERSTANDING", self.observed_states, "UNDERSTANDING state flashed for greeting!")
        self.assertLess(total_ms, 80.0, f"Total execution exceeded 80ms ({total_ms:.2f}ms)")

    # =========================================================================
    # 2. CONVERSATIONAL INQUIRIES: "How are you?"
    # =========================================================================
    def test_scenario_2_conversational_how_are_you(self):
        """'How are you?' -> Give conversational response without unnecessary tool analysis."""
        t0 = time.perf_counter()
        req = self.router.route("How are you?")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "HOW_ARE_YOU")
        self.assertLess(route_ms, 35.0, f"How are you routing exceeded 35ms ({route_ms:.2f}ms)")

        t_exec0 = time.perf_counter()
        res = self.runtime._process_single_command("How are you?", speak=False)
        total_ms = (time.perf_counter() - t_exec0) * 1000

        self.assertTrue(res.get("success"))
        self.assertNotIn("UNDERSTANDING", self.observed_states)
        self.assertLess(total_ms, 50.0)

    # =========================================================================
    # 3. SOCIAL HUMOR: "Tell me a joke."
    # =========================================================================
    def test_scenario_3_social_humor_tell_me_a_joke(self):
        """'Tell me a joke.' -> Respond directly from social humor engine."""
        t0 = time.perf_counter()
        req = self.router.route("Tell me a joke.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "SOCIAL_HUMOR")
        self.assertLess(route_ms, 35.0)

        t_exec0 = time.perf_counter()
        res = self.runtime._process_single_command("Tell me a joke.", speak=False)
        total_ms = (time.perf_counter() - t_exec0) * 1000

        self.assertTrue(res.get("success"))
        self.assertTrue(len(res.get("message", "")) > 10)
        self.assertNotIn("UNDERSTANDING", self.observed_states)
        self.assertLess(total_ms, 50.0)

    # =========================================================================
    # 4. DETERMINISTIC COMMANDS: "Open Chrome."
    # =========================================================================
    def test_scenario_4_open_chrome(self):
        """'Open Chrome.' -> Execute application control tool directly without LLM."""
        t0 = time.perf_counter()
        req = self.router.route("Open Chrome.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "OPEN_APP")
        self.assertEqual(req.target, "chrome")
        self.assertLess(route_ms, 100.0)

        with patch.object(self.runtime.executor, "execute") as mock_exec:
            mock_exec.return_value = {"success": True, "action": "open_app", "message": "Google Chrome launched."}
            t_exec0 = time.perf_counter()
            res = self.runtime._process_single_command("Open Chrome.", speak=False)
            total_ms = (time.perf_counter() - t_exec0) * 1000

            mock_exec.assert_called()
            self.assertTrue(res.get("success"))
            self.assertNotIn("UNDERSTANDING", self.observed_states)
            self.assertIn("EXECUTING", self.observed_states)
            self.assertLess(total_ms, 150.0)

    # =========================================================================
    # 5. HARDWARE TELEMETRY: "What is my battery percentage?"
    # =========================================================================
    def test_scenario_5_battery_status_telemetry(self):
        """'What is my battery percentage?' -> Read real Windows battery telemetry without LLM delay."""
        t0 = time.perf_counter()
        req = self.router.route("What is my battery percentage?")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "SYSTEM_TELEMETRY")
        self.assertEqual(req.action, "battery_info")
        self.assertLess(route_ms, 100.0)

        t_exec0 = time.perf_counter()
        res = self.runtime._process_single_command("What is my battery percentage?", speak=False)
        total_ms = (time.perf_counter() - t_exec0) * 1000

        self.assertTrue(res.get("success"))
        self.assertIn("battery", res.get("message", "").lower())
        self.assertNotIn("UNDERSTANDING", self.observed_states)
        self.assertLess(total_ms, 150.0)

    # =========================================================================
    # 6. EDUCATIONAL EXPLANATIONS: "Explain binary search."
    # =========================================================================
    def test_scenario_6_explain_binary_search(self):
        """'Explain binary search.' -> Route to intelligence provider for substantive explanation."""
        t0 = time.perf_counter()
        req = self.router.route("Explain binary search.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertIn(req.layer, [LAYER_2, LAYER_3])
        self.assertIn(req.intent, ["COMPLEX_TASK", "informational_question"])
        self.assertLess(route_ms, 35.0)

        # Mock provider response to test runtime integration and substantive explanation delivery
        mock_explanation = "Binary search is an efficient search algorithm that finds the position of a target value within a sorted array in O(log n) time. It repeatedly divides the search interval in half."
        with patch.object(self.runtime.conversation_manager.provider_manager, "generate_response", return_value=mock_explanation):
            with patch.object(self.runtime.conversation_manager.agent.provider_manager, "generate_response", return_value=f"Final Answer: {mock_explanation}"):
                t_exec0 = time.perf_counter()
                res = self.runtime._process_single_command("Explain binary search.", speak=False)
                total_ms = (time.perf_counter() - t_exec0) * 1000

                self.assertTrue(res.get("success"))
                self.assertIn("binary search", res.get("message", "").lower())
                self.assertIn("O(log n)", res.get("message", ""))
                self.assertNotIn("UNDERSTANDING", self.observed_states)

    # =========================================================================
    # 7. PAGE ANALYSIS: "Analyze this Chrome page."
    # =========================================================================
    def test_scenario_7_analyze_chrome_page(self):
        """'Analyze this Chrome page.' -> Retrieve actual page content and analyze it."""
        t0 = time.perf_counter()
        req = self.router.route("Analyze this Chrome page.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "BROWSER_ACTION")
        self.assertEqual(req.action, "analyze_page")
        self.assertLess(route_ms, 100.0)

        with patch.object(self.runtime.executor, "execute") as mock_exec:
            mock_exec.return_value = {"success": True, "action": "analyze_page", "message": "Active page is 'Python.org'. Summary: Welcome to Python."}
            res = self.runtime._process_single_command("Analyze this Chrome page.", speak=False)
            mock_exec.assert_called()
            self.assertTrue(res.get("success"))
            self.assertIn("Python.org", res.get("message", ""))

    # =========================================================================
    # 8. SAFE FILE CREATION: "Create a Python file."
    # =========================================================================
    def test_scenario_8_create_python_file(self):
        """'Create a Python file.' -> Use existing safe file-creation workflow."""
        t0 = time.perf_counter()
        req = self.router.route("Create a Python file.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "FILE_MANAGEMENT.CREATE_FILE")
        self.assertLess(route_ms, 100.0)

        with patch.object(self.runtime.executor, "execute") as mock_exec:
            mock_exec.return_value = {"success": True, "action": "create_file", "message": "Created script.py safely."}
            res = self.runtime._process_single_command("Create a Python file.", speak=False)
            mock_exec.assert_called()
            self.assertTrue(res.get("success"))

    # =========================================================================
    # 9. SPOTIFY INTEGRATION: "Play my Spotify playlist."
    # =========================================================================
    def test_scenario_9_play_spotify_playlist(self):
        """'Play my Spotify playlist.' -> Use configured Spotify integration."""
        t0 = time.perf_counter()
        req = self.router.route("Play my Spotify playlist.")
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "SPOTIFY_CONTROL")
        self.assertEqual(req.action, "play_playlist")
        self.assertLess(route_ms, 100.0)

        with patch.object(self.runtime.executor, "execute") as mock_exec:
            mock_exec.return_value = {"success": True, "action": "play_playlist", "message": "Playing Spotify playlist."}
            res = self.runtime._process_single_command("Play my Spotify playlist.", speak=False)
            mock_exec.assert_called()
            self.assertTrue(res.get("success"))

    # =========================================================================
    # 10. FOLLOW-UP CONTEXT & PRONOMINALS
    # =========================================================================
    def test_scenario_10_follow_up_pronominals(self):
        """Pronominals resolve against session context without repeating heavy classification."""
        context = {"last_target": "chrome", "last_action": "open_application"}
        t0 = time.perf_counter()
        req = self.router.route("Close it.", session_context=context)
        route_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(req.layer, LAYER_2)
        self.assertEqual(req.mode, MODE_CONTEXT)
        self.assertEqual(req.intent, "CLOSE_APP")
        self.assertEqual(req.target, "chrome")
        self.assertLess(route_ms, 100.0)

    # =========================================================================
    # 11. STREAMING TTS & SENTENCE BOUNDARY DELIVERY
    # =========================================================================
    def test_sentence_streaming_delivery(self):
        """Verify tokens are chunked at sentence boundaries and queued safely to TTS."""
        tokens = [
            "Binary ", "search ", "is ", "a ", "fast ", "search ", "algorithm. ",
            "It ", "runs ", "in ", "logarithmic ", "time. ",
            "It ", "requires ", "a ", "sorted ", "array."
        ]
        def mock_stream(messages, context=None, is_cancelled=None):
            for t in tokens:
                yield t

        spoken_chunks = []
        def _on_sentence(sent):
            spoken_chunks.append(sent)

        test_q = f"Explain binary search details {time.time()}."
        with patch.object(self.runtime.conversation_manager.provider_manager, "stream_response", side_effect=mock_stream):
            res = self.runtime.conversation_manager.process_query(
                test_q,
                on_sentence=_on_sentence
            )

            self.assertEqual(len(spoken_chunks), 3)
            self.assertEqual(spoken_chunks[0], "Binary search is a fast search algorithm.")
            self.assertEqual(spoken_chunks[1], "It runs in logarithmic time.")
            self.assertEqual(spoken_chunks[2], "It requires a sorted array.")
            self.assertIn("logarithmic time", res["text"])

    # =========================================================================
    # 12. BARGE-IN & CANCELLATION
    # =========================================================================
    def test_streaming_cancellation_barge_in(self):
        """Verify cancellation breaks out of streaming immediately without generating extra speech."""
        cancelled = False
        def mock_stream(messages, context=None, is_cancelled=None):
            yield "Sentence one is here. "
            if is_cancelled and is_cancelled():
                return
            yield "Sentence two should not appear. "

        spoken_chunks = []
        def _on_sentence(sent):
            nonlocal cancelled
            spoken_chunks.append(sent)
            # Simulate barge-in after first sentence
            cancelled = True

        test_q = f"Tell me a long story {time.time()}."
        with patch.object(self.runtime.conversation_manager.provider_manager, "stream_response", side_effect=mock_stream):
            res = self.runtime.conversation_manager.process_query(
                test_q,
                on_sentence=_on_sentence,
                is_cancelled=lambda: cancelled
            )

            self.assertEqual(len(spoken_chunks), 1)
            self.assertEqual(spoken_chunks[0], "Sentence one is here.")
            self.assertNotIn("Sentence two", res["text"])

if __name__ == "__main__":
    unittest.main()
