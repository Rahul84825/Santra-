# SANTRA — CRITICAL INCIDENT ROOT CAUSE INVESTIGATION
## Investigation: 10+ Minute Stuck State `WAITING_FOR_NVIDIA`, Silent Provider Model Overwrite, and Phantom Cancellations

**Incident Date:** November 3, 2026  
**Environment:** Windows 11 AMD64, Python 3.14.7, PyQt6 Desktop UI, NVIDIA NIM API  
**Severity:** CRITICAL (Complete Runtime Hang & Conversational Failure)  
**Status:** FULLY REPAIRED & REGRESSION VERIFIED

---

## 1. INCIDENT SYNOPSIS & OBSERVED SYMPTOMS

Following an earlier optimization pass that claimed to switch to the low-latency `nvidia/nemotron-3.5-bolt-e4b` model with a 15-second timeout, the running SANTRA application exhibited critical failures during live execution:

1. **Persistent UI Hang:** The SANTRA desktop UI status bar remained frozen displaying `WAITING_FOR_NVIDIA` for over 10 minutes without releasing the pipeline.
2. **Model Reversion:** Telemetry showed the active engine was still using the massive `nemotron-3.5-super-vl-120b-a12b` model with a 30-second timeout and 3 retries, contrary to previous reports.
3. **Spurious Pre-Dispatch Cancellation:** Ordinary user inquiries were aborted before reaching the network (`[NVIDIA Stream] Generation cancelled by caller before dispatch`).
4. **Late Response Drops:** Legitimate responses arriving from the network were discarded with `[LATE_RESPONSE_IGNORED] ... because runtime is SLEEPING or utterance was cancelled.`
5. **Garbage Transcripts Routed to AI:** Repetitive wake-word loops (`Santra, Santra, Santra, Santra...` x75) and fragments (`And else.`) bypassed the transcript validator and were routed as conversational queries.

---

## 2. DEEP FORENSIC INVESTIGATION & 4 INTERLOCKING ROOT CAUSES

A thorough audit of the actual codebase (disregarding optimistic claims in previous documentation) pinpointed four distinct architectural flaws that combined to create this failure mode.

```
+----------------------------------------------------------------------------------------------------+
|                                    INCIDENT RECOVERY ARCHITECTURE                                  |
|                                                                                                    |
|  [Transcribed Text]                                                                               |
|          |                                                                                         |
|          v                                                                                         |
|  [TranscriptValidator] ----(Regex \b\w+\b: Discards Repetitive Wake Words & Fragments)            |
|          |                                                                                         |
|          v (Valid)                                                                                 |
|  [IntentEngine / Router]                                                                           |
|          |                                                                                         |
|          v (Needs AI)                                                                              |
|  [ProviderSettings / Manager] ---> Syncs directly from config & env (bolt-e4b, 15s timeout, 1 ret)|
|          |                                                                                         |
|          v                                                                                         |
|  [NvidiaNemotronProvider] --------> Total request deadline enforcement (15s hard cap)              |
|          |                          Guaranteed response.close() in finally block                   |
|          v                                                                                         |
|  [JarvisRuntime._check_cancelled] -> Detangled from TTS playback interrupt flag                   |
|          |                          Only cancels on explicit Sleep Mode or cancelled utterance ID  |
|          v                                                                                         |
|  [Safe UI Terminal State] --------> try...finally guarantees transition to STANDBY/COMPLETED      |
+----------------------------------------------------------------------------------------------------+
```

---

### ROOT CAUSE 1: Silent Configuration Overwrite in `core/ai/provider_settings.py`

#### The Defect:
While `config/config.py` had been updated to point to `nvidia/nemotron-3.5-bolt-e4b` and a 15-second timeout, `core/ai/provider_settings.py` retained a hardcoded dictionary:
```python
# Previous core/ai/provider_settings.py
DEFAULT_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "nvidia": {
        "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "timeout_sec": 30.0,
        ...
    }
}
```
Whenever `ProviderManager` was initialized or resolved its active provider (`ProviderManager.get_active_provider()` or `ProviderManager.active_provider_key`), it executed `_sync_with_settings()`:
```python
def _sync_with_settings(self):
    cfg = provider_settings_manager.get_provider_config("nvidia")
    # This silently overwrote the provider instance's model back to 120b!
    self._providers["nvidia"].model = cfg.model 
    self._providers["nvidia"].timeout = cfg.timeout_sec
```
#### Impact:
The application never used `bolt-e4b` in practice. It was perpetually reset to the 120B parameter model, forcing 30-second socket timeouts with 3 retries (potentially hanging for 90+ seconds per HTTP call).

---

### ROOT CAUSE 2: Total Deadline Absence & Unclosed Streaming Sockets in `nvidia_provider.py`

