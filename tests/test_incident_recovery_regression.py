"""
tests/test_incident_recovery_regression.py
Master Incident Recovery Regression Test Suite.
Verifies authoritative configuration, timeout deadlines, cancellation isolation,
sleep/wake transitions, UI terminal states, and STT anti-hallucination guardrails.
"""

import unittest
import time
import requests
from unittest.mock import MagicMock, patch

from core.transcript_validator import (
    transcript_validator,
    ValidationStatus
)
from core.ai.provider_manager import ProviderManager
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from ui.state_machine import JarvisUIState, map_runtime_status_to_ui_state


class TestAuthoritativeConfiguration(unittest.TestCase):
    """Phase A: Authoritative configuration path verification."""

    def test_effective_model_is_bolt_e4b(self):
        """ProviderManager must strictly initialize with nvidia/nemotron-3.5-bolt-e4b."""
        pm = ProviderManager()
        diag = pm.get_diagnostics()
        self.assertEqual(diag.get("model"), "nvidia/nemotron-3.5-bolt-e4b")
        self.assertNotEqual(diag.get("model"), "nvidia/nemotron-3.5-super-vl-120b-a12b")

    def test_effective_timeout_and_retries(self):
        """Read timeout must be 15.0s, connect 4.0s, and max_retries 1."""
        pm = ProviderManager()
        diag = pm.get_diagnostics()
        self.assertEqual(diag.get("connect_timeout_sec"), 4.0)
        self.assertEqual(diag.get("read_timeout_sec"), 15.0)
        self.assertEqual(diag.get("max_retries"), 1)

    def test_provider_settings_sync_preserves_bolt(self):
        """Calling active_provider_key or get_provider repeatedly must never revert model to 120B."""
        pm = ProviderManager()
        for _ in range(5):
            _ = pm.active_provider_key
            prov = pm.get_active_provider()
            self.assertEqual(prov.model, "nvidia/nemotron-3.5-bolt-e4b")
            self.assertEqual(prov.timeout, 15.0)


