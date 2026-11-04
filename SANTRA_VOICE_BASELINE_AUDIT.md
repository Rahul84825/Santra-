# SANTRA — VOICE INTELLIGENCE BASELINE AUDIT

**Date:** November 5, 2026  
**Auditor:** Principal AI Systems Engineer & Speech Pipeline Specialist  
**Platform:** Windows 11 AMD64 / Python 3.14.7  
**Scope:** Microphone Capture, VAD, Wake-Word, Whisper STT, Normalization, Intent Routing, and Execution

---

## 1. PIPELINE TOPOLOGY & TRACE

The actual voice and text interaction pipeline in SANTRA was traced from hardware capture through to execution:

```
[Hardware Microphone] (16kHz / 48kHz mono/stereo)
       ↓
[core/audio_device_resolver.py] (Selects device index from Windows endpoint)
       ↓
[core/listener.py] (PyAudio/SoundDevice callback, polyphase resampler to 16kHz)
       ↓
 ┌────────────────────────────────────────────────────────┐
 │ In Standby:                                            │
 │ - Feeds 16-bit PCM frames to SantraWakeWordDetector    │
 │ - Maintains 0.5s pre-roll ring buffer                  │
 │ - Runs energy VAD hysteresis (onset & hold thresholds) │
 └────────────────────────────────────────────────────────┘
       ↓
 [Wake-Word Spotted: "Hey Santra"]
       ↓
 [core/listener.py: trigger_manual_recording]
 (Switches to speech recording; gathers audio chunks until silence or max_duration)
       ↓
 [core/listener.py: _save_and_dispatch] (Encodes 16-bit PCM WAV to tempfile)
       ↓
 [core/transcriber.py: transcribe] (Faster-Whisper int8 on CPU/CUDA)
       ↓
 [core/transcript_validator.py] (Filters hallucinations, empty noise, wake-word only tokens)
       ↓
 [core/command_normalizer.py] (Strips polite fillers, maps aliases & wake words)
       ↓
 [core/intent_engine.py] (Deterministic intent regex, application resolver, action extraction)
       ↓
 [core/jarvis_runtime.py / modules/system/executor.py] (Executes desktop action or routes to research/conversation)
       ↓
 [Verification & Response] (Verifies filesystem/process state, generates UI turn and TTS)
```

---

## 2. AUDIT QUESTIONS & VERIFIED FINDINGS

### 1. Is wake-word detection independent of the normal STT pipeline?
- **Finding:** Partially coupled. `SantraWakeWordDetector` runs on a dedicated background thread (`SantraWakeWordThread`), but shares the underlying Faster-Whisper model instance with `SpeechTranscriber` via `set_shared_model()`. While this prevents loading two 150MB+ models into RAM, concurrent inference on CPU threads can cause latency contention.

### 2. Does the microphone remain active while SANTRA is in standby?
- **Finding:** Yes. `SpeechListener` keeps a continuous audio stream open to supply PCM frames to the wake-word detector and compute ambient RMS noise floors for adaptive VAD hysteresis.

### 3. Does VAD prematurely cut off words or the beginning/end of sentences?
- **Finding:** Yes. When transitioning from wake-word detection to active recording via `trigger_manual_recording()`, the pre-roll buffer was previously cleared, discarding initial command words if the user spoke the command continuously in a single breath (e.g. *"Hey Santra open Valorant"*).

### 4. Is the audio buffer losing initial speech?
- **Finding:** Confirmed. Clearing `_pre_roll_buffer` during wake transition resulted in lost command prefixes. Additionally, `MIN_CONSECUTIVE_FRAMES = 3` (approx 240ms) delayed onset confirmation, clipping plosive consonants (`p`, `b`, `t`).

### 5. Are incorrect sample rates, channel conversions, or audio formats being passed to STT?
- **Finding:** No format errors. All audio is converted to single-channel 16,000 Hz, 16-bit signed PCM WAV files via `scipy.signal.resample_poly` before Whisper ingestion.

### 6. Is the selected microphone actually the intended microphone?
- **Finding:** `core/audio_device_resolver.py` scans DirectSound, MME, and WASAPI endpoints. If an explicit device name is not configured in `config.json`, it selects Windows default input. However, device disconnection recovery occasionally reverted to index 0 rather than the active default communication device.

### 7. Are multiple audio listeners or STT workers running simultaneously?
- **Finding:** When `SantraWakeWordDetector` operated in standalone fallback mode, it opened its own `sd.InputStream`, creating two active microphone streams simultaneously. The shared consumer model (`add_audio_consumer`) resolves this when healthy, but fallback recovery needed strict stream cleanup.

### 8. Is the STT model being reloaded unnecessarily?
- **Finding:** No unnecessary reloads. The Faster-Whisper model remains resident once loaded unless idle timeout (600s) elapses.

### 9. Is the transcription language being forced incorrectly?
- **Finding:** `language="en"` is forced. While preventing Devanagari script hallucination, it forces English phonetics on Indian proper nouns and game titles unless guided by initial prompt vocabulary.

### 10. Are short commands being transcribed before the user finishes speaking?
- **Finding:** For commands with pauses (e.g. *"Create a folder... [pause] ...named Mini Project"*), silence duration timeout of 1.5s prematurely terminated recording before the user completed the clause.

### 11. Are transcripts being normalized differently for voice and typed commands?
- **Finding:** Yes. Spoken transcripts contain ASR errors and phonetic variations (`"ballorant"`, `"anti gravity"`, `"pyth on"`), whereas typed commands are orthographically precise. Normalizer lacked phonetic correction mappings for technical targets.

### 12. Are proper nouns being incorrectly replaced by common words?
- **Finding:** Confirmed. Faster-Whisper defaults `"Valorant"` to `"ballorant"`, `"valerant"`, or `"valor ant"`. `"Antigravity"` was split into `"anti gravity"`. Because `initial_prompt` in `transcriber.py` was hardcoded to a generic list of standard desktop tools (`"VS Code, YouTube, Chrome, Spotify..."`), Whisper had no acoustic bias toward gaming titles, IDEs, or user project names.

### 13. Does the wake-word detector compete with the normal speech-recognition pipeline?
- **Finding:** If wake-word inference is triggered immediately before or during speech recording, both compete for CPU threads (`whisper_threads=4`).

### 14. Does the UI show the actual raw transcript or a modified version?
- **Finding:** The UI displays raw Whisper text for user turns (`"You: {text}"`). However, for responses, intermediate research stage descriptions (e.g. `"Research completed."`) were overwriting the final assistant answer card.

---

## 3. AUDIT CONCLUSION & REPAIR PRIORITIES

1. **Wake-Word & Continuous Audio Capture:** Preserve pre-roll buffer when wake word transitions into speech capture; prevent dropping command words spoken immediately after "Hey Santra".
2. **Contextual Vocabulary in Faster-Whisper:** Dynamically inject installed applications, project names, developer tools, and gaming proper nouns into `initial_prompt`.
3. **Phonetic Normalization:** Add targeted phonetic corrections in `command_normalizer.py` for `Valorant`, `Antigravity`, `Python`, etc.
4. **Intent Classification Alignment:**
   - Add `named` / `called` regex for folder creation on Desktop.
   - Add `open <X> folder` regex in intent engine.
   - Resolve `that folder` in `workspace.open_folder` using current working directory fallback.
5. **Execution Verification:** Verify process and folder state on disk before returning success.
6. **Research Answer Disconnect:** Stop stage descriptions (`"Research completed."`) from overwriting the final research answer.

