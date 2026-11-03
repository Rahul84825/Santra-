"""Search Manager for SANTRA Research Engine.
Coordinates search adapters, applies regional India-first filters, expands queries,
deduplicates results, and converts search telemetry into typed Source records.
"""

import time
import logging
from typing import List, Dict, Any, Optional, Callable

from core.research.research_models import Source, SourceType, VerificationStatus, ResearchConstraints
from core.research.source_registry import source_registry, SourceRegistry
from core.research.search_adapters.base import BaseSearchAdapter, SearchResult
from core.research.search_adapters.ddg_adapter import DuckDuckGoSearchAdapter
from core.research.search_adapters.rss_adapter import RSSSearchAdapter
from core.research.search_adapters.browser_search_adapter import BrowserSearchAdapter

logger = logging.getLogger("Jarvis.SearchManager")

class SearchManager:
    """Orchestrates multi-adapter search, query expansion, and source conversion."""

    def __init__(self, adapters: Optional[List[BaseSearchAdapter]] = None):
        if adapters is not None:
            self.adapters = adapters
        else:
            self.adapters = [
                DuckDuckGoSearchAdapter(),
                RSSSearchAdapter(),
                BrowserSearchAdapter()
            ]

    def expand_query_for_market(self, query: str, constraints: ResearchConstraints, category: str = "general") -> List[str]:
        """Expands a search query with targeted regional and domain keywords."""
        queries = [query]
        clean_q = query.lower().strip()

        # India-First Shopping Expansion
        if category in ["shopping", "product", "pricing", "SHOPPING_RESEARCH", "PRODUCT_COMPARISON"]:
            if constraints.market == "India" or "india" in clean_q or "₹" in clean_q or "rupees" in clean_q or "inr" in clean_q:
                # Add Indian marketplace queries if not already present
                if "amazon" not in clean_q and "flipkart" not in clean_q:
                    queries.append(f"{query} amazon india price")
                    queries.append(f"{query} flipkart")
                elif "price" not in clean_q:
                    queries.append(f"{query} price in india")
        
        # Technology / Programming Expansion
        elif category in ["programming", "PROGRAMMING_RESEARCH", "software", "SOFTWARE_RESEARCH"]:
            if "docs" not in clean_q and "documentation" not in clean_q:
                queries.append(f"{query} official documentation")

        # Gaming Expansion
        elif category in ["gaming", "GAMING_RESEARCH"]:
            if "patch" not in clean_q and "valorant" in clean_q:
                queries.append(f"{query} patch notes latest")

        return queries[:3]

    def search(
        self,
        query: str,
        research_id: str,
        constraints: Optional[ResearchConstraints] = None,
        category: str = "general",
        limit_per_query: int = 5,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> List[Source]:
        """Executes coordinated multi-adapter search and returns structured Source objects."""
        if not query or not query.strip():
            return []

        c = constraints or ResearchConstraints()
        search_queries = self.expand_query_for_market(query, c, category=category)
        logger.info(f"[SearchManager] Executing research search for queries: {search_queries}")

        aggregated_results: List[SearchResult] = []
        seen_urls = set()

        for q in search_queries:
            if is_cancelled and is_cancelled():
                logger.info("[SearchManager] Search cancelled by caller.")
                break

            for adapter in self.adapters:
                if is_cancelled and is_cancelled():
                    break
                try:
                    # Choose region filter
                    reg = "in-en" if c.market == "India" else "wt-wt"
                    res_list = adapter.search(q, region=reg, limit=limit_per_query)
                    for r in res_list:
                        norm_url = r.url.split("?")[0].rstrip("/").lower()
                        if norm_url and norm_url not in seen_urls:
                            seen_urls.add(norm_url)
                            aggregated_results.append(r)
                except Exception as ae:
                    logger.warning(f"[SearchManager] Adapter '{adapter.name}' failed on query '{q}': {ae}")

        # Convert SearchResults to strongly-typed Source models
        sources: List[Source] = []
        for res in aggregated_results:
            domain = res.domain or SourceRegistry.extract_domain(res.url)
            src_type, auth_score, is_in = source_registry.classify_domain(res.url or domain)

            # Boost authority score if regional match aligns with query constraints
            if c.market == "India" and is_in:
                auth_score = min(1.0, auth_score + 0.05)

            source_obj = Source(
                research_id=research_id,
                url=res.url,
                domain=domain,
                title=res.title,
                source_type=src_type,
                publication_date=res.publication_date,
                retrieved_at=res.retrieved_at,
                verification_status=VerificationStatus.UNVERIFIED,
                authority_score=auth_score,
                raw_snippet=res.snippet,
                adapter_identity=res.adapter_identity
            )
            sources.append(source_obj)

        # Sort sources by authority score descending
        sources.sort(key=lambda s: s.authority_score, reverse=True)
        logger.info(f"[SearchManager] Aggregated {len(sources)} unique sources for research session '{research_id}'.")
        return sources

