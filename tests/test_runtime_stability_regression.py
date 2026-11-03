"""SANTRA Runtime Stability and Duplicate Response Regression Test Suite.
Tests Groups A, B, C, D, E, F and Concurrency / Stress Scenarios.
"""

import os
import sys
import time
import unittest
import threading
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.jarvis_runtime import JarvisRuntime, LEGAL_TRANSITIONS
from core.tts.tts_manager import TTSManager
from core.conversation_manager import ConversationManager, ExplanationState
from core.listener import SpeechListener
from core.transcriber import SpeechTranscriber


def get_mocked_runtime():
    """Helper to instantiate JarvisRuntime safely without occupying physical audio streams."""
    with patch("core.listener.SpeechListener.start"), \
         patch("core.wakeword.WakeWordDetectorFactory.create_detector"), \
         patch("core.transcriber.SpeechTranscriber.preload_in_background"), \
         patch("sounddevice.stop"), \
         patch("sounddevice.play"):
        rt = JarvisRuntime()
        rt.transcriber.preload_in_background = MagicMock()
        return rt


class TestGroupA_DuplicateResponsePrevention(unittest.TestCase):
    """Test group A: Verifies single-response lifecycle, idempotency, and deduplication."""

    def setUp(self):
        self.tts = TTSManager()
        self.conv = ConversationManager(max_turns=10)

    def test_single_input_single_worker(self):
        """Verify that an identical utterance dispatched twice with same ID is deduplicated."""
        runtime = get_mocked_runtime()
        try:
            uid = "UTT_A01"
            processed_count = 0
            lock = threading.Lock()

            def mock_worker(*args, **kwargs):
                nonlocal processed_count
                with lock:
                    processed_count += 1

            runtime._process_command_worker = mock_worker

            # Rapid duplicate dispatches with same utterance_id
            runtime.process_command("open chrome", utterance_id=uid)
            runtime.process_command("open chrome", utterance_id=uid)

            time.sleep(0.05)
            self.assertEqual(processed_count, 1, "Duplicate utterance_id should only dispatch worker once")
        finally:
            runtime.stop()

    def test_rapid_identical_bursts_deduplicated_without_uid(self):
        """Verify that rapid bursts (<1.2s) without distinct utterance ID are deduplicated."""
        runtime = get_mocked_runtime()
        try:
            self.assertFalse(runtime._is_duplicate_request("open chrome", utterance_id=None))
            self.assertTrue(runtime._is_duplicate_request("open chrome", utterance_id=None))
        finally:
            runtime.stop()

    def test_distinct_spoken_utterance_repeats_earlier_command_normally(self):
        """Verify that identical text from two legitimately distinct spoken requests is allowed."""
        runtime = get_mocked_runtime()
        try:
            self.assertFalse(runtime._is_duplicate_request("what time is it", utterance_id="UTT_1"))
            self.assertFalse(runtime._is_duplicate_request("what time is it", utterance_id="UTT_2"))
        finally:
            runtime.stop()

    def test_duplicate_tts_callback_ignored(self):
        """Verify that stale generations cannot queue or speak."""
        tts = TTSManager()
        tts.interrupt()
        initial_gen = tts.current_generation_id

        # Stale generation cannot speak
        tts.speak("Stale generation speech", interrupt=False, generation_id=initial_gen - 1)
        self.assertEqual(tts.speech_queue.qsize(), 0)

    def test_stream_chunks_do_not_revive_interrupted_generation(self):
        """Verify that arriving stream chunks do not revive an interrupted stream."""
        tts = TTSManager()
        tts.interrupt()  # Sets _interrupt_event and increments gen
        self.assertTrue(tts._interrupt_event.is_set())

        # An incoming stream chunk without interrupt=True must be dropped safely
        tts.enqueue_stream_sentence("Late chunk arriving after interruption", stream_job_id="test_stream", sentence_index=1, interrupt=False)
        self.assertEqual(tts.speech_queue.qsize(), 0)