#### The Defect:
In `core/ai/providers/nvidia_provider.py`, HTTP request timeouts were applied per-read or per-connect on the raw `requests` / `urllib3` socket:
```python
resp = requests.post(..., timeout=(self.connect_timeout, self.timeout), stream=True)
```
If the upstream server accepted the TCP handshake and sent keep-alive packets or sparse SSE bytes every few seconds, the socket never triggered a timeout. There was no cumulative deadline. Furthermore, when generators were cancelled or exited early, the underlying HTTP stream was not reliably closed in a `finally` block, leaving sockets open in the OS connection pool.

#### Impact:
A stalled stream could block worker threads indefinitely, while consuming network handles.

---

### ROOT CAUSE 3: Conflated Cancellation Flags & Missing Terminal State in `jarvis_runtime.py`

#### The Defect:
In `core/jarvis_runtime.py`, the worker's cooperative cancellation check was defined as:
```python
def _check_cancelled():
    if not self.is_alive or self._runtime_mode == "SLEEPING":
        return True
    if self.tts_manager._interrupt_event.is_set():  # <--- CRITICAL BUG 1
        return True
    if self._active_utterance_id is not None and self._active_utterance_id != uid: # <--- CRITICAL BUG 2
        return True
    return uid in self._cancelled_utterance_ids
```
1. `self.tts_manager._interrupt_event`: This flag is used by the audio output subsystem to stop audio playback when a user speaks. It is left in a "set" state after playback finishes until the next speech item resets it. Because it was set, any subsequent AI request immediately evaluated `_check_cancelled() == True` before even calling the NVIDIA API, logging:
   `[NVIDIA Stream] Generation cancelled by caller before dispatch`.
2. `self._active_utterance_id != uid`: Any ambient sound that triggered VAD or STT updated `_active_utterance_id`, immediately causing the running worker to consider itself cancelled.
3. Missing Terminal State Transition: When `_check_cancelled()` returned True, `_process_single_command` executed:
```python
if _check_cancelled():
    logger.info(f"[LATE_RESPONSE_IGNORED] ...")
    return # <--- CRITICAL BUG 3: Returns without setting status!
```
Because line 1545 exited without resetting `self.current_status` or emitting `status_changed`, the UI was left displaying `WAITING_FOR_NVIDIA` forever!

---

### ROOT CAUSE 4: Split Whitespace Tokenizer in `transcript_validator.py`

#### The Defect:
In `core/transcript_validator.py`, hallucination suppression relied on:
```python
words = text.lower().split()
```
When Whisper hallucinated repetitive wake-word loops formatted with punctuation:
`Santra,Santra,Santra,Santra...`
`text.lower().split()` treated the comma-separated sequence as a single token: `"santra,santra,santra"`. The token repetition counter (`Counter(words)`) only saw 1 unique word of length 1, completely missing the repetition threshold!

#### Impact:
Massive 75-token wake-word hallucination strings bypassed validation, were classified as general queries, and dispatched to NVIDIA.

---

## 3. SUMMARY OF ROOT CAUSES & REMEDIATION MATRIX

| Component | Defect | Root Cause | Permanent Remediation |
|---|---|---|---|
| `core/ai/provider_settings.py` | Model defaulted to `120b` with 30s timeout | Hardcoded dictionary out of sync with `config.py` | Sync defaults directly from `config.py` and environment variables. Set `bolt-e4b` as canonical default. |
| `core/ai/provider_manager.py` | `_sync_with_settings` overwrote settings blindly | Missing max retries synchronization and verification diagnostics | Synced `max_retries=1`, added `get_diagnostics()`. |
| `core/ai/providers/nvidia_provider.py` | No total deadline cap; lingering streams | Socket-only timeout; missing `finally: resp.close()` | Enforced `time.time() + self.timeout` hard cumulative deadline in both sync and stream modes. Closed response explicitly. |
| `core/jarvis_runtime.py` | Pre-dispatch cancellation aborting requests | `tts_manager._interrupt_event` and `_active_utterance_id` used as cancellation flags | Restructured `_check_cancelled()` to only cancel if runtime is `SLEEPING` or utterance ID is explicitly marked cancelled. |
| `core/jarvis_runtime.py` | Frozen `WAITING_FOR_NVIDIA` state in UI | Early `return` in Case 5 without state cleanup | Enclosed all AI processing in `try...finally` with guaranteed terminal transitions (`COMPLETED`, `CANCELLED`, `STANDBY`). |
| `core/transcript_validator.py` | Hallucination strings bypassing validation | `text.split()` failed on punctuation without whitespace | Replaced with regex `re.findall(r'[a-zA-Z0-9]+', text)` and strict prepositional fragment filtering. |

