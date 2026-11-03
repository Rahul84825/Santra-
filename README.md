# SANTRA — Autonomous AI Desktop Assistant & Reasoning Brain

**SANTRA** is a native, local-first voice assistant and autonomous desktop copilot engineered in Python 3.14 and PyQt6 for Windows 11 (with Ubuntu compatibility).

> [!IMPORTANT]
> **Project Identity:**
> **SANTRA** is the official system identity. All prompts, conversational responses, wake-word models, and desktop UI elements are unified under this name.

---

## 1. ARCHITECTURE AT A GLANCE

SANTRA combines three distinct intelligence layers to maximize speed, reliability, and cognitive power:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SANTRA THREE-LAYER CORE                         │
├────────────────────┬──────────────────────────────────┬────────────────┤
│ Layer              │ Engine & Technology              │ Latency Profile│
├────────────────────┼──────────────────────────────────┼────────────────┤
│ Layer 1: Reflex    │ Native Windows APIs & Local OS   │ < 50ms         │
│ Layer 2: Context   │ Offline Conversational Engine    │ < 100ms        │
│ Layer 3: Cognition │ NVIDIA Nemotron 3.5 Bolt (Fast)  │ 700ms - 1800ms │
└────────────────────┴──────────────────────────────────┴────────────────┘
```

1. **Layer 1 — Deterministic Reflex Core:** Near-zero-latency local execution for launching apps, focusing windows, controlling audio/power, navigating web destinations via Chrome/Brave CDP, and capturing screenshots. Completely bypasses cloud LLMs.
2. **Layer 2 — Contextual Conversation & Memory:** Resolves anaphoric pronouns (`"it"`, `"its"`, `"re-explain"`, `"give another example"`), preserves active learning topics across intervening OS commands, and provides conversational etiquette.
3. **Layer 3 — Multimodal AI Reasoning Brain:** Connects to NVIDIA Nemotron for deep technical explanations, C++ algorithms, Data Structures (DSA), problem solving, and gaming strategy (Valorant, Clash Royale).

---

## 2. KEY CAPABILITIES

- **Universal Research & Live Knowledge Engine:** Autonomous multi-stage research engine (DuckDuckGo, RSS, deep page and document extraction, claim verification, conflict resolution, and numbered citations `[1]`, `[2]`). Supports India-first retail price tracking (₹ INR, Amazon India, Flipkart), technology releases, programming documentation, news, gaming patch notes, and comparisons.
- **Enterprise-Grade Research Security & Truthful Verification:** SSRF protection with forward DNS resolution verification (`_verify_dns_resolution`), safe 3-hop redirect inspection (`SafeRedirectHandler`), syndicated PR copy discounting, and transparent e-commerce bot protection classification (`SEARCH_RESULT_PRICE` vs `VERIFIED_PRODUCT_PAGE_PRICE`).
- **Sub-Second Cloud AI & Anti-Hallucination Pipeline:** Sub-second Time-to-First-Token (~744ms) via NVIDIA Nemotron Bolt/Lightning, multi-factor Whisper repetition and compression ratio filtering, and dynamic prompt stripping (85% smaller payload).
- **Universal Application Discovery:** Introspects installed Windows applications, steam games, UWP apps, and development environments.
- **Idempotent Turn Management & Sleep Lifecycle:** Single-response lifecycle with cooperative task cancellation, in-place streaming chat card updates, and zero late-response leakage during Sleep Mode.
- **Instant Explanation Resumption:** Structured multi-sentence progress tracking capable of instantly pausing and resuming technical explanations in 0.5ms without redundant remote LLM calls.
- **Intelligent Desktop Perception (UIA):** Discovers and distinguishes document editors (Notepad), code editors (Antigravity IDE, VS Code), and prompt boxes (ChatGPT, Gemini).
- **Ask-Before-Send Security Gate:** Enforces cryptographic draft binding (SHA-256) and explicit confirmation before sending any external message or web submission.
- **Robust Audio Hot-Swapping:** Continuously monitors Windows audio endpoints, seamlessly transitioning wake-word listening between headphones (e.g. Noise Buds N1 Pro) and Realtek laptop microphones without dropping state.
- **Categorized Command Palette (`Ctrl+K`):** Searchable launcher providing immediate access to all registered capabilities, diagnostic tools, and system hubs.

---

## 3. QUICK START

### Prerequisites
- **OS:** Windows 11 (AMD64) recommended, Ubuntu 22.04+ compatible.
- **Python:** Python 3.10 to 3.14.
- **Hardware:** Microphone and audio output device.

### Installation
```bash
# Clone the repository
git clone https://github.com/Rahul84825/Jarvis_.git
cd jarvis

