# SANTRA — ENGINEERING BACKLOG & ROADMAP
## Prioritized Work Items, Architectural Enhancements & Acceptance Criteria

**Project:** SANTRA  
**Platform:** Windows 11 / Ubuntu  
**Baseline:** Post-Stage 1 Audit Baseline  
**Date:** November 3, 2026  

---

## UNIVERSAL RESEARCH ENGINE STAGE 4 — PRODUCTION VERIFICATION, SOAK & READINESS [COMPLETED]

### Status: Complete (Verified via `tests/test_stage4_production_verification.py` — 15/15 Pass; Full Regression Suite — 46/46 Pass; Total 61/61 Pass; 100-Cycle Soak Test Pass)

#### Item RES-STAGE4-1: Hardened NVIDIA Read Timeout Upper Ceiling [COMPLETED]
- **Delivered:** Fixed `_get_timeout_tuple()` in `core/ai/providers/nvidia_provider.py` enforcing `min(15.0, max(5.0, self.timeout))` so custom caller timeouts cannot exceed the 15.0s fail-fast ceiling.
- **Verification:** `test_01_timeout_upper_ceiling_enforced` verified clamping from 60s to 15s.

#### Item RES-STAGE4-2: Cancellation Stream Suppression & Memory Cleanup [COMPLETED]
- **Delivered:** Hardened `core/conversation_manager.py` to discard in-flight streamed buffers upon barge-in or sleep cancellation, returning empty text and preventing partial turns from leaking into SQLite episodic memory.
- **Verification:** `test_04_cancelled_conversation_suppresses_history_and_persistence` verified 0 assistant turns appended.

#### Item RES-STAGE4-3: Advanced SSRF Alternative Numeric IP Protection [COMPLETED]
- **Delivered:** Extended `core/research/research_security.py` to block integer IPs (`http://2130706433/`), hex IPs (`http://0x7f000001/`), IPv4-mapped IPv6, and link-local ranges.
- **Verification:** Tests `test_05_ssrf_blocks_integer_ip_representation` through `test_08_ssrf_blocks_ipv6_link_local` pass.

#### Item RES-STAGE4-4: ZIP Bomb Defense & Structured Table Extraction [COMPLETED]
- **Delivered:** Enforced 25 MB uncompressed byte ceiling on XML document parsing in `core/research/document_extractor.py`. Added table grid extraction for DOCX and multi-sheet cell extraction for XLSX.
- **Verification:** Tests `test_09_zip_bomb_protection_aborts_excessive_decompressed_payload` and `test_10_docx_table_structure_extraction` pass.

#### Item RES-STAGE4-5: 100-Cycle Concurrency & Soak Test Verification [COMPLETED]
- **Delivered:** Created and ran `scripts/stage4_soak_test.py` across 100 continuous research, conversational, memory, and sleep/wake cycles.
- **Verification:** Verified 0 thread leaks (7 threads constant), memory bounded under 70 MB, P50 latency 14.19 ms, and 100% database record preservation (3,055 records in 19 tables).

---

## UNIVERSAL RESEARCH ENGINE STAGE 3 — QUALITY, CONTINUITY & ACCEPTANCE [COMPLETED]

### Status: Complete (Verified via `tests/test_stage3_nvidia_runtime_reliability.py` — 15/15 Pass; `scripts/validate_stage3_acceptance.py` — 6/6 Pass; 52/52 Total Regression Pass)

#### Item RES-STAGE3-1: Complete NVIDIA Runtime Reliability & Failure Injection Suite [COMPLETED]
- **Delivered:** Created `tests/test_stage3_nvidia_runtime_reliability.py` testing 15 comprehensive lifecycle scenarios (connect/read timeouts, 429 backoff, 5xx retry, invalid payloads, stream disconnects, user cancellation, sleep transition, wake token isolation, simultaneous workers).
- **Verification:** 15/15 scenarios passing with 100% test coverage.

#### Item RES-STAGE3-2: Zero-Dependency Local Offline OCR Engine [COMPLETED]
- **Delivered:** Integrated Windows 11 `Windows.Media.Ocr` via PowerShell in `core/vision/ocr_engine.py` and `core/research/document_extractor.py`. Added in-memory SHA-256 duplicate file detection and text vs scanned PDF detection.
- **Verification:** Physical synthetic invoice OCR extracted in 1.4s offline with 0 cloud dependencies. Duplicate image detected and bypassed in 0.1ms.

