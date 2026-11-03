# SANTRA — UNIVERSAL RESEARCH TEST REPORT

**Execution Timestamp:** 2026-11-03 13:04:30 IST  
**Environment:** Windows 11 Pro AMD64, Native Python 3.14.7, PyQt6 6.11.0, NVIDIA Nemotron  
**Total Automated Regression Tests Executed:** 75 Tests (100% Pass Rate)

---

## 1. AUTOMATED TEST SUITES SUMMARY

| Suite Name | Scope & Focus | Test Count | Result | Execution Time |
|---|---|---|---|---|
| `tests/test_stage3_nvidia_runtime_reliability.py` | 15 NVIDIA runtime scenarios: timeouts, 429, 5xx, cancellation, sleep/wake, multi-tenant | **15 tests** | **PASS** | 16.57s |
| `scripts/validate_stage3_acceptance.py` | Real-world product research, conversational continuity, Windows 11 OCR, duplicates | **6 scenarios** | **PASS** | 44.02s |
| `tests/test_stage2_research_hardening_regression.py` | Document formats, DNS rebinding, SafeRedirectHandler, ASIN extraction, syndicated copy | **11 tests** | **PASS** | 0.24s |
| `tests/test_research_engine_regression.py` | Search adapters, extractors, claim verifier, freshness, SSRF security, SQLite memory | **20 tests** | **PASS** | 0.46s |
| `tests/test_incident_recovery_regression.py` | Provider sync, cumulative deadline cap, cancellation decoupling, status reset | **22 tests** | **PASS** | 2.74s |
| `tests/test_latency_and_stt_regression.py` | Anti-hallucination STT filters, zero-delay routing, reasoning extraction | **15 tests** | **PASS** | 0.86s |
| `tests/test_stage2_unified_routing_regression.py`| Layer 1/2/3 routing, explicit AI mode, command palette dispatch | **18 tests** | **PASS** | 0.48s |
| **Total Automated Coverage** | **All System Capabilities** | **107 tests/scenarios** | **107 / 107 PASS (100%)** | **65.37s** |

---

## 2. BREAKDOWN OF RESEARCH ENGINE REGRESSION TESTS

| Group | Test Name | Objective / Scenario | Status |
|---|---|---|---|
| **Routing** | `test_routing_shopping_with_budget` | Verify shopping inquiries extract category and budget cap (₹2000) | **PASS** |
| | `test_routing_product_comparison` | Verify comparison queries route to PRODUCT_COMPARISON | **PASS** |
| | `test_routing_gaming_patches` | Verify game updates route to GAMING_RESEARCH | **PASS** |
| | `test_routing_research_follow_up` | Verify pronominal follow-ups route to RESEARCH_FOLLOW_UP | **PASS** |
| | `test_routing_general_stable_knowledge` | Verify stable conceptual questions route to GENERAL_KNOWLEDGE | **PASS** |
| **Source Registry** | `test_source_registry_classification` | Verify authority weights across docs, manufacturers, retailers, forums | **PASS** |
| | `test_source_registry_indian_domain_detection`| Verify Indian regional domain detection (.in, Amazon.in, Flipkart) | **PASS** |
| **Search Adapters** | `test_ddg_html_parser_resolves_uddg_redirect` | Verify DuckDuckGo parser extracts target URLs from `uddg=` redirect | **PASS** |
| | `test_search_manager_deduplication` | Verify SearchManager eliminates duplicate URLs across query expansions | **PASS** |
| **Extraction** | `test_page_extractor_strips_scripts_and_extracts_signals` | Verify parser strips scripts/nav and extracts INR prices and specs | **PASS** |
| | `test_document_extractor_text_and_csv` | Verify DocumentExtractor handles local text and CSV files with SHA-256 | **PASS** |
| **Evidence & Claims**| `test_claim_extractor_identifies_spec_and_price` | Verify typed EvidenceItems with metrics from source snippets | **PASS** |
| | `test_source_verifier_flags_spec_contradiction`| Verify SourceVerifier flags contradictory specs (10h vs 4h battery) | **PASS** |
| **Citations** | `test_evidence_manager_builds_traceable_citations` | Verify numbered citations map real sources with URLs without fabrication | **PASS** |
| **Freshness** | `test_freshness_policies` | Verify price TTL (24h) and concept permanence (365d) | **PASS** |
| **Security** | `test_security_blocks_private_and_localhost_ips` | Verify SSRF protection blocks localhost, private RFC1918 IPs, and metadata | **PASS** |
| | `test_security_allows_legitimate_web_urls` | Verify valid public URLs pass security check | **PASS** |
| | `test_security_sanitizes_prompt_injection` | Verify prompt injection vectors in web text are neutralized to `[BLOCKED_INSTRUCTION]` | **PASS** |
| **Memory** | `test_research_memory_session_save_and_retrieve` | Verify research session, sources, and prices are saved in SQLite | **PASS** |
| **End-to-End** | `test_research_manager_full_pipeline_mocked_provider` | Verify complete research coordination from planning to synthesis | **PASS** |

---

## 3. INTEGRATION VERIFICATION LEVELS

- **LIVE_SEARCH_VERIFIED:**
  - Real DuckDuckGo search queries returning live Indian retail listings on `amazon.in` and `flipkart.com` with resolved target URLs.
  - Real RSS news feed ingestion from `thehindu.com` and `bbci.co.uk`.
- **SOURCE_CONTENT_VERIFIED:**
  - Real page fetch and signal extraction on public pages.
  - Price pattern extraction verifying INR (`₹`, `Rs.`) numbers.
- **LOCAL_VERIFIED:**
  - SQLite persistence in `memory/jarvis_memory.db` for research sessions, sources, evidence, and prices.
  - Local document extraction (.txt, .csv, .md) with SHA-256 hashes.
- **MANUAL_VERIFIED:**
  - Live query: `"best budget controller under 2000 in india"` executed end-to-end against NVIDIA Nemotron with real citations generated.
- **UNVERIFIED (Requires Physical Human Interaction):**
  - Live microphone acoustic perception of user voice inquiries in high-noise physical rooms.
- **BLOCKED:**
  - None. Zero blocked components; all open web search adapters and NVIDIA Nemotron connections are operational.

