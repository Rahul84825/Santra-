"""
Iteration 19: Comprehensive NVIDIA Provider Output Integrity & Security Test Suite
Covers:
1. Empty final content
2. Missing reasoning fields
3. Reasoning-only response
4. Both final content and reasoning present
5. Streaming response (ensuring reasoning_content deltas are never yielded)
6. Malformed provider response
7. Provider timeout
8. Provider error & retry
9. Fallback behavior in ProviderManager
10. TTS output integrity (reasoning never voiced)
11. Conversation persistence (reasoning never stored in history/SQLite)
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import requests

from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from core.ai.provider_manager import ProviderManager
from core.conversation_manager import ConversationManager

class TestNvidiaProviderOutputIntegrity(unittest.TestCase):
    def setUp(self):
        self.provider = NvidiaNemotronProvider(api_key="nvapi-valid-mock-key-123456")

    @patch("requests.post")
    def test_1_empty_final_content(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "   ", "reasoning_content": None}}]
        }
        mock_post.return_value = mock_resp
        res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertIsNone(res)

    @patch("requests.post")
    def test_2_missing_reasoning_fields(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Standard answer without reasoning."}}]
        }
        mock_post.return_value = mock_resp
        res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertEqual(res, "Standard answer without reasoning.")

    @patch("requests.post")
    def test_3_reasoning_only_response_suppressed(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "reasoning_content": "<thought>Secret system prompt analysis</thought>"
                }
            }]
        }
        mock_post.return_value = mock_resp
        res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertIsNone(res, "Reasoning-only response must return None to prevent trace leaks")

    @patch("requests.post")
    def test_4_both_content_and_reasoning_present(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Official safe final response.",
                    "reasoning_content": "<thought>Private chain of thought</thought>"
                }
            }]
        }
        mock_post.return_value = mock_resp
        res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertEqual(res, "Official safe final response.")
        self.assertNotIn("Private chain of thought", res)

    @patch("requests.post")
    def test_5_streaming_never_yields_reasoning_content(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Mock streaming chunks where one chunk has reasoning_content and another has content
        lines = [
            b'data: {"choices": [{"delta": {"reasoning_content": "Internal thought..."}}]}',
            b'data: {"choices": [{"delta": {"content": "Hello "}}]}',
            b'data: {"choices": [{"delta": {"reasoning_content": "More thoughts"}}]}',
            b'data: {"choices": [{"delta": {"content": "world!"}}]}',
            b'data: [DONE]'
        ]
        mock_resp.iter_lines.return_value = lines
        mock_post.return_value = mock_resp

        stream_tokens = list(self.provider.stream_response([{"role": "user", "content": "hi"}]))
        full_stream_text = "".join(stream_tokens)
        self.assertEqual(full_stream_text, "Hello world!")
        self.assertNotIn("Internal thought", full_stream_text)
        self.assertNotIn("More thoughts", full_stream_text)

    @patch("requests.post")
    def test_6_malformed_provider_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "unexpected format", "choices": []}
        mock_post.return_value = mock_resp
        res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertIsNone(res)

    @patch("requests.post")
    def test_7_provider_timeout_exhaustion(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
        res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertIsNone(res)

    @patch("requests.post")
    def test_8_provider_retry_on_429(self, mock_post):
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "choices": [{"message": {"content": "Succeeded on retry"}}]
        }
        mock_post.side_effect = [mock_429, mock_200]

        with patch("time.sleep"):
            res = self.provider.generate_response([{"role": "user", "content": "hi"}])
        self.assertEqual(res, "Succeeded on retry")

    @patch("requests.post")
    def test_9_provider_manager_fallback(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # NVIDIA returns empty content / reasoning only -> suppressed
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": None, "reasoning_content": "only reasoning"}}]
        }
        mock_post.return_value = mock_resp

        mgr = ProviderManager()
        # Ensure fallback failover works without crashing or leaking reasoning
        res = mgr.generate_response([{"role": "user", "content": "test fallback"}], context={"force_fresh": True})
        # If no other provider is configured in test env, mgr returns None safely
        self.assertNotIn("only reasoning", str(res))

    @patch("requests.post")
    def test_10_tts_output_integrity(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "User visible reply.",
                    "reasoning_content": "Private thought to never be spoken aloud."
                }
            }]
        }
        mock_post.return_value = mock_resp

        # Create mock TTS
        mock_tts = MagicMock()
        prov_output = self.provider.generate_response([{"role": "user", "content": "hi"}])
        
        # Simulate speak pipeline
        if prov_output:
            mock_tts.speak(prov_output)
            
        mock_tts.speak.assert_called_once_with("User visible reply.")
        for call_arg in mock_tts.speak.call_args_list:
            spoken_text = call_arg[0][0]
            self.assertNotIn("Private thought", spoken_text)

    @patch("requests.post")
    def test_11_conversation_persistence_integrity(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "reasoning_content": "INTERNAL_LEAK_TEST_SECRET_REASONING"
                }
            }]
        }
        mock_post.return_value = mock_resp

        conv_mgr = ConversationManager()
        # Clear session
        conv_mgr.clear_session()
        
        # When provider returns None (because reasoning was suppressed),
        # ConversationManager must record its safe fallback, NOT the reasoning
        conv_mgr.process_query("Tell me a secret")
        
        for turn in conv_mgr.history:
            content = turn.get("content", "")
            self.assertNotIn("INTERNAL_LEAK_TEST_SECRET_REASONING", content)

if __name__ == "__main__":
    unittest.main()