#### Item RES-STAGE3-3: Enriched Product Entity Schema & Concrete Verification Tiers [COMPLETED]
- **Delivered:** Added `recommendation_tier` (`Best Overall`, `Best Budget`, `Best Specifications`, `Best Value`, `Best Compatibility`), dual price lineage (`search_result_price` vs `product_page_price`), mandatory `disadvantages` extraction, and detailed specs (Hall Effect sticks, 1000Hz polling rate, RTX GPUs).
- **Verification:** Controller and laptop scenarios validated in `scripts/validate_stage3_acceptance.py`.

#### Item RES-STAGE3-4: Conversational Continuity Across Intervening Local Commands [COMPLETED]
- **Delivered:** Hardened `ResearchRouter` and `ResearchManager` to preserve active research sessions across local OS actions (e.g. volume control). Added pronoun resolution, budget shifting, price freshness re-checks, and SQLite rehydration across reboots.
- **Verification:** Multi-turn conversational flow validated in `scripts/validate_stage3_acceptance.py`.

---

## UNIVERSAL RESEARCH ENGINE STAGE 2 — HARDENING & MULTI-DOMAIN VALIDATION [COMPLETED]

### Status: Complete (Verified via Regression Suite `tests/test_stage2_research_hardening_regression.py` — 11/11 Pass; 86/86 Hardening Total Pass)

#### Item RES-STAGE2-1: NVIDIA Model Identity Forensics & Cache Manager Repair [COMPLETED]
- **Delivered:** Identified and eliminated lingering defaults in `core/ai/caching/cache_manager.py` referencing `nvidia/nemotron-3.5-super-vl-120b-a12b`. Harmonized caching layer to `nvidia/nemotron-3.5-bolt-e4b`.
- **Verification:** Verified zero references to 120b in codebase; live smoke test passed in 1.93s.

#### Item RES-STAGE2-2: DNS Rebinding & Safe Redirect Defense [COMPLETED]
- **Delivered:** Added `_verify_dns_resolution` to `core/research/research_security.py` resolving hostnames to IPs before connection to block DNS rebinding to local/private/cloud IPs. Implemented `SafeRedirectHandler` in `page_extractor.py` capping hops to 3 and verifying every destination.
- **Verification:** Regression tests `test_security_dns_rebinding_prevention`, `test_safe_redirect_handler_blocks_ssrf_hop`, `test_safe_redirect_handler_max_hops` pass.

#### Item RES-STAGE2-3: Truthful E-Commerce Bot Classification & Product Schema [COMPLETED]
- **Delivered:** Added `PriceType` enum and expanded `ProductEntity` (ASIN, variant, seller, warranty, extraction_status). Handled Amazon/Flipkart bot detection (HTTP 503) truthfully as `PARTIAL_SNIPPET` and `PriceType.SEARCH_RESULT_PRICE`.
- **Verification:** Regression test `test_product_entity_extraction_and_price_type` passes; shopping domain validation verified.

#### Item RES-STAGE2-4: Syndicated Wire Copy Detection & Authoritative Sources [COMPLETED]
- **Delivered:** Added `_detect_syndicated_copy` in `source_verifier.py` discounting repeated text excerpts (>= 40 chars) across domains. Added `VERIFIED_BY_PRIMARY_SOURCE` for official documentation.
- **Verification:** Regression tests `test_source_verifier_syndicated_copy_detection` and `test_source_verifier_primary_source_verification` pass.

#### Item RES-STAGE2-5: Multi-Format Document Knowledge Extraction [COMPLETED]
- **Delivered:** Added `.docx` and `.xlsx` safe XML parsing and image metadata extraction with OCR required status flagging in `document_extractor.py`.
- **Verification:** Regression tests `test_document_extractor_docx`, `test_document_extractor_xlsx`, `test_document_extractor_image_metadata`, `test_document_extractor_unsupported_format` pass.

#### Item RES-STAGE2-6: Seven-Domain Empirical Validation [COMPLETED]
- **Delivered:** Validated Shopping, Technology, Programming, Gaming, News, Comparison, and General Knowledge via `scripts/validate_stage2_domains.py`.
- **Verification:** 100% of queries completed; results written to `stage2_domain_validation_results.json`.

---

## UNIVERSAL RESEARCH & LIVE INTELLIGENCE ENGINE [COMPLETED]

### Status: Complete (Verified via Regression Suite `tests/test_research_engine_regression.py` — 20/20 Pass; 75/75 Total Pass)

