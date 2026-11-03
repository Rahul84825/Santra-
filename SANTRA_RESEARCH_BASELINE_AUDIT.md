# SANTRA — UNIVERSAL RESEARCH BASELINE AUDIT
## Capability Inventory, Architectural Audit & Research Subsystem Assessment

**Date:** November 3, 2026  
**System:** SANTRA Autonomous Desktop Assistant  
**Platform:** Windows 11 AMD64 (Ubuntu Compatibility Preserved), Python 3.14.7, PyQt6  
**Auditor:** Principal AI Systems Architect & Research Infrastructure Engineer  
**Status:** AUDIT COMPLETE — BASELINE ESTABLISHED

---

## 1. EXECUTIVE SUMMARY & REPOSITORY AUDIT

Before implementing the Universal Research Engine, a systematic audit of the existing SANTRA codebase was performed. Rather than assuming capabilities from legacy reports, every component was inspected, imported, and directly executed against test queries.

The audit revealed that while SANTRA possesses foundational browser controls, local system discovery, and a prototype DuckDuckGo search function in `modules/web/web_intel.py`, it lacked:
1. **Target URL Extraction in Fallbacks:** The existing DuckDuckGo HTML fallback parser scraped text snippets but left `url: ""` blank, rendering downstream deep-page extraction and source citation impossible.
2. **Unified Research State Machine:** No concept of research sessions, evidence provenance, claim extraction, conflict resolution, or freshness lifecycles existed.
3. **Structured Evidence Package for Nemotron:** Queries were either routed to raw web browser commands or directly dumped into conversational chat without structured evidence.
4. **India-First Market Intelligence:** No specialized retailer awareness (Amazon.in, Flipkart, Croma, Reliance Digital), INR price normalizer, or warranty tracking.

---

## 2. CAPABILITY INVENTORY & REUSE MATRIX

| Capability Area | Existing Implementation | File & Entry Point | Status | Reusability Assessment | Deficiencies / Required Action |
|---|---|---|---|---|---|
| **Web Search** | `WebIntelligence.search_web()` | `modules/web/web_intel.py:27` | Partially Functional | **Reused as baseline adapter** | Fallback parser drops target URLs (`url: ""`); no region filtering; lacks domain filtering or multi-adapter orchestration. |
| **News & RSS** | `WebIntelligence.get_live_news()` | `modules/web/web_intel.py:103` | Functional | **Reused for news profile** | Hardcoded BBC/TechCrunch feeds; needs Indian news outlets (The Hindu, NDTV, Times of India, TechRadar India). |
| **Weather Telemetry** | `WebIntelligence.get_weather()` | `modules/web/web_intel.py:140` | Functional | **Reused for local weather** | Works via open wttr.in endpoint. |
| **Browser Control** | `BrowserManager` | `core/os/browser_manager.py:16` | Functional | **Reused for browser viewing** | Launches browsers and opens URLs; not an automated headless scraping or extraction engine. |
| **CDP Inspection** | `CDPClient` | `core/os/cdp_client.py:20` | Functional | **Reused for active tabs** | Strictly inspects localhost:9222 when Chrome is launched in debug mode; graceful offline fallback. |
| **Intelligence Router** | `IntelligenceRouter` | `core/ai/intelligence_router.py:43` | Functional | **Reused & Extended** | Classifies Layer 1, 2, and 3; lacks fine-grained research intent classification (shopping, comparison, gaming, academic). |
| **AI Provider** | `NvidiaNemotronProvider` | `core/ai/providers/nvidia_provider.py:28` | Functional | **Sole AI Provider** | Uses `nvidia/nemotron-3.5-bolt-e4b` with 15s deadline; ready for structured evidence reasoning. |
| **Conversation Context**| `ConversationManager` | `core/conversation_manager.py:228` | Functional | **Reused & Extended** | Retains task context and topic; needs persistent `active_research_session` tracking for pronominal research follow-ups. |
| **SQLite Memory** | `PersistentMemory` | `memory/persistent_memory.py:12` | Functional | **Authoritative DB** | SQLite database at `memory/jarvis_memory.db` with connection pooling, redaction, and migrations. Ideal for research tables. |
| **Desktop UI** | `MainWindow` | `ui/main_window.py:73` | Functional | **Reused & Extended** | PyQt6 HUD with modular panel dialogs and keybindings; ready for dedicated Research Panel (`Ctrl+Shift+R`). |
| **File Extraction** | `PathResolver`, `FileMemory` | `core/files/` | Functional | **Reused for import** | Discovers Documents, Desktop, and user folders; needs structured text, markdown, CSV, and PDF parsers. |

---

## 3. AUDIT FINDINGS: TECHNICAL DEBT & GAPS

### Finding 1: The "Empty URL" Scraper Flaw in `modules/web/web_intel.py`
When testing `web_intel.search_web('gaming controller under 2000 amazon india')`, the DuckDuckGo Instant Answer API returned zero instant abstracts, triggering fallback to `html.duckduckgo.com/html/`. While snippets were extracted, the HTML parser ignored `<a class="result__a" href="...">`.
- **Consequence:** Results contained snippets with empty strings for URLs. SANTRA could not verify the source, cite the link in chat, or navigate to the product page.
- **Resolution:** A dedicated `DuckDuckGoSearchAdapter` will be built inside `core/research/search_adapters/` using a complete HTMLParser that extracts the title, snippet, and resolves the target URL by parsing DuckDuckGo's `uddg=` redirection query parameter.

### Finding 2: Lack of Source Categorization & Authority Weighting
The existing application treated all external text identically. An unverified forum post on Reddit carried the same cognitive weight as official documentation on `python.org` or an official listing on `amazon.in`.
- **Resolution:** Implement `SourceRegistry` with explicit domain categories (Manufacturer, Retailer, Tech Docs, Academic, Established News, Community Forum, Unverified) and authority weighting (0.1 to 1.0).

### Finding 3: Stale Knowledge versus Current Evidence
Currently, conversational queries either use Nemotron's static pre-trained weights or local responses. There was no mechanism to distinguish stable algorithmic concepts (binary search) from time-varying real-world facts (laptop prices, game patches, software versions).
- **Resolution:** Implement `FreshnessManager` with differentiated TTLs (prices: 6-24 hours; patches: 7 days; specifications: 30 days; stable concepts: indefinite).

### Finding 4: Single SQLite Database Rule
To avoid database fragmentation, SANTRA must not create disconnected SQLite files across the repository.
- **Resolution:** All research sessions, sources, evidence items, product observations, and price histories will be housed inside the authoritative `memory/jarvis_memory.db` through structured schema migrations.

---

## 4. ARCHITECTURAL BASELINE READINESS

- **Python Version:** 3.14.7 (AMD64)
- **GUI Engine:** PyQt6 6.11.0
- **AI Backend:** NVIDIA NIM Nemotron API (`nvidia/nemotron-3.5-bolt-e4b`)
- **Search Backend:** Zero-cost open web adapters (DuckDuckGo HTML/Instant Answer, Regional RSS Feeds, Browser Navigation)
- **Database:** SQLite 3 WAL mode (`memory/jarvis_memory.db`)
- **Ready for Implementation:** Yes.

