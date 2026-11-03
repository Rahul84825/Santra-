"""Search adapters package for SANTRA Research Engine."""

from core.research.search_adapters.base import BaseSearchAdapter, SearchResult
from core.research.search_adapters.ddg_adapter import DuckDuckGoSearchAdapter
from core.research.search_adapters.rss_adapter import RSSSearchAdapter
from core.research.search_adapters.browser_search_adapter import BrowserSearchAdapter

__all__ = [
    "BaseSearchAdapter",
    "SearchResult",
    "DuckDuckGoSearchAdapter",
    "RSSSearchAdapter",
    "BrowserSearchAdapter"
]