#### Item RES-1: Open Web Search Adapters & Redirect Unquoting [COMPLETED]
- **Delivered:** `core/research/search_adapters/` featuring zero-cost `DuckDuckGoSearchAdapter` (resolving target URLs from `uddg=` redirect params), `RSSSearchAdapter` (Indian news & tech feeds), and `BrowserSearchAdapter` (CDP client).
- **Verification:** Unit tests `test_ddg_html_parser_resolves_uddg_redirect` and `test_search_manager_deduplication` pass.

#### Item RES-2: Source Registry, Authority Scoring & Indian Prioritization [COMPLETED]
- **Delivered:** `core/research/source_registry.py` classifying 100+ domains into 9 tiers with authority scores (0.35 to 1.0) and Indian regional relevance tagging (`.in`, Amazon.in, Flipkart, Croma, Reliance Digital).
- **Verification:** Unit tests `test_source_registry_classification` and `test_source_registry_indian_domain_detection` pass.

#### Item RES-3: Deep Page & Local Document Extraction [COMPLETED]
- **Delivered:** `core/research/page_extractor.py` and `core/research/document_extractor.py` extracting clean text, INR prices, stock availability, and specs from web pages and local files (.txt, .md, .csv, .json, .pdf) with SHA-256 provenance hashes.
- **Verification:** Unit tests `test_page_extractor_strips_scripts_and_extracts_signals` and `test_document_extractor_text_and_csv` pass.

#### Item RES-4: Claim Extraction, Contradiction Detection & Citations [COMPLETED]
- **Delivered:** `core/research/claim_extractor.py`, `core/research/source_verifier.py`, and `core/research/evidence_manager.py` extracting atomic claims, detecting specification contradictions, resolving conflicts by authority, and generating traceable numbered citations (`[1]`, `[2]`).
- **Verification:** Unit tests `test_claim_extractor_identifies_spec_and_price`, `test_source_verifier_flags_spec_contradiction`, `test_evidence_manager_builds_traceable_citations` pass.

#### Item RES-5: SQLite Knowledge Database & Freshness TTL Policies [COMPLETED]
- **Delivered:** `core/research/research_memory.py` persisting sessions, sources, evidence, products, and prices inside `memory/jarvis_memory.db` with indexed tables. `core/research/freshness_manager.py` enforcing domain TTLs (prices: 24h, stock: 1h, news: 2h, patches: 7d, specs: 30d, concepts: 365d).
- **Verification:** Unit tests `test_freshness_policies` and `test_research_memory_session_save_and_retrieve` pass.

#### Item RES-6: SSRF Protection & Prompt Injection Defense [COMPLETED]
- **Delivered:** `core/research/research_security.py` blocking loopback, private RFC1918 IPs, and cloud metadata (`169.254.169.254`). Prompt injection vectors sanitized to `[BLOCKED_INSTRUCTION]`. Read-only research permissions decoupled from transactional purchase execution.
- **Verification:** Unit tests `test_security_blocks_private_and_localhost_ips`, `test_security_allows_legitimate_web_urls`, `test_security_sanitizes_prompt_injection` pass.

#### Item RES-7: PyQt6 Desktop Research Panel & Shortcuts [COMPLETED]
- **Delivered:** `ui/panels/research_panel.py` interactive HUD with live stage progress, evidence viewer, and citations. Integrated with `Ctrl+Shift+R` and Command Palette (`Ctrl+K`).
- **Verification:** End-to-end integration test `test_research_manager_full_pipeline_mocked_provider` passes.

---

## CRITICAL INCIDENT REPAIR — NVIDIA MODEL CONFIGURATION & STUCK WAITING STATE [COMPLETED]

### Status: Complete (Verified via Regression Suite `tests/test_incident_recovery_regression.py` — 22/22 Pass)

#### Item INC-1: Provider Configuration Hierarchy & Silent 120b Overwrite [COMPLETED]
- **Delivered:** Repaired `core/ai/provider_settings.py` where hardcoded dictionary reset `ProviderManager` to `nvidia/nemotron-3.5-super-vl-120b-a12b` and 30.0s timeout. Harmonized defaults across `config.py`, environment variables, and settings manager to `nvidia/nemotron-3.5-bolt-e4b` (15s read timeout, 1 retry). Added non-leaking diagnostic telemetry `ProviderManager.get_diagnostics()`.
- **Verification:** Unit tests `test_provider_settings_default_bolt`, `test_provider_manager_syncs_bolt_model`, `test_provider_manager_diagnostics` pass.

#### Item INC-2: Total Request Deadline & Stream Socket Management [COMPLETED]
- **Delivered:** Implemented cumulative deadline (`time.time() + self.timeout`) in `core/ai/providers/nvidia_provider.py` for both synchronous generation and streaming chunk iterations. Enforced guaranteed `resp.close()` in `finally:` blocks to prevent socket exhaustion and lingering threads.
- **Verification:** `test_total_deadline_enforcement`, `test_stream_response_cleans_up_on_error` pass.

