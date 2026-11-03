"""DuckDuckGo Search Adapter for SANTRA Research Engine.
Performs live searches using DuckDuckGo Instant Answer API and HTML parsing
with target URL extraction, redirect unquoting (uddg), and Indian regional support.
Zero paid credentials required.
"""

import re
import json
import logging
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import List, Dict, Any, Optional

from core.research.search_adapters.base import BaseSearchAdapter, SearchResult
from core.research.source_registry import SourceRegistry

logger = logging.getLogger("Jarvis.DDGAdapter")

class DDGHTMLResultParser(HTMLParser):
    """Parses html.duckduckgo.com/html/ into clean search results with true target URLs."""

    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._curr_result: Optional[Dict[str, str]] = None
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()

        # Target link title
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            raw_href = attrs_dict.get("href", "")
            # DuckDuckGo wraps target URLs in /l/?uddg=<encoded_target_url>
            target_url = raw_href
            if "uddg=" in raw_href:
                match = re.search(r"uddg=([^&]+)", raw_href)
                if match:
                    try:
                        target_url = urllib.parse.unquote(match.group(1))
                    except Exception:
                        target_url = raw_href

            self._curr_result = {
                "title": "",
                "url": target_url,
                "snippet": ""
            }

        # Target snippet
        elif tag == "a" and "result__snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_title:
            self._in_title = False
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            if self._curr_result and self._curr_result.get("url"):
                # Clean up extracted strings
                self._curr_result["title"] = " ".join(self._curr_result["title"].split()).strip()
                self._curr_result["snippet"] = " ".join(self._curr_result["snippet"].split()).strip()
                if self._curr_result["title"]:
                    self.results.append(self._curr_result)
                self._curr_result = None

    def handle_data(self, data: str):
        if self._in_title and self._curr_result is not None:
            self._curr_result["title"] += data
        elif self._in_snippet and self._curr_result is not None:
            self._curr_result["snippet"] += data


class DuckDuckGoSearchAdapter(BaseSearchAdapter):
    """Reliable, zero-credential web search adapter with target URL resolution."""

    def __init__(self):
        super().__init__(name="duckduckgo")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

    def search(
        self,
        query: str,
        region: str = "in-en",
        language: str = "en",
        limit: int = 5,
        time_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """Executes search with Instant Answer check and deep HTML fallback."""
        clean_query = query.strip()
        if not clean_query:
            return []

        logger.info(f"[DDGAdapter] Searching: '{clean_query}' (limit={limit}, region={region})")
        results: List[SearchResult] = []
        seen_urls = set()

        # Step 1: Query DuckDuckGo Instant Answer API for structured abstract
        try:
            ia_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_query)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(ia_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                abstract_url = data.get("AbstractURL", "")
                abstract_text = data.get("AbstractText", "")
                if abstract_url and abstract_text:
                    domain = SourceRegistry.extract_domain(abstract_url)
                    results.append(SearchResult(
                        title=data.get("Heading", "Instant Answer"),
                        url=abstract_url,
                        domain=domain,
                        snippet=abstract_text,
                        adapter_identity=self.name,
                        metadata={"source_type": "instant_answer"}
                    ))
                    seen_urls.add(abstract_url)
        except Exception as e:
            logger.debug(f"[DDGAdapter] Instant answer lookup skipped: {e}")

        # Step 2: Query HTML endpoint for full search results with target URLs
        if len(results) < limit:
            try:
                # Add region parameters if specified
                encoded_q = urllib.parse.quote(clean_query)
                html_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
                if region:
                    html_url += f"&kl={region}"
                if time_filter:
                    html_url += f"&df={time_filter}"

                req = urllib.request.Request(html_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    html_content = resp.read().decode("utf-8", errors="ignore")
                    parser = DDGHTMLResultParser()
                    parser.feed(html_content)

                    for item in parser.results:
                        url = item.get("url", "").strip()
                        title = item.get("title", "").strip()
                        snippet = item.get("snippet", "").strip()

                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        domain = SourceRegistry.extract_domain(url)

                        results.append(SearchResult(
                            title=title,
                            url=url,
                            domain=domain,
                            snippet=snippet,
                            adapter_identity=self.name,
                            metadata={"region": region}
                        ))
                        if len(results) >= limit:
                            break
            except Exception as e:
                logger.error(f"[DDGAdapter] HTML search execution error: {e}")

        logger.info(f"[DDGAdapter] Search returned {len(results)} verified results.")
        return results

