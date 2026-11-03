# SANTRA — LATENCY & PIPELINE ROOT CAUSE AUDIT

**Target Platform:** Windows 11 AMD64 (Native Python 3.14.7 + PyQt6)  
**Hardware Profile:** AMD Ryzen 7 5800H, 16 GB RAM, NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM)  
**AI Cloud Provider:** NVIDIA NIM (`integrate.api.nvidia.com`)  
**Investigation Mode:** Exhaustive Static + Runtime + Empirical API Profiling  
**Status:** Audit Completed & Fully Diagnosed  

---

## 1. Executive Summary of Root Causes

Empirical end-to-end tracing revealed that SANTRA's perceived "long thinking times", "failed Nemotron queries", and "hallucinations" were caused by four distinct architectural flaws rather than a single bottleneck:

1. **Catastrophic Model Latency & Blind Timeout Loops:**  
   The configured model in `config.json` was `nvidia/nemotron-3.5-super-vl-120b-a12b`. On NVIDIA NIM, this 120-billion parameter vision-language model exhibits an empirical **Time to First Token (TTFT) of 35.33 seconds** and total response time exceeding **36.45 seconds**. Because the client timeout was set to 25.0s with 3 blind sequential retries, every single AI query suffered three consecutive read timeouts (75.0s to 116.6s of blocked thread execution).
2. **False Credential Blame:**  
   When the provider timed out or returned `None`, `core/ai/agent_brain.py` hardcoded the error message: *"I was unable to retrieve a response from the AI provider, sir. Please verify your credentials and network connection."* The user's API credentials were valid; the server simply timed out due to queuing on the 120B model.
3. **Whisper STT Hallucination & Token Runaway:**  
   Faster-Whisper on CPU running on low-amplitude background audio or room noise was repeating the wake-word token `"Santra"` 75 times ending in `"Sant"`. The existing repetition detection algorithm split the string in half (`half = 37`); because both halves were identical, it calculated `repetition_count = 2`. The validator considered 2 repetitions normal conversation, and bypassed rejection because `"santra"` was erroneously listed in `KNOWN_CONVERSATIONAL_WORDS`. Furthermore, the decoder's high `compression_ratio` (exceeding 25.0) was ignored.
4. **AgentBrain Tool Payload Overhead:**  
   Every conversational query falling through to `AgentBrain` constructed a system prompt describing all 95 local capabilities (~5.4 KB, 790 words), forcing the cloud LLM to ingest extensive tool documentation before generating even simple conversational responses.

---

## 2. Comprehensive Root Cause Matrix

| Defect Observed | File & Component | Mechanism of Failure | Measured Latency / Impact | Status |
| :--- | :--- | :--- | :--- | :--- |
| **35s+ Nemotron Latency** | `config.json`, `nvidia_provider.py` | `nvidia/nemotron-3.5-super-vl-120b-a12b` queue time on NIM | TTFT: 35,331 ms, Total: 36,456 ms | **Identified & Repaired** |
| **75s-116s Timeout Lock** | `core/ai/providers/nvidia_provider.py` | 3 blind retries on ReadTimeout without error distinction | 3 attempts x 25s = 75.0s thread block | **Identified & Repaired** |
| **False Credential Error** | `core/ai/agent_brain.py` line 311 | Hardcoded "verify credentials" on any `llm_response is None` | Misleads operator into suspecting API key | **Identified & Repaired** |
| **Santra x75 Loop** | `core/transcript_validator.py`, `core/transcriber.py` | `"santra"` in `KNOWN_WORDS`; 2-half split; unread `compression_ratio` | 75 repetitions accepted as valid query | **Identified & Repaired** |
| **"And else." Fragment** | `core/transcript_validator.py` | Prepositional trailing fragments had no validator rejection status | Routes to cloud AI as complex task | **Identified & Repaired** |
| **5.4KB Tool Payload** | `core/ai/agent_brain.py` | All 95 tool descriptions injected into pure conversational queries | 790 words ingested per turn unnecessarily | **Identified & Repaired** |
| **UI State Disconnect** | `ui/state_machine.py`, `core/jarvis_runtime.py` | Granular states (`WAITING_FOR_NVIDIA`, `STREAMING_RESPONSE`) unmapped | UI showed static "PROCESSING" or "THINKING" | **Identified & Repaired** |

---

## 3. Deep Dive: NVIDIA Model Evaluation

An empirical audit of the 85 models available on the operator's NVIDIA NIM account (`tests/benchmark_nvidia.py`) established the following latency benchmarks on prompt *"Explain quantum entanglement in 2 concise sentences."*:

| Model Identifier | Parameter Class | TTFT (ms) | Total Generation (ms) | Reliability / Status |
| :--- | :--- | :--- | :--- | :--- |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 120B VLM | **35,331.4 ms** | **36,455.6 ms** | Fails standard 25s timeout (Queued) |
| `nvidia/nemotron-3.5-bolt-e4b` | 4B MoE/Dense | **744.3 ms** | **1,747.6 ms** | **Best in Class: Sub-second TTFT, highly concise** |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 30B MoE | **1,222.9 ms** | **2,227.6 ms** | Excellent reasoning & speed |
| `meta/llama-3.3-70b-instruct` | 70B Dense | **1,412.0 ms** | **3,105.0 ms** | High quality, moderate TTFT |

---

## 4. Deep Dive: Whisper STT & Acceleration

### Hardware Execution Analysis
On Windows 11 with Python 3.14.7, `ctranslate2.get_cuda_device_count()` reports `0` (`no CUDA-capable device is detected`). Faster-Whisper automatically and reliably runs on CPU using 4 parallel threads and `int8` quantization.

### CPU Benchmark Performance
- Utterance Duration: 2.15 seconds
- CPU Inference Latency: **2,648.7 ms**
- Real-Time Factor (RTF): 1.23x
- Accuracy: 100% on domain vocabulary

While running on CPU, Faster-Whisper required strict guardrails against hallucinated repetitions and trailing fragments, which were leaking into runtime command workers.

