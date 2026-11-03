"""Source Quality, Evidence Verification, and Contradiction Detection Engine.
Evaluates source authority, detects contradictory claims, resolves conflicts,
identifies syndicated duplicate copy, and applies fine-grained verification statuses.
"""

import logging
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict

from core.research.research_models import (
    EvidenceItem, Source, SourceType, VerificationStatus, ConflictStatus
)

logger = logging.getLogger("Jarvis.SourceVerifier")

class SourceVerifier:
    """Detects claim conflicts, syndicated wire copies, and assigns authoritative verification weights."""

    def verify_evidence(self, evidence_list: List[EvidenceItem]) -> List[EvidenceItem]:
        """Analyzes a collection of evidence items, flags contradictions, syndicated copy, and updates status."""
        if not evidence_list:
            return []

        # 1. Detect syndicated copy (sources repeating identical excerpts verbatim)
        self._detect_syndicated_copy(evidence_list)

        # 2. Group evidence by entity and metric to detect corroboration or conflict
        metric_groups = defaultdict(list)
        for ev in evidence_list:
            if ev.metric_name and ev.metric_value:
                key = (ev.entity_name or "general", ev.metric_name)
                metric_groups[key].append(ev)

        PRIMARY_TYPES = [SourceType.OFFICIAL_DOCS, SourceType.OFFICIAL_MANUFACTURER, SourceType.ACADEMIC_RESEARCH]

        for (entity, metric), items in metric_groups.items():
            if len(items) == 1:
                item = items[0]
                if item.source_type in PRIMARY_TYPES and item.confidence >= 0.80:
                    item.verification_status = VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE
                elif item.verification_status == VerificationStatus.UNVERIFIED:
                    item.verification_status = VerificationStatus.INSUFFICIENT_EVIDENCE
                continue

            # Check distinct values
            distinct_values = set(i.metric_value.lower() for i in items if i.metric_value)
            if len(distinct_values) > 1:
                logger.info(f"[SourceVerifier] Contradiction detected for entity '{entity}' metric '{metric}': {distinct_values}")
                self._resolve_metric_conflict(items)
            else:
                # Corroborated across multiple sources
                # Check if independent domains
                domains = set(i.source_domain for i in items if i.source_domain)
                if len(domains) > 1:
                    for it in items:
                        it.conflict_status = ConflictStatus.NO_CONFLICT
                        if it.source_type in PRIMARY_TYPES:
                            it.verification_status = VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE
                        else:
                            it.verification_status = VerificationStatus.CORROBORATED
                else:
                    for it in items:
                        it.conflict_status = ConflictStatus.NO_CONFLICT
                        if it.source_type in PRIMARY_TYPES:
                            it.verification_status = VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE
                        else:
                            it.verification_status = VerificationStatus.VERIFIED

        # 3. For any remaining unclassified items
        for ev in evidence_list:
            if ev.verification_status == VerificationStatus.UNVERIFIED:
                if ev.source_type in PRIMARY_TYPES and ev.confidence >= 0.85:
                    ev.verification_status = VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE
                elif ev.confidence < 0.60:
                    ev.verification_status = VerificationStatus.INSUFFICIENT_EVIDENCE

        return evidence_list

    def _detect_syndicated_copy(self, items: List[EvidenceItem]):
        """Detects identical or near-identical text repeated across different domains."""
        seen_excerpts: Dict[str, str] = {} # excerpt_norm -> first domain
        for it in items:
            raw = (it.evidence_excerpt or "").strip().lower()
            if len(raw) >= 40:
                # Normalize spaces
                norm = " ".join(raw.split())
                if norm in seen_excerpts:
                    original_domain = seen_excerpts[norm]
                    if it.source_domain != original_domain:
                        logger.debug(f"[SourceVerifier] Syndicated copy detected: '{it.source_domain}' mirrors '{original_domain}'.")
                        # Discount confidence slightly because it's syndicated rather than independent
                        it.confidence = max(0.5, it.confidence * 0.85)
                else:
                    seen_excerpts[norm] = it.source_domain

    def _resolve_metric_conflict(self, items: List[EvidenceItem]):
        """Resolves conflict by selecting the most authoritative source or flagging as unresolved."""
        items.sort(key=lambda x: x.confidence, reverse=True)
        top_item = items[0]
        second_item = items[1]

        # If highest authority significantly exceeds second (e.g., official docs vs community forum)
        if top_item.confidence >= second_item.confidence + 0.25:
            top_item.conflict_status = ConflictStatus.CONFLICT_RESOLVED
            top_item.verification_status = (
                VerificationStatus.VERIFIED_BY_PRIMARY_SOURCE 
                if top_item.source_type in [SourceType.OFFICIAL_DOCS, SourceType.OFFICIAL_MANUFACTURER, SourceType.ACADEMIC_RESEARCH]
                else VerificationStatus.VERIFIED
            )
            for lesser in items[1:]:
                lesser.conflict_status = ConflictStatus.CONFLICT_RESOLVED
                lesser.verification_status = VerificationStatus.CONTRADICTORY
        else:
            # Unresolved conflict (e.g. two retailers offering different prices)
            for it in items:
                it.conflict_status = ConflictStatus.CONFLICT_UNRESOLVED
                if it.metric_name == "price_inr":
                    # Legitimate seller price variation is not a defect, it's market pricing
                    it.verification_status = VerificationStatus.VERIFIED
                else:
                    it.verification_status = VerificationStatus.CONTRADICTORY

# Singleton instance
source_verifier = SourceVerifier()
