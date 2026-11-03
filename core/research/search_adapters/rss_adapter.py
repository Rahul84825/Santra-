"""RSS News Search Adapter for SANTRA Research Engine.
Performs live searches across curated RSS feeds including global and Indian news outlets.
"""

import logging
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

from core.research.search_adapters.base import BaseSearchAdapter, SearchResult
from core.research.source_registry import SourceRegistry

logger = logging.getLogger("Jarvis.RSSAdapter")

class RSSSearchAdapter(BaseSearchAdapter):
    """Searches curated RSS news feeds without API keys."""

    FEEDS = {
        # Global
        "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "tech": "https://feeds.feedburner.com/TechCrunch/",
        "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        # India
        "india_thehindu": "https://www.thehindu.com/news/national/feeder/default.rss",
        "india_ndtv": "https://feeds.feedburner.com/ndtvnews-india-news",
        "india_tech": "https://www.gadgets360.com/rss/feeds"
    }

    def __init__(self):
        super().__init__(name="rss_news")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def search(
        self,
        query: str,
        region: str = "in-en",
        language: str = "en",
        limit: int = 5,
        time_filter: Optional[str] = None
    ) -> List[SearchResult]:
        clean_query = query.lower().strip()
        query_words = set(clean_query.split()) if clean_query else set()
        logger.info(f"[RSSAdapter] Searching feeds for query: '{clean_query}'")

        results: List[SearchResult] = []
        seen_urls = set()

        # Prioritize Indian feeds if regional query
        feeds_to_check = list(self.FEEDS.items())
        if "india" in region.lower() or "in" in region.lower():
            feeds_to_check = [f for f in feeds_to_check if "india" in f[0]] + [f for f in feeds_to_check if "india" not in f[0]]

        for feed_name, feed_url in feeds_to_check:
            if len(results) >= limit:
                break
            try:
                req = urllib.request.Request(feed_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    xml_data = resp.read()
                    root = ET.fromstring(xml_data)

                    for item in root.findall(".//item"):
                        title = item.findtext("title", "").strip()
                        desc = item.findtext("description", "").strip()
                        link = item.findtext("link", "").strip()
                        pub_date = item.findtext("pubDate", "").strip()

                        # Strip simple HTML from description
                        desc_clean = desc.split("<")[0].strip() if "<" in desc else desc

                        if not link or link in seen_urls:
                            continue

                        # Check relevance if query provided
                        title_lower = title.lower()
                        desc_lower = desc_clean.lower()
                        combined = f"{title_lower} {desc_lower}"

                        # If user asked for general news or query matches words
                        is_match = False
                        if not query_words or any(q in clean_query for q in ["news", "headline", "breaking"]):
                            is_match = True
                        elif any(word in combined for word in query_words if len(word) > 2):
                            is_match = True

                        if is_match:
                            seen_urls.add(link)
                            domain = SourceRegistry.extract_domain(link)
                            results.append(SearchResult(
                                title=title,
                                url=link,
                                domain=domain,
                                snippet=desc_clean,
                                publication_date=pub_date,
                                adapter_identity=self.name,
                                metadata={"feed": feed_name}
                            ))
                            if len(results) >= limit:
                                break
            except Exception as e:
                logger.debug(f"[RSSAdapter] Feed '{feed_name}' query error: {e}")

        logger.info(f"[RSSAdapter] RSS search found {len(results)} relevant articles.")
        return results