# Install required Python dependencies
pip install -r requirements.txt
```

### Configuration
Configure your environment in `.env` or open the in-app AI settings panel (`Ctrl+Shift+A`):
```env
# Cloud AI Provider (NVIDIA Nemotron)
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b

# Speech & Voice Settings
WAKEWORD_ENGINE=faster_whisper
TTS_PROVIDER=edge  # edge or sapi
```

### Launching SANTRA
```bash
# Launch GUI Desktop Dashboard
python main.py

# Launch Headless Voice Core (Console Mode)
python main.py --headless
```

### Voice Controls & AI Mode
- **Activate AI Mode:** Say `"switch to AI mode"`, `"enable AI mode"`, or `"ask Nemotron"` (header displays `✦ AI MODE`). Technical queries route to Nemotron; local commands still execute locally.
- **Deactivate AI Mode:** Say `"exit AI mode"`, `"disable AI mode"`, or `"return to normal mode"` (header displays `● NORMAL MODE`).
- **Natural Affirmative Commands:** Speak naturally: `"Yes, open Chrome"`, `"Sure, open Notepad"`, `"Please check my battery"`.
- **Negations & Cancellations:** Say `"No, cancel that"` or `"Actually don't open Chrome"` to safely abort commands.
- **Educational Follow-ups:** Ask `"explain binary search"`, execute any intervening command like `"open Notepad"`, then say `"give another example"` or `"in C++"` — SANTRA preserves the educational topic seamlessly.

---

## 4. KEYBOARD SHORTCUTS

| Shortcut | Description |
| :--- | :--- |
| `Ctrl+K` | Open Categorized Command Palette & Capability Hub |
| `Ctrl+Shift+A` | Open AI Provider Settings & Model Selector |
| `Ctrl+Shift+R` | Open Universal Research & Live Knowledge Hub |
| `Ctrl+Shift+C` | Open Project Architecture & Codebase Explorer |
| `Ctrl+Shift+L` | Open Virtual Testing Room & Simulation Lab |
| `Ctrl+Shift+S` | Open Visual Screen Intelligence Panel |
| `Ctrl+Shift+P` | Open Accent & Pronunciation Settings |
| `Ctrl+Shift+M` | Open Spotify Control Suite |
| `Space` | Immediate Manual Voice Trigger (Bypasses wake word) |
| `Escape` | Close active dialogs or cancel pending operations |

---

## 5. DOCUMENTATION DIRECTORY

- **[SANTRA_STAGE3_ACCEPTANCE_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE3_ACCEPTANCE_REPORT.md):** Final Stage 3 Acceptance and Production Readiness Report.
- **[SANTRA_STAGE3_RUNTIME_VALIDATION.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE3_RUNTIME_VALIDATION.md):** Stage 3 NVIDIA Nemotron Runtime Reliability and Failure Injection Audit (15/15 scenarios).
- **[SANTRA_STAGE3_PRODUCT_RESEARCH.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE3_PRODUCT_RESEARCH.md):** Real-world product intelligence, price lineage, and trade-off verification report.
- **[SANTRA_STAGE3_CITATION_QUALITY.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE3_CITATION_QUALITY.md):** Citation quality, contradiction detection, and bracket reference validation.
- **[SANTRA_STAGE3_DOCUMENT_UNDERSTANDING.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE3_DOCUMENT_UNDERSTANDING.md):** Windows 11 zero-dependency local offline OCR and document deduplication report.
- **[SANTRA_STAGE3_CONVERSATION_TESTS.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE3_CONVERSATION_TESTS.md):** Multi-turn conversational continuity across intervening local OS commands.
- **[SANTRA_STAGE4_FINAL_ACCEPTANCE_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE4_FINAL_ACCEPTANCE_REPORT.md):** Stage 4 Production Verification, Real-World Reliability & Acceptance (61/61 tests PASS, 100-cycle soak test).
- **[SANTRA_STAGE4_SOAK_TEST_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE4_SOAK_TEST_REPORT.md):** Stage 4 Soak & Concurrency Report (Zero thread/memory leaks, sub-50ms latency).
- **[SANTRA_STAGE4_SECURITY_AUDIT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE4_SECURITY_AUDIT.md):** Stage 4 SSRF numeric IP exploit defense and prompt injection sanitization.
- **[SANTRA_STAGE4_NVIDIA_RUNTIME_AUDIT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE4_NVIDIA_RUNTIME_AUDIT.md):** Stage 4 Nemotron runtime timeout clamping and barge-in socket teardown.
- **[SANTRA_RESEARCH_ARCHITECTURE.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RESEARCH_ARCHITECTURE.md):** Architecture of the Universal Research, Live Knowledge & Intelligence Engine.
- **[SANTRA_RESEARCH_BASELINE_AUDIT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RESEARCH_BASELINE_AUDIT.md):** Initial capability audit and reuse assessment of search/browser tools.
- **[SANTRA_SOURCE_REGISTRY.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_SOURCE_REGISTRY.md):** Directory of 100+ domains with authority weights and Indian regional relevance.
- **[SANTRA_EVIDENCE_VERIFICATION.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_EVIDENCE_VERIFICATION.md):** Evidence extraction, contradiction detection, and citation standards.
- **[SANTRA_RESEARCH_MEMORY.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RESEARCH_MEMORY.md):** SQLite database schema and domain-specific freshness TTL policies.
- **[SANTRA_RESEARCH_SECURITY.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RESEARCH_SECURITY.md):** SSRF protection, prompt injection defenses, and shopping permissions.
- **[SANTRA_RESEARCH_TEST_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RESEARCH_TEST_REPORT.md):** Comprehensive test results (75/75 passing automated regression tests).
- **[SANTRA_RESEARCH_IMPLEMENTATION_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RESEARCH_IMPLEMENTATION_REPORT.md):** Final engineering implementation and deployment report.
- **[SANTRA_CRITICAL_INCIDENT_ROOT_CAUSE.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_CRITICAL_INCIDENT_ROOT_CAUSE.md):** Forensic audit of WAITING_FOR_NVIDIA freeze, configuration overwrite, and cancellation bugs.
- **[SANTRA_PROVIDER_CONFIGURATION_AUDIT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_PROVIDER_CONFIGURATION_AUDIT.md):** Authoritative audit of AI provider hierarchy, runtime diagnostics, and security.
- **[SANTRA_RUNTIME_CANCELLATION_AUDIT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_RUNTIME_CANCELLATION_AUDIT.md):** Audit of cooperative task cancellation, TTS flag decoupling, and UI state cleanup.
- **[SANTRA_INCIDENT_REPAIR_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_INCIDENT_REPAIR_REPORT.md):** Engineering repair report, benchmarks, and verification evidence.
- **[SANTRA_REGRESSION_TEST_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_REGRESSION_TEST_REPORT.md):** Automated regression test results (54/54 passing tests).
- **[SANTRA_STAGE_2_IMPLEMENTATION_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE_2_IMPLEMENTATION_REPORT.md):** Stage 2 report: Unified Intelligence Routing, Command Execution & Conversational Reliability.
- **[SANTRA_ARCHITECTURE.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_ARCHITECTURE.md):** Complete architectural specification, state machine, and perception models.
- **[SANTRA_STAGE_1_AUDIT_REPORT.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE_1_AUDIT_REPORT.md):** Comprehensive Stage 1 audit report covering routing, memory, and telemetry.
- **[BACKLOG.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/BACKLOG.md):** Active engineering backlog and future implementation roadmap.
- **[CHANGELOG.md](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/CHANGELOG.md):** Version history, bugfixes, and release candidate milestones.

---

## 6. LICENSE & GOVERNANCE

Engineered for local-first autonomy, user privacy, and system security on Windows 11.

