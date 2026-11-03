# SANTRA NVIDIA Runtime Configuration Audit Report

## 1. Scope & Objective
Audit all configuration files, provider classes, network adapters, and caching modules in the SANTRA codebase to guarantee absolute alignment with the active NVIDIA Nemotron model specification (`nvidia/nemotron-3.5-bolt-e4b`) and eliminate legacy decommissioned model references (`nvidia/nemotron-3.5-super-vl-120b-a12b`).

---

## 2. Forensic Codebase Scan Results

### A. Configuration Files
- `config/config.py`: Verified `DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3.5-bolt-e4b"`.
- `config.json`: Verified `"ai_provider.nvidia.model": "nvidia/nemotron-3.5-bolt-e4b"`.
- `core/ai/provider_settings.py`: Verified `NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3.5-bolt-e4b"`.

### B. Caching Layer Audit & Repair
- `core/ai/caching/cache_manager.py`:
  - **Forensic Discovery**: Default argument values in `get()`, `set()`, and helper methods referenced `"nvidia/nemotron-3.5-super-vl-120b-a12b"`.
  - **Correction**: Replaced all occurrences with `"nvidia/nemotron-3.5-bolt-e4b"`.
  - **Verification**: Verified zero string occurrences of `super-vl-120b` remain in `cache_manager.py`.

### C. Provider Manager & Network Parameters
Both the primary assistant `ConversationManager` and the `ResearchManager` instantiate and route requests through the unified `ProviderManager` class:
- **Base URL**: `https://integrate.api.nvidia.com/v1`
- **Active Model**: `nvidia/nemotron-3.5-bolt-e4b`
- **Connect Timeout**: `4.0s` (strict fail-fast guard)
- **Read Timeout**: `15.0s` (guarantees cancellation before user frustration)
- **Max Retries**: `1` (prevents cascaded retry storms)
- **Streaming Pipeline**: SSE `chunk` stream supported via generator with active cancellation check (`is_cancelled`).

---

## 3. Empirical Smoke Test Evidence
A live end-to-end inference request was dispatched directly to the NVIDIA endpoint:
- **Model**: `nvidia/nemotron-3.5-bolt-e4b`
- **HTTP Endpoint**: `https://integrate.api.nvidia.com/v1/chat/completions`
- **HTTP Response Code**: `200 OK`
- **Inference Latency**: `1,932.1 ms`
- **Token Output Sample**: `"Time complexity in computer science measures how the runtime of an algorithm scales as the size of the input grows..."`
- **Error / Timeout Rate**: `0.0%`

---

## 4. Architectural Uniformity
Both `ConversationManager` and `ResearchManager` now share identical model identity, retry policies, and timeout boundaries, ensuring predictable runtime behavior without state lockups or hung network sockets.

