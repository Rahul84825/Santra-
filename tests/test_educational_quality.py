"""
Tests for Educational & Algorithmic Answer Quality:
- Verifies that educational queries ("Explain binary search", "Explain recursion", "Teach me polymorphism", "Compare BFS and DFS")
  route to AgentBrain / AI Provider Router rather than generic acknowledgments.
- Verifies that procedure learning does not falsely intercept educational questions based on intent alone.
- Verifies that system prompts include detailed pedagogical requirements (prerequisites, step-by-step logic, code, complexity O(log n), pitfalls).
- Verifies that provider failures return actionable diagnostic messages rather than generic acknowledgements or fake success.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.ai.agent_brain import AgentBrain
from core.intent_engine import IntentEngine
from core.learning.procedure_learner import procedure_learner


class TestEducationalAnswerQuality(unittest.TestCase):
    """Verifies that educational and technical questions produce high-quality, substantive answers."""

    def setUp(self):
        self.brain = AgentBrain()
        self.intent_engine = IntentEngine()

    def test_educational_system_prompt_includes_pedagogical_rules(self):
        """Technical prompts must explicitly mandate approaches, code, complexity analysis, and edge cases."""
        queries = [
            "Explain binary search.",
            "Explain recursion.",
            "Teach me polymorphism.",
            "Compare BFS and DFS.",
            "Explain this algorithm with an example."
        ]
        for q in queries:
            prompt = self.brain._build_system_prompt(q)
            self.assertIn("TECHNICAL & PROGRAMMING RULES", prompt, f"Failed rules inclusion for: '{q}'")
            self.assertIn("O(log n)", prompt)
            self.assertIn("complexity", prompt)
            self.assertIn("prerequisites", prompt.lower())

    def test_procedure_learner_does_not_intercept_educational_questions(self):
        """Educational queries must not trigger stale or unrelated learned procedures."""
        queries = [
            "Explain binary search.",
            "Explain recursion.",
            "Teach me polymorphism.",
            "Compare BFS and DFS."
        ]
        for q in queries:
            matched = procedure_learner.match_procedure(q, intent="COMPLEX_TASK")
            self.assertIsNone(
                matched,
                f"Educational query '{q}' was falsely intercepted as procedure '{matched.get('name') if matched else None}'"
            )

    def test_provider_failure_returns_actionable_error_not_generic_acknowledgement(self):
        """When AI providers return empty or fail, system must report actionable diagnostic error, never a fake success acknowledgement."""
        with patch.object(self.brain.provider_manager, "generate_response", return_value=None):
            res = self.brain.reason_and_execute("Explain binary search.")

            text = res.get("text", "")
            self.assertNotIn("Task completed", text)
            self.assertNotIn("I have investigated and executed the necessary actions", text)
            self.assertIn("unable to retrieve a response", text)
            self.assertIn("AI provider", text)

    def test_mocked_binary_search_explanation_substantive_content(self):
        """Verifies parsing of a full educational answer containing algorithm steps, complexity, and prerequisites."""
        mock_explanation = (
            "Final Answer: Binary search is an efficient search algorithm with O(log n) time complexity. "
            "It requires the input array to be sorted. It works by repeatedly comparing the target value to the "
            "middle element: if the target matches, its index is returned; if target is smaller, the search "
            "continues in the left half; if greater, in the right half. "
            "Space complexity is O(1) for iterative implementations and O(log n) for recursive implementations."
        )
        with patch.object(self.brain.provider_manager, "generate_response", return_value=mock_explanation):
            res = self.brain.reason_and_execute("Explain binary search.")

            ans = res.get("text", "")
            self.assertIn("Binary search", ans)
            self.assertIn("O(log n)", ans)
            self.assertIn("sorted", ans)
            self.assertIn("middle element", ans)
            self.assertIn("Space complexity", ans)


if __name__ == "__main__":
    unittest.main()
