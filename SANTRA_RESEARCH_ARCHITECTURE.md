# SANTRA — UNIVERSAL RESEARCH & LIVE KNOWLEDGE ARCHITECTURE

**System:** SANTRA Autonomous Desktop Assistant  
**Platform:** Windows 11 AMD64 (Ubuntu Compatible), Python 3.14.7, PyQt6  
**Provider:** NVIDIA Nemotron API (`nvidia/nemotron-3.5-bolt-e4b`)  
**Status:** IMPLEMENTED & PRODUCTION VERIFIED

---

## 1. ARCHITECTURAL OVERVIEW

The Universal Research Engine transforms SANTRA into a self-grounding cognitive assistant capable of real-time web discovery, multi-source evidence extraction, claim verification, conflict resolution, anti-hallucination synthesis, and persistent SQLite knowledge caching.

```
USER REQUEST (Voice / Text)
       ↓
[ResearchRouter] ───────────────> Classifies Research Intent & Extracts Constraints (Market: India, Budget ₹)
       ↓
[SearchManager] ────────────────> Coordinates DuckDuckGo HTML, RSS News, & CDP Browser Adapters
       ↓
[Page & Doc Extractor] ─────────> Fetches clean sandboxed text, structured pricing, & specs
       ↓
[ClaimExtractor] ───────────────> Normalizes text into atomic, source-attributed EvidenceItems
       ↓
[SourceVerifier] ───────────────> Evaluates authority weights, detects & flags contradictory claims
       ↓
[ResearchSynthesizer] ──────────> Prepares prompt payload with strict anti-injection & anti-hallucination rules
       ↓
[NVIDIA Nemotron Provider] ─────> High-speed reasoning (TTFT ~584ms) generating cited answers
       ↓
[EvidenceManager] ──────────────> Generates numbered, verifiable [1], [2] citations with exact URLs
       ↓
[ResearchMemory] ───────────────> Persists Session, Sources, Evidence, Products & Prices in SQLite (jarvis_memory.db)
       ↓
[PyQt6 Desktop UI & Audio] ─────> Real-time streaming into HUD Chat Card, Research Panel (Ctrl+Shift+R), & TTS
```

---

## 2. SUBSYSTEM MODULE BREAKDOWN

| Subsystem Module | File Path | Core Responsibility |
|---|---|---|
| **Data Schemas** | `core/research/research_models.py` | Strongly-typed schemas for sessions, sources, evidence, products, prices (`PriceType`), and citations. |
| **Source Registry** | `core/research/source_registry.py` | Directory of 100+ domains with authority weighting (0.35–1.0) and Indian regional tagging. |
| **Search Adapters** | `core/research/search_adapters/` | Open web discovery adapters (`DuckDuckGoSearchAdapter`, `RSSSearchAdapter`, `BrowserSearchAdapter`). |
| **Search Manager** | `core/research/search_manager.py` | Multi-query expansion (India-first retail & specs), adapter fallback, and URL deduplication. |
| **Page Extractor** | `core/research/page_extractor.py` | Sandboxed HTML parser with `SafeRedirectHandler` (3-hop cap, SSRF checks) and bot protection detection. |
| **Document Extractor**| `core/research/document_extractor.py` | Safe reader for user files (.txt, .md, .csv, .json, .pdf, .docx, .xlsx, images) with zero-dependency Windows 11 `Windows.Media.Ocr` engine, in-memory SHA-256 duplicate caching, and stream vs scanned PDF classification. |
| **Claim Extractor** | `core/research/claim_extractor.py` | Converts text into atomic `EvidenceItem` records and structured `ProductEntity` instances. |
| **Source Verifier** | `core/research/source_verifier.py` | Conflict resolution, syndicated copy suppression, and primary source verification. |
| **Research Security** | `core/research/research_security.py` | SSRF guard, forward DNS rebinding verification (`_verify_dns_resolution`), and prompt injection defense. |
| **Source Verifier** | `core/research/source_verifier.py` | Identifies specification and pricing contradictions, assigns conflict statuses (`RESOLVED`/`UNRESOLVED`). |
| **Evidence Manager** | `core/research/evidence_manager.py` | Constructs traceable, numbered bibliography citations without fabricating links. |
| **Freshness Manager** | `core/research/freshness_manager.py` | Enforces domain-specific TTLs (prices: 24h, patches: 7d, specs: 30d, concepts: 365d). |
| **Research Security** | `core/research/research_security.py` | Defends against prompt injection, SSRF (blocking loopback/private IPs/metadata), and file misuse. |
| **Research Memory** | `core/research/research_memory.py` | SQLite persistence inside `memory/jarvis_memory.db` across 6 indexed research tables. |
| **Research Synthesizer**| `core/research/research_synthesizer.py`| Packages evidence into Nemotron prompts and formats final answers with citation bibliographies. |
| **Research Router** | `core/research/research_router.py` | Fine-grained classification across 7 research domains and conversational follow-ups. |
| **Research Orchestrator**| `core/research/research_manager.py` | Central lifecycle manager executing end-to-end research pipelines. |
| **PyQt6 Desktop Panel** | `ui/panels/research_panel.py` | Dedicated HUD dialog displaying live stages, evidence provenance, and citations (`Ctrl+Shift+R`). |

---

## 3. SEPARATION OF CONCERNS: REFLEX VS. RESEARCH

- **Layer 1 (Deterministic Reflex):** Operating system commands (`"open Chrome"`, `"set volume to 50"`, `"mute audio"`, `"take a screenshot"`) bypass the research engine entirely and execute in `< 50ms`.
- **Layer 2 (Contextual Etiquette & Resumption):** Greetings, local identity, and paused educational explanations resume in `< 1ms` from local memory.
- **Layer 3 (Universal Research & Cognition):** Live inquiries requiring real-world facts, Indian retail prices, hardware comparisons, software documentation, and game patches route to `ResearchManager` with verified evidence grounding.

---

## 4. STAGE 4 PRODUCTION VERIFICATION & HARDENING

1. **Timeout & Fail-Fast Bounds:**
   - Enforces a 15.0s upper ceiling on HTTP read timeouts in `NvidiaNemotronProvider` and 4.0s connect timeouts.
2. **Stream Cancellation & Memory Hygiene:**
   - Cancelled queries suppress partial assistant turns from SQLite episodic memory.
   - Immediate audio watchdog purge (`tts_manager.interrupt(force=True)`) prevents ghost audio.
3. **Advanced SSRF & Numeric IP Defense:**
   - Detects and rejects integer and hex IP representations (`2130706433`, `0x7f000001`), IPv4-mapped IPv6, and link-local ranges before socket initiation.
4. **ZIP Bomb Decompression Armor:**
   - 25 MB uncompressed byte ceiling on Office OpenXML document parsing.
5. **Soak Test Validation:**
   - 100 continuous cycles verified with 0 thread leaks (7 threads constant) and sub-50ms latency.


