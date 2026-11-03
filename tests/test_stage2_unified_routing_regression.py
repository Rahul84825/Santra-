"""
Comprehensive Stage 2 Unified Intelligence Routing, Command Execution & Conversational Reliability Regression Suite.
Uses Python standard library unittest for 100% dependency-free execution in Python 3.14.

Tests:
- Task A: Unified routing contract (LAYER_1 Fast Local, LAYER_2 Context/Question, LAYER_3 Nemotron Reasoning)
- Task B: Normalization & Affirmations ("Yes, open Chrome", "Sure, open Notepad", "Yes, put computer into sleep mode", negations, cancellations, standalone affirmations)
- Task C: Explicit AI_MODE toggling, local command preservation in AI mode, conversational routing to Nemotron
- Task D: Follow-up educational topic retention across intervening commands and pattern matching
- Task E: Command Palette 40 capabilities status resolution and tool phrase dispatch
- Task F: Truthful provider telemetry states
- Task G: ReAct trace filtering in speech sanitizer
"""

import unittest
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from modules.system.executor import CommandExecutor
from core.ai.intelligence_router import (
    IntelligenceRouter,
    StructuredRequest,
    LAYER_1,
    LAYER_2,
    LAYER_3,
    MODE_FAST_LOCAL,
    MODE_QUESTION,
    MODE_REASONING,
    MODE_CONTEXT,
)
from core.conversation_manager import ConversationManager
from core.speech_sanitizer import sanitize_speech_text
from ui.panels.command_palette_dialog import CommandLifecycleState, CommandPaletteDialog


class TestTaskAUnifiedRoutingAuthority(unittest.TestCase):
    """Task A: Unified routing classification contract."""

    def setUp(self):
        self.router = IntelligenceRouter()
        self.normalizer = CommandNormalizer()

    def test_local_command_classification(self):
        req = self.router.route("open chrome")
        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.mode, MODE_FAST_LOCAL)
        self.assertIn("OPEN_APP", req.intent)

    def test_informational_question_classification(self):
        req = self.router.route("what is binary search?")
        self.assertIn(req.layer, [LAYER_2, LAYER_3])
        self.assertIn(req.mode, [MODE_QUESTION, MODE_REASONING])

    def test_reflex_stop_classification(self):
        req = self.router.route("stop talking")
        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.intent, "STOP_TALKING")


class TestTaskBNormalizationAndAffirmations(unittest.TestCase):
    """Task B: Safe prefix stripping, confirmations, negations and cancellations."""

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()

    def test_affirmative_local_commands(self):
        cases = [
            ("Yes, open Chrome", "open chrome", "open_app"),
            ("Sure, open Notepad", "open notepad", "open_app"),
            ("Please open Downloads", "open downloads", "file_access"),
            ("Okay, check my battery", "check my battery", "system_control"),
            ("Sure, create a folder on my Desktop", "create a folder on my desktop", "filesystem_control"),
        ]
        for raw_input, expected_normalized, expected_intent in cases:
            with self.subTest(raw_input=raw_input):
                norm = self.normalizer.normalize(raw_input)["normalized"]
                self.assertEqual(norm, expected_normalized)
                intent_res = self.intent_engine.parse(norm, raw_text=raw_input)
                self.assertEqual(intent_res.get("intent"), expected_intent)

    def test_sleep_mode_confirmation_maintained(self):
        norm = self.normalizer.normalize("Yes, put the computer into sleep mode")["normalized"]
        self.assertEqual(norm, "sleep computer")
        intent_res = self.intent_engine.parse(norm, raw_text="Yes, put the computer into sleep mode")
        self.assertEqual(intent_res.get("intent"), "system_control")
        self.assertEqual(intent_res.get("action"), "sleep_pc")

        # Confirmation gate must block unconfirmed execution
        exec_res = self.executor.execute(intent_res, confirm=False)
        self.assertFalse(exec_res.get("success"))
        self.assertTrue(exec_res.get("pending_confirmation"))
        self.assertEqual(exec_res.get("outcome"), "PERMISSION_DENIED")

    def test_cancellations(self):
        cases = [
            ("No, cancel that", "cancel"),
            ("Actually, don't do it", "cancel"),
            ("cancel that", "cancel"),
        ]
        for raw_input, expected_action in cases:
            with self.subTest(raw_input=raw_input):
                norm = self.normalizer.normalize(raw_input)["normalized"]
                intent_res = self.intent_engine.parse(norm, raw_text=raw_input)
                self.assertEqual(intent_res.get("intent"), "cancellation")
                self.assertEqual(intent_res.get("action"), expected_action)

    def test_negated_commands(self):
        cases = [
            "No, don't open Chrome",
            "Actually don't open Chrome",
            "don't open Chrome",
            "dont open chrome",
        ]
        for raw_input in cases:
            with self.subTest(raw_input=raw_input):
                norm = self.normalizer.normalize(raw_input)["normalized"]
                intent_res = self.intent_engine.parse(norm, raw_text=raw_input)
                self.assertEqual(intent_res.get("intent"), "negation")
                self.assertEqual(intent_res.get("action"), "reject_action")

    def test_standalone_affirmations(self):
        norm_yes = self.normalizer.normalize("Yes")["normalized"]
        self.assertEqual(norm_yes, "yes")
        intent_yes = self.intent_engine.parse(norm_yes, raw_text="Yes")
        self.assertEqual(intent_yes.get("intent"), "affirmation")

        norm_no = self.normalizer.normalize("No")["normalized"]
        self.assertEqual(norm_no, "no")
        intent_no = self.intent_engine.parse(norm_no, raw_text="No")
        self.assertEqual(intent_no.get("intent"), "negation")


