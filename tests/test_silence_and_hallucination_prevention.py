import os
import time
import unittest
import numpy as np
from unittest.mock import MagicMock, patch

from core.listener import SpeechListener
from core.transcriber import SpeechTranscriber
from core.transcript_validator import transcript_validator, ValidationStatus
from core.jarvis_runtime import JarvisRuntime


def _wait_for(condition_fn, timeout=1.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if condition_fn():
            return True
        time.sleep(0.02)
    return False


class TestSilenceAndHallucinationPrevention(unittest.TestCase):
    """Exhaustive regression test suite verifying silence detection,
    hallucination suppression, idempotency, audio buffer isolation,
    and preventing repeated command execution.
    """

    def setUp(self):
        self.listener = SpeechListener(
            sample_rate=16000,
            threshold=0.015,
            silence_duration=0.5,
            max_duration=3.0,
            enable_vad_onset=True
        )

    def tearDown(self):
        if hasattr(self, "listener") and self.listener:
            self.listener.stop()

    def test_01_continuous_silence_produces_zero_transcripts_and_zero_commands(self):
        """1. Continuous silence for 30s produces zero transcripts and zero commands."""
        executed_commands = []
        transcripts = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.transcriber.transcribe = MagicMock(side_effect=lambda p: transcripts.append(p) or "")
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed_commands.append(n) or {"success": True})

            # Simulate 30 seconds of audio frames (chunks of 2048 samples at 16kHz = ~128ms per chunk)
            # 30s / 0.128s ~= 235 frames of ambient silence (RMS ~ 0.001)
            silent_chunk = np.zeros((2048, 1), dtype=np.float32)

            runtime.listener.start(runtime._on_speech_start, runtime._on_speech_end)
            for _ in range(240):
                runtime.listener._audio_callback(silent_chunk, 2048, None, None)

            # Assert listener remained in standby and never dispatched recording
            self.assertEqual(len(transcripts), 0, "Silence must not produce any transcripts.")
            self.assertEqual(len(executed_commands), 0, "Silence must produce zero commands.")
            self.assertEqual(runtime.current_status, "STANDBY")
            runtime.stop()

    def test_02_silence_immediately_after_command_does_not_repeat_execution(self):
        """2. Silence immediately after saying 'Open Google' does not execute it again."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True, "message": "Opened"})

            # First, genuine spoken utterance
            u1 = "UTTER_001"
            runtime.process_command("open google", utterance_id=u1)
            self.assertTrue(_wait_for(lambda: len(executed) == 1), "First command must execute once.")

            # Now simulate subsequent silence/noise callback (empty or discarded WAV)
            runtime._on_speech_end("")
            time.sleep(0.15)

            # Assert no additional execution occurred
            self.assertEqual(len(executed), 1, "Subsequent silence must cause zero additional executions.")
            runtime.stop()

    def test_03_empty_stt_result_never_reuses_previous_command(self):
        """3. An empty STT result never reuses 'Open Google' or any prior command."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            # User speaks Open Google
            runtime.process_command("Open Google", utterance_id="UTTER_CMD1")
            self.assertTrue(_wait_for(lambda: len(executed) == 1))

            # Next utterance transcribes to empty string (silence/inaudible)
            with patch.object(runtime.transcriber, "transcribe", return_value=""):
                import tempfile
                fd, path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                try:
                    runtime._on_speech_end(path)
                    time.sleep(0.15)
                finally:
                    if os.path.exists(path):
                        os.remove(path)

            self.assertEqual(len(executed), 1, "Empty STT must never fall back or replay previous command.")
            self.assertEqual(runtime.current_status, "STANDBY")
            runtime.stop()

    def test_04_failed_transcription_never_falls_back_to_previous_transcript(self):
        """4. A failed transcription never falls back to the previous transcript."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            # First command succeeds
            runtime.process_command("Open Google", utterance_id="UTTER_OK")
            self.assertTrue(_wait_for(lambda: len(executed) == 1))

            # Transcriber raises an exception
            with patch.object(runtime.transcriber, "transcribe", side_effect=RuntimeError("Whisper decode error")):
                import tempfile
                fd, path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                try:
                    runtime._on_speech_end(path)
                    time.sleep(0.15)
                finally:
                    if os.path.exists(path):
                        os.remove(path)

            self.assertEqual(len(executed), 1, "Failed transcription must not execute any command.")
            runtime.stop()

    def test_05_duplicate_callback_for_one_utterance_executes_at_most_once(self):
        """5. A duplicate callback for one utterance executes the command at most once."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            uid = "SAME_UTTERANCE_ID"
            # Dispatch multiple times concurrently or rapidly
            runtime.process_command("open google", utterance_id=uid)
            runtime.process_command("open google", utterance_id=uid)
            runtime.process_command("open google", utterance_id=uid)
            self.assertTrue(_wait_for(lambda: len(executed) == 1))
            time.sleep(0.15)

            self.assertEqual(len(executed), 1, "Same utterance ID must execute at most once.")
            runtime.stop()

    def test_06_new_separately_spoken_command_works_normally(self):
        """6. A new, separately spoken 'Open Google' works normally (not blocked by a blunt cooldown)."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            # Utterance 1
            runtime.process_command("open google", utterance_id="UTTER_1")
            self.assertTrue(_wait_for(lambda: len(executed) == 1))

            # Utterance 2 (distinct utterance)
            runtime.process_command("open google", utterance_id="UTTER_2")
            self.assertTrue(_wait_for(lambda: len(executed) == 2), "Distinct utterance with same text must execute normally.")
            runtime.stop()

    def test_07_open_google_once_executes_single_action(self):
        """7. Saying 'Open Google' once does not open multiple tabs or windows."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True, "message": "Navigated"})

            runtime.process_command("Open Google", utterance_id="UTTER_SINGLE")
            self.assertTrue(_wait_for(lambda: len(executed) == 1))

            self.assertEqual(len(executed), 1, "Must trigger exactly one execution.")
            intent_node = executed[0]
            self.assertIn(intent_node.get("intent"), ["browser_action", "open_website", "open_url", "web_search", "open_browser"])
            runtime.stop()

    def test_08_tts_output_does_not_trigger_commands(self):
        """8. Santra's own TTS output does not trigger commands (echo suppression)."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            runtime.listener.start(runtime._on_speech_start, runtime._on_speech_end)

            # Simulate TTS starting
            runtime._on_speaker_started()
            self.assertTrue(runtime.listener.speaking_active)

            # While TTS is speaking, loud sound enters mic (e.g. speaker sound)
            loud_chunk = np.full((2048, 1), 0.03, dtype=np.float32)
            for _ in range(5):
                runtime.listener._audio_callback(loud_chunk, 2048, None, None)

            # Stop TTS
            runtime._on_speaker_stopped()
            time.sleep(0.1)

            # Ensure pre-roll buffer was cleared and no command executed
            self.assertEqual(len(runtime.listener._pre_roll_buffer), 0)
            self.assertEqual(len(executed), 0, "TTS audio output must not trigger any command execution.")
            runtime.stop()

    def test_09_microphone_restart_does_not_replay_previous_audio(self):
        """9. A microphone restart does not replay previous audio."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            runtime.listener.start(runtime._on_speech_start, runtime._on_speech_end)
            # Put audio into buffer
            runtime.listener._pre_roll_buffer.append(np.full((2048, 1), 0.02, dtype=np.float32))

            # Stop and restart listener
            runtime.listener.stop()
            self.assertEqual(len(runtime.listener._pre_roll_buffer), 0, "Pre-roll buffer must be cleared on stop.")

            runtime.listener.start(runtime._on_speech_start, runtime._on_speech_end)
            self.assertEqual(len(runtime.listener._pre_roll_buffer), 0, "Pre-roll buffer must be empty on start.")

            # Simulate silence on new stream
            silent_chunk = np.zeros((2048, 1), dtype=np.float32)
            for _ in range(10):
                runtime.listener._audio_callback(silent_chunk, 2048, None, None)

            self.assertEqual(len(executed), 0)
            runtime.stop()

    def test_10_repeated_vad_end_events_do_not_duplicate_execution(self):
        """10. Repeated VAD end-of-utterance events do not duplicate execution."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            import tempfile
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

            try:
                with patch.object(runtime.transcriber, "transcribe", return_value="open google"):
                    # First dispatch
                    runtime._on_speech_end(path)
                    self.assertTrue(_wait_for(lambda: len(executed) == 1))

                    # Re-dispatching the exact same path (e.g. duplicate callback) is caught by deduplication
                    runtime._on_speech_end(path)
                    time.sleep(0.15)
                    self.assertEqual(len(executed), 1, "Duplicate WAV event must not execute command again.")
            finally:
                if os.path.exists(path):
                    os.remove(path)
            runtime.stop()

    def test_11_genuine_new_command_after_silence_recognized_normally(self):
        """11. A genuine new command after silence is recognized normally."""
        executed = []

        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.executor.execute = MagicMock(side_effect=lambda n, **kw: executed.append(n) or {"success": True})

            # Period of silence
            runtime._on_speech_end("")
            time.sleep(0.05)
            self.assertEqual(len(executed), 0)

            # New command spoken
            runtime.process_command("take a screenshot", utterance_id="UTTER_SCREENSHOT")
            self.assertTrue(_wait_for(lambda: len(executed) == 1))
            self.assertIn(executed[0].get("intent"), ["screenshot", "take_screenshot"])
            runtime.stop()

    def test_12_wakeword_and_awake_state_behavior(self):
        """12. Wake-word and awake-state behavior continue to work."""
        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            runtime.current_status = "SLEEPING"
            runtime.listener._sleep_mode = True

            # Trigger wake word -> puts assistant into LISTENING mode
            runtime._on_wakeword("santra")
            self.assertEqual(runtime.current_status, "LISTENING", "Wake word must transition from SLEEPING to LISTENING.")
            self.assertFalse(runtime.listener._sleep_mode, "Listener sleep mode must be cleared.")
            runtime.stop()

    def test_13_low_battery_proactive_alert_still_works(self):
        """13. The existing low-battery proactive alert still works."""
        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()
            with patch.object(runtime.response_manager, "conversation") as mock_conv:
                runtime._on_proactive_alert("Battery Alert", "Battery is at 15%. Please plug in your charger.", speak=True)
                mock_conv.assert_called_once()
                self.assertIn("Battery is at 15%", runtime.current_speech_text)
            runtime.stop()

    def test_14_deterministic_commands_remain_functional(self):
        """14. Panel controls, browser navigation, Spotify, and other deterministic commands remain functional."""
        with patch("sounddevice.InputStream"):
            runtime = JarvisRuntime()

            # Test deterministic parsing
            cmd_tests = [
                ("lock computer", "system_control"),
                ("take a screenshot", "screenshot"),
                ("play music", "media_control"),
                ("open chrome", "open_app"),
                ("what is the battery status", "system_telemetry"),
            ]

            for phrase, expected_intent in cmd_tests:
                parsed = runtime.intent_engine.parse(phrase)
                self.assertEqual(parsed.get("intent"), expected_intent, f"Routing failed for '{phrase}' -> expected {expected_intent}")
            runtime.stop()

    def test_15_hallucination_filter_rejects_repetitive_whisper_loops(self):
        """Verify that repetitive hallucination loops (e.g. 112x Google) are rejected."""
        loop_text = "Google, " * 40
        val_res = transcript_validator.validate(loop_text)
        self.assertFalse(val_res.is_valid, "Repetitive hallucination loop must be marked invalid.")
        self.assertEqual(val_res.status, ValidationStatus.REPETITIVE_HALLUCINATION)

        # Single word loop
        loop_single = "okay okay okay okay"
        val_res2 = transcript_validator.validate(loop_single)
        self.assertFalse(val_res2.is_valid, "Short repetition loop must be invalid.")

        # Known hallucination phrase
        val_res3 = transcript_validator.validate("Thank you for watching.")
        self.assertFalse(val_res3.is_valid, "Hallucination phrase must be invalid.")

        # Genuine command
        val_res4 = transcript_validator.validate("open Google")
        self.assertTrue(val_res4.is_valid, "Genuine command must be valid.")


if __name__ == "__main__":
    unittest.main()
