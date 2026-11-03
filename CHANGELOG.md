# SANTRA — ENGINEERING CHANGELOG

All notable changes, bug fixes, architecture overhauls, and verification milestones for SANTRA are documented in this file.

---

## [2.4.0] - 2026-11-03
### Universal Research Engine Stage 4: Production Verification, Real-World Reliability & Cross-Platform Validation

#### Hardened & Verified
- **NVIDIA Read Timeout Upper Ceiling (`core/ai/providers/nvidia_provider.py`):**
  - Enforced strict upper ceiling `read_timeout = min(15.0, max(5.0, self.timeout))` in `_get_timeout_tuple()` to prevent custom caller timeouts from defeating the 15.0s fail-fast limit.
- **Cancelled Stream Memory Suppression (`core/conversation_manager.py`):**
  - Suppressed partial streamed tokens from appending to `self.history` or persisting to SQLite episodic memory upon barge-in or sleep cancellation, returning empty text.
- **Immediate Audio Watchdog & Queue Purge (`core/jarvis_runtime.py`):**
  - Added `self.tts_manager.interrupt(force=True)` on research cancellation, guaranteeing immediate cessation of queued audio chunks and eliminating ghost speech.
- **Advanced SSRF Armor (`core/research/research_security.py`):**
  - Blocked alternative numeric IP representations including integer IPs (`http://2130706433/`), hex IPs (`http://0x7f000001/`), IPv4-mapped IPv6 (`::ffff:0:0/96`), and link-local subnets (`fe80::/10`).
  - Expanded prompt injection regex filters for `system instructions:` and `disregard all prior orders`.
- **ZIP Bomb Decompression Protection (`core/research/document_extractor.py`):**
  - Enforced 25 MB uncompressed byte ceiling on Office OpenXML document parsing (`.docx`, `.xlsx`) to prevent XML expansion attacks.
  - Added structured table and cell extraction for DOCX documents and multi-sheet value extraction for XLSX files.
- **Transparent Heuristic Claim Tagging (`core/research/claim_extractor.py`):**
  - Tagged all deduced product disadvantages with `(Inferred: ...)` to clearly differentiate source-backed review excerpts from heuristic technical deductions.
- **Soak Test & Concurrency Verification (`scripts/stage4_soak_test.py`):**
  - Completed 100 continuous end-to-end cycles with 0 thread leaks (7 threads constant), memory bounded under 70 MB (baseline 52.06 MB -> 68.32 MB), P50 latency 14.19 ms, and 100% SQLite database record preservation (3,055 records in 19 tables).
- **Test Automation & Regressions (`tests/test_stage4_production_verification.py`):**
  - Created 15 dedicated Stage 4 production verification tests (15/15 PASS).
  - Maintained 100% passing status across Stage 2 and Stage 3 regression suites (46/46 PASS), achieving a total of 61/61 passing automated tests.

---

## [2.3.0] - 2026-11-03
### Universal Research Engine Stage 3: Real-World Research Quality, Conversational Continuity & Acceptance Testing

#### Added & Hardened
- **NVIDIA Nemotron Complete Runtime Reliability Suite (`tests/test_stage3_nvidia_runtime_reliability.py`):**
  - Implemented and passed all 15 real-world runtime lifecycle scenarios: connect timeout (4.0s), read timeout (15.0s), HTTP 429 backoff, HTTP 5xx retry, invalid choices payload, stream severance, barge-in cancellation, sleep mode interruption, wake-during-request unique token isolation, late response suppression, and multi-tenant worker isolation.
- **Real-World Zero-Dependency Offline OCR (`core/vision/ocr_engine.py`, `core/research/document_extractor.py`):**
  - Integrated native Windows 11 `Windows.Media.Ocr` via PowerShell with `pytesseract` cross-platform fallback.
  - Achieved 100% offline document and invoice extraction (~1.4s per image) with zero external cloud dependencies or API keys.
  - Added in-memory SHA-256 duplicate image and document detection, bypassing redundant OCR compute in 0.1ms.
  - Differentiated native text-stream PDFs (`TEXT_EXTRACTED_FROM_STREAM`) from scanned PDFs (`SCANNED_PDF_DETECTED`).
