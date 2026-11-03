"""SANTRA Universal Research & Live Intelligence Engine."""

from core.research.research_models import (
    ResearchSession, Source, EvidenceItem, ProductEntity, PriceObservation,
    ResearchCitation, ResearchIntent, ResearchStatus, SourceType,
    VerificationStatus, ConflictStatus, ResearchConstraints
)
from core.research.research_manager import ResearchManager, research_manager
from core.research.research_router import ResearchRouter, research_router
from core.research.search_manager import SearchManager
from core.research.source_registry import SourceRegistry, source_registry
from core.research.page_extractor import PageExtractor, page_extractor
from core.research.document_extractor import DocumentExtractor, document_extractor
from core.research.claim_extractor import ClaimExtractor, claim_extractor
from core.research.source_verifier import SourceVerifier, source_verifier
from core.research.evidence_manager import EvidenceManager, evidence_manager
from core.research.freshness_manager import FreshnessManager, freshness_manager
from core.research.research_security import ResearchSecurity, research_security
from core.research.research_memory import ResearchMemory, research_memory
from core.research.research_synthesizer import ResearchSynthesizer, research_synthesizer

__all__ = [
    "ResearchSession", "Source", "EvidenceItem", "ProductEntity", "PriceObservation",
    "ResearchCitation", "ResearchIntent", "ResearchStatus", "SourceType",
    "VerificationStatus", "ConflictStatus", "ResearchConstraints",
    "ResearchManager", "research_manager",
    "ResearchRouter", "research_router",
    "SearchManager",
    "SourceRegistry", "source_registry",
    "PageExtractor", "page_extractor",
    "DocumentExtractor", "document_extractor",
    "ClaimExtractor", "claim_extractor",
    "SourceVerifier", "source_verifier",
    "EvidenceManager", "evidence_manager",
    "FreshnessManager", "freshness_manager",
    "ResearchSecurity", "research_security",
    "ResearchMemory", "research_memory",
    "ResearchSynthesizer", "research_synthesizer"
]

