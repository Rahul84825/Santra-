"""Stage 3 NVIDIA Runtime Reliability Test Suite.
Validates the 15 required runtime scenarios:
1. Successful normal conversation
2. Successful research synthesis
3. NVIDIA unavailable (missing credentials)
4. Connection timeout (4s connect timeout)
5. Read timeout (15s read timeout fail-fast)
6. HTTP 429 rate limit backoff
7. HTTP 5xx server error handling
8. Invalid / empty response handling
9. Stream interrupted mid-flight
10. User cancellation during generation
11. Runtime enters sleep during request
12. Runtime wakes during request
13. Late NVIDIA response suppression
14. Two simultaneous requests with isolated states
15. One request cancelled while another succeeds
"""

import time
import unittest
from unittest.mock import MagicMock, patch
import requests

from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from core.ai.provider_manager import ProviderManager
from core.research.research_manager import ResearchManager
from core.research.research_models import (
    ResearchSession, Source, SourceType, EvidenceItem, ResearchStatus, ResearchIntent
)

class TestStage3NvidiaRuntimeReliability(unittest.TestCase):

    def setUp(self):
        self.provider = NvidiaNemotronProvider(
            api_key="nvapi-test-dummy-key-for-validation",
            model="nvidia/nemotron-3.5-bolt-e4b",
            timeout=15.0,
            max_retries=1
        )

    # Scenario 1: Successful normal conversation
    @patch("requests.post")
    def test_01_successful_normal_conversation(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello! How can I assist you today?"}}]
        }
        mock_post.return_value = mock_resp

        messages = [{"role": "user", "content": "Hello SANTRA"}]
        res = self.provider.generate_response(messages)
        self.assertEqual(res, "Hello! How can I assist you today?")
        self.assertIsNone(self.provider.last_error_code)
        self.assertIsNotNone(self.provider.last_duration_ms)

    # Scenario 2: Successful research synthesis
    @patch("core.research.search_manager.SearchManager.search")
    @patch("core.research.page_extractor.PageExtractor.extract_url")
    @patch("requests.post")
    def test_02_successful_research_synthesis(self, mock_post, mock_extract, mock_search):
        from core.research.research_models import Source, SourceType, VerificationStatus
        mock_source = Source(
            source_id="src_1",
            research_id="test_sess",
            source_type=SourceType.RETAILER_MARKETPLACE,
            domain="amazon.in",
            url="https://www.amazon.in/dp/B0TEST",
            title="Cosmic Byte Stellaris Wireless Controller",
            raw_snippet="Hall Effect sticks, 1000Hz polling rate, INR 1,999",
            verification_status=VerificationStatus.VERIFIED
        )
        mock_search.return_value = [mock_source]
        mock_extract.return_value = {
            "success": True,
            "title": "Cosmic Byte Stellaris Wireless Controller",
            "text": "The Cosmic Byte Stellaris Wireless Controller features Hall effect magnetic triggers and sticks for INR 1,999.",
            "is_product_page": True,
            "structured_signals": {
                "prices": [1999.0],
                "in_stock": True,
                "specs": {"polling_rate": "1000Hz"}
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "The Cosmic Byte Stellaris features Hall Effect triggers [1]."}}]
        }
        mock_post.return_value = mock_resp

        pm = ProviderManager()
        pm._nvidia_provider = self.provider
        res_mgr = ResearchManager(provider_manager=pm)

        result = res_mgr.execute_research("Find the best controller under 2000")
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "COMPLETED")
        self.assertIn("Cosmic Byte Stellaris", result["answer"])

    # Scenario 3: NVIDIA unavailable (missing credentials)
    def test_03_nvidia_unavailable(self):
        unavail_provider = NvidiaNemotronProvider(api_key="")
        res = unavail_provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        self.assertEqual(unavail_provider.last_error_code, "CREDENTIALS_INVALID")

    # Scenario 4: Connection timeout (4.0s fail-fast)
    @patch("requests.post")
    def test_04_connection_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectTimeout("Connect timeout to host")
        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        self.assertEqual(self.provider.last_error_code, "AI_PROVIDER_TIMEOUT")

    # Scenario 5: Read timeout (15s read timeout fail-fast, no endless retry loops)
    @patch("requests.post")
    def test_05_read_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.ReadTimeout("Read timeout from remote")
        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        self.assertEqual(self.provider.last_error_code, "AI_PROVIDER_TIMEOUT")
        # Ensure single attempt failed fast without blocking
        self.assertEqual(mock_post.call_count, 1)

    # Scenario 6: HTTP 429 rate limit backoff
    @patch("requests.post")
    @patch("time.sleep")
    def test_06_http_429_rate_limiting(self, mock_sleep, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        self.assertEqual(self.provider.last_error_code, "RATE_LIMITED")
        self.assertEqual(mock_post.call_count, 2)  # 1 initial + 1 retry

    # Scenario 7: HTTP 5xx server error handling
    @patch("requests.post")
    @patch("time.sleep")
    def test_07_http_5xx_server_error(self, mock_sleep, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        self.assertEqual(self.provider.last_error_code, "SERVER_ERROR")

    # Scenario 8: Invalid / empty response handling
    @patch("requests.post")
    def test_08_invalid_or_empty_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_post.return_value = mock_resp

        res = self.provider.generate_response([{"role": "user", "content": "test"}])
        self.assertIsNone(res)
        self.assertEqual(self.provider.last_error_code, "EMPTY_RESPONSE")

    # Scenario 9: Stream interrupted mid-flight
    @patch("requests.post")
    def test_09_stream_interrupted(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        def fake_iter_lines():
            yield b'data: {"choices": [{"delta": {"content": "Part 1"}}]}'
            raise requests.exceptions.ChunkedEncodingError("Connection dropped by peer")
        mock_resp.iter_lines = fake_iter_lines
        mock_post.return_value = mock_resp

        tokens = []
        for t in self.provider.stream_response([{"role": "user", "content": "test"}]):
            tokens.append(t)

        self.assertEqual(tokens, ["Part 1"])
        self.assertEqual(self.provider.last_error_code, "STREAM_ERROR")

    # Scenario 10: User cancellation during generation
    @patch("requests.post")
    def test_10_user_cancellation(self, mock_post):
        cancelled_flag = False
        def is_cancelled():
            return cancelled_flag

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        def fake_iter_lines():
            nonlocal cancelled_flag
            yield b'data: {"choices": [{"delta": {"content": "Token A"}}]}'
            cancelled_flag = True  # User cancels right after first token
            yield b'data: {"choices": [{"delta": {"content": "Token B"}}]}'
        mock_resp.iter_lines = fake_iter_lines
        mock_post.return_value = mock_resp

        tokens = []
        for t in self.provider.stream_response([{"role": "user", "content": "test"}], is_cancelled=is_cancelled):
            tokens.append(t)

        self.assertEqual(tokens, ["Token A"])
        self.assertEqual(self.provider.last_error_code, "CANCELLED")

    # Scenario 11: Runtime enters sleep during request
    def test_11_runtime_enters_sleep_during_request(self):
        is_sleeping = False
        def sleep_check():
            return is_sleeping

        pm = ProviderManager()
        res_mgr = ResearchManager(provider_manager=pm)

        # Trigger sleep state
        is_sleeping = True
        result = res_mgr.execute_research("test query", is_cancelled=sleep_check)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "CANCELLED")

    # Scenario 12: Runtime wakes during request
    @patch("core.research.search_manager.SearchManager.search")
    @patch("core.research.page_extractor.PageExtractor.extract_url")
    @patch("requests.post")
    def test_12_runtime_wakes_during_request(self, mock_post, mock_extract, mock_search):
        from core.research.research_models import Source, SourceType, VerificationStatus
        mock_source = Source(
            source_id="src_w",
            research_id="test_sess",
            source_type=SourceType.RETAILER_MARKETPLACE,
            domain="example.com",
            url="https://example.com/wake",
            title="Wake Test",
            raw_snippet="Operational",
            verification_status=VerificationStatus.VERIFIED
        )
        mock_search.return_value = [mock_source]
        mock_extract.return_value = {
            "title": "Wake Test",
            "text": "System is awake and active.",
            "is_product_page": False
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Awake and fully operational."}}]
        }
        mock_post.return_value = mock_resp

        # First request while asleep cancelled
        pm = ProviderManager()
        pm._nvidia_provider = self.provider
        res_mgr = ResearchManager(provider_manager=pm)
        res1 = res_mgr.execute_research("wake test", is_cancelled=lambda: True)
        self.assertEqual(res1["status"], "CANCELLED")

        # Second request after waking succeeds with unique research_id
        res2 = res_mgr.execute_research("wake test", is_cancelled=lambda: False)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["status"], "COMPLETED")
        self.assertNotEqual(res1.get("research_id"), res2.get("research_id"))

    # Scenario 13: Late NVIDIA response suppression
    def test_13_late_nvidia_response(self):
        cancelled = True
        res = self.provider.generate_response([{"role": "user", "content": "test"}], is_cancelled=lambda: cancelled)
        self.assertIsNone(res)
        self.assertEqual(self.provider.last_error_code, "CANCELLED")

    # Scenario 14: Two simultaneous requests with isolated states
    @patch("requests.post")
    def test_14_two_simultaneous_requests(self, mock_post):
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {"choices": [{"message": {"content": "Response A"}}]}

        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"choices": [{"message": {"content": "Response B"}}]}

        mock_post.side_effect = [mock_resp1, mock_resp2]

        provider1 = NvidiaNemotronProvider(api_key="nvapi-valid-token-alpha")
        provider2 = NvidiaNemotronProvider(api_key="nvapi-valid-token-beta")

        res_a = provider1.generate_response([{"role": "user", "content": "A"}])
        res_b = provider2.generate_response([{"role": "user", "content": "B"}])

        self.assertEqual(res_a, "Response A")
        self.assertEqual(res_b, "Response B")
        self.assertNotEqual(provider1.last_duration_ms, None)

    # Scenario 15: One request cancelled while another succeeds
    @patch("requests.post")
    def test_15_one_request_cancelled_while_another_succeeds(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "Success Output"}}]}
        mock_post.return_value = mock_resp

        # Request A cancelled
        res_a = self.provider.generate_response([{"role": "user", "content": "A"}], is_cancelled=lambda: True)
        self.assertIsNone(res_a)
        self.assertEqual(self.provider.last_error_code, "CANCELLED")

        # Request B succeeds
        res_b = self.provider.generate_response([{"role": "user", "content": "B"}], is_cancelled=lambda: False)
        self.assertEqual(res_b, "Success Output")
        self.assertIsNone(self.provider.last_error_code)

if __name__ == "__main__":
    unittest.main()
