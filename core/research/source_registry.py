"""Source Registry & Quality Assessment for SANTRA Research Engine.
Categorizes domains into authoritative source types, computes baseline
credibility weights, tags Indian regional relevance, and filters low-quality sources.
"""

import re
import urllib.parse
from typing import Dict, Tuple, Optional
from core.research.research_models import SourceType

class SourceRegistry:
    """Configurable directory of online sources with authority scoring and regional tagging."""

    # Explicit domain categorizations
    OFFICIAL_MANUFACTURERS = {
        "nvidia.com", "intel.com", "amd.com", "apple.com", "microsoft.com",
        "sony.com", "playstation.com", "asus.com", "dell.com", "lenovo.com",
        "hp.com", "logitech.com", "cosmicbyte.com", "amkette.com", "evofox.com",
        "razer.com", "corsair.com", "samsung.com", "oneplus.in", "realme.com",
        "xiaomi.com", "mi.com", "boat-lifestyle.com", "noise.com", "redgear.in"
    }

    GOVERNMENT_REGULATORY = {
        "bis.gov.in", "cbic-gst.gov.in", "india.gov.in", "consumerhelpline.gov.in",
        "meity.gov.in", "rbi.org.in", "trai.gov.in", "epfindia.gov.in",
        "uidai.gov.in", "gov.uk", "usa.gov", "nih.gov", "cdc.gov"
    }

    OFFICIAL_DOCS = {
        "docs.python.org", "python.org", "pypi.org", "developer.mozilla.org",
        "learn.microsoft.com", "docs.microsoft.com", "react.dev", "nextjs.org",
        "vuejs.org", "angular.dev", "go.dev", "rust-lang.org", "kernel.org",
        "docs.docker.com", "kubernetes.io", "git-scm.com", "sqlite.org",
        "cppreference.com", "en.cppreference.com", "nodejs.org", "pytorch.org"
    }

    INDIAN_RETAILERS = {
        "amazon.in", "flipkart.com", "croma.com", "reliancedigital.in",
        "vijaysales.com", "tatacliq.com", "myntra.com", "mdcomputers.in",
        "primeabgb.com", "vedantcomputers.com", "elitehubs.com"
    }

    GLOBAL_RETAILERS = {
        "amazon.com", "bestbuy.com", "newegg.com", "ebay.com", "bnh.com"
    }

    ESTABLISHED_NEWS = {
        "thehindu.com", "ndtv.com", "timesofindia.indiatimes.com", "indianexpress.com",
        "livemint.com", "economictimes.indiatimes.com", "bbc.com", "bbc.co.uk",
        "reuters.com", "apnews.com", "bloomberg.com", "hindustantimes.com"
    }

    REPUTABLE_TECH = {
        "techcrunch.com", "anandtech.com", "tomshardware.com", "theverge.com",
        "arstechnica.com", "gsmarena.com", "xda-developers.com", "ign.com",
        "pcgamer.com", "digitaltrends.com", "9to5google.com", "9to5mac.com",
        "techradar.com", "beebom.com", "digit.in", "mysmartprice.com"
    }

    ACADEMIC_RESEARCH = {
        "arxiv.org", "semanticscholar.org", "ieee.org", "acm.org",
        "nature.com", "sciencedirect.com", "springer.com", "ncbi.nlm.nih.gov",
        "jstor.org", "researchgate.net"
    }

    COMMUNITY_FORUMS = {
        "reddit.com", "stackoverflow.com", "stackexchange.com", "quora.com",
        "medium.com", "dev.to", "discord.com", "huggingface.co/spaces"
    }

    @classmethod
    def extract_domain(cls, url_or_domain: str) -> str:
        """Extracts clean lowercase domain from URL or domain string."""
        if not url_or_domain:
            return ""
        if "://" in url_or_domain:
            parsed = urllib.parse.urlparse(url_or_domain)
            domain = parsed.netloc.lower()
        else:
            domain = url_or_domain.split("/")[0].lower()

        # Strip standard port or www prefix
        domain = re.sub(r":\d+$", "", domain)
        domain = re.sub(r"^www\.", "", domain)
        return domain.strip()

    @classmethod
    def is_indian_domain(cls, domain: str) -> bool:
        """Determines if the domain is India-specific (.in, Indian retailer, or news)."""
        domain = cls.extract_domain(domain)
        if domain.endswith(".in") or domain.endswith(".co.in") or domain.endswith(".gov.in"):
            return True
        if domain in cls.INDIAN_RETAILERS:
            return True
        if domain in ["digit.in", "beebom.com", "mysmartprice.com", "livemint.com", "hindustantimes.com"]:
            return True
        return False

    @classmethod
    def classify_domain(cls, url_or_domain: str) -> Tuple[SourceType, float, bool]:
        """Classifies domain, returning (SourceType, authority_score, is_indian_relevance)."""
        domain = cls.extract_domain(url_or_domain)
        is_in = cls.is_indian_domain(domain)

        # 1. Government & Regulatory
        for g in cls.GOVERNMENT_REGULATORY:
            if domain == g or domain.endswith("." + g):
                return SourceType.GOVERNMENT_REGULATORY, 1.0, is_in

        # 2. Official Technical Documentation
        for doc in cls.OFFICIAL_DOCS:
            if domain == doc or domain.endswith("." + doc):
                return SourceType.OFFICIAL_DOCS, 0.95, is_in

        # 3. Official Manufacturer
        for m in cls.OFFICIAL_MANUFACTURERS:
            if domain == m or domain.endswith("." + m):
                return SourceType.OFFICIAL_MANUFACTURER, 0.95, is_in

        # 4. Academic Research
        for a in cls.ACADEMIC_RESEARCH:
            if domain == a or domain.endswith("." + a):
                return SourceType.ACADEMIC_RESEARCH, 0.92, is_in

        # 5. Retailers
        for r in cls.INDIAN_RETAILERS:
            if domain == r or domain.endswith("." + r):
                return SourceType.RETAILER_MARKETPLACE, 0.85, True
        for r in cls.GLOBAL_RETAILERS:
            if domain == r or domain.endswith("." + r):
                return SourceType.RETAILER_MARKETPLACE, 0.80, False

        # 6. Established News
        for n in cls.ESTABLISHED_NEWS:
            if domain == n or domain.endswith("." + n):
                return SourceType.ESTABLISHED_NEWS, 0.85, is_in

        # 7. Reputable Tech
        for t in cls.REPUTABLE_TECH:
            if domain == t or domain.endswith("." + t):
                return SourceType.REPUTABLE_TECH, 0.80, is_in

        # 8. Community Forums
        for f in cls.COMMUNITY_FORUMS:
            if domain == f or domain.endswith("." + f):
                return SourceType.COMMUNITY_FORUM, 0.45, is_in

        # 9. Fallback Unverified
        return SourceType.UNVERIFIED, 0.35, is_in

# Singleton instance
source_registry = SourceRegistry()

