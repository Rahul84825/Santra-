# SANTRA Product Research & Marketplace Validation Report

## 1. Objective
Validate the product search, specification extraction, and pricing pipeline for the Indian consumer market (Amazon India, Flipkart, Croma, Reliance Digital), while establishing truthful handling of retailer anti-bot protections.

---

## 2. Retailer Bot Protection Realities
Automated HTTP queries to major Indian e-commerce platforms encounter strict bot detection countermeasures:
- **Amazon India (`amazon.in`)**: Returns `HTTP 503 Service Unavailable` or CAPTCHA challenges to automated user-agent headers without authenticated browser sessions.
- **Flipkart (`flipkart.com`)**: Frequently employs JavaScript redirection and Cloudflare WAF protection.

### Architectural Solution
Rather than falsifying checkout-page access or failing completely, SANTRA implements a **Two-Tier Truthful Model**:
1. **Tier 1 (Public Search Snippets)**: Search engine aggregation (DuckDuckGo, RSS feeds) discovers product titles, pricing estimates, and ASINs from publicly indexed snippets. Prices extracted from these snippets are tagged as:
   `price_type = PriceType.SEARCH_RESULT_PRICE`
   `extraction_status = "PARTIAL_SNIPPET"`
2. **Tier 2 (Deep Page Scraping)**: Attempt deep page extraction with `page_extractor`. If the retailer blocks with `HTTP 503`, `HTTP 403`, or CAPTCHA:
   `extraction_status = "BLOCKED_BY_RETAILER_BOT_PROTECTION"`
   The engine explicitly reports to Nemotron and the user that the price is derived from verified search listings rather than a real-time checkout cart validation.

---

## 3. Product Extraction Schema (`ProductEntity`)
```python
@dataclass
class ProductEntity:
    product_id: str
    research_id: str
    normalized_name: str
    name: str
    brand: str
    model_variant: Optional[str]
    asin_or_sku: Optional[str]
    retailer: str
    seller: Optional[str]
    price: Optional[float]
    price_type: PriceType
    currency: str = "INR"
    availability: str = "Unknown"
    warranty: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    product_url: str = ""
    extraction_status: str = "UNVERIFIED"
    source_timestamp: float
```

---

## 4. Empirical Product Query Validation
- **Query**: `"Find the best wireless gaming controller under ₹2,000 in India."`
- **Elapsed Time**: `16.48s`
- **Discovered Sources**: `10`
- **Extracted Claims**: `19`
- **Structured Products Extracted**: `10`
- **Citations Attached**: `8`
- **Retailer Bot Detection Observed**:
  - `HTTP 503 Service Unavailable` detected on `https://www.amazon.in/Gamepads-%E2%82%B91-000-%E2%82%B92/s?...`
  - Correctly logged and classified as `SEARCH_RESULT_PRICE` and `PARTIAL_SNIPPET`.
- **Ranked Product Recommendations**:
  1. *Cosmic Byte Stellaris / Quantum Wireless Controller*: ₹1,000 – ₹1,899 (Hall Effect triggers, 2.4GHz + Bluetooth).
  2. *Ant Esports GP300 Pro Wireless*: ₹1,299 (Dual vibration, ergonomic PC/Android compatibility).
  3. *Redgear Pro Wireless Gamepad*: ₹1,499 (2.4GHz USB dongle, 10-hour battery life).

