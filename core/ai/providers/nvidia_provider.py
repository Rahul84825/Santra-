import os
import json
import time
import re
import logging
from typing import List, Dict, Any, Optional, Generator, Tuple
import requests

from core.ai.base_provider import BaseAIProvider
from config import config

logger = logging.getLogger("Jarvis.NvidiaProvider")

class NvidiaNemotronProvider(BaseAIProvider):
    """NVIDIA Nemotron Cloud Reasoning Provider.
    Interfaces with NVIDIA's OpenAI-compatible API endpoint for Nemotron models
    (e.g. nvidia/nemotron-3.5-bolt-e4b, nvidia/nemotron-3.5-super-vl-120b-a12b).
    Features:
      - High-performance streaming with separate connection (4s) and read deadlines
      - Safe credential isolation (never logs or reveals keys)
      - Bounded transient retries (429 / 5xx) with no wasteful 30s timeout loops
      - Authoritative error classification (TIMEOUT, CREDENTIALS_INVALID, CANCELLED)
      - Clean reasoning extraction (separating internal chain-of-thought from user content)
      - Native OpenAI-compatible tool call support
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None
    ):
        self.api_key = api_key if api_key is not None else (getattr(config, "nvidia_api_key", "") or os.environ.get("NVIDIA_API_KEY", ""))
        self.model = model or getattr(config, "nvidia_model", "nvidia/nemotron-3.5-bolt-e4b")
        self.base_url = (base_url or getattr(config, "nvidia_base_url", "https://integrate.api.nvidia.com/v1")).rstrip("/")
        self.timeout = float(timeout or getattr(config, "nvidia_timeout_sec", 15.0))
        self.max_retries = max_retries if max_retries is not None else getattr(config, "nvidia_max_retries", 1)
        self.temperature = getattr(config, "nvidia_temperature", 0.6)
        self.max_tokens = getattr(config, "nvidia_max_tokens", 2048)

        # Performance & Telemetry Tracking
        self.last_error_code: Optional[str] = None
        self.last_ttft_ms: Optional[float] = None
        self.last_duration_ms: Optional[float] = None

    def get_name(self) -> str:
        return f"NVIDIA Nemotron ({self.model.split('/')[-1]})"

    def is_available(self) -> bool:
        key = self.api_key if self.api_key is not None else (getattr(config, "nvidia_api_key", "") or os.environ.get("NVIDIA_API_KEY", ""))
        return bool(key and len(key.strip()) > 10)

    def get_last_error_code(self) -> Optional[str]:
        return self.last_error_code

    def get_last_ttft_ms(self) -> Optional[float]:
        return self.last_ttft_ms

    def get_diagnostics(self) -> Dict[str, Any]:
        """Safe startup and runtime diagnostics without exposing secrets."""
        connect_t, read_t = self._get_timeout_tuple()
        return {
            "provider": "nvidia",
            "model": self.model,
            "connect_timeout_sec": connect_t,
            "read_timeout_sec": read_t,
            "max_retries": self.max_retries,
            "is_configured": self.is_available(),
            "instance_id": hex(id(self))
        }

    def _sanitize_error_message(self, err_msg: str) -> str:
        """Ensures no API key or sensitive token appears in logs or error traces."""
        if not self.api_key:
            return err_msg
        clean_key = self.api_key.strip()
        if len(clean_key) > 5 and clean_key in err_msg:
            return err_msg.replace(clean_key, "[REDACTED_NVIDIA_KEY]")
        return err_msg

    def _get_timeout_tuple(self) -> Tuple[float, float]:
        """Returns (connect_timeout, read_timeout) with strict upper ceilings to fail fast."""
        connect_timeout = 4.0
        read_timeout = min(15.0, max(5.0, self.timeout))
        return (connect_timeout, read_timeout)

    def health_check(self) -> bool:
        """Lightweight connectivity check against NVIDIA models endpoint."""
        if not self.is_available():
            return False
        url = f"{self.base_url}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "User-Agent": "JARVIS-Assistant/1.1"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=(3.0, 5.0))
            return resp.status_code == 200
        except Exception as e:
            logger.debug(f"[NVIDIA] Health check failed: {self._sanitize_error_message(str(e))}")
            return False

    def _clean_reasoning_from_content(self, text: str) -> str:
        """Strips internal thought tags or thinking process headers from user content."""
        if not text:
            return ""
        # 1. Remove XML-style thought blocks: <thought>...</thought>
        cleaned = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL).strip()

        # 2. Remove standard Nemotron markdown reasoning prefixes
        # e.g., "Here's a thinking process:\n\n1. Analyze...\n\n**Response:** Hello"
        if "Here's a thinking process:" in cleaned:
            parts = re.split(r'\n\n(?:\*{0,2}(?:Final Answer|Response|Answer|Conclusion):?\*{0,2}:?|\*{0,2}\d+\.\s+Final Answer:?\*{0,2}:?)\s*', cleaned, flags=re.IGNORECASE)
            if len(parts) >= 2:
                cleaned = parts[-1].strip()
            else:
                # Fallback: find double newline after numbered analysis
                sub_parts = re.split(r'\n\n(?=[A-Z][a-z]+)', cleaned)
                if len(sub_parts) >= 2 and ("thinking" in sub_parts[0].lower() or "analyze" in sub_parts[0].lower()):
                    cleaned = "\n\n".join(sub_parts[1:]).strip()

        return cleaned

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
        is_cancelled: Optional[Any] = None
    ) -> Optional[str]:
        """Generates a text completion or tool call response from NVIDIA Nemotron.
        Handles reasoning model formatting, bounded retries, and network error categorization.
        """
        self.last_error_code = None
        self.last_ttft_ms = None
        self.last_duration_ms = None

        if is_cancelled and callable(is_cancelled) and is_cancelled():
            self.last_error_code = "CANCELLED"
            logger.info("[NVIDIA] Generation request aborted prior to dispatch: caller cancelled.")
            return None

        if not self.is_available():
            self.last_error_code = "CREDENTIALS_INVALID"
            logger.debug("[NVIDIA] Provider unavailable (missing or empty NVIDIA_API_KEY).")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "JARVIS-Assistant/1.1"
        }

        ctx = context or {}
        max_tokens = ctx.get("max_tokens", self.max_tokens)
        temperature = ctx.get("temperature", self.temperature)
        tools = ctx.get("tools")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        if tools and isinstance(tools, list):
            payload["tools"] = tools

        attempt = 0
        backoff_delay = 1.0
        req_timeout = self._get_timeout_tuple()
        deadline = time.time() + self.timeout

        while attempt < (self.max_retries + 1):
            attempt += 1
            if time.time() > deadline:
                self.last_error_code = "AI_PROVIDER_TIMEOUT"
                logger.warning(f"[NVIDIA] Total request deadline exceeded ({self.timeout:.1f}s). Aborting.")
                return None
            if is_cancelled and callable(is_cancelled) and is_cancelled():
                self.last_error_code = "CANCELLED"
                logger.info("[NVIDIA] Generation request aborted: caller cancelled.")
                return None

            try:
                t0 = time.time()
                resp = requests.post(url, headers=headers, json=payload, timeout=req_timeout)
                duration_ms = (time.time() - t0) * 1000
                self.last_duration_ms = duration_ms

                # Case 1: Success (200 OK)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        logger.warning("[NVIDIA] Empty choices array returned by API.")
                        self.last_error_code = "EMPTY_RESPONSE"
                        return None

                    msg_obj = choices[0].get("message", {})
                    content = msg_obj.get("content")
                    tool_calls = msg_obj.get("tool_calls")

                    logger.info(
                        f"[NVIDIA] Generation succeeded in {duration_ms:.1f}ms "
                        f"(Model: {self.model}, Attempt: {attempt}, ToolCalls: {bool(tool_calls)})"
                    )

                    # If model invoked a tool call in standard OpenAI format
                    if tool_calls and isinstance(tool_calls, list):
                        first_call = tool_calls[0]
                        fn_info = first_call.get("function", {})
                        fn_name = fn_info.get("name", "")
                        fn_args = fn_info.get("arguments", "{}")
                        return f"Action: {fn_name}\nAction Input: {fn_args}"

                    # If standard content is present
                    if content and isinstance(content, str) and content.strip():
                        cleaned_content = self._clean_reasoning_from_content(content)
                        if cleaned_content:
                            return cleaned_content
                        return content.strip()

                    # Raw reasoning traces (<thought>, chain-of-thought tokens) must never leak
                    if msg_obj.get("reasoning_content"):
                        logger.warning(
                            "[NVIDIA] Provider response omitted user-facing content (reasoning-only payload received). "
                            "Internal reasoning suppressed for security and output integrity."
                        )
                        self.last_error_code = "REASONING_ONLY"
                        return None

                    self.last_error_code = "EMPTY_RESPONSE"
                    return None

                # Case 2: Authentication / Authorization Errors (401, 403) - Non-retriable
                if resp.status_code in (401, 403):
                    self.last_error_code = "CREDENTIALS_INVALID"
                    logger.error(f"[NVIDIA] Authentication error ({resp.status_code}): Invalid or unauthorized API key.")
                    return None

                # Case 3: Rate Limiting (429) - Retriable with bounded backoff
                if resp.status_code == 429:
                    self.last_error_code = "RATE_LIMITED"
                    if attempt <= self.max_retries:
                        logger.warning(f"[NVIDIA] Rate limited (HTTP 429). Attempt {attempt}/{self.max_retries}. Backing off {backoff_delay}s...")
                        time.sleep(backoff_delay)
                        backoff_delay *= 2.0
                        continue
                    else:
                        logger.error("[NVIDIA] Rate limiting persisted; retries exhausted.")
                        return None

                # Case 4: Server Errors (500, 502, 503, 504) - Retriable
                if resp.status_code >= 500:
                    self.last_error_code = "SERVER_ERROR"
                    if attempt <= self.max_retries:
                        logger.warning(f"[NVIDIA] Server error (HTTP {resp.status_code}). Attempt {attempt}/{self.max_retries}. Backing off {backoff_delay}s...")
                        time.sleep(backoff_delay)
                        backoff_delay *= 2.0
                        continue
                    else:
                        logger.error(f"[NVIDIA] Server errors persisted (HTTP {resp.status_code}); retries exhausted.")
                        return None

                # Other HTTP Errors
                logger.error(f"[NVIDIA] Request failed with HTTP {resp.status_code}: {resp.text[:200]}")
                self.last_error_code = f"HTTP_{resp.status_code}"
                return None

            except requests.exceptions.Timeout:
                self.last_error_code = "AI_PROVIDER_TIMEOUT"
                logger.warning(f"[NVIDIA] Request timed out after {self.timeout}s (Attempt {attempt}).")
                # Do NOT perform blind serial retries on read timeout; fail fast for interactive responsiveness
                return None

            except requests.exceptions.ConnectionError as ce:
                self.last_error_code = "NETWORK_ERROR"
                clean_err = self._sanitize_error_message(str(ce))
                logger.warning(f"[NVIDIA] Connection error on attempt {attempt}: {clean_err}")
                if attempt <= self.max_retries:
                    time.sleep(backoff_delay)
                    continue
                return None

            except requests.exceptions.RequestException as e:
                clean_err = self._sanitize_error_message(str(e))
                self.last_error_code = "NETWORK_ERROR"
                logger.warning(f"[NVIDIA] Network error on attempt {attempt}: {clean_err}")
                return None

            except Exception as e:
                clean_err = self._sanitize_error_message(str(e))
                self.last_error_code = "UNEXPECTED_ERROR"
                logger.error(f"[NVIDIA] Unexpected error during generation: {clean_err}")
                return None

        return None

    def stream_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
        is_cancelled: Optional[Any] = None
    ) -> Generator[str, None, None]:
        """Streams response tokens from NVIDIA Nemotron endpoint with cancellation support."""
        self.last_error_code = None
        self.last_ttft_ms = None
        self.last_duration_ms = None

        if is_cancelled and callable(is_cancelled) and is_cancelled():
            self.last_error_code = "CANCELLED"
            logger.info("[NVIDIA Stream] Generation cancelled by caller before dispatch.")
            return

        if not self.is_available():
            self.last_error_code = "CREDENTIALS_INVALID"
            logger.warning("[NVIDIA Stream] Provider unavailable (missing or empty key).")
            return

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "JARVIS-Assistant/1.1"
        }
        ctx = context or {}
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": ctx.get("max_tokens", self.max_tokens),
            "temperature": ctx.get("temperature", self.temperature),
            "stream": True
        }

        resp = None
        t0 = time.time()
        req_timeout = self._get_timeout_tuple()
        deadline = time.time() + self.timeout

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=req_timeout, stream=True)
            if resp.status_code != 200:
                self.last_error_code = f"HTTP_{resp.status_code}"
                if resp.status_code in (401, 403):
                    self.last_error_code = "CREDENTIALS_INVALID"
                elif resp.status_code == 429:
                    self.last_error_code = "RATE_LIMITED"
                elif resp.status_code >= 500:
                    self.last_error_code = "SERVER_ERROR"
                logger.error(f"[NVIDIA Stream] Request failed with HTTP {resp.status_code}")
                return

            first_token = True
            for line in resp.iter_lines():
                if time.time() > deadline:
                    self.last_error_code = "AI_PROVIDER_TIMEOUT"
                    logger.warning(f"[NVIDIA Stream] Total stream deadline exceeded ({self.timeout:.1f}s). Aborting stream.")
                    break

                if is_cancelled and callable(is_cancelled) and is_cancelled():
                    self.last_error_code = "CANCELLED"
                    logger.info("[NVIDIA Stream] Generation cancelled by caller (barge-in/abort).")
                    break

                if line:
                    decoded = line.decode("utf-8").strip()
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_json = json.loads(data_str)
                            delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                            content_delta = delta.get("content")
                            # If content is present, yield user-facing token
                            if content_delta:
                                if first_token:
                                    first_token = False
                                    self.last_ttft_ms = (time.time() - t0) * 1000
                                    logger.info(f"[NVIDIA Stream] TTFT: {self.last_ttft_ms:.1f}ms on model '{self.model}'")
                                yield content_delta
                        except Exception:
                            continue
            self.last_duration_ms = (time.time() - t0) * 1000
        except requests.exceptions.Timeout:
            self.last_error_code = "AI_PROVIDER_TIMEOUT"
            logger.warning(f"[NVIDIA Stream] Request timed out after {self.timeout}s.")
        except requests.exceptions.ConnectionError:
            self.last_error_code = "NETWORK_ERROR"
            logger.warning("[NVIDIA Stream] Connection failed.")
        except Exception as e:
            self.last_error_code = "STREAM_ERROR"
            logger.error(f"[NVIDIA Stream] Error: {self._sanitize_error_message(str(e))}")
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
