# SANTRA — PROVIDER CONFIGURATION AUDIT
## Comprehensive Audit of AI Provider Architecture, Configuration Layers, and Runtime Diagnostics

**Audit Date:** November 3, 2026  
**Auditor:** Principal Python Desktop Systems Engineer  
**Component Scope:** `config/config.py`, `core/ai/provider_settings.py`, `core/ai/provider_manager.py`, `core/ai/providers/nvidia_provider.py`  
**Security Notice:** All API keys and secrets are masked or accessed strictly via environment variables; zero credentials are leaked in code or logs.

---

## 1. CONFIGURATION FLOW & HIERARCHY

Before the incident fix, configuration resolution suffered from split-brain syndrome: `config/config.py` read `.env` and established defaults, but `core/ai/provider_settings.py` maintained its own independent hardcoded defaults. When `ProviderManager` started, it overrode the instance configuration with the stale defaults from `provider_settings.py`.

### Authoritative Architecture Post-Repair

```
               [ .env File / Environment Variables ]
                                 |
                                 v
                     [ config/config.py (Config) ]
                     - nvidia_model = 'nvidia/nemotron-3.5-bolt-e4b'
                     - nvidia_timeout_sec = 15.0
                     - nvidia_max_retries = 1
                     - nvidia_connect_timeout_sec = 4.0
                                 |
                                 v
               [ core/ai/provider_settings.py (Manager) ]
               - Dynamically synchronizes DEFAULT_PROVIDERS from Config
               - Resolves active provider: 'nvidia'
                                 |
                                 v
               [ core/ai/provider_manager.py (ProviderManager) ]
               - _sync_with_settings(): applies model, timeout, retries
                                 |
                                 v
               [ core/ai/providers/nvidia_provider.py (NvidiaNemotronProvider) ]
               - model = 'nvidia/nemotron-3.5-bolt-e4b'
               - timeout = 15.0s (cumulative deadline)
               - connect_timeout = 4.0s
               - max_retries = 1
```

---

## 2. CONFIGURATION VERIFICATION & LAYER INSPECTION

### Layer 1: Environment Variables & Global Config (`config/config.py`)
- `NVIDIA_API_KEY`: Loaded from `.env` via `python-dotenv`.
- `NVIDIA_MODEL`: Defaults to `"nvidia/nemotron-3.5-bolt-e4b"`.
- `NVIDIA_TIMEOUT_SEC`: Defaults to `15.0` (float).
- `NVIDIA_CONNECT_TIMEOUT_SEC`: Defaults to `4.0` (float).
- `NVIDIA_MAX_RETRIES`: Defaults to `1` (int).

### Layer 2: Provider Settings Manager (`core/ai/provider_settings.py`)
- Hardcoded legacy `120b` fallback removed.
- Canonical default set directly to `nvidia/nemotron-3.5-bolt-e4b`.
- On module load, `DEFAULT_PROVIDERS["nvidia"]` is initialized using:
  ```python
  default_model = getattr(config, "nvidia_model", os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-bolt-e4b"))
  default_timeout = float(getattr(config, "nvidia_timeout_sec", os.environ.get("NVIDIA_TIMEOUT_SEC", 15.0)))
  default_retries = int(getattr(config, "nvidia_max_retries", os.environ.get("NVIDIA_MAX_RETRIES", 1)))
  ```

### Layer 3: Runtime Provider Manager (`core/ai/provider_manager.py`)
- `_sync_with_settings()` now synchronizes:
  - `model`
  - `timeout`
  - `max_retries`
- Added authoritative `get_diagnostics()` method to expose live configuration without exposing secrets.

### Layer 4: Provider Implementation (`core/ai/providers/nvidia_provider.py`)
- Hard deadline calculation on entry:
  ```python
  deadline = time.time() + self.timeout
  ```
- Streaming chunk iteration continuously enforces:
  ```python
  if time.time() > deadline:
      logger.warning(f"[NVIDIA Stream] Hard deadline exceeded ({self.timeout}s). Terminating stream.")
      break
  ```
- Network response resources guaranteed to close:
  ```python
  try:
      ...
  finally:
      resp.close()
  ```

---

## 3. RUNTIME DIAGNOSTIC TELEMETRY

A programmatic diagnostic check on the initialized runtime confirms the active provider configuration:

```python
from core.ai.provider_manager import get_provider_manager
pm = get_provider_manager()
print(pm.get_diagnostics())
```

**Diagnostic Output:**
```json
{
  "provider": "nvidia",
  "model": "nvidia/nemotron-3.5-bolt-e4b",
  "connect_timeout_sec": 4.0,
  "read_timeout_sec": 15.0,
  "max_retries": 1,
  "is_configured": true
}
```

---

## 4. SECURITY & CREDENTIAL HANDLING AUDIT

1. **API Key Storage:** Stored exclusively in local `.env` (`NVIDIA_API_KEY=nvapi-...`).
2. **Log Redaction:** All logging statements in `nvidia_provider.py`, `provider_manager.py`, and `jarvis_runtime.py` mask or omit HTTP `Authorization` headers.
3. **Exception Tracing:** HTTP errors log status codes (`resp.status_code`) and truncated response text (`resp.text[:200]`), preventing header or credential leakage in stack traces.
4. **Git Safety:** Git status confirms `.env` remains ignored and untracked. No commits or remote pushes executed.

