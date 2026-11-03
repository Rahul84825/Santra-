import re
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger("Jarvis.TranscriptValidator")

class ValidationStatus:
    VALID = "VALID"
    EMPTY = "EMPTY"
    TOO_SHORT = "TOO_SHORT"
    FRAGMENT = "FRAGMENT"
    WAKEWORD_ONLY = "WAKEWORD_ONLY"
    REPETITIVE_HALLUCINATION = "REPETITIVE_HALLUCINATION"
    LIKELY_HALLUCINATION = "LIKELY_HALLUCINATION"

@dataclass
class ValidationResult:
    """Standardized validation result for Whisper speech transcripts."""
    raw_text: str
    cleaned_text: str
    status: str  # VALID, EMPTY, TOO_SHORT, FRAGMENT, WAKEWORD_ONLY, REPETITIVE_HALLUCINATION, LIKELY_HALLUCINATION
    is_valid: bool
    is_command_candidate: bool
    repetition_detected: bool
    repetition_ratio: float = 0.0
    original_repetition_count: int = 1
    confidence: float = 1.0
    is_hallucination_compressed: bool = False
    compression_ratio: float = 0.0

class TranscriptValidator:
    """Validates Whisper transcription outputs, detects hallucinations,
    compresses repetitive loops, and filters empty/noise artifacts.
    """

    KNOWN_CONVERSATIONAL_WORDS = {
        "okay", "ok", "yes", "yeah", "yup", "no", "nope", "please", "thanks", 
        "thank you", "bye", "goodbye", "hello", "hi", "hey", "what", "oh"
    }

    WAKE_WORD_TOKENS = {
        "santra", "jarvis", "goliya", "buddy", "sant", "samtra", "suntra", "santhra"
    }

    WAKE_PREFIX_TOKENS = {
        "hey", "hello", "hi", "ok", "okay"
    }

    LOW_INFO_FRAGMENTS = {
        "and else", "or else", "and then", "and", "or", "else", "then", "so", "but", "also",
        "and also", "what else", "anything else"
    }

    KNOWN_HALLUCINATION_PHRASES = {
        "thank you for watching", "thanks for watching", "subtitles by",
        "transcribed by", "amara.org", "please subscribe", "like and subscribe",
        "see you next time", "watching", "subscribe",
    }

    ACTION_VERBS = {
        "open", "launch", "start", "close", "exit", "terminate",
        "lock", "sleep", "restart", "shutdown", "reboot", "turn",
        "increase", "decrease", "mute", "unmute", "take",
        "show", "list", "search", "find", "minimize", "maximize", "restore",
        "run", "calculate", "solve", "play", "pause", "resume",
        "type", "insert", "send", "approve", "cancel", "deny", "explain"
    }

    QUERY_PREFIXES = {
        "what", "what's", "whats", "how", "how's", "hows", "tell", "check", "get", "show", "explain"
    }

    COMMAND_KEYWORDS = {
        "volume", "screenshot", "lock", "sleep", "restart", "shutdown",
        "tab", "tabs", "window", "windows"
    }

    SYSTEM_KEYWORDS = {
        "battery", "percentage", "volume", "screenshot", "lock", "sleep",
        "restart", "shutdown", "tab", "window", "wifi", "network",
        "time", "date", "weather", "cpu", "ram", "memory", "status"
    }

    def __init__(self):
        logger.info("Initializing Jarvis Transcript Validator and Hallucination Filter.")

    def validate(
        self,
        raw_text: Optional[str],
        confidence: float = 1.0,
        audio_duration: float = 0.0,
        compression_ratio: Optional[float] = None
    ) -> ValidationResult:
        """Evaluates raw Whisper transcript text and returns a ValidationResult."""
        if raw_text is None:
            return ValidationResult(
                raw_text="",
                cleaned_text="",
                status=ValidationStatus.EMPTY,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False
            )

        text = raw_text.strip()
        if not text:
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=ValidationStatus.EMPTY,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False
            )

        eff_comp_ratio = float(compression_ratio) if compression_ratio is not None else 0.0

        # 0. Check Whisper Segment Compression Ratio Hallucination Signature (> 2.4)
        if eff_comp_ratio > 2.4:
            logger.warning(
                f"[VALIDATOR] Discarding repetitive Whisper hallucination by compression_ratio: "
                f"{eff_comp_ratio:.2f} > 2.4 (raw='{raw_text[:60]}...')"
            )
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=ValidationStatus.REPETITIVE_HALLUCINATION,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=True,
                repetition_ratio=1.0,
                original_repetition_count=10,
                confidence=confidence,
                is_hallucination_compressed=False,
                compression_ratio=eff_comp_ratio
            )

        # Check single non-word characters, pure punctuation or isolated 1-char noise
        alphanumeric = re.sub(r'[^\w\s]', '', text).strip()
        if not alphanumeric or len(alphanumeric) <= 1:
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=ValidationStatus.TOO_SHORT,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False,
                compression_ratio=eff_comp_ratio
            )

        # Check low-information prepositional/conjunction fragments (e.g. "And else.", "Or else.")
        norm_alphanumeric = alphanumeric.lower().strip()
        if norm_alphanumeric in self.LOW_INFO_FRAGMENTS:
            logger.info(f"[VALIDATOR] Discarding low-information fragment: '{text}'")
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=ValidationStatus.FRAGMENT,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=False,
                compression_ratio=eff_comp_ratio
            )

        # Check wake-word only utterances (e.g. "Santra", "Hey Santra", "Santra, Santra...", "Santra,Santra")
        raw_tokens = [tok.lower() for tok in re.findall(r'[a-zA-Z0-9]+', text)]
        wake_tokens_present = [tok for tok in raw_tokens if tok in self.WAKE_WORD_TOKENS]
        if raw_tokens and all(tok in (self.WAKE_WORD_TOKENS | self.WAKE_PREFIX_TOKENS) for tok in raw_tokens):
            if wake_tokens_present and len(raw_tokens) <= 2:
                logger.info(f"[VALIDATOR] Wake-word address only: '{text}'")
                return ValidationResult(
                    raw_text=raw_text,
                    cleaned_text=text,
                    status=ValidationStatus.WAKEWORD_ONLY,
                    is_valid=False,
                    is_command_candidate=False,
                    repetition_detected=False,
                    compression_ratio=eff_comp_ratio
                )
            elif len(raw_tokens) > 2:
                logger.info(f"[VALIDATOR] Repetitive wake-word loop discarded ({len(raw_tokens)}x): '{text[:60]}...'")
                return ValidationResult(
                    raw_text=raw_text,
                    cleaned_text="",
                    status=ValidationStatus.REPETITIVE_HALLUCINATION,
                    is_valid=False,
                    is_command_candidate=False,
                    repetition_detected=True,
                    repetition_ratio=1.0,
                    original_repetition_count=len(raw_tokens),
                    compression_ratio=eff_comp_ratio
                )

        # 1. Repetitive Loop & Hallucination Analysis
        cleaned_text, rep_detected, rep_count, rep_ratio = self._analyze_and_compress_repetitions(text)

        # Check known silence hallucination phrases
        norm_clean = re.sub(r'[^\w\s]', '', cleaned_text).strip().lower()
        if norm_clean in self.KNOWN_HALLUCINATION_PHRASES or any(p in norm_clean for p in ["subtitles by", "amara.org", "transcribed by"]):
            logger.info(f"[VALIDATOR] Discarding known hallucination phrase: '{cleaned_text}'")
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=ValidationStatus.LIKELY_HALLUCINATION,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=rep_detected,
                repetition_ratio=rep_ratio,
                original_repetition_count=rep_count,
                confidence=confidence,
                is_hallucination_compressed=False,
                compression_ratio=eff_comp_ratio
            )

        # Discard critically low-confidence transcripts (< 0.20) as noise or hallucination
        if confidence is not None and isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            if confidence < 0.20:
                logger.info(f"[VALIDATOR] Discarding low-confidence transcript (confidence={confidence:.3f} < 0.20): '{cleaned_text}'")
                return ValidationResult(
                    raw_text=raw_text,
                    cleaned_text="",
                    status=ValidationStatus.LIKELY_HALLUCINATION,
                    is_valid=False,
                    is_command_candidate=False,
                    repetition_detected=rep_detected,
                    repetition_ratio=rep_ratio,
                    original_repetition_count=rep_count,
                    confidence=confidence,
                    is_hallucination_compressed=False,
                    compression_ratio=eff_comp_ratio
                )

        # 2. Check for Hallucination Signatures
        status = ValidationStatus.VALID
        is_valid = True
        is_known_conversational = (
            norm_clean in self.KNOWN_CONVERSATIONAL_WORDS
            or any(w in self.KNOWN_CONVERSATIONAL_WORDS for w in norm_clean.split())
        )

        if rep_detected:
            words = cleaned_text.lower().split()
            first_word = words[0] if words else ""
            clean_tokens = set(re.findall(r'\b\w+\b', cleaned_text.lower()))
            is_action_command = (
                first_word in self.ACTION_VERBS or
                any(w in self.ACTION_VERBS for w in words[:3]) or
                bool(clean_tokens & self.COMMAND_KEYWORDS) or
                any(cleaned_text.lower().startswith(p) for p in ["open", "launch", "type", "search", "close", "mute", "unmute", "lock", "shutdown", "restart", "volume"])
            )

            # If the repetition was purely wake words, discard
            if clean_tokens and all(tok in (self.WAKE_WORD_TOKENS | self.WAKE_PREFIX_TOKENS) for tok in clean_tokens):
                status = ValidationStatus.REPETITIVE_HALLUCINATION
                is_valid = False
                logger.info(f"[VALIDATOR] Discarding repetitive wake-word hallucination ({rep_count}x '{cleaned_text}')")
            elif is_action_command:
                # Compressed repetitive command (decoder loop recovery e.g. "Open Chrome" looped 30x)
                status = ValidationStatus.VALID
                is_valid = True
                logger.info(f"[VALIDATOR] Retained compressed repetitive command ({rep_count}x '{cleaned_text}'): raw='{raw_text[:60]}...'")
            elif (len(cleaned_text.split()) == 1 and rep_count >= 3) or rep_count >= 4:
                status = ValidationStatus.REPETITIVE_HALLUCINATION
                is_valid = False
                logger.info(f"[VALIDATOR] Discarding repetitive hallucination ({rep_count}x '{cleaned_text}'): raw='{raw_text[:60]}...'")
            elif rep_count >= 3 and not is_known_conversational:
                status = ValidationStatus.REPETITIVE_HALLUCINATION
                is_valid = False
                logger.info(f"[VALIDATOR] Discarding non-conversational repetitive hallucination ({rep_count}x '{cleaned_text}'): raw='{raw_text[:60]}...'")
            else:
                # Natural conversational repetition (e.g., "okay okay", "hello hello")
                status = ValidationStatus.VALID
                is_valid = True

        if not is_valid:
            return ValidationResult(
                raw_text=raw_text,
                cleaned_text="",
                status=status,
                is_valid=False,
                is_command_candidate=False,
                repetition_detected=rep_detected,
                repetition_ratio=rep_ratio,
                original_repetition_count=rep_count,
                confidence=confidence,
                is_hallucination_compressed=rep_detected,
                compression_ratio=eff_comp_ratio
            )

        # 3. Determine if candidate looks like an actionable command
        words = cleaned_text.lower().split()
        first_word = words[0] if words else ""
        clean_tokens = set(re.findall(r'\b\w+\b', cleaned_text.lower()))

        has_action = (
            first_word in self.ACTION_VERBS or
            any(w in self.ACTION_VERBS for w in words[:3]) or
            bool(clean_tokens & self.COMMAND_KEYWORDS) or
            (bool(words and words[0] in self.QUERY_PREFIXES) and bool(clean_tokens & self.SYSTEM_KEYWORDS))
        )

        logger.debug(f"[VALIDATOR] Raw: '{raw_text}' -> Cleaned: '{cleaned_text}' | Status: {status} | RepCount: {rep_count} | CommandCandidate: {has_action}")

        return ValidationResult(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            status=status,
            is_valid=True,
            is_command_candidate=has_action,
            repetition_detected=rep_detected,
            repetition_ratio=rep_ratio,
            original_repetition_count=rep_count,
            confidence=confidence,
            is_hallucination_compressed=rep_detected,
            compression_ratio=eff_comp_ratio
        )

    def _analyze_and_compress_repetitions(self, text: str) -> (str, bool, int, float):
        """Detects word or phrase-level looping repetitions (e.g., 'okay okay okay', 'oh please oh please')
        and compresses them into a single clean semantic representation.
        """
        # Split on sentence/phrase punctuation: commas, periods, exclamation marks, question marks
        raw_phrases = [p.strip() for p in re.split(r'[,.!?]+', text) if p.strip()]
        if len(raw_phrases) >= 2:
            normalized_phrases = [re.sub(r'[^\w\s]', '', p).lower().strip() for p in raw_phrases if p.strip()]
            if normalized_phrases and all(p == normalized_phrases[0] for p in normalized_phrases):
                rep_count = len(normalized_phrases)
                compressed = raw_phrases[0]
                ratio = rep_count / float(max(len(text.split()), 1))
                return compressed, True, rep_count, ratio

        # Word-level repetition check (e.g. "okay okay okay okay", "bye bye bye")
        words = text.split()
        if len(words) >= 3:
            norm_words = [re.sub(r'[^\w]', '', w).lower() for w in words if re.sub(r'[^\w]', '', w)]
            if not norm_words:
                return text, False, 1, 0.0

            # Check single word dominant repetition (e.g. 'Santra, Santra, ... Sant')
            from collections import Counter
            counts = Counter(norm_words)
            most_common_word, most_common_cnt = counts.most_common(1)[0]
            if most_common_cnt >= 3 and (most_common_cnt / float(len(norm_words))) >= 0.70:
                # 70%+ of the entire transcript is the exact same word
                return most_common_word, True, most_common_cnt, (most_common_cnt / float(len(norm_words)))

            # Check 1-word exact loop
            if all(w == norm_words[0] for w in norm_words):
                return words[0].strip(' ,.!?'), True, len(words), 1.0

            # Check 2-word loop (e.g. "oh please oh please oh please")
            if len(norm_words) >= 4 and len(norm_words) % 2 == 0:
                pattern = norm_words[:2]
                all_match = True
                for i in range(0, len(norm_words), 2):
                    if norm_words[i:i+2] != pattern:
                        all_match = False
                        break
                if all_match:
                    compressed_phrase = " ".join(words[:2]).strip(' ,.!?')
                    rep_count = len(norm_words) // 2
                    return compressed_phrase, True, rep_count, 1.0

            # Check multi-word phrase loop (e.g., "What do you want to do? What do you want to do?")
            half = len(words) // 2
            p1 = " ".join(norm_words[:half])
            p2 = " ".join(norm_words[half:half*2])
            if p1 == p2 and half >= 2:
                compressed_phrase = " ".join(words[:half]).strip(' ,.!?')
                return compressed_phrase, True, 2, 0.5

        return text, False, 1, 0.0

transcript_validator = TranscriptValidator()
