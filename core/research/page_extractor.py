"""Page Content & Specification Extractor for SANTRA Research Engine.
Extracts clean, sandboxed text, structured pricing, specifications, and metadata
from accessible web pages with redirect validation and bot-challenge detection.
"""

import re
import hashlib
import logging
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from typing import Dict, List, Any, Optional

from core.research.research_security import research_security

logger = logging.getLogger("Jarvis.PageExtractor")

class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validates that HTTP redirect destinations satisfy SSRF security restrictions."""

    MAX_REDIRECTS = 3

    def __init__(self):
        super().__init__()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > self.MAX_REDIRECTS:
            logger.warning(f"[PageExtractor] Maximum redirect limit ({self.MAX_REDIRECTS}) exceeded for '{newurl}'.")
            return None

        is_safe, reason = research_security.is_safe_url(newurl)
        if not is_safe:
            logger.warning(f"[PageExtractor] Blocked unsafe redirect to '{newurl}': {reason}")
            return None

        return super().redirect_request(req, fp, code, msg, headers, newurl)


class CleanHTMLTextParser(HTMLParser):
    """Robust standard library parser that strips scripts, styles, and extracts main readable text."""

    IGNORED_TAGS = {"script", "style", "nav", "header", "footer", "iframe", "noscript", "svg"}

    def __init__(self):
        super().__init__()
        self.text_chunks: List[str] = []
        self.meta_description: str = ""
        self.page_title: str = ""
        self._tag_stack: List[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        tag_lower = tag.lower()
        self._tag_stack.append(tag_lower)
        attrs_dict = dict(attrs)

        if tag_lower == "title":
            self._in_title = True
        elif tag_lower == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            if name in ["description", "og:description"] or prop in ["description", "og:description"]:
                self.meta_description = attrs_dict.get("content", "").strip()

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == tag_lower:
            self._tag_stack.pop()
        elif tag_lower in self._tag_stack:
            while self._tag_stack and self._tag_stack[-1] != tag_lower:
                self._tag_stack.pop()
            if self._tag_stack:
                self._tag_stack.pop()

        if tag_lower == "title":
            self._in_title = False

    def handle_data(self, data: str):
        if any(ignored in self._tag_stack for ignored in self.IGNORED_TAGS):
            return

        cleaned = " ".join(data.split())
        if not cleaned:
            return

        if self._in_title:
            self.page_title += " " + cleaned
        else:
            self.text_chunks.append(cleaned)


class PageExtractor:
    """Safe, rate-limited webpage reader with specification and price extraction."""

    MAX_BYTES = 2 * 1024 * 1024  # 2 MB limit
    DEFAULT_TIMEOUT = 5.0

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def _build_safe_opener(self) -> urllib.request.OpenerDirector:
        """Constructs a custom URL opener with SSRF-safe redirect validation."""
        redirect_handler = SafeRedirectHandler()
        return urllib.request.build_opener(redirect_handler)

    def extract_url(self, url: str) -> Dict[str, Any]:
        """Fetches and extracts structured content from a public webpage."""
        is_safe, reason = research_security.is_safe_url(url)
        if not is_safe:
            return {"success": False, "url": url, "error": f"Security restriction: {reason}", "extraction_status": "BLOCKED_BY_SECURITY"}

        # Classify URL type
        is_product_page = bool(re.search(r"/(?:dp|gp/product)/[A-Z0-9]{10}", url) or re.search(r"/p/itm[a-zA-Z0-9]+", url))
        asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        asin = asin_match.group(1) if asin_match else None

        logger.info(f"[PageExtractor] Fetching content for URL: {url} (is_product_page={is_product_page})")
        opener = self._build_safe_opener()

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with opener.open(req, timeout=self.DEFAULT_TIMEOUT) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type and "text/plain" not in content_type:
                    return {
                        "success": False,
                        "url": url,
                        "error": f"Unsupported Content-Type: {content_type}",
                        "extraction_status": "UNSUPPORTED_CONTENT_TYPE"
                    }

                raw_bytes = response.read(self.MAX_BYTES)
                content_hash = hashlib.sha256(raw_bytes).hexdigest()
                html_text = raw_bytes.decode("utf-8", errors="ignore")

                # Check for anti-bot challenge
                if "robot check" in html_text.lower() or "enter the characters you see below" in html_text.lower():
                    logger.warning(f"[PageExtractor] Retailer anti-bot challenge detected on '{url}'.")
                    return {
                        "success": False,
                        "url": url,
                        "error": "Retailer anti-bot challenge encountered.",
                        "extraction_status": "BLOCKED_BY_RETAILER_BOT_PROTECTION",
                        "is_product_page": is_product_page,
                        "asin": asin
                    }

                parser = CleanHTMLTextParser()
                parser.feed(html_text)

                main_text = "\n".join(parser.text_chunks)
                if len(main_text) > 20000:
                    main_text = main_text[:20000] + "..."

                signals = self._extract_structured_signals(main_text, parser.page_title, url)
                signals["is_product_page"] = is_product_page
                signals["asin"] = asin

                return {
                    "success": True,
                    "url": url,
                    "title": parser.page_title.strip(),
                    "meta_description": parser.meta_description,
                    "content_hash": content_hash,
                    "text": main_text,
                    "signals": signals,
                    "extraction_status": "VERIFIED_PRODUCT_PAGE" if is_product_page else "EXTRACTED_CATEGORY_PAGE"
                }

        except urllib.error.HTTPError as he:
            status_desc = "BLOCKED_BY_RETAILER_BOT_PROTECTION" if he.code in [503, 403] else f"HTTP_ERROR_{he.code}"
            logger.warning(f"[PageExtractor] HTTP {he.code} on '{url}': {he.reason}")
            return {
                "success": False,
                "url": url,
                "error": f"HTTP Error {he.code}: {he.reason}",
                "extraction_status": status_desc,
                "is_product_page": is_product_page,
                "asin": asin
            }
        except Exception as e:
            logger.warning(f"[PageExtractor] Failed to extract URL '{url}': {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "extraction_status": "EXTRACTION_FAILED",
                "is_product_page": is_product_page,
                "asin": asin
            }

    def _extract_structured_signals(self, text: str, title: str, url: str) -> Dict[str, Any]:
        """Extracts prices (INR ₹), warranty, availability, and specs via pattern matching."""
        signals: Dict[str, Any] = {
            "prices": [],
            "availability": "Unknown",
            "warranty": None,
            "ratings": None,
            "review_count": None,
            "brand": None,
            "model": None,
            "specs": {}
        }

        # 1. Price extraction (INR priority)
        price_patterns = [
            r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)",
            r"\bPrice:\s*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)"
        ]
        found_prices = []
        for pat in price_patterns:
            for match in re.finditer(pat, text, re.IGNORECASE):
                val_str = match.group(1).replace(",", "")
                try:
                    val = float(val_str)
                    if 10.0 <= val <= 10000000.0:
                        found_prices.append(val)
                except ValueError:
                    pass
        if found_prices:
            signals["prices"] = sorted(list(set(found_prices[:5])))

        # 2. Availability detection
        text_lower = text.lower()
        if any(term in text_lower for term in ["in stock", "available to ship", "get it by", "in-stock"]):
            signals["availability"] = "In Stock"
        elif any(term in text_lower for term in ["out of stock", "currently unavailable", "sold out"]):
            signals["availability"] = "Out of Stock"

        # 3. Warranty extraction
        warranty_match = re.search(r"(\d+\s*(?:year|years|month|months)\s*(?:domestic|brand|manufacturer)?\s*warranty)", text_lower)
        if warranty_match:
            signals["warranty"] = warranty_match.group(1).title()

        # 4. Rating & Reviews
        rating_match = re.search(r"(\d\.\d)\s*(?:out of 5|stars|\/ 5)", text_lower)
        if rating_match:
            try:
                signals["ratings"] = float(rating_match.group(1))
            except ValueError:
                pass

        rev_match = re.search(r"([\d,]+)\s*(?:ratings|reviews|customer reviews)", text_lower)
        if rev_match:
            try:
                signals["review_count"] = int(rev_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # 5. Hardware specifications
        if "hall effect" in text_lower:
            signals["specs"]["hall_effect"] = True
        if "wireless" in text_lower or "bluetooth" in text_lower:
            signals["specs"]["connectivity"] = "Wireless / Bluetooth"
        elif "wired" in text_lower:
            signals["specs"]["connectivity"] = "Wired"

        # Compatibility
        compats = []
        if "pc" in text_lower or "windows" in text_lower:
            compats.append("PC / Windows")
        if "android" in text_lower:
            compats.append("Android")
        if "ps4" in text_lower or "playstation" in text_lower:
            compats.append("PlayStation")
        if "xbox" in text_lower:
            compats.append("Xbox")
        if "switch" in text_lower or "nintendo" in text_lower:
            compats.append("Nintendo Switch")
        signals["specs"]["compatibility"] = compats

        return signals

# Singleton instance
page_extractor = PageExtractor()
