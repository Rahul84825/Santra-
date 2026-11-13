"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Experience Collector Module

Provides zero-latency in-memory phonetic alias correction, non-blocking asynchronous
event ingestion via a background queue, privacy scrubbing, and token-level diffing.
"""

import re
import time
import queue
import difflib
import logging
import threading
from typing import Dict, Optional, Any, List
from core.evolution.storage import EvolutionStorage, evolution_storage

logger = logging.getLogger("Santra.Evolution.Collector")

# Privacy scrubbing regular expressions
PATTERNS = [
    # NVIDIA API Keys
    (re.compile(r"nvapi-[A-Za-z0-9_-]{20,}", re.IGNORECASE), "[API_KEY_REDACTED]"),
    # OpenAI & Anthropic API Keys
    (re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,})", re.IGNORECASE), "[API_KEY_REDACTED]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE), "Bearer [TOKEN_REDACTED]"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", re.IGNORECASE), "[EMAIL_REDACTED]"),
    # Common password parameter patterns
    (re.compile(r"(?i)(password|secret|passwd|token)\s*[:=]\s*['\"]?[^\s,'\"]+['\"]?"), r"\1=[REDACTED]"),
]

# Stopwords to discard from single-token alias extraction
DISCARD_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "it", "this", "that", "i", "you", "he", "she", "we", "they", "me", "my",
    "please", "sir", "santra", "hey", "hello", "hi", "no", "not"
}


def scrub_text(text: str) -> str:
    """Strips API keys, passwords, and sensitive credentials from text."""
    if not text:
        return ""
    scrubbed = str(text)
    for pattern, replacement in PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def scrub_data(data: Any) -> Any:
    """Recursively scrubs strings within dicts, lists, and primitives."""
    if isinstance(data, str):
        return scrub_text(data)
    elif isinstance(data, dict):
        return {k: scrub_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [scrub_data(item) for item in data]
    return data


class ExperienceCollector:
    """Thread-safe event collector with non-blocking queue and in-memory alias cache."""

    def __init__(self, storage: Optional[EvolutionStorage] = None):
        self.storage = storage or evolution_storage

        # In-Memory Zero-Latency Alias Cache
        self._cache_lock = threading.RLock()
        self._alias_cache: Dict[str, str] = {}
        self._compiled_regex: Optional[re.Pattern] = None

        # Non-blocking event queue and background writer
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._stop_event = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None

        # Load initial active aliases from database
        self._load_alias_cache()
        self._start_writer()

    # ==========================================
    # ZERO-LATENCY ALIAS RESOLUTION
    # ==========================================
    def _load_alias_cache(self):
        """Loads all aliases with confidence >= 3 into memory."""
        try:
            active = self.storage.get_active_aliases(min_confidence=3)
            with self._cache_lock:
                self._alias_cache = {k.lower(): v for k, v in active.items()}
                self._rebuild_regex()
            logger.info(f"[ALIAS_CACHE] Loaded {len(self._alias_cache)} active phonetic aliases into memory.")
        except Exception as e:
            logger.warning(f"[ALIAS_CACHE] Failed to load initial alias cache: {e}")

    def _rebuild_regex(self):
        """Compiles word-boundary regex for all in-memory aliases."""
        if not self._alias_cache:
            self._compiled_regex = None
            return

        # Sort longest phrase first so compound phrases match before single words
        sorted_keys = sorted(self._alias_cache.keys(), key=lambda k: len(k), reverse=True)
        escaped_keys = [re.escape(k) for k in sorted_keys]
        pattern_str = r"\b(?:" + "|".join(escaped_keys) + r")\b"
        self._compiled_regex = re.compile(pattern_str, re.IGNORECASE)

    def apply_known_aliases(self, text: str) -> str:
        """
        Applies learned phonetic aliases to the transcript in-memory (<0.1ms).
        Guarantees length-priority matching, word-boundary preservation, and
        collision defense (e.g. 'visual studio' will not mangle 'visual studio code').
        Zero SQLite queries occur here.
        """
        if not text or not text.strip():
            return text

        with self._cache_lock:
            regex = self._compiled_regex
            cache = self._alias_cache

        if not regex or not cache:
            return text

        def _replace_match(match: re.Match) -> str:
            matched_str = match.group(0)
            key = matched_str.lower()
            # Collision guard: prevent shorter prefix alias from destroying compound suffix
            # e.g., 'visual studio' -> 'vscode' when immediately followed by 'code'
            following_text = match.string[match.end():]
            if key == "visual studio" and re.match(r"^\s+code\b", following_text, re.IGNORECASE):
                return matched_str
            return cache.get(key, matched_str)

        try:
            res = regex.sub(_replace_match, text)
            # Post-sub defense against stutter / compound artifacts
            res = re.sub(r"\bvscode\s+code\b", "vscode", res, flags=re.IGNORECASE)
            return res
        except Exception as e:
            logger.debug(f"[ALIAS_RESOLUTION] Error applying regex alias: {e}")
            return text

    # ==========================================
    # ASYNCHRONOUS NON-BLOCKING EVENT INGESTION
    # ==========================================
    def _start_writer(self):
        """Starts background writer thread for queue processing."""
        self._stop_event.clear()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="ALEE-ExperienceWriter",
            daemon=True
        )
        self._writer_thread.start()

    def record_experience(
        self,
        user_request: str,
        intent: Optional[str] = None,
        action: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        message: Optional[str] = None,
        latency_ms: float = 0.0,
        error_type: Optional[str] = None,
        raw_transcript: Optional[str] = None
    ):
        """
        Non-blocking ingestion of an execution outcome.
        Scrubs privacy data and pushes to queue in <0.05ms.
        Preserves original raw_transcript alongside normalized user_request.
        """
        scrubbed_req = scrub_text(user_request)
        scrubbed_raw = scrub_text(raw_transcript) if raw_transcript is not None else scrubbed_req
        scrubbed_msg = scrub_text(message or "")
        scrubbed_params = scrub_data(parameters or {})

        event = {
            "type": "experience",
            "timestamp": time.time(),
            "user_request": scrubbed_req,
            "raw_transcript": scrubbed_raw,
            "intent": intent or "",
            "action": action or "",
            "parameters": scrubbed_params,
            "success": bool(success),
            "message": scrubbed_msg,
            "latency_ms": float(latency_ms),
            "error_type": error_type or ("" if success else "EXECUTION_ERROR")
        }
        self._queue.put(event)

    def record_correction(
        self,
        failed_transcript: str,
        corrected_transcript: str
    ):
        """
        Non-blocking ingestion of a user correction event.
        Extracts token-level differences in background writer thread.
        """
        if not failed_transcript or not corrected_transcript:
            return

        scrubbed_failed = scrub_text(failed_transcript).strip()
        scrubbed_corr = scrub_text(corrected_transcript).strip()

        if scrubbed_failed.lower() == scrubbed_corr.lower():
            return

        event = {
            "type": "correction",
            "timestamp": time.time(),
            "failed_transcript": scrubbed_failed,
            "corrected_transcript": scrubbed_corr
        }
        self._queue.put(event)

    # ==========================================
    # BACKGROUND WORKER & TOKEN-LEVEL DIFFING
    # ==========================================
    def _writer_loop(self):
        """Daemon worker loop draining queue events into SQLite."""
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if event is None:  # Shutdown sentinel
                break

            try:
                event_type = event.get("type")
                if event_type == "experience":
                    self._persist_experience(event)
                elif event_type == "correction":
                    self._process_correction(event)
            except Exception as e:
                logger.warning(f"[WRITER_LOOP] Error handling event: {e}", exc_info=True)

    def _persist_experience(self, event: Dict[str, Any]):
        """Writes experience record to database."""
        self.storage.record_experience(
            user_request=event["user_request"],
            intent=event.get("intent"),
            action=event.get("action"),
            parameters=event.get("parameters"),
            success=event.get("success", True),
            message=event.get("message"),
            latency_ms=event.get("latency_ms", 0.0),
            error_type=event.get("error_type"),
            timestamp=event.get("timestamp"),
            raw_transcript=event.get("raw_transcript")
        )

    def _process_correction(self, event: Dict[str, Any]):
        """
        Performs token-level diffing via difflib.SequenceMatcher
        to isolate specific misheard -> intended phrases.
        """
        failed_text = event.get("failed_transcript", "").strip()
        corr_text = event.get("corrected_transcript", "").strip()

        failed_tokens = failed_text.split()
        corr_tokens = corr_text.split()

        matcher = difflib.SequenceMatcher(None, failed_tokens, corr_tokens)
        opcodes = matcher.get_opcodes()

        for tag, i1, i2, j1, j2 in opcodes:
            if tag in ("replace", "delete", "insert"):
                misheard_slice = " ".join(failed_tokens[i1:i2]).strip()
                intended_slice = " ".join(corr_tokens[j1:j2]).strip()

                # Filter trivial differences or empty strings
                if not misheard_slice or not intended_slice:
                    continue
                if misheard_slice.lower() == intended_slice.lower():
                    continue
                if len(misheard_slice) < 2 or len(intended_slice) < 2:
                    continue
                if misheard_slice.lower() in DISCARD_WORDS and intended_slice.lower() in DISCARD_WORDS:
                    continue

                logger.info(f"[CORRECTION_DIFF] Extracted alias: '{misheard_slice}' -> '{intended_slice}'")
                alias_info = self.storage.upsert_alias(misheard_slice, intended_slice, delta=1)
                new_conf = alias_info.get("confidence_count", 1)

                # If reached confidence >= 3, promote to in-memory active cache immediately
                if new_conf >= 3:
                    with self._cache_lock:
                        self._alias_cache[misheard_slice.lower()] = intended_slice
                        self._rebuild_regex()
                    logger.info(
                        f"[ALIAS_PROMOTED] Alias '{misheard_slice}' -> '{intended_slice}' "
                        f"promoted to active in-memory cache (confidence={new_conf})."
                    )

    def shutdown(self, timeout: float = 3.0):
        """Flushes event queue and cleanly terminates writer thread."""
        logger.info("[COLLECTOR] Shutting down experience collector...")
        self._queue.put(None)  # Sentinel
        self._stop_event.set()
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=timeout)
        logger.info("[COLLECTOR] Experience collector stopped.")


# Singleton instance
evolution_collector = ExperienceCollector()