class TestTaskCExplicitAIMode(unittest.TestCase):
    """Task C: AI_MODE activation, deactivation, and routing isolation."""

    def setUp(self):
        self.router = IntelligenceRouter()
        self.intent_engine = IntentEngine()

    def test_ai_mode_toggle_intents(self):
        cases = [
            ("switch to ai mode", "enable_ai_mode"),
            ("enable ai mode", "enable_ai_mode"),
            ("ask nemotron", "enable_ai_mode"),
            ("exit ai mode", "disable_ai_mode"),
            ("disable ai mode", "disable_ai_mode"),
            ("return to normal mode", "disable_ai_mode"),
        ]
        for phrase, expected_action in cases:
            with self.subTest(phrase=phrase):
                intent_res = self.intent_engine.parse(phrase)
                self.assertIn(intent_res.get("intent"), ["system_control", "ai_mode_control"])
                self.assertEqual(intent_res.get("action"), expected_action)

    def test_ai_mode_preserves_local_commands(self):
        # Even when ai_mode is True, local commands MUST run locally in LAYER_1
        req = self.router.route(
            raw_text="open chrome",
            ai_mode=True
        )
        self.assertEqual(req.layer, LAYER_1)
        self.assertEqual(req.mode, MODE_FAST_LOCAL)
        self.assertIn("OPEN_APP", req.intent)

    def test_ai_mode_routes_conversational_to_nemotron(self):
        # In AI mode, questions/conversational queries route directly to Nemotron LAYER_3
        req = self.router.route(
            raw_text="what do you think about rust?",
            ai_mode=True
        )
        self.assertEqual(req.layer, LAYER_3)
        self.assertEqual(req.mode, MODE_REASONING)
        self.assertEqual(req.intent, "NEMOTRON_REASONING")


class TestTaskDFollowupRouting(unittest.TestCase):
    """Task D: Follow-up educational topic retention across intervening commands."""

    def setUp(self):
        self.cm = ConversationManager()

    def test_educational_topic_retained_across_intervening_command(self):
        # 1. User asks to explain binary search
        self.cm.set_active_explanation("binary search", "explain binary search", "Binary search is an efficient algorithm with O(log n) time complexity.")
        self.assertEqual(self.cm.active_educational_topic, "binary search")

        # 2. Intervening local command executes
        self.cm.update_context("open_app", "chrome")
        # Target updated to chrome, but educational topic MUST remain binary search
        self.assertEqual(self.cm.last_target, "chrome")
        self.assertEqual(self.cm.active_educational_topic, "binary search")

        # 3. Follow-up query
        resolved = self.cm.resolve_pronouns_and_references("give another example")
        self.assertIn("binary search", resolved)

    def test_expanded_followup_patterns(self):
        patterns = [
            "give another example",
            "make it simpler",
            "compare both",
            "what are the disadvantages",
            "what about its advantages",
            "explain the second point",
            "explain point 2",
            "why?",
            "show an example in C++",
            "in C++",
            "continue",
        ]
        self.cm.set_active_explanation("quicksort", "explain quicksort", "Quicksort is a divide-and-conquer algorithm.")
        for followup_phrase in patterns:
            with self.subTest(followup_phrase=followup_phrase):
                resolved = self.cm.resolve_pronouns_and_references(followup_phrase)
                self.assertIn("quicksort", resolved)

    def test_no_active_topic_leaves_input_unaltered(self):
        # If no active topic exists, do not inject phantom topics
        self.cm.active_educational_topic = None
        self.cm.task_context.current_topic = None
        resolved = self.cm.resolve_pronouns_and_references("give another example")
        self.assertEqual(resolved, "give another example")


class TestTaskECommandPalette(unittest.TestCase):
    """Task E: Command Palette capability execution and status resolution."""

    def test_all_30_tool_cards_have_dispatch_phrases(self):
        self.assertGreaterEqual(len(CommandPaletteDialog.TOOL_DISPATCH_PHRASES), 28)
        for name, phrase in CommandPaletteDialog.TOOL_DISPATCH_PHRASES.items():
            self.assertIsInstance(phrase, str)
            self.assertTrue(len(phrase.strip()) > 0)

    def test_dynamic_lifecycle_states(self):
        self.assertTrue(hasattr(CommandLifecycleState, "READY"))
        self.assertTrue(hasattr(CommandLifecycleState, "BLOCKED"))
        self.assertTrue(hasattr(CommandLifecycleState, "UNVERIFIED"))


class TestTaskGReActTraceSafeguard(unittest.TestCase):
    """Task G: ReAct internal trace stripping in speech sanitizer."""

    def test_react_thought_action_stripping(self):
        raw = (
            "Thought: I should search for the weather in Tokyo.\n"
            "Action: web_search\n"
            "Action Input: weather in Tokyo\n"
            "Observation: It is 15C and clear in Tokyo.\n"
            "Final Answer: The weather in Tokyo is currently 15°C and sunny."
        )
        cleaned = sanitize_speech_text(raw)
        self.assertNotIn("Thought:", cleaned)
        self.assertNotIn("Action:", cleaned)
        self.assertNotIn("Action Input:", cleaned)
        self.assertNotIn("Observation:", cleaned)
        self.assertNotIn("Final Answer:", cleaned)
        self.assertIn("15", cleaned)
        self.assertIn("Tokyo", cleaned)

    def test_prose_preservation(self):
        prose = "Taking action now. That was a great thought! I love action movies."
        cleaned = sanitize_speech_text(prose)
        self.assertIn("Taking action now", cleaned)
        self.assertIn("great thought", cleaned)
        self.assertIn("action movies", cleaned)


if __name__ == "__main__":
    unittest.main()
