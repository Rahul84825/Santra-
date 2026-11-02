"""
Unit and Integration Tests for SANTRA Audio Input Hot-Swap,
Dynamic Recovery, Watchdog Health, and Sample Rate Resampling.
"""

import time
import unittest
import numpy as np
from unittest.mock import MagicMock, patch

from core.audio_device_resolver import (
    AudioDeviceResult,
    resolve_audio_input_device,
    get_device_topology_signature,
    refresh_device_cache
)
from core.audio_device_watcher import AudioDeviceWatcher
from core.listener import SpeechListener
from core.wakeword import MockWakeWordDetector, OpenWakeWordDetector
from core.jarvis_runtime import JarvisRuntime


class TestAudioDeviceHotSwap(unittest.TestCase):

    def setUp(self):
        self.listener = SpeechListener(sample_rate=16000)

    def tearDown(self):
        if hasattr(self, "listener") and self.listener:
            self.listener.stop()

    def test_01_audio_device_result_backward_compatibility(self):
        """AudioDeviceResult must unpack as a 2-tuple (idx, name) while exposing metadata."""
        res = AudioDeviceResult(2, "Headset Mic", sample_rate=48000, requires_resampling=True)
        idx, name = res
        self.assertEqual(idx, 2)
        self.assertEqual(name, "Headset Mic")
        self.assertEqual(res.sample_rate, 48000)
        self.assertTrue(res.requires_resampling)
        self.assertEqual(len(res), 2)

    def test_02_audio_device_watcher_lifecycle(self):
        """AudioDeviceWatcher must start cleanly, initialize thread/COM, and stop safely."""
        callback = MagicMock()
        watcher = AudioDeviceWatcher(on_endpoint_change=callback, debounce_seconds=0.1, watchdog_interval=0.5)
        watcher.start()
        self.assertTrue(watcher._running)
        time.sleep(0.1)
        watcher.stop()
        self.assertFalse(watcher._running)

    def test_03_audio_device_watcher_event_debouncing(self):
        """Rapid bursts of hardware endpoint events must be coalesced into a single debounced callback."""
        callback = MagicMock()
        watcher = AudioDeviceWatcher(on_endpoint_change=callback, debounce_seconds=0.15, watchdog_interval=1.0)
        watcher.start()

        # Fire 5 simulated events within 40ms
        for i in range(5):
            watcher._on_raw_event("state_changed", {"index": i})
            time.sleep(0.008)

        # Before debounce window expires, callback should not have fired yet
        time.sleep(0.04)
        callback.assert_not_called()

        # Wait for debounce window (0.15s) to complete
        time.sleep(0.2)
        self.assertEqual(callback.call_count, 1)
        args, kwargs = callback.call_args
        self.assertEqual(args[0], "state_changed")
        self.assertEqual(args[1]["coalesced_count"], 5)
        watcher.stop()

    def test_04_listener_recover_stream_transitions_device(self):
        """SpeechListener.recover_stream must cleanly stop old stream and open new stream on fallback device."""
        with patch("sounddevice.InputStream") as mock_stream_cls, \
             patch("core.audio_device_resolver.resolve_audio_input_device") as mock_resolve:

            mock_old_stream = MagicMock()
            mock_old_stream.active = True
            mock_new_stream = MagicMock()
            mock_new_stream.active = True
            mock_stream_cls.side_effect = [mock_old_stream, mock_new_stream]

            # Start listener on simulated headphones (device 2)
            mock_resolve.return_value = AudioDeviceResult(2, "Headset (Noise Buds)", 16000, False)
            self.listener.start()
            self.assertEqual(self.listener.active_input_device_index, 2)
            self.assertEqual(self.listener.active_input_device_name, "Headset (Noise Buds)")

            # Setup switched callback mock
            switched_cb = MagicMock()
            self.listener.on_device_switched_cb = switched_cb

            # Simulate headphones disconnected -> resolve returns Realtek mic (device 1)
            mock_resolve.return_value = AudioDeviceResult(1, "Microphone (Realtek)", 16000, False)

            # Trigger stream recovery
            recovered = self.listener.recover_stream(reason="headphones_unplugged")
            self.assertTrue(recovered)

            # Verify old stream was stopped and closed
            mock_old_stream.stop.assert_called_once()
            mock_old_stream.close.assert_called_once()

            # Verify new stream started
            mock_new_stream.start.assert_called_once()
            self.assertEqual(self.listener.active_input_device_index, 1)
            self.assertEqual(self.listener.active_input_device_name, "Microphone (Realtek)")

            # Verify callback notified
            time.sleep(0.05)
            switched_cb.assert_called_once()
            old_d, new_d, lat = switched_cb.call_args[0]
            self.assertEqual(old_d, "Headset (Noise Buds)")
            self.assertEqual(new_d, "Microphone (Realtek)")
            self.assertGreater(lat, 0.0)

    def test_05_dynamic_downsampling_from_48khz_to_16khz(self):
        """SpeechListener must downsample 48kHz audio to 16kHz before consumer delivery."""
        consumer = MagicMock()
        self.listener.add_audio_consumer(consumer)
        self.listener._running = True
        self.listener._hardware_sample_rate = 48000
        self.listener.sample_rate = 16000
        self.listener._resample_needed = True

        # Generate 4800 samples of float32 test audio at 48kHz (100ms)
        chunk_48k = (np.sin(np.linspace(0, 100, 4800)) * 0.5).astype(np.float32).reshape(-1, 1)
        self.listener._audio_callback(chunk_48k, 4800, None, None)

        # Consumer should receive 1600 samples (100ms at 16kHz) as int16
        consumer.assert_called_once()
        received_pcm = consumer.call_args[0][0]
        self.assertEqual(len(received_pcm), 1600)
        self.assertEqual(received_pcm.dtype, np.int16)

    def test_06_transient_cooldown_prevents_pop_trigger(self):
        """Hardware transients/pops during switch must be ignored during cooldown window."""
        consumer = MagicMock()
        self.listener.add_audio_consumer(consumer)
        self.listener._running = True
        self.listener._transient_cooldown_until = time.time() + 0.5  # 500ms in future

        # Simulate massive pop (amplitude 0.9)
        pop_chunk = np.ones((2048, 1), dtype=np.float32) * 0.9
        self.listener._audio_callback(pop_chunk, 2048, None, None)

        # Audio should be ignored during cooldown
        consumer.assert_not_called()
        self.assertEqual(len(self.listener._audio_buffer), 0)

    def test_07_is_stream_healthy_detects_inactive_stream(self):
        """is_stream_healthy must detect when stream.active drops to False."""
        self.listener._running = True
        mock_stream = MagicMock()
        mock_stream.active = False
        self.listener._stream = mock_stream

        healthy, reason = self.listener.is_stream_healthy()
        self.assertFalse(healthy)
        self.assertIn("inactive", reason.lower())

    def test_08_is_stream_healthy_detects_callback_timeout(self):
        """is_stream_healthy must detect when audio callback has not fired for > 2 seconds."""
        self.listener._running = True
        mock_stream = MagicMock()
        mock_stream.active = True
        self.listener._stream = mock_stream
        self.listener._last_callback_time = time.time() - 3.5

        healthy, reason = self.listener.is_stream_healthy()
        self.assertFalse(healthy)
        self.assertIn("timeout", reason.lower())

    def test_09_sustained_zero_frames_anomaly_detection(self):
        """Continuous bit-exact zeros must be flagged as stream failure."""
        self.listener._running = True
        mock_stream = MagicMock()
        mock_stream.active = True
        self.listener._stream = mock_stream
        self.listener._last_callback_time = time.time()

        zero_chunk = np.zeros((1024, 1), dtype=np.float32)
        for _ in range(70):
            self.listener._audio_callback(zero_chunk, 1024, None, None)

        self.assertGreater(self.listener._zero_frame_count, 60)
        healthy, reason = self.listener.is_stream_healthy()
        self.assertFalse(healthy)
        self.assertIn("zero", reason.lower())

    def test_10_wakeword_detector_reset_audio_state(self):
        """WakeWordDetector reset_audio_state must clear queue and set debounce guard."""
        detector = MockWakeWordDetector()
        detector.received_frames = [b"chunk1", b"chunk2"]
        detector.reset_audio_state()
        self.assertEqual(len(detector.received_frames), 0)

    def test_11_runtime_startup_health_includes_audio_diagnostics(self):
        """JarvisRuntime.get_startup_health must report comprehensive stream health diagnostics."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            runtime = JarvisRuntime()
            runtime.listener.is_listening.return_value = True
            runtime.listener.active_input_device_name = "Realtek Mic"
            runtime.listener.active_input_device_index = 1
            runtime.listener.get_stream_health.return_value = {
                "healthy": True,
                "reason": "Healthy",
                "stream_active": True,
                "resampling_active": False
            }

            health = runtime.get_startup_health()
            self.assertIn("microphone", health)
            self.assertIn("stream_health", health["microphone"])
            self.assertTrue(health["microphone"]["stream_health"]["healthy"])


if __name__ == "__main__":
    unittest.main()