#### Item INC-3: Cancellation Decoupling & UI Terminal State Cleanup [COMPLETED]
- **Delivered:** Decoupled `_check_cancelled()` from `self.tts_manager._interrupt_event` and transient ambient acoustic IDs. Fixed persistent `WAITING_FOR_NVIDIA` UI hang (> 10 mins) by enclosing Case 5 AI worker execution in `try ... finally`, guaranteeing transition to `STANDBY` or `SLEEPING`.
- **Verification:** `test_check_cancelled_not_triggered_by_tts_interrupt`, `test_runtime_status_cleared_on_cancellation`, `test_runtime_status_cleared_on_stream_failure` pass.

#### Item INC-4: STT Anti-Hallucination & Tokenizer Hardening [COMPLETED]
- **Delivered:** Replaced whitespace-only splitting with `re.findall(r'[a-zA-Z0-9]+', text)` in `core/transcript_validator.py`. Repetitive wake-word loops (75x "Santra", comma-separated, dot-separated) are rejected as `REPETITIVE_HALLUCINATION`. Prepositional fragments (`"And else."`, `"Or else."`) rejected as `FRAGMENT`.
- **Verification:** `test_repetitive_wake_words_comma_separated`, `test_sentence_fragment_and_else`, `test_worker_discards_invalid_hallucination` pass.

---

## STAGE 2 — INTELLIGENT ROUTING & ROUTER CONSOLIDATION [COMPLETED]

### Status: Complete (Verified via Regression Suite `tests/test_stage2_unified_routing_regression.py` — 18/18 Pass)

#### Item 2.1: Affirmation & Conversational Prefix Normalization [COMPLETED]
- **Delivered:** Safe leading affirmative token stripping (`yes`, `yeah`, `sure`, `please`, `okay`, `santra`). Standalone affirmations preserved for safety gates. Power commands (`"Yes, put the computer into sleep mode"`) normalize to `sleep computer` with mandatory confirmation gate. Negations (`"No, don't open Chrome"`) and cancellations (`"No, cancel that"`) handled via suppression intents.
- **Verification:** Unit tests `test_affirmative_local_commands`, `test_sleep_mode_confirmation_maintained`, `test_cancellations`, `test_negated_commands` all pass.

#### Item 2.2: Explicit AI Mode Toggle Architecture [COMPLETED]
- **Delivered:** `ai_mode` boolean state in `JarvisRuntime` with voice commands (`"switch to AI mode"`, `"exit AI mode"`, `"ask Nemotron"`). In AI mode, deterministic local actions run locally, while exploratory/conversational requests route to Layer 3 Nemotron. UI badge (`✦ AI MODE` / `● NORMAL MODE`) live updates.
- **Verification:** `test_ai_mode_toggle_intents`, `test_ai_mode_preserves_local_commands`, `test_ai_mode_routes_conversational_to_nemotron` pass.

#### Item 2.3: Command Palette Execution Dispatch [COMPLETED]
- **Delivered:** Connected `on_command_submit` in `MainWindow`, added dynamic capability lifecycle calculation (`READY`, `BLOCKED`, `UNVERIFIED`), mapped all 30 tool cards to safe executable phrases in `TOOL_DISPATCH_PHRASES`. Hardcoded `● READY` and `FAILED: No handler` eliminated.
- **Verification:** `test_all_30_tool_cards_have_dispatch_phrases`, `test_dynamic_lifecycle_states` pass.

#### Item 2.4: Educational Topic Retention Across OS Commands [COMPLETED]
- **Delivered:** Decoupled `active_educational_topic` from transient OS focus targets. Intervening commands (`"open Chrome"`) no longer purge the active learning topic. Expanded follow-up patterns (`"give another example"`, `"make it simpler"`, `"in C++"`) resolve accurately.
- **Verification:** `test_educational_topic_retained_across_intervening_command`, `test_expanded_followup_patterns` pass.

#### Item 2.5: Output Channel & Telemetry Safeguards [COMPLETED]
- **Delivered:** Replaced `f"N/A ({stage_source})"` with live truthful states (`LOCAL EXECUTION`, `NVIDIA NEMOTRON — REQUESTING`, `NVIDIA NEMOTRON — RESPONSE RECEIVED`, `PROVIDER UNAVAILABLE`). ReAct reasoning traces stripped in `core/speech_sanitizer.py`. Microphone transcription captioning strictly isolated to `Transcribing: "..."`.
- **Verification:** `test_react_thought_action_stripping`, `test_prose_preservation` pass.

