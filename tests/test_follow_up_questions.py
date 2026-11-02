import unittest
from unittest.mock import patch
from core.conversation_manager import ConversationManager

class TestFollowUpQuestions(unittest.TestCase):

    def setUp(self):
        self.cm = ConversationManager()

    def test_follow_up_context_preservation(self):
        with patch.object(self.cm.provider_manager, "generate_response") as mock_gen:
            mock_gen.return_value = "Quantum computing uses qubits."
            self.cm.process_query("Explain quantum computing.")

            mock_gen.return_value = "Simpler: Qubits can be 0 and 1 at the same time."
            self.cm.process_query("Make that simpler.")

            # Second call should preserve context turns: Q1, A1, Q2 (excluding system prompt if prepended)
            last_call_args = mock_gen.call_args[0][0]
            conv_msgs = [m for m in last_call_args if m.get("role") != "system"]
            self.assertEqual(len(conv_msgs), 3)
            self.assertEqual(conv_msgs[0]["content"], "Explain quantum computing.")
            self.assertEqual(conv_msgs[1]["content"], "Quantum computing uses qubits.")
            self.assertEqual(conv_msgs[2]["content"], "Make that simpler.")

if __name__ == "__main__":
    unittest.main()
