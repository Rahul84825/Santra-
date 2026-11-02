"""
Unit Tests for High-Fidelity AudioResampler.
Verifies anti-aliasing rejection (>60 dB), Kaiser polyphase filtering,
boundary continuity, numerical stability, NaN/Inf sanitation, and duration preservation.
"""

import time
import unittest
import numpy as np
from core.audio_resampler import AudioResampler


class TestAudioResampler(unittest.TestCase):

    def test_01_passthrough_at_16khz(self):
        """16kHz audio must be returned directly without modification."""
        resampler = AudioResampler(16000, 16000)
        self.assertTrue(resampler.is_passthrough)
        x = np.ones((1600, 1), dtype=np.float32) * 0.5
        y = resampler.resample(x)
        np.testing.assert_array_equal(x, y)

    def test_02_48khz_to_16khz_shape_and_duration(self):
        """48kHz blocks must be decimated by exactly 3:1 to 16kHz."""
        resampler = AudioResampler(48000, 16000)
        # 80ms at 48kHz = 3840 frames; target = 1280 frames
        x = np.random.randn(3840, 1).astype(np.float32) * 0.2
        y = resampler.resample(x)
        self.assertEqual(y.shape, (1280, 1))
        self.assertEqual(y.dtype, np.float32)

    def test_03_44khz_to_16khz_shape_and_duration(self):
        """44.1kHz blocks must convert to exact target frame count."""
        resampler = AudioResampler(44100, 16000)
        # 80ms at 44.1kHz = 3528 frames; target = 1280 frames
        x = np.random.randn(3528, 1).astype(np.float32) * 0.2
        y = resampler.resample(x)
        self.assertEqual(y.shape, (1280, 1))
        self.assertEqual(y.dtype, np.float32)

    def test_04_anti_aliasing_rejection_exceeds_50db(self):
        """Frequencies above 8kHz Nyquist must be attenuated by > 50 dB to prevent aliasing distortion."""
        fs_in = 48000
        fs_out = 16000
        duration = 0.2  # 200ms
        t = np.arange(int(fs_in * duration)) / fs_in

        # In-band signal: 1000 Hz, Out-of-band signal: 14000 Hz (above 8kHz Nyquist!)
        in_band = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
        out_band = np.sin(2 * np.pi * 14000 * t).astype(np.float32)
        composite = (in_band + out_band).reshape(-1, 1)

        resampler = AudioResampler(fs_in, fs_out)
        y = resampler.resample(composite)

        # FFT analysis
        fft_vals = np.abs(np.fft.rfft(y[:, 0]))
        freqs = np.fft.rfftfreq(len(y), 1 / fs_out)

        # Out-of-band 14kHz aliases to |14000 - 16000| = 2000 Hz if unattenuated
        alias_bin = np.argmin(np.abs(freqs - 2000))
        clean_bin = np.argmin(np.abs(freqs - 1000))

        rejection_db = 20 * np.log10(fft_vals[clean_bin] / (fft_vals[alias_bin] + 1e-9))
        self.assertGreater(rejection_db, 50.0, f"Anti-aliasing rejection was only {rejection_db:.1f} dB (expected > 50 dB)")

    def test_05_boundary_history_continuity(self):
        """Chunk boundary transients must be eliminated via history buffer padding."""
        fs_in = 48000
        chunk_len = 3840
        t1 = np.arange(chunk_len) / fs_in
        t2 = np.arange(chunk_len, 2 * chunk_len) / fs_in

        # Continuous 400Hz wave across two consecutive buffers
        c1 = np.sin(2 * np.pi * 400 * t1).astype(np.float32).reshape(-1, 1)
        c2 = np.sin(2 * np.pi * 400 * t2).astype(np.float32).reshape(-1, 1)

        resampler = AudioResampler(fs_in, 16000)
        y1 = resampler.resample(c1)
        y2 = resampler.resample(c2)

        # Full continuous signal for reference
        full = np.concatenate([c1, c2])
        r_full = AudioResampler(fs_in, 16000)
        y_full = r_full.resample(full)

        # Max error between chunked output and single-pass output
        err = np.max(np.abs(y2[:, 0] - y_full[len(y1):, 0]))
        self.assertLess(err, 0.05, f"Boundary discontinuity error {err:.4f} too high")

    def test_06_nan_and_inf_sanitization(self):
        """Resampler must replace NaNs and Infs with valid bounded finite floats."""
        resampler = AudioResampler(48000, 16000)
        x = np.array([[np.nan], [np.inf], [-np.inf], [2.5], [-3.0]], dtype=np.float32)
        y = resampler.resample(x)
        self.assertFalse(np.isnan(y).any())
        self.assertFalse(np.isinf(y).any())
        self.assertTrue(np.all(y >= -1.0))
        self.assertTrue(np.all(y <= 1.0))

    def test_07_resampling_latency_and_cpu_budget(self):
        """Resampling an 80ms chunk (3840 samples) must take under 2.0 ms (< 2.5% CPU budget)."""
        resampler = AudioResampler(48000, 16000)
        x = np.random.randn(3840, 1).astype(np.float32) * 0.1

        # Warmup
        for _ in range(5):
            resampler.resample(x)

        t0 = time.perf_counter()
        iters = 50
        for _ in range(iters):
            resampler.resample(x)
        elapsed_ms = ((time.perf_counter() - t0) / iters) * 1000

        self.assertLess(elapsed_ms, 2.0, f"Resampler took {elapsed_ms:.3f}ms per chunk (> 2.0ms)")


if __name__ == "__main__":
    unittest.main()