class TestRequestTimeoutAndRetries(unittest.TestCase):
    """Phase B: Timeout deadlines, error classification, and stream cleanup."""

    def setUp(self):
        self.provider = NvidiaNemotronProvider(api_key="nvapi-mock-test-key", model="nvidia/nemotron-3.5-bolt-e4b")

    def test_connect_timeout(self):
        """Connection timeout fails fast without blind retries."""
        with patch("requests.post", side_effect=requests.exceptions.ConnectTimeout("Connect timed out")):
            res = self.provider.generate_response([{"role": "user", "content": "test"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "AI_PROVIDER_TIMEOUT")

    def test_read_timeout_no_blind_retries(self):
        """Read timeout terminates immediately with error code AI_PROVIDER_TIMEOUT."""
        with patch("requests.post", side_effect=requests.exceptions.ReadTimeout("Read timed out")) as mock_post:
            res = self.provider.generate_response([{"role": "user", "content": "test"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "AI_PROVIDER_TIMEOUT")
            # Only 1 attempt made (0 retries on timeout)
            self.assertEqual(mock_post.call_count, 1)

    def test_http_401_error(self):
        """HTTP 401 must classify as CREDENTIALS_INVALID."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch("requests.post", return_value=mock_resp):
            res = self.provider.generate_response([{"role": "user", "content": "test"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "CREDENTIALS_INVALID")

    def test_http_429_rate_limited(self):
        """HTTP 429 classifies as RATE_LIMITED."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        with patch("requests.post", return_value=mock_resp):
            res = self.provider.generate_response([{"role": "user", "content": "test"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "RATE_LIMITED")

    def test_http_503_server_error(self):
        """HTTP 503 classifies as SERVER_ERROR."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        with patch("requests.post", return_value=mock_resp):
            res = self.provider.generate_response([{"role": "user", "content": "test"}])
            self.assertIsNone(res)
            self.assertEqual(self.provider.get_last_error_code(), "SERVER_ERROR")

    def test_stream_closes_on_completion(self):
        """Response stream must be closed in finally block."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [b"data: [DONE]"]
        with patch("requests.post", return_value=mock_resp):
            list(self.provider.stream_response([{"role": "user", "content": "test"}]))
            mock_resp.close.assert_called_once()

    def test_total_deadline_enforcement(self):
        """Total stream deadline halts iteration if server hangs."""
        self.provider.timeout = 0.1  # Very short deadline for test
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        def slow_iter():
            time.sleep(0.7)  # Exceeds deadline (0.1 + 0.5s)
            yield b'data: {"choices":[{"delta":{"content":"late"}}]}'

        mock_resp.iter_lines = slow_iter
        with patch("requests.post", return_value=mock_resp):
            tokens = list(self.provider.stream_response([{"role": "user", "content": "test"}]))
            self.assertEqual(tokens, [])
            self.assertEqual(self.provider.get_last_error_code(), "AI_PROVIDER_TIMEOUT")


class TestCancellationAndSleepLifecycle(unittest.TestCase):
    """Phase C: Independent request cancellation and sleep/wake state isolation."""

    def setUp(self):
        self.provider = NvidiaNemotronProvider(api_key="nvapi-mock-test-key", model="nvidia/nemotron-3.5-bolt-e4b")

    def test_cancellation_before_dispatch(self):
        """Cancelled token before dispatch aborts with CANCELLED code."""
        tokens = list(self.provider.stream_response(
            [{"role": "user", "content": "test"}],
            is_cancelled=lambda: True
        ))
        self.assertEqual(tokens, [])
        self.assertEqual(self.provider.get_last_error_code(), "CANCELLED")

    def test_cancellation_during_streaming(self):
        """Cancellation mid-stream aborts further token emission."""
        cancel_flag = False
        def check_cancel():
            return cancel_flag

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        def chunk_gen():
            nonlocal cancel_flag
            yield b'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            cancel_flag = True  # User cancels after first token
            yield b'data: {"choices":[{"delta":{"content":" World"}}]}'

        mock_resp.iter_lines = chunk_gen
        with patch("requests.post", return_value=mock_resp):
            tokens = list(self.provider.stream_response(
                [{"role": "user", "content": "test"}],
                is_cancelled=check_cancel
            ))
            self.assertEqual(tokens, ["Hello"])
            self.assertEqual(self.provider.get_last_error_code(), "CANCELLED")


class TestUIRecoveryAndTerminalStates(unittest.TestCase):
    """Phase D: Terminal states and UI state synchronization."""

    def test_terminal_states_exist(self):
        """JarvisUIState must support all required terminal states."""
        for state_name in ["COMPLETED", "TIMED_OUT", "CANCELLED", "ERROR", "STANDBY", "SLEEPING"]:
            self.assertTrue(hasattr(JarvisUIState, state_name))

    def test_map_runtime_status_terminal_states(self):
        """map_runtime_status_to_ui_state maps terminal status strings correctly."""
        self.assertEqual(map_runtime_status_to_ui_state("COMPLETED"), JarvisUIState.COMPLETED)
        self.assertEqual(map_runtime_status_to_ui_state("TIMED_OUT"), JarvisUIState.TIMED_OUT)
        self.assertEqual(map_runtime_status_to_ui_state("CANCELLED"), JarvisUIState.CANCELLED)
        self.assertEqual(map_runtime_status_to_ui_state("STANDBY"), JarvisUIState.STANDBY)


class TestSTTValidationDefects(unittest.TestCase):
    """Phase E: Speech recognition anti-hallucination and fragment tests."""

    def test_repetitive_wake_word_comma_separated(self):
        """'Santra, Santra, Santra...' must be rejected as REPETITIVE_HALLUCINATION."""
        res = transcript_validator.validate("Santra, Santra, Santra...")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_repetitive_wake_word_no_spaces(self):
        """'Santra,Santra,Santra...' without spaces must be rejected as REPETITIVE_HALLUCINATION."""
        res = transcript_validator.validate("Santra,Santra,Santra...")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_37_repeated_wake_words(self):
        """37 repeated wake words must be rejected as REPETITIVE_HALLUCINATION."""
        text = " ".join(["Santra"] * 37)
        res = transcript_validator.validate(text)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_75_repeated_wake_words(self):
        """75 repeated wake words must be rejected as REPETITIVE_HALLUCINATION."""
        text = " ".join(["Santra"] * 75)
        res = transcript_validator.validate(text)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_mixed_wake_word_repetition(self):
        """'Santra Jarvis Santra' must be rejected as REPETITIVE_HALLUCINATION."""
        res = transcript_validator.validate("Santra Jarvis Santra")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

    def test_legitimate_sentence_with_santra_passes(self):
        """A normal question mentioning Santra once must pass as VALID."""
        valid_queries = [
            "Santra what is binary search?",
            "Hey Santra explain quicksort",
            "What is the capital of Japan, Santra?"
        ]
        for q in valid_queries:
            res = transcript_validator.validate(q)
            self.assertTrue(res.is_valid, f"Legitimate query '{q}' must pass")
            self.assertEqual(res.status, ValidationStatus.VALID)

    def test_fragment_rejections(self):
        """'And else.' and 'Or else.' must be rejected as FRAGMENT."""
        for frag in ["And else.", "Or else.", "And else", "Or else", "Else.", "And."]:
            res = transcript_validator.validate(frag)
            self.assertFalse(res.is_valid, f"Fragment '{frag}' must be rejected")
            self.assertEqual(res.status, ValidationStatus.FRAGMENT)

    def test_legitimate_short_commands_pass(self):
        """Legitimate short commands must pass."""
        for cmd in ["open chrome", "stop", "volume up", "mute", "help"]:
            res = transcript_validator.validate(cmd)
            self.assertTrue(res.is_valid, f"Short command '{cmd}' must pass")


if __name__ == "__main__":
    unittest.main()

