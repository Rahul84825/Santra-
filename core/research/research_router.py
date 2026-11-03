"""Research Intent Router and Parameter Extraction for SANTRA Research Engine.
Classifies incoming inquiries into distinct research domains, extracts budget
and platform constraints, and identifies conversational research follow-ups.
Guarantees local deterministic OS commands are never classified as research.
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional

from core.research.research_models import ResearchIntent, ResearchConstraints

logger = logging.getLogger("Jarvis.ResearchRouter")

class ResearchRouter:
    """Specialized classifier and constraint extractor for research queries."""

    # Pronominal and context continuation patterns
    FOLLOW_UP_PATTERNS = [
        r"^(?:find\s+)?(?:more\s+options|more\s+alternatives|other\s+options|other\s+alternatives)\b",
        r"^(?:explain|tell\s+me\s+about|describe)\s+the\s+(?:first|1st|second|2nd|third|3rd|fourth|4th|last)\s+(?:one|product|option|item)\b",
        r"^(?:what\s+are\s+its|what's\s+its)\s+(?:disadvantages|cons|pros|advantages|flaws|drawbacks|specs)\b",
        r"^(?:is\s+there\s+a\s+)?(?:cheaper\s+option|cheaper\s+alternative|better\s+alternative)\b",
        r"^(?:find\s+)?(?:something|anything)\s+cheaper\b",
        r"^(?:is\s+that|is\s+this|is\s+the)\s+price\s+still\s+valid\b",
        r"^(?:what\s+about\s+the|does\s+it\s+have\s+a?)\s*(?:warranty|guarantee|return\s+policy)\b",
        r"^(?:is\s+it|are\s+they)\s+still\s+available\b",
        r"^give\s+me\s+the\s+cheapest\s+(?:one|option|product)\b",
        r"^which\s+one\s+(?:has|features|comes\s+with)\s+(?:hall\s+effect|bluetooth|wireless|ssd)\b",
        r"^(?:which\s+one\s+is\s+more\s+reliable|which\s+is\s+more\s+reliable)\b",
        r"^(?:compare\s+the\s+top\s+\w+|compare\s+them)\b",
        r"^(?:explain\s+why\s+you\s+selected\s+that\s+one|why\s+that\s+one)\b",
        r"^(?:under\s+two\s+thousand\s+rupees|under\s+[\w\s]+\s+rupees)\b"
    ]

    OS_COMMAND_PREFIXES = (
        "open ", "launch ", "close ", "kill ", "quit ", "minimize", "maximize",
        "set volume", "volume ", "mute", "unmute", "sleep", "restart", "shutdown",
        "turn on camera", "turn off camera", "screenshot", "capture screen",
        "switch to ", "work on ", "test audio", "test speaker", "test microphone"
    )

    def is_research_query(self, text: str) -> bool:
        """Fast pre-check to distinguish research inquiries from ordinary chat or local commands."""
        clean = text.lower().strip()
        if any(clean.startswith(p) for p in self.OS_COMMAND_PREFIXES):
            return False
        intent, _ = self.classify_research_intent(text)
        return intent is not None and intent != ResearchIntent.GENERAL_KNOWLEDGE

    def classify_research_intent(self, text: str) -> Tuple[Optional[ResearchIntent], ResearchConstraints]:
        """Classifies text into ResearchIntent and extracts constraints. Returns None if not research."""
        clean = text.lower().strip()
        constraints = self._extract_constraints(clean)

        # Reject local OS imperatives immediately
        if any(clean.startswith(p) for p in self.OS_COMMAND_PREFIXES):
            return None, constraints

        # 1. Follow-up detection
        for pat in self.FOLLOW_UP_PATTERNS:
            if re.search(pat, clean):
                logger.info(f"[ResearchRouter] Classified as RESEARCH_FOLLOW_UP: '{text}'")
                return ResearchIntent.RESEARCH_FOLLOW_UP, constraints

        # 2. Explicit research / online discovery prompt
        if clean.startswith("research ") or clean.startswith("do research on ") or "look up on the web" in clean or "find online" in clean:
            logger.info(f"[ResearchRouter] Classified as LIVE_RESEARCH: '{text}'")
            return ResearchIntent.LIVE_RESEARCH, constraints

        # 3. Comparison detection
        if any(term in clean for term in ["compare", " vs ", " versus ", "which is better", "difference between"]):
            logger.info(f"[ResearchRouter] Classified as PRODUCT_COMPARISON: '{text}'")
            return ResearchIntent.PRODUCT_COMPARISON, constraints

        # 4. Shopping and product research
        if any(term in clean for term in [
            "best budget", "best controller", "best laptop", "best phone", "best mouse", "best keyboard",
            "best headphones", "best gpu", "price in india", "under ₹", "under rs", "under inr",
            "find me a good", "good controller", "good gaming mouse", "best value", "laptop under", "mouse under", "controller under"
        ]) or (("best" in clean or "buy" in clean or "good" in clean) and any(c in clean for c in ["controller", "laptop", "phone", "headset", "mouse", "gpu", "monitor", "earbuds"])):
            logger.info(f"[ResearchRouter] Classified as SHOPPING_RESEARCH: '{text}'")
            return ResearchIntent.SHOPPING_RESEARCH, constraints

        # 5. Gaming research (patches, agents, maps, meta)
        if any(term in clean for term in ["valorant", "clash royale", "patch notes", "meta deck", "agent lineup", "game update"]):
            logger.info(f"[ResearchRouter] Classified as GAMING_RESEARCH: '{text}'")
            return ResearchIntent.GAMING_RESEARCH, constraints

        # 6. Programming & documentation research
        if any(term in clean for term in [
            "latest python version", "documentation for", "pypi package",
            "api reference for", "package version of", "official docs"
        ]) or (any(lang in clean for lang in ["python", "c++", "cpp", "javascript", "rust", "react", "fastapi"]) and any(w in clean for w in ["version", "docs", "documentation", "api reference"])):
            logger.info(f"[ResearchRouter] Classified as PROGRAMMING_RESEARCH: '{text}'")
            return ResearchIntent.PROGRAMMING_RESEARCH, constraints

        # 7. Technology & Hardware releases
        if any(term in clean for term in [
            "latest nvidia", "latest gpu", "latest cpu", "rtx 50", "intel core ultra", "windows 11 update",
            "new hardware releases"
        ]):
            logger.info(f"[ResearchRouter] Classified as TECHNOLOGY_RESEARCH: '{text}'")
            return ResearchIntent.TECHNOLOGY_RESEARCH, constraints

        # 8. News & Current Events
        if any(term in clean for term in ["latest news", "breaking news", "headlines today", "recent announcements", "tech news today", "technology news"]) or ("news" in clean and any(w in clean for w in ["latest", "today", "current", "recent"])):
            logger.info(f"[ResearchRouter] Classified as NEWS_RESEARCH: '{text}'")
            return ResearchIntent.NEWS_RESEARCH, constraints

        # 9. Document & Local File Research
        if any(term in clean for term in ["in this file", "in my document", "read this pdf", "summarize this file"]):
            logger.info(f"[ResearchRouter] Classified as DOCUMENT_RESEARCH: '{text}'")
            return ResearchIntent.DOCUMENT_RESEARCH, constraints

        # 10. Stable / Foundational Knowledge
        if any(clean.startswith(p) for p in ["what is ", "explain ", "how does ", "how do ", "define "]) and not any(k in clean for k in ["latest", "price", "current", "cost", "news", "under", "today"]):
            logger.info(f"[ResearchRouter] Classified as GENERAL_KNOWLEDGE: '{text}'")
            return ResearchIntent.GENERAL_KNOWLEDGE, constraints

        return None, constraints

    def _extract_constraints(self, text: str) -> ResearchConstraints:
        """Extracts budget caps, market tags, and hardware platforms."""
        constraints = ResearchConstraints(market="India", currency="INR", currency_symbol="₹")

        # Budget extraction: e.g. under 2000, under 60k, under 60,000, under ₹1,500
        budget_match = re.search(r"under\s*(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(k)?\b", text, re.IGNORECASE)
        if budget_match:
            try:
                base_val = float(budget_match.group(1).replace(",", ""))
                if budget_match.group(2):  # 'k' multiplier (e.g. 60k = 60,000)
                    base_val *= 1000.0
                constraints.budget_max = base_val
            except ValueError:
                pass
        else:
            word_budgets = [
                ("two thousand", 2000.0),
                ("three thousand", 3000.0),
                ("five thousand", 5000.0),
                ("ten thousand", 10000.0),
                ("fifteen hundred", 1500.0),
                ("sixty thousand", 60000.0),
                ("fifty thousand", 50000.0),
                ("forty thousand", 40000.0)
            ]
            for wb, val in word_budgets:
                if f"under {wb}" in text:
                    constraints.budget_max = val
                    break

        # Platform extraction
        if "pc" in text or "windows" in text:
            constraints.target_platform = "PC (Windows)"
        elif "ps5" in text or "playstation" in text:
            constraints.target_platform = "PlayStation"
        elif "xbox" in text:
            constraints.target_platform = "Xbox"
        elif "android" in text or "mobile" in text:
            constraints.target_platform = "Android Mobile"

        return constraints

# Singleton instance
research_router = ResearchRouter()