- **Enriched Product Entity & Concrete Verification Schema (`core/research/research_models.py`, `core/research/claim_extractor.py`):**
  - Added deterministic recommendation tiers: `Best Overall`, `Best Budget`, `Best Specifications`, `Best Value`, `Best Compatibility`.
  - Added dual price lineage: `search_result_price` (observed in indexed listings) vs `product_page_price` (verified checkout page).
  - Enforced mandatory extraction and disclosure of disadvantages/trade-offs for every recommended product.
  - Expanded specification extraction for Hall Effect magnetic sticks/triggers, polling rates (1000Hz), optical mouse sensors, laptop GPUs (RTX 2050/3050), and display refresh rates (144Hz).
- **Conversational Continuity Across Intervening Local Commands (`core/research/research_router.py`, `core/research/research_manager.py`):**
  - Preserved active research session across intervening local operating system commands (e.g. volume control, window focus).
  - Added support for pronoun resolution (`its disadvantages`, `that one`), budget shifts (`find something cheaper`), and price freshness re-checks (`is that price still valid?`).
  - Added durable session and candidate rehydration from SQLite on assistant reboot via `restore_active_session()`.
  - Enforced immediate cancellation check in `jarvis_runtime.py`, eliminating ghost audio playback or conversation memory pollution when transitioning to sleep mode.
- **Stage 3 Acceptance Validation Suite (`scripts/validate_stage3_acceptance.py`):**
  - Validated end-to-end execution of controllers, laptops, budget shifts, price freshness, and local OCR document understanding (6/6 scenarios passed).

---

## [2.2.0] - 2026-11-03
### Universal Research Engine Stage 2: Reliability, Hardening & Multi-Domain Validation

#### Hardened & Secured
- **NVIDIA Model Identity Synchronization (`core/ai/caching/cache_manager.py`):**
  - Eliminated lingering defaults referencing decommissioned `nvidia/nemotron-3.5-super-vl-120b-a12b`.
  - Harmonized all cache lookup and persistence operations to use `nvidia/nemotron-3.5-bolt-e4b`.
- **SSRF & DNS Rebinding Protection (`core/research/research_security.py`, `core/research/page_extractor.py`):**
  - Added forward DNS resolution verification (`_verify_dns_resolution`) preventing public hostnames from resolving to internal network or cloud metadata IPs.
  - Added link-local IPv6 (`fe80::/10`) and IPv4-mapped IPv6 (`::ffff:0:0/96`) to blocked IP subnets.
  - Implemented `SafeRedirectHandler` enforcing a 3-hop limit and re-verifying every HTTP redirect destination before connection.
- **Retailer Bot Detection & Product Pricing Schema (`core/research/research_models.py`, `core/research/claim_extractor.py`):**
  - Introduced `PriceType` enum (`SEARCH_RESULT_PRICE`, `EXTRACTED_LISTING_PRICE`, `VERIFIED_PRODUCT_PAGE_PRICE`, `HISTORICAL_PRICE`, `UNAVAILABLE_PRICE`).
  - Added rich product listing fields to `ProductEntity`: `model_variant`, `asin_or_sku`, `retailer`, `seller`, `price`, `price_type`, `availability`, `warranty`, `rating`, `review_count`, `extraction_status`.
  - Handled e-commerce anti-bot challenges truthfully by marking `extraction_status = "BLOCKED_BY_RETAILER_BOT_PROTECTION"` on HTTP 503/403/CAPTCHA rather than claiming direct cart verification.
- **Syndicated Wire Copy Detection & Primary Source Verification (`core/research/source_verifier.py`):**
  - Added `_detect_syndicated_copy()` discounting confidence by 15% when identical verbatim excerpts (>= 40 characters) are repeated across multiple domains.
  - Added `VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE` for official documentation and manufacturer specs.
- **Document & Image Extraction Hardening (`core/research/document_extractor.py`):**
  - Added native parsing for `.docx` and `.xlsx` via standard library `zipfile` and XML parsing.
  - Added image metadata extraction (.png, .jpg, .webp, .bmp) with Pillow and explicit `OCR_NOT_AVAILABLE` status flagging.
  - Rejection of unsupported binary and executable files with `extraction_status = "UNSUPPORTED_FORMAT"`.
- **Automated Hardening Test Suite (`tests/test_stage2_research_hardening_regression.py`):**
  - 11 comprehensive regression tests covering document parsing, DNS rebinding, redirect hops, ASIN extraction, and syndicated copy suppression (100% pass rate).
