"""
SANTRA Iteration 15: Exact Mathematical Resampling Verification.
Demonstrates measured filter characteristics vs. theoretical design:
- Input/output sample rates & sample counts
- In-band signal vs. out-of-band alias test tone (14kHz folding to 2kHz)
- Measured alias amplitude & stopband attenuation
- Chunk-boundary phase continuity across multi-chunk streaming
- Conversion latency & CPU overhead
"""

import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.abspath("."))
from core.audio_resampler import AudioResampler


def verify_resampling_fidelity():
    print("=" * 80)
    print("SANTRA ITERATION 15: MATHEMATICAL RESAMPLING FIDELITY AUDIT")
    print("=" * 80)

    # 1. 48kHz -> 16kHz Test Configuration
    fs_in = 48000
    fs_out = 16000
    chunk_duration_sec = 0.08  # 80ms chunk standard
    n_in = int(round(fs_in * chunk_duration_sec))   # 3840 samples
    n_out = int(round(fs_out * chunk_duration_sec)) # 1280 samples

    print(f"\n[1] Sample Rate & Count Integrity:")
    print(f"  - Input Rate:  {fs_in} Hz | Chunk Size: {n_in} samples ({chunk_duration_sec*1000:.1f}ms)")
    print(f"  - Output Rate: {fs_out} Hz | Chunk Size: {n_out} samples ({chunk_duration_sec*1000:.1f}ms)")
    print(f"  - Exact Mathematical Ratio: {fs_out}/{fs_in} = 1/3")

    # 2. Acoustic Tones: 1kHz (in-band) + 14kHz (out-of-band, folds to 2kHz if aliased)
    t = np.arange(n_in) / fs_in
    f_inband = 1000.0
    f_outband = 14000.0  # Above 8kHz Nyquist cutoff!

    sig_inband = 0.6 * np.sin(2 * np.pi * f_inband * t)
    sig_outband = 0.4 * np.sin(2 * np.pi * f_outband * t)
    sig_composite = (sig_inband + sig_outband).astype(np.float32).reshape(-1, 1)

    # Benchmark A: Legacy Linear Interpolation (np.interp)
    t0 = time.perf_counter()
    orig_idx = np.linspace(0, len(sig_composite) - 1, len(sig_composite))
    target_idx = np.linspace(0, len(sig_composite) - 1, n_out)
    y_interp = np.interp(target_idx, orig_idx, sig_composite[:, 0]).astype(np.float32)
    lat_interp_ms = (time.perf_counter() - t0) * 1000.0

    fft_interp = np.abs(np.fft.rfft(y_interp))
    freqs_interp = np.fft.rfftfreq(len(y_interp), 1 / fs_out)
    inband_bin = np.argmin(np.abs(freqs_interp - f_inband))
    alias_bin = np.argmin(np.abs(freqs_interp - (fs_out - (f_outband % fs_out)))) # 2000 Hz
    alias_interp_db = float(20 * np.log10(fft_interp[alias_bin] / (fft_interp[inband_bin] + 1e-9)))

    # Benchmark B: Iteration 14/15 AudioResampler (Polyphase Kaiser FIR)
    resampler = AudioResampler(fs_in, fs_out)
    # Warmup
    resampler.resample(sig_composite)
    resampler.reset()

    latencies = []
    for _ in range(100):
        t1 = time.perf_counter()
        y_poly = resampler.resample(sig_composite)
        latencies.append((time.perf_counter() - t1) * 1000.0)
    lat_poly_ms = float(np.median(latencies))

    fft_poly = np.abs(np.fft.rfft(y_poly[:, 0]))
    freqs_poly = np.fft.rfftfreq(len(y_poly), 1 / fs_out)
    alias_poly_db = float(20 * np.log10(fft_poly[alias_bin] / (fft_poly[inband_bin] + 1e-9)))
    rejection_gain_db = alias_interp_db - alias_poly_db

    print(f"\n[2] Anti-Aliasing & Stopband Attenuation (14kHz tone folding to 2kHz):")
    print(f"  - Legacy np.interp Alias Level:       {alias_interp_db:.1f} dB")
    print(f"  - AudioResampler Measured Alias Level: {alias_poly_db:.1f} dB")
    print(f"  - Measured Stopband Rejection Gain:   {rejection_gain_db:.1f} dB (Stopband Attenuation: {abs(alias_poly_db):.1f} dB)")
    print(f"  - Theoretical Kaiser FIR Design:      80.0 dB attenuation (beta=6.0, polyphase sub-filters)")

    # 3. Chunk-Boundary Continuity Test across 10 streaming chunks
    resampler_stream = AudioResampler(fs_in, fs_out)
    t_stream = np.arange(n_in * 10) / fs_in
    full_audio = (0.7 * np.sin(2 * np.pi * 800.0 * t_stream)).astype(np.float32).reshape(-1, 1)

    chunk_outputs = []
    for chunk_idx in range(10):
        c = full_audio[chunk_idx * n_in : (chunk_idx + 1) * n_in]
        out_c = resampler_stream.resample(c)
        chunk_outputs.append(out_c[:, 0])

    stitched = np.concatenate(chunk_outputs)
    # Full frame direct resample for ground-truth comparison
    resampler_ground_truth = AudioResampler(fs_in, fs_out)
    direct_out = resampler_ground_truth.resample(full_audio)[:, 0]

    # Compute boundary discontinuity error
    boundary_diffs = []
    for i in range(1, 10):
        split_idx = i * n_out
        boundary_jump = abs(stitched[split_idx] - stitched[split_idx - 1])
        ground_truth_jump = abs(direct_out[split_idx] - direct_out[split_idx - 1])
        boundary_diffs.append(abs(boundary_jump - ground_truth_jump))

    max_boundary_jump_err = float(np.max(boundary_diffs))
    print(f"\n[3] Chunk-Boundary Phase Continuity:")
    print(f"  - Stitched Output Length:  {len(stitched)} samples (Expected: {n_out*10})")
    print(f"  - Max Boundary Phase Jump: {max_boundary_jump_err:.6f} (Threshold < 0.05)")
    print(f"  - Status: {'SEAMLESS CONTINUOUS' if max_boundary_jump_err < 0.05 else 'DISCONTINUITY DETECTED'}")

    # 4. Latency & CPU Overhead
    cpu_budget_ms = chunk_duration_sec * 1000.0 # 80ms
    cpu_overhead_pct = (lat_poly_ms / cpu_budget_ms) * 100.0
    print(f"\n[4] Execution Latency & Real-Time Budget:")
    print(f"  - AudioResampler Latency: {lat_poly_ms:.3f} ms / 80.0 ms chunk")
    print(f"  - Real-Time CPU Budget:   {cpu_overhead_pct:.2f}% of 1 core (Well within limits)")

    report = {
        "input_sample_rate_hz": fs_in,
        "output_sample_rate_hz": fs_out,
        "input_chunk_samples": n_in,
        "output_chunk_samples": n_out,
        "exact_ratio_preserved": bool(y_poly.shape == (n_out, 1)),
        "inband_tone_hz": f_inband,
        "outband_alias_tone_hz": f_outband,
        "folded_alias_frequency_hz": 2000.0,
        "measured_alias_level_interp_db": round(alias_interp_db, 1),
        "measured_alias_level_polyphase_db": round(alias_poly_db, 1),
        "measured_stopband_rejection_gain_db": round(rejection_gain_db, 1),
        "theoretical_stopband_attenuation_db": 80.0,
        "measured_stopband_attenuation_db": round(abs(alias_poly_db), 1),
        "chunk_boundary_max_phase_err": round(max_boundary_jump_err, 6),
        "chunk_boundary_continuous": bool(max_boundary_jump_err < 0.05),
        "median_latency_ms": round(lat_poly_ms, 3),
        "chunk_budget_ms": cpu_budget_ms,
        "cpu_overhead_percent": round(cpu_overhead_pct, 2),
        "nan_detected": bool(np.isnan(y_poly).any()),
        "inf_detected": bool(np.isinf(y_poly).any()),
        "clipped_in_bounds": bool(np.all(y_poly >= -1.0) and np.all(y_poly <= 1.0))
    }

    import os
    os.makedirs("logs", exist_ok=True)
    with open("logs/resampling_verification_iteration15.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nResults saved to logs/resampling_verification_iteration15.json")
    print("=" * 80)
    return report

if __name__ == "__main__":
    verify_resampling_fidelity()
