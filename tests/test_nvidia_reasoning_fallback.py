import unittest
from unittest.mock import patch, MagicMock
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider

class TestNvidiaReasoningFallback(unittest.TestCase):
    def setUp(self):
        self.provider = NvidiaNemotronProvider(api_key="nvapi-valid-test-key-mock-123456")

    @patch("requests.post")
    def test_reasoning_content_is_suppressed_when_content_is_none(self, mock_post):
        """Iteration 19 Policy: Never treat internal reasoning as a substitute for final answer.
        Internal reasoning traces must never leak into user-visible responses.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning_content": "<thought>Analyzing quicksort example...</thought>\nInternal chain of thought."
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "example"}])
        # Must return None so fallback system takes over safely without leaking reasoning
        self.assertIsNone(res)

    @patch("requests.post")
    def test_content_is_returned_when_both_present(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Quicksort divides and conquers.",
                        "reasoning_content": "<thought>Secret model deliberation</thought>"
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "example"}])
        self.assertEqual(res, "Quicksort divides and conquers.")
        self.assertNotIn("Secret model deliberation", res)

if __name__ == "__main__":
    unittest.main()