class TestGroupB_SleepMode(unittest.TestCase):
    """Test group B: Invalidation of active requests, TTS stoppage, and sleep lifecycle."""

    def test_sleep_mode_blocks_conversation_speech(self):
        """Verify that speech is rejected while TTSManager is in sleep mode, except sleep confirmation."""
        tts = TTSManager()
        tts.set_sleep_mode(True)

        # Standard speech rejected
        tts.speak("This should not speak in sleep mode", job_id="conv_late")
        self.assertEqual(tts.speech_queue.qsize(), 0)

        # Stream chunk rejected
        tts.enqueue_stream_sentence("Stream chunk in sleep", stream_job_id="stream_late")
        self.assertEqual(tts.speech_queue.qsize(), 0)

        # Sleep confirmation explicitly allowed
        tts.speak("Entering sleep mode, Sir.", job_id="sleep_confirm")
        self.assertEqual(tts.speech_queue.qsize(), 1)

    def test_enter_sleep_mode_marks_active_request_cancelled(self):
        """Verify that enter_sleep_mode sets cancellation event and records active utterance."""
        runtime = get_mocked_runtime()
        try:
            runtime._active_utterance_id = "UTT_ACTIVE"

            runtime.enter_sleep_mode(reason="user_request", speak=False)

            self.assertEqual(runtime.current_status, "SLEEPING")
            self.assertTrue(runtime._sleep_cancel_event.is_set())
            self.assertIn("UTT_ACTIVE", runtime._cancelled_utterance_ids)
            self.assertTrue(runtime.tts_manager._sleep_mode)
        finally:
            runtime.stop()

    def test_wake_clears_sleep_mode_and_cancellation(self):
        """Verify waking up restores normal operation."""
        runtime = get_mocked_runtime()
        try:
            runtime.enter_sleep_mode(speak=False)
            self.assertEqual(runtime.current_status, "SLEEPING")

            runtime.wake_up(source="voice", force=True)
            self.assertFalse(runtime._sleep_cancel_event.is_set())
            self.assertFalse(runtime.tts_manager._sleep_mode)
            self.assertIn(runtime.current_status, ["WAKING", "STANDBY", "ACTIVE", "LISTENING"])
        finally:
            runtime.stop()


class TestGroupC_InterruptionAndExplanationResumption(unittest.TestCase):
    """Test group C: Interrupted explanations retain context and resume instantly."""

    def test_explanation_tracking_and_interruption(self):
        """Verify that multi-sentence explanation records progress and marks interrupted."""
        cm = ConversationManager()
        text = "First sentence of the concept. Second sentence with details. Third sentence summarizing everything."
        cm.set_active_explanation(topic="quantum computing", goal="explain quantum computing", text=text)

        self.assertIsNotNone(cm.explanation_state)
        self.assertEqual(len(cm.explanation_state.sentences), 3)

        # Simulate user listening to first sentence, then interrupting
        cm.update_sentence_progress(sentence_idx=0, total_sentences=3, text=cm.explanation_state.sentences[0])
        cm.mark_interrupted()

        self.assertTrue(cm.has_interrupted_explanation())
        self.assertEqual(cm.explanation_state.current_sentence_idx, 0)

    def test_instant_continuation_without_remote_query(self):
        """Verify that saying 'continue' resumes remaining sentences instantly without calling LLM."""
        cm = ConversationManager()
        text = "Step one is initialization. Step two is configuration. Step three is execution."
        cm.set_active_explanation(topic="setup", goal="explain setup", text=text)
        cm.update_sentence_progress(sentence_idx=0, total_sentences=3, text="Step one is initialization.")
        cm.mark_interrupted()

        # Call process_query with 'continue'
        res = cm.process_query("continue")

        self.assertEqual(res.get("source"), "SANTRA Explanation Engine")
        self.assertEqual(res.get("tool_used"), "resume_explanation")
        self.assertIn("Step two is configuration.", res["text"])
        self.assertIn("Step three is execution.", res["text"])
        self.assertFalse(cm.has_interrupted_explanation())


class TestGroupD_RuntimeStateTransitions(unittest.TestCase):
    """Test group D: State machine guarantees and legal/illegal transitions."""

    def test_legal_barge_in_transitions_from_speaking(self):
        """Verify that barge-in transitions from SPEAKING to LISTENING, TRANSCRIBING, PROCESSING are permitted."""
        allowed_from_speaking = LEGAL_TRANSITIONS["SPEAKING"]
        self.assertIn("LISTENING", allowed_from_speaking)
        self.assertIn("TRANSCRIBING", allowed_from_speaking)
        self.assertIn("PROCESSING", allowed_from_speaking)

    def test_sleeping_guards_against_illegal_speaking_transition(self):
        """Verify that while SLEEPING, speaker start event does not illegally transition state to SPEAKING."""
        runtime = get_mocked_runtime()
        try:
            runtime.enter_sleep_mode(speak=False)
            self.assertEqual(runtime.current_status, "SLEEPING")

            # Simulate TTS playback starting (e.g. from an audio callback)
            runtime._on_speaker_started()
            self.assertEqual(runtime.current_status, "SLEEPING", "Status must remain SLEEPING when speaker starts in sleep mode")
        finally:
            runtime.stop()


