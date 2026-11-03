"""Claim and Evidence Extraction Engine for SANTRA Research Engine.
Transforms unstructured source snippets and extracted pages into atomic,
source-attributed EvidenceItem claims and structured ProductEntity listings.
"""

import re
import uuid
import logging
from typing import List, Dict, Any, Optional

from core.research.research_models import (
    EvidenceItem, Source, SourceType, VerificationStatus, ConflictStatus,
    ProductEntity, PriceType
)

logger = logging.getLogger("Jarvis.ClaimExtractor")

class ClaimExtractor:
    """Extracts factual claims, product specifications, and price points from text."""

    SPEC_PATTERNS = [
        (r"\b(hall\s+effect(?:\s+joystick|\s+sticks|\s+triggers)?)\b", "Hardware Feature", "Hall Effect"),
        (r"\b(bluetooth(?:\s+5\.\d)?|2\.4\s*ghz\s+wireless|wired\s+usb-c|wired\s+connection)\b", "Connectivity", None),
        (r"\b(\d+\s*(?:hour|hr|hrs)\s*battery(?:\s*life)?)\b", "Battery Life", None),
        (r"\b(\d+\s*hz(?:\s+refresh\s+rate|\s+display)?)\b", "Display Refresh", None),
        (r"\b(rtx\s*40\d0(?:\s*ti)?|rtx\s*30\d0|rtx\s*2050|gtx\s*\d{3,4}|radeon\s*rx\s*\d{4})\b", "GPU", None),
        (r"\b(intel\s*core\s*(?:ultra\s*\d+|i[3579]-?\d+)|ryzen\s*[3579]\s*\d{4}[a-z]?)\b", "CPU", None),
        (r"\b(\d{1,2}\s*gb\s*(?:ddr[45]|ram))\b", "RAM", None),
        (r"\b(\d{3,4}\s*gb|\d\s*tb)\s*(?:nvme|ssd|storage)\b", "Storage", None),
        (r"\b(paw\s*33\d{2}|pmw\s*33\d{2}|\d{4,5}\s*dpi)\b", "Mouse Sensor", None),
        (r"\b(\d{2,3}\s*g(?:rams)?\s*(?:ultra-light|lightweight)?)\b", "Weight", None),
        (r"\b(bis\s*certified|bis\s*certification)\b", "Certification", "BIS Certified"),
        (r"\b(\d+\s*(?:year|month)s?\s*(?:brand|domestic|manufacturer)?\s*warranty)\b", "Warranty", None)
    ]

    RETAILER_MAP = {
        "amazon.in": "Amazon India",
        "flipkart.com": "Flipkart",
        "croma.com": "Croma",
        "reliancedigital.in": "Reliance Digital",
        "vijaysales.com": "Vijay Sales",
        "tatacliq.com": "Tata CLiQ"
    }

    def extract_claims_from_source(self, source: Source, page_signals: Optional[Dict[str, Any]] = None) -> List[EvidenceItem]:
        """Extracts atomic evidence items from a single Source."""
        claims: List[EvidenceItem] = []
        text_corpus = f"{source.title}. {source.raw_snippet}"

        # 1. Price claims
        prices = []
        price_type = PriceType.SEARCH_RESULT_PRICE
        if page_signals and page_signals.get("prices"):
            prices = page_signals["prices"]
            price_type = PriceType.VERIFIED_PRODUCT_PAGE_PRICE
        else:
            price_matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([\d,]+)", text_corpus, re.IGNORECASE)
            for pm in price_matches:
                try:
                    prices.append(float(pm.replace(",", "")))
                except ValueError:
                    pass

        if prices:
            best_price = min(prices)
            status = VerificationStatus.VERIFIED if source.source_type == SourceType.RETAILER_MARKETPLACE else VerificationStatus.UNVERIFIED
            claims.append(EvidenceItem(
                research_id=source.research_id,
                source_id=source.source_id,
                claim_text=f"Product listed at ₹{best_price:,.0f} ({price_type.value}) on {source.domain}",
                source_url=source.url,
                source_domain=source.domain,
                source_type=source.source_type,
                publication_date=source.publication_date,
                evidence_excerpt=source.raw_snippet[:200] if source.raw_snippet else source.title,
                confidence=0.85 if source.source_type == SourceType.RETAILER_MARKETPLACE else 0.70,
                verification_status=status,
                entity_name=source.title.split("-")[0].strip(),
                metric_name="price_inr",
                metric_value=str(best_price)
            ))

        # 2. Hardware and Feature Specifications
        text_lower = text_corpus.lower()
        for pat, metric_label, override_val in self.SPEC_PATTERNS:
            match = re.search(pat, text_lower, re.IGNORECASE)
            if match:
                val = override_val or match.group(1).title()
                claims.append(EvidenceItem(
                    research_id=source.research_id,
                    source_id=source.source_id,
                    claim_text=f"{metric_label}: {val}",
                    source_url=source.url,
                    source_domain=source.domain,
                    source_type=source.source_type,
                    publication_date=source.publication_date,
                    evidence_excerpt=match.group(0),
                    confidence=source.authority_score,
                    verification_status=VerificationStatus.VERIFIED if source.authority_score >= 0.8 else VerificationStatus.UNVERIFIED,
                    entity_name=source.title.split("-")[0].strip(),
                    metric_name=metric_label.lower().replace(" ", "_"),
                    metric_value=val
                ))

        # 3. Informational Summary Claim (General fallback evidence)
        if source.raw_snippet and len(source.raw_snippet) > 20:
            claims.append(EvidenceItem(
                research_id=source.research_id,
                source_id=source.source_id,
                claim_text=source.raw_snippet[:180],
                source_url=source.url,
                source_domain=source.domain,
                source_type=source.source_type,
                publication_date=source.publication_date,
                evidence_excerpt=source.raw_snippet[:200],
                confidence=source.authority_score,
                verification_status=VerificationStatus.VERIFIED if source.authority_score >= 0.8 else VerificationStatus.UNVERIFIED,
                entity_name=source.title.split("-")[0].strip()
            ))

        return claims

    def extract_product_from_source(self, source: Source, page_signals: Optional[Dict[str, Any]] = None) -> Optional[ProductEntity]:
        """Extracts a structured ProductEntity candidate from a source listing."""
        text_corpus = f"{source.title} {source.raw_snippet}"
        
        # 1. Price extraction
        price = 0.0
        price_type = PriceType.SEARCH_RESULT_PRICE
        if page_signals and page_signals.get("prices"):
            price = min(page_signals["prices"])
            price_type = PriceType.VERIFIED_PRODUCT_PAGE_PRICE
        else:
            price_matches = re.findall(r"(?:₹|Rs\.?|INR)\s*([\d,]+)", text_corpus, re.IGNORECASE)
            if price_matches:
                try:
                    price = float(price_matches[0].replace(",", ""))
                except ValueError:
                    pass

        # If no price found, we may still extract as UNAVAILABLE_PRICE
        if price <= 0:
            price_type = PriceType.UNAVAILABLE_PRICE

        # 2. ASIN / SKU detection
        asin = None
        asin_match = re.search(r"\b(B0[A-Z0-9]{8})\b", source.url or text_corpus)
        if asin_match:
            asin = asin_match.group(1)

        # 3. Retailer & Seller
        retailer = self.RETAILER_MAP.get(source.domain, source.domain or "Unknown Retailer")
        seller = "Unknown"
        seller_match = re.search(r"(?:sold by|seller:?)\s*([A-Za-z0-9\s]+?)(?:[.,]|$)", text_corpus, re.IGNORECASE)
        if seller_match:
            seller = seller_match.group(1).strip()

        # 4. Availability
        availability = "IN_STOCK"
        if "out of stock" in text_corpus.lower() or "currently unavailable" in text_corpus.lower():
            availability = "OUT_OF_STOCK"

        # 5. Rating & Review Count
        rating = 0.0
        review_count = 0
        rating_match = re.search(r"(\d\.\d)\s*(?:out of 5|stars?|\★)", text_corpus, re.IGNORECASE)
        if rating_match:
            try:
                rating = float(rating_match.group(1))
            except ValueError:
                pass

        rev_match = re.search(r"([\d,]+)\s*(?:ratings?|reviews?)", text_corpus, re.IGNORECASE)
        if rev_match:
            try:
                review_count = int(rev_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 6. Warranty
        warranty = None
        war_match = re.search(r"(\d+\s*(?:year|yr|month|mo)s?\s*(?:brand|domestic|manufacturer)?\s*warranty)", text_corpus, re.IGNORECASE)
        if war_match:
            warranty = war_match.group(1).title()

        # 7. Brand detection
        known_brands = [
            "Cosmic Byte", "Ant Esports", "Redgear", "Evofox", "Logitech", "Razer",
            "Lenovo", "ASUS", "HP", "Acer", "Dell", "MSI", "Sony", "Microsoft", "8BitDo", "PowerA"
        ]
        brand = ""
        for b in known_brands:
            if b.lower() in text_corpus.lower():
                brand = b
                break

        # 8. Model Number detection
        model_no_match = re.search(r"\b(?:model(?:\s+no\.?|\s+number)?:?\s*|item\s+model\s+number:?\s*)([A-Z0-9\-_]{3,15})\b", text_corpus, re.IGNORECASE)
        model_number = model_no_match.group(1) if model_no_match else None

        # 9. Model variant
        model_variant = None
        var_match = re.search(r"\b(v\d|pro|plus|ultra|wireless|wired|rgb|edition|512gb|1tb|256gb)\b", source.title, re.IGNORECASE)
        if var_match:
            model_variant = var_match.group(1).title()

        # 10. Disadvantages & Trade-offs
        disadvantages = []
        text_lower = text_corpus.lower()
        if "wired" in text_lower and "wireless" not in text_lower:
            disadvantages.append("(Inferred: Wired only; lacks wireless connectivity)")
        if "battery" in text_lower and any(w in text_lower for w in ["4 hour", "5 hour", "4-5 hr"]):
            disadvantages.append("(Inferred: Modest battery run time ~4-5 hours based on listing)")
        if "hall effect" not in text_lower and any(k in text_lower for k in ["controller", "gamepad", "joystick"]):
            disadvantages.append("(Inferred: Lacks Hall Effect sensors; uses standard potentiometers)")
        if "60hz" in text_lower and "laptop" in text_lower:
            disadvantages.append("(Inferred: Standard 60Hz display refresh rate)")

        # 11. Recommendation Tier
        recommendation_tier = "Best Value"
        if "hall effect" in text_lower:
            recommendation_tier = "Best Specifications"
        elif price > 0 and price < 1300:
            recommendation_tier = "Best Budget"
        elif rating >= 4.2 and review_count > 300:
            recommendation_tier = "Best Overall"
        elif any(k in text_lower for k in ["multi-platform", "pc/ps", "android, ios", "compatibility"]):
            recommendation_tier = "Best Compatibility"

        # 12. Field Verification Statuses
        field_verification_statuses = {
            "name": "VERIFIED_BY_PRIMARY_SOURCE" if source.source_type == SourceType.OFFICIAL_MANUFACTURER else "CORROBORATED",
            "price": price_type.value,
            "asin_or_sku": "VERIFIED" if asin else "UNAVAILABLE",
            "brand": "VERIFIED" if brand else "UNVERIFIED",
            "warranty": "VERIFIED" if warranty else "UNVERIFIED",
            "specifications": "VERIFIED_BY_PRIMARY_SOURCE" if source.authority_score >= 0.85 else "CORROBORATED"
        }

        search_result_price = price if price_type == PriceType.SEARCH_RESULT_PRICE else None
        product_page_price = price if price_type == PriceType.VERIFIED_PRODUCT_PAGE_PRICE else None

        title_parts = source.title.split("-")[0].split("|")[0].strip()
        product_name = title_parts or source.title

        extraction_status = "SUCCESS" if (page_signals and page_signals.get("is_product_page")) else "PARTIAL_SNIPPET"

        return ProductEntity(
            research_id=source.research_id,
            name=product_name,
            brand=brand,
            model_number=model_number,
            model_variant=model_variant,
            asin_or_sku=asin,
            retailer=retailer,
            seller=seller,
            price=price,
            search_result_price=search_result_price,
            product_page_price=product_page_price,
            price_type=price_type,
            currency="INR",
            availability=availability,
            warranty=warranty,
            rating=rating,
            review_count=review_count,
            product_url=source.url,
            extraction_status=extraction_status,
            recommendation_tier=recommendation_tier,
            disadvantages=disadvantages,
            cons=disadvantages,
            field_verification_statuses=field_verification_statuses
        )

# Singleton instance
claim_extractor = ClaimExtractor()
