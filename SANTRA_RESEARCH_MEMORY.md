# SANTRA — RESEARCH MEMORY & FRESHNESS POLICIES

**System:** SANTRA Universal Research Engine  
**Database:** `memory/jarvis_memory.db` (Authoritative SQLite WAL)  
**Modules:** `core/research/research_memory.py`, `core/research/freshness_manager.py`  
**Status:** PRODUCTION OPERATIONAL

---

## 1. UNIFIED SQLITE SCHEMA

All research sessions, sources, evidence, products, prices, and user preferences are persisted inside SANTRA's canonical SQLite database `memory/jarvis_memory.db`. No fragmented secondary databases are created.

### Schema Table Definitions:

```sql
-- 1. Research Sessions
CREATE TABLE IF NOT EXISTS research_sessions (
    research_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    normalized_query TEXT,
    category TEXT,
    market TEXT DEFAULT 'India',
    language TEXT DEFAULT 'en',
    created_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL,
    final_answer TEXT,
    comparison_table_json TEXT
);

-- 2. Research Sources
CREATE TABLE IF NOT EXISTS research_sources (
    source_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    source_type TEXT,
    publication_date TEXT,
    retrieved_at REAL NOT NULL,
    content_hash TEXT,
    verification_status TEXT,
    authority_score REAL,
    raw_snippet TEXT,
    adapter_identity TEXT
);
CREATE INDEX IF NOT EXISTS idx_res_sources_session ON research_sources(research_id);

-- 3. Research Evidence
CREATE TABLE IF NOT EXISTS research_evidence (
    evidence_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_domain TEXT,
    source_type TEXT,
    publication_date TEXT,
    retrieval_date REAL NOT NULL,
    evidence_excerpt TEXT,
    confidence REAL,
    verification_status TEXT,
    conflict_status TEXT,
    entity_name TEXT,
    metric_name TEXT,
    metric_value TEXT
);
CREATE INDEX IF NOT EXISTS idx_res_evidence_session ON research_evidence(research_id);

-- 4. Research Products
CREATE TABLE IF NOT EXISTS research_products (
    product_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    specifications_json TEXT,
    compatibility_json TEXT,
    rank INTEGER DEFAULT 1,
    best_for TEXT
);

-- 5. Price Observations
CREATE TABLE IF NOT EXISTS research_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    seller TEXT NOT NULL,
    price REAL NOT NULL,
    currency TEXT DEFAULT 'INR',
    product_url TEXT,
    availability TEXT,
    observed_at REAL NOT NULL,
    is_verified INTEGER DEFAULT 0,
    rating REAL,
    review_count INTEGER,
    warranty_info TEXT
);
CREATE INDEX IF NOT EXISTS idx_res_prices_product ON research_prices(product_id);

-- 6. User Research Preferences
CREATE TABLE IF NOT EXISTS research_user_preferences (
    pref_key TEXT PRIMARY KEY,
    pref_value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    updated_at REAL NOT NULL
);
```

---

## 2. TIME-TO-LIVE (TTL) & FRESHNESS POLICIES

To prevent outdated information from contaminating current recommendations, the `FreshnessManager` enforces domain-specific lifecycles:

| Information Type | Maximum TTL | Enforcement Action Upon Expiry |
|---|---|---|
| **Stock Availability** | **1 Hour** | Marked `STALE`. Triggers live retailer search upon follow-up. |
| **Breaking News** | **2 Hours** | Purged from fresh cache; treated as historical record. |
| **Product Prices (INR)** | **24 Hours** | Retained in `research_prices` for historical charting, but flagged `Stale` for new purchase advice. |
| **Game Patches / Meta** | **7 Days** | Rechecked against live patch feeds before answering competitive inquiries. |
| **Software Versions** | **7 Days** | Rechecked against official package repositories (PyPI, GitHub, Docs). |
| **Hardware Specifications**| **30 Days** | Revalidated periodically against manufacturer listings. |
| **Product Warranty Terms** | **30 Days** | Rechecked against official brand warranty pages. |
| **Foundational Concepts** | **365 Days** | Indefinitely fresh (e.g., Binary Search, Polymorphism, TCP/IP). |

---

## 3. USER RESEARCH PREFERENCES

User research preferences explicitly provided by the user (e.g., preferred brand, budget range, target platform) are saved in `research_user_preferences`. Sensitive information (passwords, payment credentials, personal identity) is strictly blocked from storage by redaction filters.