- **Multi-Domain Empirical Validation (`scripts/validate_stage2_domains.py`):**
  - Validated live research execution across all 7 core domains: Shopping, Technology, Programming, Gaming, News, Comparison, General Knowledge.

---

## [2.1.0] - 2026-11-03
### Universal Research, Live Knowledge & Intelligence Engine

#### Added
- **Universal Research Subsystem (`core/research/`):** Central cognitive research engine coordinating intent classification, search adapters, page/document extraction, claim verification, conflict resolution, Nemotron reasoning, and SQLite persistence.
- **Source Registry & Quality Directory (`core/research/source_registry.py`):** Authoritative classification of 100+ domains across 9 tiers (Government, Docs, Manufacturer, Retailer, News, Tech, Academic, Forums, Unverified) with India-first regional prioritization.
- **Zero-Cost Open Web Search Adapters (`core/research/search_adapters/`):**
  - `DuckDuckGoSearchAdapter`: Zero-credential web search resolving target URLs by unquoting `uddg=` redirect links.
  - `RSSSearchAdapter`: Live news feed ingestion prioritizing Indian news outlets (`thehindu.com`, `ndtv.com`) and tech feeds.
  - `BrowserSearchAdapter`: Chrome DevTools Protocol (CDP) client extracting open browser tab context.
  - `SearchManager`: Multi-query expansion (India retail keywords) and cross-adapter URL deduplication.
- **Deep Page & Local Document Extractors (`core/research/page_extractor.py`, `core/research/document_extractor.py`):**
  - Rate-limited, sandboxed HTML parser extracting text, INR prices (`₹`), stock availability, and hardware specifications.
  - Reader for user-provided files (.txt, .md, .csv, .json, .pdf) with SHA-256 provenance hashes.
- **Evidence Verification & Conflict Resolution Engine (`core/research/source_verifier.py`, `core/research/claim_extractor.py`):**
  - Atomic claim extraction with metric attribution.
  - Automatic cross-source contradiction detection and resolution by authority score difference.
- **Verifiable Citation Generator (`core/research/evidence_manager.py`):**
  - Formats numbered citations (`[1]`, `[2]`) pointing strictly to real retrieved URLs.
- **Research Freshness & Expiry Engine (`core/research/freshness_manager.py`):**
  - Domain-specific TTL policies (prices: 24h, stock: 1h, news: 2h, patches: 7d, specs: 30d, concepts: 365d).
- **Research Security & SSRF Protection (`core/research/research_security.py`):**
  - Prompt injection neutralization (`[BLOCKED_INSTRUCTION]`).
  - Strict SSRF protection blocking loopback (`127.0.0.1`, `localhost`), private RFC1918 subnets, and cloud metadata (`169.254.169.254`).
- **Research SQLite Database (`core/research/research_memory.py`):**
  - Unified storage inside `memory/jarvis_memory.db` across 6 indexed tables (`research_sessions`, `research_sources`, `research_evidence`, `research_products`, `research_prices`, `research_user_preferences`).
- **Interactive PyQt6 Research Panel (`ui/panels/research_panel.py`):**
  - Dedicated desktop research HUD accessible via `Ctrl+Shift+R` and Command Palette (`Ctrl+K`).
- **Automated Regression Suite (`tests/test_research_engine_regression.py`):**
  - 20 unit and integration tests verifying all research subsystems (100% pass rate).

---

## [2.0.5] - 2026-11-03
### Critical Incident Repair: NVIDIA Model Overwrite, Request Timeouts & Stuck WAITING_FOR_NVIDIA State

#### Fixed & Stabilized
- **Authoritative Provider Settings Sync (`core/ai/provider_settings.py`, `core/ai/provider_manager.py`):**
  - Eliminated silent reversion to `nvidia/nemotron-3.5-super-vl-120b-a12b` (30s timeout, 3 retries) caused by hardcoded defaults in `provider_settings.py`.
  - Harmonized defaults across `config.py`, environment variables, and `ProviderSettingsManager` to canonically use `nvidia/nemotron-3.5-bolt-e4b` (15s read timeout, 1 retry).
  - Added runtime diagnostics method `ProviderManager.get_diagnostics()` reporting active model and timeout properties without exposing API keys.
- **Total Request Deadline & Stream Resource Cleanup (`core/ai/providers/nvidia_provider.py`):**
  - Enforced cumulative hard deadline `deadline = time.time() + self.timeout` across both synchronous generation and streaming chunk iterations, preventing indefinitely hung streams on keep-alive packets.
  - Guaranteed response stream socket closure (`resp.close()`) in strict `finally:` blocks.
