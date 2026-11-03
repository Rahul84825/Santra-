# SANTRA — SOURCE REGISTRY & QUALITY DIRECTORY

**System:** SANTRA Universal Research Engine  
**Module:** `core/research/source_registry.py`  
**Status:** PRODUCTION OPERATIONAL

---

## 1. SOURCE HIERARCHY & AUTHORITY WEIGHTS

The `SourceRegistry` maintains a directory of online domains, assigning baseline credibility scores and source types to ensure SANTRA distinguishes primary documentation from unverified community forums.

| Source Category | Authority Score | Primary Description | Example Domains |
|---|---|---|---|
| **GOVERNMENT_REGULATORY** | **1.00** | Official government portals, consumer protection, standards & tax authorities | `bis.gov.in`, `cbic-gst.gov.in`, `india.gov.in`, `meity.gov.in`, `rbi.org.in` |
| **OFFICIAL_DOCS** | **0.95** | Official software documentation, language specs, API references | `docs.python.org`, `developer.mozilla.org`, `learn.microsoft.com`, `react.dev` |
| **OFFICIAL_MANUFACTURER** | **0.95** | Hardware and peripheral manufacturers, official brand portals | `nvidia.com`, `intel.com`, `amd.com`, `apple.com`, `evofox.com`, `cosmicbyte.com` |
| **ACADEMIC_RESEARCH** | **0.92** | Peer-reviewed academic publications and preprints | `arxiv.org`, `semanticscholar.org`, `ieee.org`, `acm.org`, `nature.com` |
| **RETAILER_MARKETPLACE (India)** | **0.85** | Verified Indian e-commerce marketplaces and electronics stores | `amazon.in`, `flipkart.com`, `croma.com`, `reliancedigital.in`, `vijaysales.com` |
| **ESTABLISHED_NEWS** | **0.85** | Mainstream global and Indian news organizations | `thehindu.com`, `ndtv.com`, `timesofindia.indiatimes.com`, `bbc.com`, `reuters.com` |
| **REPUTABLE_TECH** | **0.80** | Established consumer tech analysis, benchmarks, and teardowns | `tomshardware.com`, `theverge.com`, `anandtech.com`, `gsmarena.com`, `digit.in` |
| **COMMUNITY_FORUM** | **0.45** | Public discussion boards and social threads | `reddit.com`, `stackoverflow.com`, `quora.com`, `medium.com` |
| **UNVERIFIED** | **0.35** | General indexed blogs and unclassified websites | All unclassified domains |

---

## 2. INDIA-FIRST REGIONAL RELEVANCE LOGIC

Every discovered URL or domain is inspected for Indian regional priority:
1. **Top-Level Domain (TLD):** Domains ending with `.in`, `.co.in`, or `.gov.in` automatically receive an Indian Regional Relevance tag.
2. **Indian Marketplace Portals:** Domains such as `amazon.in`, `flipkart.com`, `croma.com`, `reliancedigital.in`, and `vijaysales.com` are marked as authoritative Indian retail entities.
3. **Regional Relevance Boost:** If a query originates with the default market `India` or mentions Indian currency (`₹`, `INR`), sources with Indian relevance receive an authority bonus (+0.05), prioritizing domestic sellers and pricing.

---

## 3. CONFIGURATION & EXTENSIBILITY

Domains can be extended dynamically via `config/sources.json` or by subclassing `SourceRegistry`. Custom user sources imported via URLs or documents inherit provenance tracking and cannot override system authority tiers without independent verification.

