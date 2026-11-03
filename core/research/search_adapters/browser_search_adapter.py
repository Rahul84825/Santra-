"""Browser / CDP Search Adapter for SANTRA Research Engine.
Reuses existing BrowserManager and CDPClient to extract content from active browser tabs.
"""

import logging
from typing import List, Optional

from core.research.search_adapters.base import BaseSearchAdapter, SearchResult
from core.os.cdp_client import CDPClient
from core.research.source_registry import SourceRegistry

logger = logging.getLogger("Jarvis.BrowserSearchAdapter")

class BrowserSearchAdapter(BaseSearchAdapter):
    """Inspects open browser tabs via CDP for local research grounding."""

    def __init__(self):
        super().__init__(name="browser_cdp")
        self.cdp = CDPClient()

    def is_available(self) -> bool:
        """Checks if Chrome is running and CDP is responding."""
        return self.cdp.is_available()

    def search(
        self,
        query: str,
        region: str = "in-en",
        language: str = "en",
        limit: int = 5,
        time_filter: Optional[str] = None
    ) -> List[SearchResult]:
        if not self.is_available():
            logger.debug("[BrowserSearchAdapter] CDP not available; skipping browser tab extraction.")
            return []

        results: List[SearchResult] = []
        try:
            active_info = self.cdp.get_active_tab_info()
            if active_info and active_info.get("url"):
                url = active_info["url"]
                title = active_info.get("title", "Active Browser Tab")
                domain = SourceRegistry.extract_domain(url)
                results.append(SearchResult(
                    title=f"[Open Tab] {title}",
                    url=url,
                    domain=domain,
                    snippet=f"Currently active tab in user browser: {title}",
                    adapter_identity=self.name,
                    metadata={"source": "cdp_active_tab"}
                ))
        except Exception as e:
            logger.debug(f"[BrowserSearchAdapter] Error querying active browser tab: {e}")

        return results