- **Decoupled Cancellation & UI Terminal Transitions (`core/jarvis_runtime.py`):**
  - Removed false pre-dispatch cancellation caused by checking `self.tts_manager._interrupt_event.is_set()` and `self._active_utterance_id != uid` in worker threads.
  - Resolved persistent `WAITING_FOR_NVIDIA` UI hang (> 10 mins) by enclosing all AI request dispatch within `try ... finally` blocks guaranteeing terminal transitions to `STANDBY` or `SLEEPING`.
- **Anti-Hallucination Regex Tokenization (`core/transcript_validator.py`, `core/jarvis_runtime.py`):**
  - Fixed tokenizer bug where comma-separated wake words (`Santra,Santra...`) bypassed split-whitespace checks; implemented `re.findall(r'[a-zA-Z0-9]+', text)` to eliminate 75x wake-word loops.
  - Hardened input gate in worker thread to drop low-information fragments (`And else.`, `Or else.`) before dispatching to AI.

#### Added
- **Incident Recovery Regression Test Suite (`tests/test_incident_recovery_regression.py`):** 22 unit and integration tests verifying provider configuration sync, cumulative deadlines, cancellation decoupling, guaranteed UI status resets, and anti-hallucination suppression. All 22 tests passing at 100%.

---

## [2.0.4] - 2026-11-03
### Master Engineering Stage 4: Single Operation Master Latency, AI Processing & STT Repair

#### Added
- **Master Latency & STT Regression Suite (`tests/test_latency_and_stt_regression.py`):** 15 unit/integration tests verifying anti-hallucination STT filters, zero-delay routing (< 10ms), truthful timeout attribution, prompt cancellation pass-through, reasoning markdown stripping, and fine-grained UI state transitions.
- **Granular Pipeline State Machine (`ui/state_machine.py`, `core/jarvis_runtime.py`, `ui/main_window.py`):** Introduced transparent latency stages: `VALIDATING_INPUT`, `ROUTING`, `WAITING_FOR_NVIDIA`, `GENERATING_RESPONSE`, `STREAMING_RESPONSE`, `COMPLETED`, `CANCELLED`, `TIMED_OUT` with distinct HUD visual themes.
- **Whisper Hallucination Suppression Filters (`core/transcript_validator.py`, `core/transcriber.py`):** Multi-factor rejection for repetitive wake-word loops (e.g. 75x "Santra"), decoder `compression_ratio > 2.4` threshold enforcement, low-info prepositional fragments ("And else."), and pure wake-word addresses ("Santra", "Hey Santra").

#### Optimized & Fixed
- **NVIDIA NIM Model & TTFT Overhaul (`config.json`, `config.py`, `.env`, `core/ai/providers/nvidia_provider.py`):**
  - Upgraded default model from queued 120B VLM (`nvidia/nemotron-3.5-super-vl-120b-a12b`, TTFT: 35.3s) to high-speed dense model (`nvidia/nemotron-3.5-bolt-e4b`, TTFT: 744ms), achieving a **47.4x TTFT acceleration**.
  - Implemented split timeouts (4.0s connection, 15.0s read) and capped retries to 1 for transient 429/5xx only, eliminating 75s-116s thread lockups.
  - Implemented clean thought/reasoning extraction (`<thought>...</thought>` and `Here's a thinking process:` markdown stripped).
- **Truthful Error Attribution (`core/ai/agent_brain.py`):**
  - Replaced misleading generic error message ("verify credentials and network connection") with accurate root cause reporting based on provider error codes (`AI_PROVIDER_TIMEOUT`, `CANCELLED`, `RATE_LIMITED`, `CREDENTIALS_INVALID`).
- **Dynamic Tool Payload Stripping (`core/ai/agent_brain.py`, `core/conversation_manager.py`):**
  - Added `include_tools: bool` parameter. Omitted all 95 tool descriptions for conversational chat queries, reducing prompt payload by **85%** (from 5.4 KB to ~800 bytes).
- **Zero-Delay Educational Query Routing (`core/ai/intelligence_router.py`):**
  - Routed informational explanation queries ("Explain quicksort in detail.") directly to Layer 2 Streaming Conversation in 4.5ms rather than Layer 3 OS automation.

---

## [2.0.3] - 2026-11-03
### Master Engineering Stage 3: Consolidated Runtime Stability & Concurrency Hardening

