"""Unit and adversarial regression tests for Phase 4: Long-Duration Voice Safety,
Acoustic Noise Immunity, and False Activation Suppression.
"""

import unittest
import numpy as np
import time

from core.listener import SpeechListener
from core.transcript_validator import TranscriptValidator, ValidationStatus
from core.intent_engine import IntentEngine


class TestLongDurationVoiceSafety(unittest.TestCase):
    """Verifies that long periods of silence, continuous ambient drone, keyboard clicks,
    conversational fragments, and hallucination loops never trigger false speech detections
    or false command executions.
    """

    def setUp(self):
        self.listener = SpeechListener(
            sample_rate=16000,
            threshold=0.015,
            silence_duration=0.5,
            enable_vad_onset=True
        )
        self.validator = TranscriptValidator()
        self.intent_engine = IntentEngine()

    def test_30_minute_continuous_silence_simulation(self):
        """Simulates 30 minutes (1,800s / 14,062 audio chunks) of continuous ambient silence.
        Verifies 0 false speech start events and 0 false speech end events.
        """
        total_sec = 1800.0
        chunk_samples = 2048
        total_chunks = int((total_sec * 16000) / chunk_samples)

        silent_chunk = np.zeros((chunk_samples, 1), dtype=np.float32)
        speech_start_count = 0
        speech_end_count = 0

        self.listener.on_speech_start = lambda: speech_start_count.__setitem__(0, speech_start_count[0] + 1) if isinstance(speech_start_count, list) else None
        
        start_events = []
        end_events = []
        self.listener.on_speech_start = lambda: start_events.append(1)
        self.listener.on_speech_end = lambda path: end_events.append(path)
        self.listener.is_listening = True

        for _ in range(total_chunks):
            self.listener._audio_callback(silent_chunk, chunk_samples, None, None)

        self.assertEqual(len(start_events), 0, "Silence must trigger zero speech start events.")
        self.assertEqual(len(end_events), 0, "Silence must trigger zero speech end events.")

    def test_ambient_acoustic_noise_immunity(self):
        """Simulates low-frequency fan noise and sharp keyboard clicks to ensure
        acoustic noise does not trigger false recordings.
        """
        sample_rate = 16000
        chunk_samples = 2048

        # 60s low-frequency drone (120Hz + 240Hz harmonics + noise)
        duration_sec = 60.0
        n_samples = int(duration_sec * sample_rate)
        t = np.linspace(0, duration_sec, n_samples, endpoint=False)
        hum = 0.008 * np.sin(2 * np.pi * 120 * t) + 0.004 * np.sin(2 * np.pi * 240 * t)
        noise = np.random.normal(0, 0.003, n_samples)
        fan_audio = (hum + noise).astype(np.float32)

        start_events = []
        self.listener.on_speech_start = lambda: start_events.append(1)
        self.listener.on_speech_end = lambda p: None
        self.listener.is_listening = True

        for i in range(0, n_samples - chunk_samples, chunk_samples):
            chunk = fan_audio[i:i+chunk_samples].reshape(-1, 1)
            self.listener._audio_callback(chunk, chunk_samples, None, None)

        self.assertEqual(len(start_events), 0, "Fan noise must not trigger false speech start.")

    def test_adversarial_transcript_validation(self):
        """Tests that adversarial non-commands, silence transcripts, YouTube outro phrases,
        and conversational phrases are rejected, while genuine commands are accepted.
        """
        adversarial_transcripts = [
            # Silence & empty
            ("", "EMPTY", False),
            ("   ", "WHITESPACE", False),
            (".", "PUNCTUATION_ONLY", False),
            ("...", "ELLIPSIS", False),
            # Repetitive hallucination loops
            ("Google Google Google Google Google", "REPETITIVE_HALLUCINATION", False),
            ("thank you thank you thank you thank you", "REPETITIVE_HALLUCINATION", False),
            ("okay okay okay okay okay okay", "REPETITIVE_HALLUCINATION", False),
            # Known YouTube/Video artifacts
            ("Thank you for watching.", "YOUTUBE_OUTRO", False),
            ("Subscribe to my channel.", "YOUTUBE_ARTIFACT", False),
            ("Subtitles by the Amara.org community", "SUBTITLE_CREDIT", False),
            ("[BLANK_AUDIO]", "WHISPER_SPECIAL_TOKEN", False),
            # Partial & ambiguous fragments
            ("the", "STOPWORD_FRAGMENT", False),
            ("and then", "CONJUNCTION_FRAGMENT", False),
            ("or", "SHORT_PARTIAL", False),
            # Similar-sounding non-commands (without wake word / imperative intent)
            ("Santa is coming to town", "CONVERSATIONAL_SPEECH", False),
            ("Sandra called me yesterday", "CONVERSATIONAL_SPEECH", False),
            ("The center of the table", "CONVERSATIONAL_SPEECH", False),
            # Genuine valid commands
            ("Open Chrome", "VALID_COMMAND", True),
            ("Take a screenshot", "VALID_COMMAND", True),
            ("Lock the computer", "VALID_COMMAND", True),
            ("What is my battery percentage?", "VALID_COMMAND", True),
            ("Mute audio", "VALID_COMMAND", True)
        ]

        false_positives = []
        false_negatives = []

        for text, category, expected_valid in adversarial_transcripts:
            val_res = self.validator.validate(text)
            is_valid = (val_res.status == ValidationStatus.VALID and val_res.is_command_candidate)

            if expected_valid and not is_valid:
                false_negatives.append((text, val_res.status))
            elif not expected_valid and is_valid:
                false_positives.append((text, val_res.status))

        self.assertEqual(len(false_positives), 0, f"False positives detected: {false_positives}")
        self.assertEqual(len(false_negatives), 0, f"False negatives detected: {false_negatives}")

    def test_ambiguous_conversational_phrases_gated_by_intent_engine(self):
        """Tests that conversational or ambiguous statements do not resolve to high-risk actions."""
        ambiguous_phrases = [
            "maybe open chrome",
            "i was thinking about google",
            "could you perhaps do something",
            "not now santra",
            "hey are you listening"
        ]
        for phrase in ambiguous_phrases:
            parsed = self.intent_engine.parse(phrase)
            intent = parsed.get("intent") if isinstance(parsed, dict) else getattr(parsed, "intent", None)
            self.assertIn(
                intent,
                [None, "unknown", "conversation", "ambiguous", "general_query", "greeting"],
                f"Phrase '{phrase}' resolved to unsafe intent '{intent}'"
            )


if __name__ == "__main__":
    unittest.main()