class TestGroupE_AudioWatchdogAndListener(unittest.TestCase):
    """Test group E: Watchdog threshold, listener speech recording, and Whisper unload safety."""

    def test_listener_zero_frame_threshold_not_premature(self):
        """Verify that silent zero frames under 300 do not report stream unhealthy if callback is active."""
        listener = SpeechListener()
        listener._stream = MagicMock(active=True)
        listener._last_callback_time = time.time()
        listener._zero_frame_count = 100  # > 60 but normal room silence

        healthy, reason = listener.is_stream_healthy()
        self.assertTrue(healthy, f"Expected healthy stream on room silence, got: {reason}")

    def test_whisper_defer_unload_during_active_transcription(self):
        """Verify unload_model returns False and defers unload if active transcription is running."""
        stt = SpeechTranscriber()
        stt._model = MagicMock()
        stt._active_transcriptions = 1

        unloaded = stt.unload_model()
        self.assertFalse(unloaded, "Unload should be deferred when active transcription is in progress")
        self.assertIsNotNone(stt._model, "Model must not be destroyed while active transcription is running")

        # When active transcriptions finish, unload succeeds
        stt._active_transcriptions = 0
        unloaded = stt.unload_model()
        self.assertTrue(unloaded)
        self.assertIsNone(stt._model)


class TestGroupF_ProjectIntelligencePanel(unittest.TestCase):
    """Test group F: Project Intelligence Panel initialization and attribute safety."""

    def test_content_widget_attribute_exists(self):
        """Verify ProjectIntelligencePanel has content_widget attribute without raising AttributeError."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.panels.project_intelligence_panel import ProjectIntelligencePanel

        panel = ProjectIntelligencePanel()
        self.assertTrue(hasattr(panel, "content_widget"))
        self.assertIsNotNone(panel.content_widget)
        self.assertTrue(hasattr(panel, "tabs"))


class TestStressAndConcurrency(unittest.TestCase):
    """Controlled stress tests: 20 consecutive requests, rapid interruption, sleep/wake cycles."""

    def test_consecutive_conversation_requests_and_turn_id_idempotency(self):
        """Simulate 20 requests and ensure turn_ids are properly finalized."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.main_window import MainWindow

        win = MainWindow()
        for i in range(20):
            uid = f"TEST_TURN_{i:02d}"
            # Step 1: Query notification (should not add card)
            win._on_pipeline_stage_updated("test query", "test query", "chat", "NVIDIA NEMOTRON — REQUESTING", "Querying NVIDIA Nemotron...", "Processing", turn_id=uid)
            # Step 2: Stream chunk (adds/updates card)
            win._on_pipeline_stage_updated("test query", "test query", "chat", "NVIDIA NEMOTRON — PROCESSING", f"Chunk for {i}", "Synthesizing", turn_id=uid)
            # Step 3: Final response (finalizes card)
            win._on_pipeline_stage_updated("test query", "test query", "chat", "NVIDIA NEMOTRON — RESPONSE RECEIVED", f"Full response for {i}", "Speaking", turn_id=uid)
            # Step 4: Duplicate delayed callback (should be ignored safely)
            win._on_pipeline_stage_updated("test query", "test query", "chat", "NVIDIA NEMOTRON — RESPONSE RECEIVED", f"Duplicate response for {i}", "Speaking", turn_id=uid)

        # Assert all 20 assistant turn_ids were registered and finalized without duplicate cards
        for i in range(20):
            self.assertIn(f"TEST_TURN_{i:02d}", win._finalized_turn_ids)
        # Check that 'Querying NVIDIA Nemotron...' never became a turn
        for turn in win._turns:
            self.assertNotEqual(turn.get("text"), "Querying NVIDIA Nemotron...")

    def test_10_rapid_sleep_wake_cycles(self):
        """Verify 10 rapid Sleep/Wake cycles do not corrupt state."""
        runtime = get_mocked_runtime()
        try:
            for i in range(10):
                runtime.enter_sleep_mode(speak=False)
                self.assertEqual(runtime.current_status, "SLEEPING")
                self.assertTrue(runtime._sleep_cancel_event.is_set())

                runtime.wake_up(source="stress_test", force=True)
                self.assertFalse(runtime._sleep_cancel_event.is_set())
                self.assertIn(runtime.current_status, ["WAKING", "STANDBY", "ACTIVE", "LISTENING"])
        finally:
            runtime.stop()


if __name__ == "__main__":
    unittest.main()
