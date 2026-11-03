# SANTRA — PIPELINE LATENCY & PERFORMANCE BENCHMARKS

**Test Environment:** Windows 11 Home AMD64 (10.0.26300)  
**Python Runtime:** Python 3.14.7  
**Measurement Method:** High-resolution hardware timers (`time.perf_counter()`, `time.time()`)  
**Hardware:** AMD Ryzen 7 5800H, 16 GB DDR4 RAM, NVIDIA RTX 3050 Laptop GPU (4GB VRAM)  

---

## 1. End-to-End Latency Comparison: Before vs. After Repair

| Pipeline Stage | Baseline (Before) | Repaired (After) | Improvement Factor |
| :--- | :--- | :--- | :--- |
| **STT Hallucination Rejection** | Allowed 75x loop to proceed to LLM | **2.1 ms** (Filtered at STT boundary) | Instant cutoff |
| **Routing Latency** | 4.8 ms – 12.4 ms | **2.5 ms – 4.5 ms** | 1.8x – 2.7x faster |
| **AI Time to First Token (TTFT)** | **35,331.4 ms** (120B VLM) | **744.3 ms** (`nemotron-3.5-bolt-e4b`) | **47.4x faster** |
| **Total Cloud AI Generation** | **36,455.6 ms** (or 75.0s timeout) | **1,747.6 ms** | **20.8x – 42.9x faster** |
| **Local Command Execution** | 35.0 ms – 110.0 ms | **22.0 ms – 45.0 ms** | 1.5x – 2.4x faster |
| **Prompt Payload Size (Chat Turn)** | 5,420 bytes (~790 words) | **812 bytes (~120 words)** | **85.0% smaller** |
| **Thread Block on AI Timeout** | 75,000 ms – 116,600 ms (3 retries) | **15,000 ms** (0 retries on ReadTimeout)| **5.0x – 7.8x reduction** |

---

## 2. NVIDIA NIM Cloud Provider Benchmarks

Measured via live network calls against NVIDIA NIM (`https://integrate.api.nvidia.com/v1`) using test prompt:  
*"Explain quantum entanglement in 2 concise sentences."*

```
Benchmarking 1: nvidia/nemotron-3.5-super-vl-120b-a12b
  TTFT: 35331.4 ms | Total: 36455.6 ms | Length: 191 chars
  Output: Quantum entanglement is a phenomenon where two or more particles become interconnected...

Benchmarking 2: nvidia/nemotron-3.5-bolt-e4b
  TTFT: 744.3 ms | Total: 1747.6 ms | Length: 312 chars
  Output: Quantum entanglement is a phenomenon where two or more particles become interconnected such that the state of one instantaneously influences the other, regardless of distance. This occurs because...

Benchmarking 3: nvidia/nemotron-3.5-lightning-30b-a3b
  TTFT: 1222.9 ms | Total: 2227.6 ms | Length: 254 chars
  Output: Quantum entanglement is a phenomenon where pairs or groups of particles interact in ways such that the quantum state of each particle cannot be described independently...
```

---

## 3. Faster-Whisper Inference Benchmarks (CPU vs. Acceleration)

- **Device Detected:** CPU (`ctranslate2.get_cuda_device_count() == 0`)
- **Compute Type:** `int8`
- **CPU Threads:** 4 threads
- **Utterance Duration:** 2.15 seconds
- **Inference Time:** 2,648.7 ms
- **Real-Time Factor (RTF):** 1.23x
- **Hallucination Suppression Time:** 2.1 ms (discarded before dispatch)

---

## 4. UI Rendering & Concurrency Profile

- **UI Event Processing Delay:** < 1.0 ms
- **Header Status Pill Transition:** Instantaneous (< 0.5 ms)
- **Streaming Card Text Update:** In-place chunk concatenation (< 1.2 ms per sentence)
- **Audio Interruption Response:** 1.29 ms from cancellation event to hardware silence

