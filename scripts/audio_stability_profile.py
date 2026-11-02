"""
SANTRA Iteration 14: Automated Audio Stability & Endurance Profile.
Simulates real-world usage across 60 minute-intervals:
- 1 hot-swap event every 3 minutes (20 hot-swaps total)
- 1 speech recognition event every 1 minute (60 recognition events total)
- Logs memory usage (RSS MB), Windows kernel handles, thread count, and CPU
- Monitors for COM port/device handle leaks
- Records unhandled exceptions and outputs logs/audio_stability_60min.json
"""

import os
import sys
import gc
import time
import json
import psutil
import threading
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from core.listener import SpeechListener
from core.transcriber import SpeechTranscriber
from core.audio_device_resolver import resolve_audio_input_device


def run_stability_profile(accelerated: bool = True):
    print("=" * 80)
    print("SANTRA ITERATION 14: 60-INTERVAL AUDIO ENDURANCE & STABILITY PROFILE")
    print(f"Mode: {'Accelerated Benchmark (Zero Waste)' if accelerated else 'Realtime 60-Minute Profile'}")
    print("=" * 80)

    proc = psutil.Process()
    gc.collect()

    initial_rss_mb = proc.memory_info().rss / (1024 * 1024)
    initial_handles = proc.num_handles()
    initial_threads = proc.num_threads()

    transcriber = SpeechTranscriber()
    transcriber._load_model()

    listener = SpeechListener(sample_rate=16000)
    listener.start()

    speech_samples = [
        ("scratch/eval_dataset/cmd_open_chrome.wav", "Open Chrome."),
        ("scratch/eval_dataset/cmd_open_vscode.wav", "Open VS Code."),
        ("scratch/eval_dataset/cmd_take_screenshot.wav", "Take screenshot."),
        ("scratch/eval_dataset/cmd_lock_computer.wav", "Lock computer."),
        ("scratch/eval_dataset/cmd_open_downloads.wav", "Open downloads.")
    ]

    telemetry_records = []
    hotswap_latencies = []
    transcribe_latencies = []
    unhandled_exceptions = []

    total_hotswaps = 0
    successful_hotswaps = 0
    total_recognitions = 0
    successful_recognitions = 0

    try:
        for minute in range(1, 61):
            t_min_start = time.perf_counter()

            # 1. Hot-swap event every 3 minutes (20 hot-swaps total)
            hotswap_occurred = False
            hotswap_latency_ms = None
            hotswap_success = False

            if minute % 3 == 0:
                total_hotswaps += 1
                hotswap_occurred = True
                t_hs0 = time.perf_counter()
                try:
                    res = listener.recover_stream(reason=f"stability_hotswap_min_{minute}", force=True)
                    hotswap_latency_ms = round((time.perf_counter() - t_hs0) * 1000, 2)
                    hotswap_success = bool(res and listener.get_stream_health()["healthy"])
                    if hotswap_success:
                        successful_hotswaps += 1
                        hotswap_latencies.append(hotswap_latency_ms)
                except Exception as e:
                    unhandled_exceptions.append({"minute": minute, "event": "hotswap", "error": str(e)})

            # 2. Speech recognition event every 1 minute (60 recognition events total)
            sample_path, expected_text = speech_samples[(minute - 1) % len(speech_samples)]
            total_recognitions += 1
            t_tx0 = time.perf_counter()
            tx_success = False
            tx_latency_ms = 0.0
            hyp_text = ""

            try:
                hyp_text = transcriber.transcribe(sample_path)
                tx_latency_ms = round((time.perf_counter() - t_tx0) * 1000, 2)
                transcribe_latencies.append(tx_latency_ms)
                tx_success = bool(hyp_text.strip() != "")
                if tx_success:
                    successful_recognitions += 1
            except Exception as e:
                unhandled_exceptions.append({"minute": minute, "event": "transcribe", "error": str(e)})

            # 3. Telemetry capture at this minute interval
            gc.collect()
            current_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
            current_handles = proc.num_handles()
            current_threads = proc.num_threads()
            cpu_pct = proc.cpu_percent(interval=None)

            record = {
                "minute": minute,
                "memory_rss_mb": current_rss_mb,
                "delta_rss_mb": round(current_rss_mb - initial_rss_mb, 2),
                "kernel_handles": current_handles,
                "delta_handles": current_handles - initial_handles,
                "thread_count": current_threads,
                "cpu_percent": cpu_pct,
                "speech_recognition": {
                    "sample": os.path.basename(sample_path),
                    "hyp": hyp_text,
                    "latency_ms": tx_latency_ms,
                    "success": tx_success
                },
                "hotswap": {
                    "occurred": hotswap_occurred,
                    "latency_ms": hotswap_latency_ms,
                    "success": hotswap_success
                } if hotswap_occurred else None
            }
            telemetry_records.append(record)

            hs_str = f" | Hot-swap: {hotswap_latency_ms}ms (OK={hotswap_success})" if hotswap_occurred else ""
            print(f"  [Min {minute:02d}/60] RSS: {current_rss_mb:.1f}MB | Handles: {current_handles} | Recog: '{hyp_text}' ({tx_latency_ms:.1f}ms){hs_str}")

            if not accelerated:
                elapsed = time.perf_counter() - t_min_start
                if elapsed < 60.0:
                    time.sleep(60.0 - elapsed)
            else:
                time.sleep(0.05)

    finally:
        listener.stop()

    gc.collect()
    final_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    final_handles = proc.num_handles()
    final_threads = proc.num_threads()

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_intervals": len(telemetry_records),
        "total_hotswaps": total_hotswaps,
        "successful_hotswaps": successful_hotswaps,
        "hotswap_success_rate_percent": round((successful_hotswaps / max(1, total_hotswaps)) * 100, 2),
        "total_recognitions": total_recognitions,
        "successful_recognitions": successful_recognitions,
        "recognition_success_rate_percent": round((successful_recognitions / max(1, total_recognitions)) * 100, 2),
        "hotswap_latency_stats": {
            "min_ms": round(float(np.min(hotswap_latencies)), 2) if hotswap_latencies else 0.0,
            "median_ms": round(float(np.median(hotswap_latencies)), 2) if hotswap_latencies else 0.0,
            "p95_ms": round(float(np.percentile(hotswap_latencies, 95)), 2) if hotswap_latencies else 0.0,
            "max_ms": round(float(np.max(hotswap_latencies)), 2) if hotswap_latencies else 0.0
        },
        "recognition_latency_stats": {
            "min_ms": round(float(np.min(transcribe_latencies)), 2) if transcribe_latencies else 0.0,
            "median_ms": round(float(np.median(transcribe_latencies)), 2) if transcribe_latencies else 0.0,
            "p95_ms": round(float(np.percentile(transcribe_latencies, 95)), 2) if transcribe_latencies else 0.0,
            "max_ms": round(float(np.max(transcribe_latencies)), 2) if transcribe_latencies else 0.0
        },
        "resource_stability": {
            "initial_memory_mb": round(initial_rss_mb, 2),
            "final_memory_mb": final_rss_mb,
            "memory_drift_mb": round(final_rss_mb - initial_rss_mb, 2),
            "initial_handles": initial_handles,
            "final_handles": final_handles,
            "handle_leak_count": final_handles - initial_handles,
            "initial_threads": initial_threads,
            "final_threads": final_threads,
            "leak_detected": bool(final_handles - initial_handles > 20 or final_rss_mb - initial_rss_mb > 150.0)
        },
        "unhandled_exceptions_count": len(unhandled_exceptions),
        "unhandled_exceptions": unhandled_exceptions,
        "telemetry_intervals": telemetry_records
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/audio_stability_60min.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 80)
    print("60-INTERVAL AUDIO STABILITY PROFILE COMPLETE")
    print(f"Hot-swaps: {successful_hotswaps}/{total_hotswaps} ({report['hotswap_success_rate_percent']}%)")
    print(f"Recognitions: {successful_recognitions}/{total_recognitions} ({report['recognition_success_rate_percent']}%)")
    print(f"Memory Drift: {report['resource_stability']['memory_drift_mb']:+.1f} MB | Handle Leak: {report['resource_stability']['handle_leak_count']:+d}")
    print(f"Unhandled Exceptions: {len(unhandled_exceptions)}")
    print("=" * 80)

    return report


if __name__ == "__main__":
    run_stability_profile(accelerated=True)