---

## STAGE 3 — CONTEXTUAL MEMORY & COMMAND HISTORY AUDIT ENGINE

### Priority: High

#### Item 3.1: Command History Audit Service
- **User Story:** As a user, I want to ask questions about recent actions (e.g., *"What was my last command?"*, *"What was the command before that?"*, *"Did any command fail today?"*) and receive structured, factual answers based on actual execution history.
- **Tasks:**
  - Replace volatile list in [`memory/execution_history.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/memory/execution_history.py) with SQLite-backed `CommandHistoryAuditService`.
  - Store fields: `command_id`, `raw_utterance`, `normalized_cmd`, `category`, `target_app`, `status` (`SUCCEEDED`, `FAILED`, `BLOCKED`, `CANCELLED`), `start_time`, `end_time`, `result_summary`, `error_details`.
  - Implement query methods: `get_last_command()`, `get_second_last_command()`, `get_today_commands()`, `get_failed_commands()`.
- **Acceptance Criteria:**
  - User says *"Open Chrome"*, then asks *"What was my last command?"* → SANTRA replies *"Your last command was opening Chrome, which succeeded."*

#### Item 3.2: Decoupled Educational Topic Memory
- **User Story:** As a user learning a concept, I want executing a local command between questions not to erase the active educational subject.
- **Tasks:**
  - Store educational topics in `ExplanationState.active_topic` independently of `last_target`.
  - Expand regex dictionary in `resolve_pronouns_and_references` to handle:
    - `"give another example"` → `Give another code example for <topic>.`
    - `"make it simpler"` → `Explain <topic> in simpler terms for a beginner.`
    - `"compare both"` → `Compare both approaches for <topic>.`
    - `"what about its disadvantages"` → `What are the disadvantages of <topic>?`
- **Acceptance Criteria:**
  - `"Explain binary search"` → SANTRA explains → `"Open Chrome"` → Chrome opens → `"Give another example"` → SANTRA provides another binary search example.

---

## STAGE 4 — DESKTOP PERCEPTION & UNIFIED INTERACTION

### Priority: High

#### Item 4.1: Unified Perception & Workspace Interaction Consolidation
- **User Story:** As a developer, I want all desktop introspection, UI automation, and application managers consolidated into a single clean package to prevent duplicate logic.
- **Tasks:**
  - Merge redundant implementations between [`core/workspace_interaction/`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/workspace_interaction/) and [`core/interaction/`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/interaction/).
  - Ensure Windows UIA client accurately identifies Notepad documents, Antigravity chat composers, Chrome ChatGPT prompt inputs, and search fields.
- **Acceptance Criteria:**
  - Saying `"Create folder Game Prediction on Desktop and open in Antigravity"` creates the directory, opens Antigravity, and verifies workspace focus.

#### Item 4.2: ReAct Trace Filtering & Speech Channel Separation
- **User Story:** As a user listening to SANTRA, I never want internal chain-of-thought (`Thought: ... Action: ...`) read aloud or displayed as speech captions.
- **Tasks:**
  - Implement token-level ReAct delimiter sanitization in [`core/conversation_manager.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/conversation_manager.py) and [`core/speech_sanitizer.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/core/speech_sanitizer.py).
  - In [`ui/main_window.py`](file:///C:/Users/activ/OneDrive/Attachments/Desktop/jarvis/ui/main_window.py), separate incoming speech signal (`sig_transcription_updated`) from assistant speech output signal (`sig_assistant_caption_updated`).
  - Reserve `Transcribing: "..."` strictly for microphone input.
- **Acceptance Criteria:**
  - Cloud responses containing ReAct tokens speak only polished conversational text.
  - Speech caption never shows `Transcribing:` on assistant responses.

---

## STAGE 5 — LIVE DESKTOP VALIDATION & ACCEPTANCE

### Priority: Medium

#### Item 5.1: Live Scenario Acceptance Testing
- **Scenarios to verify on Windows 11 host:**
  1. Desktop project creation and Antigravity opening.
  2. Dictating text into Notepad with verified document control focus.
  3. Typing prompt into ChatGPT/Antigravity with gated confirmation.
  4. Conversational continuity test across local commands.
  5. Structured command history queries.
- **Acceptance Criteria:**
  - 100% of physical scenarios pass without crashes or trace leaks.

---

*Backlog established by Antigravity Autonomous Engineering Core.*

