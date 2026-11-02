"""
SANTRA Iteration 15: Live Physical Acceptance & Hardware State Monitor.
Monitors Windows audio endpoint state, active microphone capture,
physical device switch events, and wake-word readiness.
"""

import os
import sys
import time
import json
import psutil
import threading
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from core.listener import SpeechListener
from core.audio_device_resolver import resolve_audio_input_device, get_all_audio_devices
from core.audio_device_watcher import AudioDeviceWatcher
from core.wakeword import SantraWakeWordDetector
from core.transcriber import SpeechTranscriber


def monitor_physical_hardware(duration_sec: float = 10.0):
    print("=" * 80)
    print("SANTRA ITERATION 15: LIVE PHYSICAL HARDWARE ACCEPTANCE AUDIT")
    print(f"Sampling duration: {duration_sec}s")
    print("=" * 80)

    devices = get_all_audio_devices()
    print(f"Total Windows Audio Endpoints Discovered: {len(devices)}")
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            print(f"  Input  [{i:02d}]: {d['name']} (Native Rate: {d['default_samplerate']}Hz)")
        elif d.get("max_output_channels", 0) > 0:
            print(f"  Output [{i:02d}]: {d['name']} (Native Rate: {d['default_samplerate']}Hz)")

    initial_resolution = resolve_audio_input_device()
    print(f"\nInitial Active Resolver Target: [{initial_resolution.device_index}] '{initial_resolution.device_name}' (Rate={initial_resolution.sample_rate}Hz, Resample={initial_resolution.requires_resampling})")

    # Start SpeechListener on physical hardware
    listener = SpeechListener(sample_rate=16000)
    pcm_frames = []
    rms_levels = []
    device_switches = []

    def on_pcm(chunk):
        if len(chunk) > 0:
            pcm_frames.append(chunk)
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            rms_levels.append(rms)

    def on_switch(old_dev, new_dev, lat):
        device_switches.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "old_device": old_dev,
            "new_device": new_dev,
            "latency_ms": lat
        })
        print(f"\n>>> [PHYSICAL SWITCH EVENT DETECTED] '{old_dev}' -> '{new_dev}' in {lat:.1f}ms <<<\n")

    listener.add_audio_consumer(on_pcm)
    listener.on_device_switched_cb = on_switch
    listener.start()

    t_start = time.time()
    try:
        while time.time() - t_start < duration_sec:
            time.sleep(1.0)
            health = listener.get_stream_health()
            print(f"  [{int(time.time() - t_start):02d}s/{int(duration_sec)}s] Active: '{listener.active_input_device_name}' | Healthy: {health['healthy']} | Frames: {len(pcm_frames)} | Last RMS: {health['ambient_rms']:.5f}")
    finally:
        listener.stop()

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_sec": duration_sec,
        "active_device_index": listener.active_input_device_index,
        "active_device_name": listener.active_input_device_name,
        "total_pcm_frames_captured": len(pcm_frames),
        "mean_acoustic_rms": round(float(np.mean(rms_levels)), 6) if rms_levels else 0.0,
        "max_acoustic_rms": round(float(np.max(rms_levels)), 6) if rms_levels else 0.0,
        "physical_switches_observed": device_switches,
        "stream_health_final": listener.get_stream_health()
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/live_physical_monitor_iteration15.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print(f"Capture Complete: {len(pcm_frames)} frames captured from physical microphone.")
    print(f"Mean Room Acoustic Energy (RMS): {summary['mean_acoustic_rms']}")
    print(f"Saved report to logs/live_physical_monitor_iteration15.json")
    print("=" * 80)
    return summary


if __name__ == "__main__":
    monitor_physical_hardware(duration_sec=5.0)

