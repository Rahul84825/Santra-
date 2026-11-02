"""
Adversarial and Stress Tests for SANTRA Audio Input Hot-Swap,
Dynamic Recovery, Watchdog Health, and PortAudio Resilience.
"""

import time
import unittest
import threading
import numpy as np
from unittest.mock import MagicMock, patch

from core.audio_device_resolver import AudioDeviceResult, resolve_audio_input_device
from core.audio_device_watcher import AudioDeviceWatcher
from core.listener import SpeechListener
from core.wakeword import MockWakeWordDetector, OpenWakeWordDetector


class TestAudioHotSwapAdversarial(unittest.TestCase):

    def setUp(self):
        self.listener = SpeechListener(sample_rate=16000)

    def tearDown(self):
        if hasattr(self, "listener") and self.listener:
            self.listener.stop()

    def test_adv_01_chattering_endpoint_storms(self):
        """Adversarial 1: Rapid storm of 50 endpoint change notifications in 100ms must not deadlock or explode threads."""
        callback = MagicMock()
        watcher = AudioDeviceWatcher(on_endpoint_change=callback, debounce_seconds=0.15, watchdog_interval=0.5)
        watcher.start()

        # Fire 50 events concurrently from 5 separate threads
        def worker(start_idx):
            for i in range(10):
                watcher._on_raw_event("chatter_event", {"thread_evt": start_idx + i})
                time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(t * 10,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Wait for debounce window
        time.sleep(0.3)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(callback.call_args[0][0], "chatter_event")
        watcher.stop()

    def test_adv_02_stream_dies_during_recording(self):
        """Adversarial 2: Audio stream terminates while recording is active; recovery safely resets state."""
        with patch("sounddevice.InputStream") as mock_stream_cls, \
             patch("core.audio_device_resolver.resolve_audio_input_device") as mock_resolve:

            mock_s1 = MagicMock()
            mock_s1.active = True
            mock_s2 = MagicMock()
            mock_s2.active = True
            mock_stream_cls.side_effect = [mock_s1, mock_s2]

            mock_resolve.return_value = AudioDeviceResult(2, "Noise Buds Headset", 16000, False)
            self.listener.start()

            # Start recording
            self.listener._recording = True
            self.listener._audio_buffer = [np.ones((1024, 1), dtype=np.float32)]

            # Stream terminates abruptly
            mock_s1.active = False
            healthy, reason = self.listener.is_stream_healthy()
            self.assertFalse(healthy)

            # Trigger recovery
            mock_resolve.return_value = AudioDeviceResult(1, "Realtek Mic", 16000, False)
            ok = self.listener.recover_stream(reason="stream_died")
            self.assertTrue(ok)
            # Recording and buffers must be safely reset
            self.assertFalse(self.listener._recording)
            self.assertEqual(len(self.listener._audio_buffer), 0)
            self.assertEqual(self.listener.active_input_device_index, 1)

    def test_adv_03_resampling_numerical_integrity(self):
        """Adversarial 3: Downsampled audio must be finite, non-NaN, and correctly scaled for int16 conversion."""
        received_chunks = []
        self.listener.add_audio_consumer(lambda chunk: received_chunks.append(chunk))
        self.listener._running = True
        self.listener._hardware_sample_rate = 44100
        self.listener.sample_rate = 16000
        self.listener._resample_needed = True

        # Generate audio with extreme float values (clipping, near-zeros, high frequencies)
        frames_44k = 4410
        t = np.linspace(0, 0.1, frames_44k)
        audio_44k = (np.sin(2 * np.pi * 440 * t) * 1.5).astype(np.float32).reshape(-1, 1)  # clipping audio

        self.listener._audio_callback(audio_44k, frames_44k, None, None)

        self.assertEqual(len(received_chunks), 1)
        pcm = received_chunks[0]
        self.assertFalse(np.isnan(pcm).any())
        self.assertFalse(np.isinf(pcm).any())
        self.assertTrue(np.all(pcm >= -32768))
        self.assertTrue(np.all(pcm <= 32767))

    def test_adv_04_recovery_concurrency_lock(self):
        """Adversarial 4: Concurrent calls to recover_stream must be serialized without crashing."""
        with patch("sounddevice.InputStream") as mock_stream_cls, \
             patch("core.audio_device_resolver.resolve_audio_input_device") as mock_resolve:

            mock_streams = [MagicMock() for _ in range(10)]
            for s in mock_streams:
                s.active = True
            mock_stream_cls.side_effect = mock_streams

            mock_resolve.return_value = AudioDeviceResult(1, "Microphone", 16000, False)
            self.listener.start()

            results = []
            def recover_worker():
                res = self.listener.recover_stream(reason="concurrent_test")
                results.append(res)

            threads = [threading.Thread(target=recover_worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All concurrent calls should complete without unhandled exceptions
            self.assertEqual(len(results), 5)
            self.assertTrue(all(results))

    def test_adv_05_transient_noise_recalibrates_ambient_rms(self):
        """Adversarial 5: Ambient noise baseline must reset to default on recovery, not latch onto loud disconnect transients."""
        with patch("sounddevice.InputStream"), \
             patch("core.audio_device_resolver.resolve_audio_input_device") as mock_resolve:
            mock_resolve.return_value = AudioDeviceResult(1, "Realtek Mic", 16000, False)
            self.listener.start()

            # Corrupt ambient RMS with high value (e.g. from acoustic noise during unplug)
            self.listener._ambient_rms = 0.85
            self.listener.recover_stream(reason="noise_recalibration")

            # Ambient RMS must be reset to 0.005 baseline
            self.assertAlmostEqual(self.listener._ambient_rms, 0.005, places=3)

    def test_adv_06_double_stop_and_restart(self):
        """Adversarial 6: Multiple stop and restart cycles must not leave dangling threads or invalid stream states."""
        with patch("sounddevice.InputStream") as mock_stream_cls, \
             patch("core.audio_device_resolver.resolve_audio_input_device") as mock_resolve:
            mock_resolve.return_value = AudioDeviceResult(1, "Mic", 16000, False)

            # Cycle 1
            self.listener.start()
            self.assertTrue(self.listener.is_listening())
            self.listener.stop()
            self.assertFalse(self.listener.is_listening())

            # Cycle 2
            self.listener.start()
            self.assertTrue(self.listener.is_listening())
            self.listener.stop()
            self.assertFalse(self.listener.is_listening())


if __name__ == "__main__":
    unittest.main()