#### Added
- **Master Stability Regression Suite (`tests/test_runtime_stability_regression.py`):** 17 comprehensive unit/integration/stress tests covering Groups A through F (Deduplication, Sleep Mode, Interruption, State Transitions, Audio Watchdog, UI Panels, and Concurrency Stress).
- **Idempotent Turn Lifecycle & In-Place UI Updates (`ui/main_window.py`):** Keyed conversation cards (`turn_id`) and in-place streaming card body updates (`_add_or_update_turn`, `_update_card_body`), suppressing transient query notifications from creating redundant chat bubbles.
- **Sleep Cooperative Cancellation:** Explicit `_sleep_cancel_event` and `_cancelled_utterance_ids` tracking in `core/jarvis_runtime.py`, ensuring pending Nemotron workers terminate cleanly without speaking late answers in sleep mode.
- **Instant Explanation Continuation Engine (`core/conversation_manager.py`):** Immediate 0.5ms resume of paused explanations from preserved sentence buffers upon saying `"continue"`, eliminating remote API round-trips and duplicate reasoning calls.

#### Fixed
- **Project Intelligence Panel Crash (`ui/panels/project_intelligence_panel.py`):** Repaired `AttributeError: 'ProjectIntelligencePanel' object has no attribute 'content_widget'` by instantiating `self.content_widget = QWidget(self)` and attaching layout.
- **TTS Lock Deadlock & Interrupt Revivals (`core/tts/tts_manager.py`):** Converted `self._lock` from `threading.Lock()` to `threading.RLock()`. Prevented stream chunk enqueue from un-cancelling interrupted generations and enforced strict sleep speech rejection.
- **Illegal State Transitions (`core/jarvis_runtime.py`):** Guarded `_on_speaker_started()` against setting `SPEAKING` during `SLEEPING` or `STOPPED`. Expanded `LEGAL_TRANSITIONS["SPEAKING"]` to permit barge-in transitions (`TRANSCRIBING`, `PROCESSING`, `UNDERSTANDING`, `THINKING`, `EXECUTING`).
- **Audio Watchdog Premature Recoveries (`core/listener.py`):** Increased sustained zero-frame threshold from 60 to 300 (~10s) with callback activity verification, preventing false stream restarts in quiet rooms.
- **Wake-Word & Utterance Capture Overlap (`core/listener.py`):** Gated audio chunk dispatch to wake-word consumers to only feed frames when utterance speech recording is inactive (`not self._recording or self._sleep_mode`).
- **Whisper Model Unload Race (`core/transcriber.py`):** Synchronized `unload_model()` with active `transcribe()` inference using `_active_transcriptions` counter.

---

## [2.0.2] - 2026-11-02
### Master Engineering Stage 2: Unified Intelligence Routing & Execution Integration

#### Added
- **Unified Routing Authority (`core/ai/intelligence_router.py`):** Established single authoritative classification contract (`LAYER_1` Fast Local, `LAYER_2` Contextual Memory, `LAYER_3` Nemotron Cloud Reasoning).
- **Explicit AI_MODE Engine:** Added global `ai_mode` toggle state machine in `core/jarvis_runtime.py`, voice commands (`"switch to AI mode"`, `"exit AI mode"`, `"ask Nemotron"`), and live UI badge indicator (`✦ AI MODE` / `● NORMAL MODE`).
- **Decoupled Educational Topic Retention (`core/conversation_manager.py`):** Added `active_educational_topic` maintaining technical topics across intervening local commands, plus expanded follow-up patterns (`"give another example"`, `"make it simpler"`, `"compare both"`, `"in C++"`).
- **Dynamic Command Palette Execution (`ui/panels/command_palette_dialog.py`):** Mapped all 30 tool cards to safe executable phrases via `TOOL_DISPATCH_PHRASES` and connected `on_command_submit` in `ui/main_window.py`. Added dynamic lifecycle status evaluation (`READY`, `BLOCKED`, `UNVERIFIED`).
- **Stage 2 Regression Test Suite (`tests/test_stage2_unified_routing_regression.py`):** Added 18 dependency-free unit/integration tests running under Python 3.14 standard library `unittest`.

