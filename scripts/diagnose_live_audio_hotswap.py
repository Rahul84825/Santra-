"""
Hardware Diagnostic & Real-World Telemetry for Audio Hot-Swap Recovery.
Runs directly on the host Windows machine to verify physical endpoints,
recovery latency, RMS levels, and stream health.
"""

import os
import sys
sys.path.insert(0, os.path.abspath("."))

import json
import time
import numpy as np
import sounddevice as sd

from core.audio_device_resolver import (
    resolve_audio_input_device,
    get_all_audio_devices,
    refresh_device_cache,
    get_device_topology_signature
)
from core.listener import SpeechListener

def run_diagnostics():
    print("=" * 60)
    print("SANTRA ITERATION 13: AUDIO INPUT HOT-SWAP DIAGNOSTICS")
    print("=" * 60)

    # 1. Hardware topology
    devices = get_all_audio_devices()
    def_in, def_out = sd.default.device
    print(f"Total Audio Devices Discovered: {len(devices)}")
    print(f"Default Input Device: [{def_in}] {devices[def_in]['name'] if def_in is not None and def_in < len(devices) else 'None'}")
    print(f"Default Output Device: [{def_out}] {devices[def_out]['name'] if def_out is not None and def_out < len(devices) else 'None'}")

    # 2. Resolver decision
    resolved = resolve_audio_input_device()
    print(f"Resolved Audio Input Device: [{resolved.device_index}] '{resolved.device_name}' (Rate={resolved.sample_rate}Hz, Resample={resolved.requires_resampling})")

    # 3. Live Listener Stream Test
    listener = SpeechListener(sample_rate=16000)
    received_pcm_chunks = []
    listener.add_audio_consumer(lambda chunk: received_pcm_chunks.append(chunk))

    print("\nStarting SpeechListener stream on live hardware...")
    t_start = time.perf_counter()
    listener.start()
    t_started = time.perf_counter()
    startup_ms = (t_started - t_start) * 1000
    print(f"Listener stream initialized in {startup_ms:.2f}ms")

    # Let audio run for 1 second to accumulate real microphone frames
    time.sleep(1.0)

    health_before = listener.get_stream_health()
    print(f"Stream Health Before Switch: {json.dumps(health_before, indent=2)}")
    print(f"Received PCM chunks: {len(received_pcm_chunks)}")

    # 4. Trigger Dynamic Hot-Swap Recovery
    print("\nExecuting Dynamic Hot-Swap Stream Recovery...")
    t_recover_start = time.perf_counter()
    recovered = listener.recover_stream(reason="live_diagnostic_test")
    t_recover_end = time.perf_counter()
    recovery_ms = (t_recover_end - t_recover_start) * 1000
    print(f"Stream Recovery Successful: {recovered} (Duration: {recovery_ms:.2f}ms)")

    # Run for another 1 second to ensure new stream delivers live audio
    received_chunks_after = []
    listener.add_audio_consumer(lambda chunk: received_chunks_after.append(chunk))
    time.sleep(1.0)

    health_after = listener.get_stream_health()
    print(f"Stream Health After Switch: {json.dumps(health_after, indent=2)}")
    print(f"Received PCM chunks on recovered stream: {len(received_chunks_after)}")

    listener.stop()
    print("\nListener stream stopped cleanly.")

    # 5. Summary Telemetry
    telemetry = {
        "status": "PASSED" if (recovered and len(received_chunks_after) > 0) else "FAILED",
        "default_input": devices[def_in]["name"] if def_in is not None and def_in < len(devices) else None,
        "default_output": devices[def_out]["name"] if def_out is not None and def_out < len(devices) else None,
        "resolved_input_name": resolved.device_name,
        "resolved_input_index": resolved.device_index,
        "hardware_sample_rate": resolved.sample_rate,
        "resampling_required": resolved.requires_resampling,
        "stream_startup_latency_ms": round(startup_ms, 2),
        "hotswap_recovery_latency_ms": round(recovery_ms, 2),
        "post_switch_chunks_received": len(received_chunks_after),
        "post_switch_ambient_rms": health_after.get("ambient_rms"),
        "stream_healthy_after_switch": health_after.get("healthy")
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/audio_hotswap_diagnostic.json", "w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=2)

    print("\nTelemetry saved to logs/audio_hotswap_diagnostic.json:")
    print(json.dumps(telemetry, indent=2))

if __name__ == "__main__":
    run_diagnostics()
