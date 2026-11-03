"""Evidence Manager and Citation Generator for SANTRA Research Engine.
Manages atomic evidence items, validates source traceability, and builds verifiable citations.
"""

import logging
from typing import List, Dict, Any, Optional

from core.research.research_models import EvidenceItem, Source, ResearchCitation, VerificationStatus

logger = logging.getLogger("Jarvis.EvidenceManager")

class EvidenceManager:
    """Manages verified evidence collections and builds citation bibliographies."""

    def build_citations(self, sources: List[Source], evidence: List[EvidenceItem]) -> List[ResearchCitation]:
        """Generates a traceable, indexed citation list from real retrieved sources."""
        citations: List[ResearchCitation] = []
        seen_urls = set()
        idx = 1

        # Prefer sources that yielded verified evidence
        source_evidence_count = {}
        for ev in evidence:
            source_evidence_count[ev.source_url] = source_evidence_count.get(ev.source_url, 0) + 1

        # Sort sources: sources with evidence first, then by authority
        sorted_sources = sorted(
            sources,
            key=lambda s: (source_evidence_count.get(s.url, 0) > 0, s.authority_score),
            reverse=True
        )

        for src in sorted_sources:
            if not src.url or src.url in seen_urls:
                continue
            seen_urls.add(src.url)

            # Find matching excerpt and verification status from evidence or snippet
            matching_excerpt = src.raw_snippet[:150] if src.raw_snippet else src.title
            status_val = "UNVERIFIED"
            for ev in evidence:
                if ev.source_url == src.url:
                    if ev.evidence_excerpt:
                        matching_excerpt = ev.evidence_excerpt[:150]
                    if hasattr(ev.verification_status, "value"):
                        status_val = ev.verification_status.value
                    elif ev.verification_status:
                        status_val = str(ev.verification_status)
                    break

            citations.append(ResearchCitation(
                index=idx,
                title=src.title or f"Source: {src.domain}",
                url=src.url,
                domain=src.domain,
                source_type=src.source_type.value,
                retrieved_at=src.retrieved_at,
                excerpt=matching_excerpt,
                publication_timestamp=src.publication_date,
                verification_status=status_val
            ))
            idx += 1
            if len(citations) >= 8:  # Cap at 8 citations
                break

        return citations

# Singleton instance
evidence_manager = EvidenceManager()