#### Fixed
- **Conversational Prefix Routing (`core/command_normalizer.py`):** Stripped leading affirmative conversational tokens (`"Yes, open Chrome"`, `"Sure, open Notepad"`, `"Please open Downloads"`) without invoking cloud LLM loops.
- **Critical Power Safety Confirmation Gate:** Normalized `"put the computer into sleep mode"` to `sleep computer` with mandatory confirmation gate (`pending_confirmation = True`).
- **Negation & Cancellation Suppression:** Handled negative requests (`"No, don't open Chrome"`, `"don't open Chrome"`) and cancellations (`"No, cancel that"`, `"Actually, don't do it"`) via fast local suppression without opening target applications.
- **Provider Telemetry Truthfulness (`core/jarvis_runtime.py`):** Eradicated `f"N/A ({stage_source})"`, replacing it with live operational states (`LOCAL EXECUTION`, `NVIDIA NEMOTRON — REQUESTING`, `NVIDIA NEMOTRON — PROCESSING`, `NVIDIA NEMOTRON — RESPONSE RECEIVED`, `PROVIDER UNAVAILABLE`).
- **ReAct Internal Trace Stripping (`core/speech_sanitizer.py`):** Filtered raw ReAct thought/action structures (`Thought: ... Action: ... Final Answer: ...`) from speech synthesis and display.
- **Speech Channel Separation (`ui/main_window.py`):** Restricted `Transcribing: "..."` captioning strictly to incoming microphone transcription from Whisper.

---

## [2.0.1] - 2026-11-02
### Master Engineering Stage 1: Architecture Audit & Intelligence Blueprint

#### Audited & Documented
- **System Architecture Baseline:** Completed comprehensive forensic audit across all 95 tool capabilities, routing engines, memory layers, and UI Automation services ([`SANTRA_STAGE_1_AUDIT_REPORT.md`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_STAGE_1_AUDIT_REPORT.md)).
- **System Architecture Blueprint:** Authored authoritative specification covering 3-Layer Intelligence Routing, Unified 5-Tier Memory, Desktop Perception, and the Interaction State Machine ([`SANTRA_ARCHITECTURE.md`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/SANTRA_ARCHITECTURE.md)).
- **Project Backlog:** Formulated prioritized implementation backlog across Stages 2 through 5 ([`BACKLOG.md`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/BACKLOG.md)).

#### Fixed (Pre-Stage 1 Baseline Hardening)
- **Silent TTS Playback Bug:** Resolved job ID string inequality check (`'722320_0'` vs `'722320'`) in [`core/tts/tts_manager.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/tts/tts_manager.py) that prematurely skipped streamed sentences. Verified physical multi-sentence playback on Noise Buds N1 Pro and Realtek speakers.
- **Git User Identity Configuration:** Remediated misspelled `usern.name` / `usern.email` entries globally and locally to restore clean Git operational status without IDE warning popups.
- **Premature Speaking UI State:** Updated [`core/jarvis_runtime.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/jarvis_runtime.py) so `SPEAKING` state triggers exclusively when audio playback stream physically starts, avoiding phantom animations while synthesizing.
- **Output Audio Device Resolution:** Added `resolve_audio_output_device()` in [`core/audio_device_resolver.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/audio_device_resolver.py) and wired target `device=` into `sounddevice.play()`.

---

## [2.0.0] - 2026-11-01
### Iterations 16–20: UI Redesign & Platform Hardening

#### Added
- **Modern PyQt6 UI:** Replaced low-contrast holographic UI with high-contrast slate-dark responsive desktop interface (`#0d1117`).
- **Command Palette (`Ctrl+K`):** Integrated 40-item capability launcher and system hub dialog.
- **NVIDIA Nemotron Super VL Integration:** Cloud reasoning backend integrated via OpenAI-compatible endpoints with bounded retries and timeout guards.
- **Desktop Context Perception:** Integrated Windows UI Automation for discovering active edit controls, document editors, and prompt boxes.

#### Fixed
- **Process Exit Code 3221226505:** Eliminated unsafe background C-extension crashes during audio device polling.
- **Audio Hot-Swap Stream Recovery:** Built automatic stream recovery and resampler reinitialization upon USB/Bluetooth headphone disconnection.
- **Indian Accent Wake-Word Adaptation:** Tuned phonetic normalizer and acoustic models to reliably trigger on `"Santra"`, `"Samtra"`, and `"Suntra"`.

---

## [1.0.0] - Historical Baseline
- Initial voice assistant release with Whisper STT, pyttsx3 TTS, local app launcher, and simple intent parsing.

