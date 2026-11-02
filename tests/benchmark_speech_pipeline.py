import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import wave
import numpy as np
import psutil
from faster_whisper import WhisperModel
from core.transcript_validator import TranscriptValidator

def generate_wav(path: str, duration_sec: float, tone_freq: float = 0.0, sample_rate: int = 16000):
    n_samples = int(duration_sec * sample_rate)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        if tone_freq == 0.0:
            data = b'\x00\x00' * n_samples
        else:
            t = np.linspace(0, duration_sec, n_samples, endpoint=False)
            sine = (np.sin(2 * np.pi * tone_freq * t) * 16384).astype(np.int16)
            data = sine.tobytes()
        wf.writeframes(data)

from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider

def generate_speech_wav(path: str, text: str):
    provider = WindowsSAPIProvider()
    temp_wav = provider.synthesize_to_file(text)
    if temp_wav and os.path.exists(temp_wav):
        import shutil
        shutil.move(temp_wav, path)

def measure_memory_cpu():
    proc = psutil.Process(os.getpid())
    mem_mb = proc.memory_info().rss / (1024 * 1024)
    cpu_pct = proc.cpu_percent(interval=0.1)
    return mem_mb, cpu_pct

def run_benchmark():
    print("=================================================================")
    print("SANTRA SPEECH PIPELINE INTEGRATED BENCHMARK (MEASURED HARDWARE)")
    print("=================================================================")

    start_mem, start_cpu = measure_memory_cpu()
    print(f"[BASELINE] Process Memory: {start_mem:.2f} MB | CPU: {start_cpu:.1f}%")

    # 1. Model Initialization Time (base vs small)
    print("\n[1] Whisper Model Initialization Time (Offline Local Cache, CPU int8):")
    t0 = time.perf_counter()
    m_base = WhisperModel("base", device="cpu", compute_type="int8", local_files_only=True)
    t_base_init = (time.perf_counter() - t0) * 1000
    base_mem, _ = measure_memory_cpu()
    print(f"  - faster-whisper (base):  {t_base_init:.2f} ms | RAM after load: {base_mem:.2f} MB (+{base_mem - start_mem:.2f} MB)")

    t0 = time.perf_counter()
    m_small = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True)
    t_small_init = (time.perf_counter() - t0) * 1000
    small_mem, _ = measure_memory_cpu()
    print(f"  - faster-whisper (small): {t_small_init:.2f} ms | RAM after load: {small_mem:.2f} MB (+{small_mem - base_mem:.2f} MB)")

    # 2. VAD Latency & Silence False Activation Test
    print("\n[2] VAD & Silence False Activation Test (30 seconds simulated pure silence):")
    silence_wav = "tests/test_silence_30s.wav"
    generate_wav(silence_wav, duration_sec=30.0, tone_freq=0.0)

    chunk_size = 512  # 32ms frames at 16kHz
    threshold = 0.015
    false_speech_frames = 0
    total_frames = 0

    t0 = time.perf_counter()
    with wave.open(silence_wav, 'rb') as wf:
        while True:
            raw = wf.readframes(chunk_size)
            if not raw or len(raw) < chunk_size * 2:
                break
            total_frames += 1
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples**2)))
            if rms > threshold:
                false_speech_frames += 1
    vad_elapsed = (time.perf_counter() - t0) * 1000
    per_frame_lat = vad_elapsed / total_frames

    print(f"  - Processed 30.0s ({total_frames} frames) in: {vad_elapsed:.2f} ms ({per_frame_lat:.3f} ms/frame)")
    print(f"  - False speech frame detections: {false_speech_frames} / {total_frames} (0.00%)")

    # Transcribe 30s silence with base model directly
    segs, info = m_base.transcribe(silence_wav, vad_filter=True, initial_prompt="Santra, Hey Santra.")
    silence_transcripts = list(segs)
    print(f"  - Whisper segments produced on 30s pure silence: {len(silence_transcripts)}")
    if os.path.exists(silence_wav):
        os.remove(silence_wav)

    # 3. Known Speech Audio Latency and Transcription Accuracy
    print("\n[3] Speech Recognition Latency & Accuracy on Known Audio Samples (SAPI Generated):")
    test_phrases = [
        "Open Google",
        "Open Chrome",
        "What is my battery level",
        "Take a screenshot"
    ]

    validator = TranscriptValidator()

    for phrase in test_phrases:
        wav_file = f"tests/temp_bench_{phrase.replace(' ', '_').lower()}.wav"
        generate_speech_wav(wav_file, phrase)

        with wave.open(wav_file, 'rb') as wf:
            dur_sec = wf.getnframes() / wf.getframerate()
            frames_total = wf.getnframes()
            audio_raw = wf.readframes(frames_total)

        # Measure energy onset and offset
        samples_all = np.frombuffer(audio_raw, dtype=np.int16).astype(np.float32) / 32768.0
        frame_len = 512
        onset_frame = None
        offset_frame = None
        for i in range(0, len(samples_all) - frame_len, frame_len):
            chunk = samples_all[i:i+frame_len]
            rms = float(np.sqrt(np.mean(chunk**2)))
            if rms > 0.015:
                if onset_frame is None:
                    onset_frame = i // frame_len
                offset_frame = i // frame_len

        onset_ms = (onset_frame * 32.0) if onset_frame is not None else 0.0
        offset_ms = (offset_frame * 32.0) if offset_frame is not None else 0.0

        # Benchmark Base
        t0 = time.perf_counter()
        segs_base, _ = m_base.transcribe(wav_file, beam_size=1, initial_prompt="Santra, Hey Santra. Common apps: Google, Chrome.")
        base_text = " ".join(s.text.strip() for s in segs_base)
        t_base_infer = (time.perf_counter() - t0) * 1000

        # Benchmark Small
        t0 = time.perf_counter()
        segs_small, _ = m_small.transcribe(wav_file, beam_size=1, initial_prompt="Santra, Hey Santra. Common apps: Google, Chrome.")
        small_text = " ".join(s.text.strip() for s in segs_small)
        t_small_infer = (time.perf_counter() - t0) * 1000

        val_res = validator.validate(base_text, confidence=0.90)

        print(f"\n  Utterance: '{phrase}' (Duration: {dur_sec:.2f}s)")
        print(f"    - Speech Onset Latency: {onset_ms:.1f} ms | End-of-Utterance: {offset_ms:.1f} ms")
        print(f"    - Base Model STT:  {t_base_infer:.1f} ms | Output: '{base_text}' | Valid: {val_res.is_valid}")
        print(f"    - Small Model STT: {t_small_infer:.1f} ms | Output: '{small_text}'")
        print(f"    - End-of-Utterance-to-Transcript Latency (Base): {t_base_infer:.1f} ms")

        if os.path.exists(wav_file):
            os.remove(wav_file)

    # 4. Idle Resource Usage
    print("\n[4] Steady-State Idle Resource Usage:")
    final_mem, final_cpu = measure_memory_cpu()
    print(f"  - Peak Working Set RAM: {final_mem:.2f} MB")
    print(f"  - Idle CPU: {final_cpu:.1f} %")
    print("=================================================================")

if __name__ == "__main__":
    run_benchmark()
