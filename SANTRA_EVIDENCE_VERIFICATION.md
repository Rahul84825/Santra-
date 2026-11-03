# SANTRA — EVIDENCE EXTRACTION, VERIFICATION & CITATION SPECIFICATION

**System:** SANTRA Universal Research Engine  
**Modules:** `core/research/claim_extractor.py`, `core/research/source_verifier.py`, `core/research/evidence_manager.py`  
**Status:** PRODUCTION OPERATIONAL

---

## 1. EVIDENCE LIFECYCLE & PROVENANCE

Every factual assertion discovered during research is parsed into an atomic `EvidenceItem`:

```
Source HTML / Snippet
       ↓
[ClaimExtractor]
  - Metric: price_inr -> "₹1,499"
  - Metric: hardware_feature -> "Hall Effect Triggers"
  - Excerpt: "Wireless gamepad with Hall Effect sticks"
       ↓
[SourceVerifier]
  - Cross-source comparison
  - Contradiction check: distinct values across sources?
       ↓
[EvidenceManager]
  - Numbered citation mapping: [1] -> https://www.amazon.in/...
       ↓
[Nemotron Synthesis]
  - Injects [1], [2] in-line
```

---

## 2. CONFLICT RESOLUTION RULES

When multiple sources make statements about the same entity and metric (e.g., Battery Life or Product Price):

1. **Authority-Weighted Resolution:**  
   If Source A has an authority score exceeding Source B by 0.25 or more (e.g., Official Manufacturer `0.95` vs Community Forum `0.45`):
   - Source A's claim is marked `VERIFIED` and `CONFLICT_RESOLVED`.
   - Source B's claim is marked `CONTRADICTORY` and `CONFLICT_RESOLVED`.
2. **Market Price Variation:**  
   If two retailers list differing prices (e.g., Amazon lists ₹1,499 while Flipkart lists ₹1,699):
   - Both claims are marked `VERIFIED` with `CONFLICT_UNRESOLVED` (Market Price Variation).
   - Both prices and their respective sellers are explicitly reported to the user.
3. **Specification Discrepancies:**  
   If two independent reviewers or retail pages disagree on technical specifications (e.g., Display Refresh Rate: 60Hz vs 120Hz):
   - Both claims are marked `CONTRADICTORY` with `CONFLICT_UNRESOLVED`.
   - The final reasoning output explicitly informs the user: *"Source [1] reports 120Hz while Source [2] reports 60Hz; official manufacturer verification recommended."*

---

## 3. CITATION INTEGRITY & ANTI-HALLUCINATION RULES

1. **Traceable Links:** Every citation output by SANTRA (`[1]`, `[2]`) corresponds to an actual HTTP/HTTPS URL retrieved during the research session.
2. **Zero Fabrication:** SANTRA's Nemotron prompt contract forbids generating citations not present in the evidence package.
3. **Snippet vs. Full Page Transparency:** Citations clearly distinguish search abstract snippets from fully-extracted web pages.

