"""Freshness and Expiry Manager for SANTRA Research Engine.
Enforces domain-specific time-to-live (TTL) policies ensuring stale information
(outdated prices, old patches, superseded software versions) is not presented as current.
"""

import time
import logging
from typing import Dict

logger = logging.getLogger("Jarvis.FreshnessManager")

class FreshnessManager:
    """Calculates freshness and expiration for cached research facts and prices."""

    DEFAULT_TTLS: Dict[str, float] = {
        "stock_availability": 3600.0,            # 1 hour
        "breaking_news": 7200.0,                 # 2 hours
        "product_price": 86400.0,                # 24 hours
        "game_patch": 604800.0,                  # 7 days
        "software_version": 604800.0,            # 7 days
        "hardware_specifications": 2592000.0,    # 30 days
        "product_warranty": 2592000.0,           # 30 days
        "fundamental_concept": 31536000.0        # 365 days
    }

    def get_ttl_seconds(self, info_type: str) -> float:
        """Returns the TTL in seconds for a given class of information."""
        return self.DEFAULT_TTLS.get(info_type.lower().strip(), 86400.0)

    def is_fresh(self, info_type: str, observed_at: float) -> bool:
        """Determines if the observed data point is still valid."""
        ttl = self.get_ttl_seconds(info_type)
        now = time.time()
        age = now - observed_at
        return age <= ttl

    def get_staleness_description(self, info_type: str, observed_at: float) -> str:
        """Returns human-readable staleness warning if expired."""
        if self.is_fresh(info_type, observed_at):
            return "Current"
        age_hours = (time.time() - observed_at) / 3600.0
        if age_hours < 48:
            return f"Stale ({age_hours:.0f} hours old)"
        age_days = age_hours / 24.0
        return f"Expired ({age_days:.0f} days old; revalidation required)"

# Singleton instance
freshness_manager = FreshnessManager()

