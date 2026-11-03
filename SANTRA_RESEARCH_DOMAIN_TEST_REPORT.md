# SANTRA Universal Research Engine — Domain Validation Test Report

## 1. Domain Coverage Matrix
The Universal Research Engine was executed across all seven core knowledge domains in live end-to-end trials on Windows 11 AMD64.

| Domain | Test Query | Discovered Sources | Extracted Evidence | Products Extracted | Citations | Latency (sec) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Shopping** | *"Find the best wireless gaming controller under ₹2,000 in India."* | 10 | 19 | 10 | 8 | 16.48s | COMPLETED |
| **Technology** | *"What is the latest NVIDIA GPU architecture?"* | 8 | 8 | 0 | 8 | 17.13s | COMPLETED |
| **Programming** | *"What is the latest stable Python version?"* | 11 | 11 | 0 | 8 | 10.21s | COMPLETED |
| **Gaming** | *"What are the latest Valorant patch notes?"* | 8 | 8 | 0 | 8 | 13.92s | COMPLETED |
| **News** | *"Give me the latest important technology news in India."* | 8 | 9 | 0 | 8 | 16.01s | COMPLETED |
| **Comparison** | *"Compare React and Next.js."* | 12 | 12 | 2 | 8 | 10.38s | COMPLETED |
| **General Knowledge** | *"Explain how database indexing works."* | 0 | 0 | 0 | 0 | 1.25s | COMPLETED (Exact Cache Hit) |

---

## 2. Domain Detailed Analysis

### Domain 1: Shopping & Product Search
- **Query**: `"Find the best wireless gaming controller under ₹2,000 in India."`
- **Discovered Platforms**: Amazon India (`amazon.in`), Flipkart (`flipkart.com`).
- **Bot Countermeasures Encountered**: `HTTP 503 Service Unavailable` on deep URL scraping. Correctly surfaced `extraction_status = "PARTIAL_SNIPPET"` and `price_type = PriceType.SEARCH_RESULT_PRICE`.
- **Ranked Findings**: Cosmic Byte Stellaris (₹1,000 – ₹1,899, Hall Effect), Ant Esports GP300 Pro (₹1,299), Redgear Pro Wireless (₹1,499).

### Domain 2: Technology & Hardware
- **Query**: `"What is the latest NVIDIA GPU architecture?"`
- **Primary Sources**: `nvidia.com` (Hopper, Blackwell architecture technical overviews).
- **Extracted Content**: Tensor Core improvements, neural rendering, data center and consumer release details.

### Domain 3: Programming & Documentation
- **Query**: `"What is the latest stable Python version?"`
- **Primary Sources**: `python.org/downloads/latest/`, `devguide.python.org`.
- **Extracted Content**: Python 3.14 / 3.13 maintenance schedules and release metadata. Assigned `VERIFIED_BY_PRIMARY_SOURCE`.

### Domain 4: Gaming & Patch Notes
- **Query**: `"What are the latest Valorant patch notes?"`
- **Discovered Sources**: News aggregators, Riot Games esports coverage.
- **Extracted Content**: Agent balance changes and map pool rotation updates.

### Domain 5: News & Current Events
- **Query**: `"Give me the latest important technology news in India."`
- **Discovered Sources**: `digit.in`, `indianexpress.com`, `economictimes.indiatimes.com`.
- **Extracted Content**: Smartphone launches, telecom spectrum rollouts, and Indian tech startup funding news.

### Domain 6: Technical Comparison
- **Query**: `"Compare React and Next.js."`
- **Discovered Sources**: React and Next.js documentation, developer articles.
- **Synthesis Quality**: Clarified client-side SPA rendering vs Server-Side Rendering (SSR) / Static Site Generation (SSG), routing paradigms, and performance implications.

### Domain 7: Foundational General Knowledge
- **Query**: `"Explain how database indexing works."`
- **Behavior**: Classified as `GENERAL_KNOWLEDGE`. Bypassed outbound search overhead. Resolved via local cache and Nemotron reasoning in 1.25s, demonstrating zero-overhead local-first routing.

