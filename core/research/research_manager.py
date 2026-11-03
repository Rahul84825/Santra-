"""Central Universal Research Engine Orchestrator for SANTRA.
Coordinates intent classification, source discovery, content extraction,
evidence verification, conflict resolution, Nemotron reasoning, and persistent memory.
"""

import time
import logging
from typing import Dict, List, Any, Optional, Callable

from core.research.research_models import (
    ResearchSession, Source, SourceType, EvidenceItem, ProductEntity, PriceObservation,
    ResearchCitation, ResearchIntent, ResearchStatus, ResearchConstraints, VerificationStatus
)
from core.research.research_router import research_router
from core.research.search_manager import SearchManager
from core.research.page_extractor import page_extractor
from core.research.document_extractor import document_extractor
from core.research.claim_extractor import claim_extractor
from core.research.source_verifier import source_verifier
from core.research.evidence_manager import evidence_manager
from core.research.research_synthesizer import research_synthesizer
from core.research.research_memory import research_memory
from core.ai.provider_manager import ProviderManager

logger = logging.getLogger("Jarvis.ResearchManager")

class ResearchManager:
    """Central orchestrator for all online research, evidence verification, and live knowledge synthesis."""

    def __init__(self, search_manager: Optional[SearchManager] = None, provider_manager: Optional[ProviderManager] = None):
        self.search_manager = search_manager or SearchManager()
        self.active_session: Optional[ResearchSession] = None
        self.provider_manager = provider_manager or ProviderManager()
        try:
            self.restore_active_session()
        except Exception as e:
            logger.debug(f"[ResearchManager] Could not restore active session on startup: {e}")

    def restore_active_session(self) -> Optional[ResearchSession]:
        """Restores the most recent research session from durable SQLite memory if available."""
        try:
            latest = research_memory.get_latest_session()
            if latest and not self.active_session:
                cat = latest.get("category", "")
                intent_enum = ResearchIntent.LIVE_RESEARCH
                for m in ResearchIntent:
                    if m.value == cat:
                        intent_enum = m
                        break

                sess = ResearchSession(
                    research_id=latest["research_id"],
                    query=latest["query"],
                    normalized_query=latest.get("normalized_query") or latest["query"],
                    intent=intent_enum
                )
                sess.final_answer = latest.get("final_answer") or ""

                # Rehydrate products for continuity
                with research_memory._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM research_products WHERE research_id = ?", (sess.research_id,))
                    for row in cursor.fetchall():
                        p = ProductEntity(
                            product_id=row["product_id"],
                            research_id=sess.research_id,
                            normalized_name=row["normalized_name"],
                            brand=row["brand"] or "",
                            category=row["category"] or ""
                        )
                        sess.products.append(p)
                self.active_session = sess
                logger.info(f"[ResearchManager] Restored active research session '{sess.research_id}' from SQLite database.")
                return sess
        except Exception as re:
            logger.debug(f"[ResearchManager] Session rehydration fallback: {re}")
        return self.active_session

    def execute_research(
        self,
        query: str,
        on_stage_change: Optional[Callable[[str, str], None]] = None,
        on_sentence_chunk: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """Executes the complete multi-stage research lifecycle."""
        t0 = time.time()
        logger.info(f"[ResearchManager] Starting research operation for: '{query}'")

        def _update_stage(status: ResearchStatus, description: str):
            if session:
                session.status = status
            if on_stage_change:
                try:
                    on_stage_change(status.value, description)
                except Exception as ce:
                    logger.debug(f"Error in on_stage_change callback: {ce}")

        # Stage 1: Intent Classification & Session Initialization
        intent, constraints = research_router.classify_research_intent(query)
        if intent is None:
            intent = ResearchIntent.LIVE_RESEARCH
        
        # Handle Follow-Up Context
        if intent == ResearchIntent.RESEARCH_FOLLOW_UP and self.active_session:
            logger.info(f"[ResearchManager] Linking query as follow-up to active session '{self.active_session.research_id}'.")
            combined_query = f"{self.active_session.query} -> Follow-up: {query}"
            session = ResearchSession(
                query=query,
                normalized_query=combined_query,
                intent=self.active_session.intent,
                constraints=self.active_session.constraints
            )
            # Inherit previous verified sources and products as baseline
            session.sources = list(self.active_session.sources)
            session.evidence = list(self.active_session.evidence)
            session.products = list(self.active_session.products)

            # Evaluate Price Freshness if query asks about price validity
            if any(k in query.lower() for k in ["price still valid", "still valid", "valid price", "price valid", "is that price"]):
                from core.research.freshness_manager import freshness_manager
                for prod in session.products:
                    staleness = freshness_manager.get_staleness_description("product_price", prod.source_timestamp)
                    age_min = max(1, int((time.time() - prod.source_timestamp) / 60.0))
                    claim_text = f"Product '{prod.name}' observed price ₹{prod.price:,.0f} ({prod.price_type.value}) recorded {age_min}m ago ({staleness})."
                    session.evidence.append(EvidenceItem(
                        research_id=session.research_id,
                        source_id="freshness_verifier",
                        claim_text=claim_text,
                        source_url=prod.product_url or "https://santra.internal/freshness",
                        source_domain=prod.retailer or "Retailer Listing",
                        source_type=SourceType.RETAILER_MARKETPLACE,
                        evidence_excerpt=claim_text,
                        confidence=0.95,
                        verification_status=VerificationStatus.VERIFIED,
                        metric_name="price_freshness",
                        metric_value=staleness
                    ))
        else:
            session = ResearchSession(
                query=query,
                normalized_query=query.strip(),
                intent=intent,
                constraints=constraints
            )

        _update_stage(ResearchStatus.PLANNING, f"Formulating research plan for {intent.value} ({constraints.market} market)")

        if is_cancelled and is_cancelled():
            session.status = ResearchStatus.CANCELLED
            return {"success": False, "status": "CANCELLED", "message": "Research cancelled by caller."}

        # Stage 2: Source Discovery & Search (Skip if stable general knowledge without explicit live search request)
        if intent != ResearchIntent.GENERAL_KNOWLEDGE or any(w in query.lower() for w in ["latest", "current", "news", "price", "today"]):
            _update_stage(ResearchStatus.SEARCHING, f"Searching online sources across {constraints.market} region...")
            discovered_sources = self.search_manager.search(
                query=query,
                research_id=session.research_id,
                constraints=constraints,
                category=intent.value,
                limit_per_query=4,
                is_cancelled=is_cancelled
            )
            # Merge with existing sources if follow-up
            existing_urls = {s.url for s in session.sources}
            for ds in discovered_sources:
                if ds.url not in existing_urls:
                    session.sources.append(ds)

        if is_cancelled and is_cancelled():
            session.status = ResearchStatus.CANCELLED
            return {"success": False, "status": "CANCELLED", "message": "Research cancelled by caller."}

        # Stage 3: Content Extraction (Deep fetch on top 2 primary sources)
        _update_stage(ResearchStatus.EXTRACTING, f"Extracting specifications and content from {len(session.sources)} sources...")
        extracted_signals_map = {}
        for src in session.sources[:2]:
            if is_cancelled and is_cancelled():
                break
            if src.url.startswith("http"):
                page_data = page_extractor.extract_url(src.url)
                if page_data.get("success"):
                    src.content_hash = page_data.get("content_hash", "")
                    if page_data.get("signals"):
                        extracted_signals_map[src.source_id] = page_data["signals"]

        # Stage 4: Claim and Evidence Extraction
        all_new_evidence: List[EvidenceItem] = []
        for src in session.sources:
            signals = extracted_signals_map.get(src.source_id)
            claims = claim_extractor.extract_claims_from_source(src, page_signals=signals)
            all_new_evidence.extend(claims)

            # If marketplace source or product search intent, extract structured product entity
            if src.source_type == SourceType.RETAILER_MARKETPLACE or session.intent in [ResearchIntent.PRODUCT_SEARCH, ResearchIntent.PRICE_TRACKING]:
                prod = claim_extractor.extract_product_from_source(src, page_signals=signals)
                if prod:
                    session.products.append(prod)
        session.evidence.extend(all_new_evidence)

        # Stage 5: Evidence Verification & Conflict Resolution
        _update_stage(ResearchStatus.VERIFYING, f"Verifying {len(session.evidence)} factual claims and resolving conflicts...")
        session.evidence = source_verifier.verify_evidence(session.evidence)

        # Stage 6: Nemotron Reasoning Synthesis
        _update_stage(ResearchStatus.REASONING, "Synthesizing verified evidence with NVIDIA Nemotron...")
        evidence_prompt = research_synthesizer.build_evidence_prompt(session)

        # Build citations
        session.citations = evidence_manager.build_citations(session.sources, session.evidence)

        # Dispatch reasoning call to NVIDIA Nemotron
        reasoning_output = ""
        system_content = "You are SANTRA's Universal Research and Knowledge Engine. Provide factual, cited answers based on provided evidence."
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": evidence_prompt}
        ]
        try:
            if on_sentence_chunk:
                _update_stage(ResearchStatus.STREAMING_RESULTS, "Streaming cited research answer...")
                for chunk in self.provider_manager.stream_response(
                    messages=messages,
                    is_cancelled=is_cancelled
                ):
                    if is_cancelled and is_cancelled():
                        break
                    reasoning_output += chunk
                    on_sentence_chunk(chunk)
            else:
                resp = self.provider_manager.generate_response(
                    messages=messages,
                    is_cancelled=is_cancelled
                )
                if isinstance(resp, dict):
                    reasoning_output = resp.get("text", "")
                elif isinstance(resp, str):
                    reasoning_output = resp
                else:
                    reasoning_output = str(resp or "")
        except Exception as ne:
            logger.error(f"[ResearchManager] NVIDIA Nemotron reasoning failed: {ne}")
            reasoning_output = f"I encountered an error synthesizing research evidence: {ne}"

        # Terminal cancellation check
        if is_cancelled and is_cancelled():
            session.status = ResearchStatus.CANCELLED
            _update_stage(ResearchStatus.CANCELLED, "Research cancelled.")
            logger.info(f"[ResearchManager] Research session '{session.research_id}' cancelled by caller.")
            return {
                "success": False,
                "research_id": session.research_id,
                "intent": session.intent.value,
                "status": "CANCELLED",
                "message": "Research operation cancelled by caller.",
                "latency_ms": (time.time() - t0) * 1000
            }

        # Stage 7: Final Answer Formatting and Citation Attachment
        session.final_answer = research_synthesizer.format_final_response(reasoning_output, session.citations)
        session.completed_at = time.time()
        session.status = ResearchStatus.COMPLETED
        _update_stage(ResearchStatus.COMPLETED, "Research completed.")

        # Stage 8: Persistent Knowledge Storage
        try:
            research_memory.save_session(session)
        except Exception as me:
            logger.error(f"[ResearchManager] Failed to persist session to database: {me}")

        # Retain as active research session for natural follow-ups
        self.active_session = session

        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"[ResearchManager] Research session '{session.research_id}' finished in {elapsed_ms:.1f}ms with {len(session.citations)} citations.")

        return {
            "success": True,
            "research_id": session.research_id,
            "intent": session.intent.value,
            "status": session.status.value,
            "answer": session.final_answer,
            "sources_count": len(session.sources),
            "evidence_count": len(session.evidence),
            "citations": [c.to_dict() for c in session.citations],
            "products": session.products,
            "evidence": session.evidence,
            "latency_ms": elapsed_ms
        }

# Singleton instance
research_manager = ResearchManager()
