"""Data models for SANTRA Universal Research & Intelligence Engine.
Defines strongly-typed schemas for research sessions, sources, evidence items,
claims, product observations, price telemetry, and verification lifecycles.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

class ResearchIntent(str, Enum):
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    LIVE_RESEARCH = "LIVE_RESEARCH"
    SHOPPING_RESEARCH = "SHOPPING_RESEARCH"
    PRODUCT_SEARCH = "SHOPPING_RESEARCH"
    PRICE_TRACKING = "SHOPPING_RESEARCH"
    PRODUCT_COMPARISON = "PRODUCT_COMPARISON"
    TECHNOLOGY_RESEARCH = "TECHNOLOGY_RESEARCH"
    SOFTWARE_RESEARCH = "SOFTWARE_RESEARCH"
    PROGRAMMING_RESEARCH = "PROGRAMMING_RESEARCH"
    GAMING_RESEARCH = "GAMING_RESEARCH"
    ACADEMIC_RESEARCH = "ACADEMIC_RESEARCH"
    NEWS_RESEARCH = "NEWS_RESEARCH"
    LOCAL_RESEARCH = "LOCAL_RESEARCH"
    DOCUMENT_RESEARCH = "DOCUMENT_RESEARCH"
    RESEARCH_FOLLOW_UP = "RESEARCH_FOLLOW_UP"

class ResearchStatus(str, Enum):
    PLANNING = "RESEARCH_PLANNING"
    SEARCHING = "SEARCHING"
    EXTRACTING = "EXTRACTING"
    VERIFYING = "VERIFYING"
    COMPARING = "COMPARING"
    REASONING = "REASONING"
    STREAMING_RESULTS = "STREAMING_RESULTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class SourceType(str, Enum):
    OFFICIAL_MANUFACTURER = "OFFICIAL_MANUFACTURER"
    GOVERNMENT_REGULATORY = "GOVERNMENT_REGULATORY"
    OFFICIAL_DOCS = "OFFICIAL_DOCS"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCS"
    PRIMARY_RESEARCH = "ACADEMIC_RESEARCH"
    RETAILER_MARKETPLACE = "RETAILER_MARKETPLACE"
    ESTABLISHED_NEWS = "ESTABLISHED_NEWS"
    REPUTABLE_TECH = "REPUTABLE_TECH"
    ACADEMIC_RESEARCH = "ACADEMIC_RESEARCH"
    INDEPENDENT_REVIEWER = "INDEPENDENT_REVIEWER"
    COMMUNITY_FORUM = "COMMUNITY_FORUM"
    USER_DOCUMENT = "USER_DOCUMENT"
    UNVERIFIED = "UNVERIFIED"

class VerificationStatus(str, Enum):
    VERIFIED_BY_PRIMARY_SOURCE = "VERIFIED_BY_PRIMARY_SOURCE"
    CORROBORATED = "CORROBORATED"
    CONFLICTING = "CONFLICTING"
    UNVERIFIED = "UNVERIFIED"
    OUTDATED = "OUTDATED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    # Backward compatibility
    VERIFIED = "VERIFIED"
    CONTRADICTORY = "CONTRADICTORY"
    STALE = "STALE"
    REJECTED = "REJECTED"

class PriceType(str, Enum):
    SEARCH_RESULT_PRICE = "SEARCH_RESULT_PRICE"
    EXTRACTED_LISTING_PRICE = "EXTRACTED_LISTING_PRICE"
    VERIFIED_PRODUCT_PAGE_PRICE = "VERIFIED_PRODUCT_PAGE_PRICE"
    HISTORICAL_PRICE = "HISTORICAL_PRICE"
    UNAVAILABLE_PRICE = "UNAVAILABLE_PRICE"

class ConflictStatus(str, Enum):
    NO_CONFLICT = "NO_CONFLICT"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    CONFLICT_UNRESOLVED = "CONFLICT_UNRESOLVED"

@dataclass
class ResearchConstraints:
    market: str = "India"
    currency: str = "INR"
    currency_symbol: str = "₹"
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    target_platform: Optional[str] = None
    preferred_brands: List[str] = field(default_factory=list)
    required_features: List[str] = field(default_factory=list)
    time_horizon_days: Optional[int] = None
    language: str = "en"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class Source:
    source_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_id: str = ""
    url: str = ""
    domain: str = ""
    title: str = ""
    source_type: SourceType = SourceType.UNVERIFIED
    publication_date: Optional[str] = None
    retrieved_at: float = field(default_factory=time.time)
    content_hash: str = ""
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    authority_score: float = 0.5
    raw_snippet: str = ""
    adapter_identity: str = "open_web"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["verification_status"] = self.verification_status.value
        return d

@dataclass
class EvidenceItem:
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_id: str = ""
    source_id: str = ""
    claim_text: str = ""
    source_url: str = ""
    source_domain: str = ""
    source_type: SourceType = SourceType.UNVERIFIED
    publication_date: Optional[str] = None
    retrieval_date: float = field(default_factory=time.time)
    evidence_excerpt: str = ""
    confidence: float = 0.8
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    conflict_status: ConflictStatus = ConflictStatus.NO_CONFLICT
    entity_name: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["verification_status"] = self.verification_status.value
        d["conflict_status"] = self.conflict_status.value
        return d

@dataclass
class PriceObservation:
    product_id: str
    seller: str
    price: float
    currency: str = "INR"
    product_url: str = ""
    price_type: PriceType = PriceType.SEARCH_RESULT_PRICE
    availability: str = "Unknown"  # "In Stock", "Out of Stock", "Pre-Order", "Unknown"
    observed_at: float = field(default_factory=time.time)
    is_verified: bool = False
    rating: Optional[float] = None
    review_count: Optional[int] = None
    warranty_info: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["price_type"] = self.price_type.value if hasattr(self.price_type, "value") else str(self.price_type)
        return d

@dataclass
class ProductEntity:
    product_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_id: str = ""
    normalized_name: str = ""
    name: str = ""
    brand: str = ""
    model_number: Optional[str] = None
    model_variant: Optional[str] = None
    asin_or_sku: Optional[str] = None
    category: str = ""
    retailer: str = ""
    seller: Optional[str] = None
    price: Optional[float] = None
    search_result_price: Optional[float] = None
    product_page_price: Optional[float] = None
    price_type: PriceType = PriceType.SEARCH_RESULT_PRICE
    currency: str = "INR"
    availability: str = "Unknown"
    specifications: Dict[str, Any] = field(default_factory=dict)
    compatibility: List[str] = field(default_factory=list)
    warranty: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    product_url: str = ""
    extraction_status: str = "UNVERIFIED"
    source_timestamp: float = field(default_factory=time.time)
    prices: List[PriceObservation] = field(default_factory=list)
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    disadvantages: List[str] = field(default_factory=list)
    recommendation_tier: Optional[str] = None  # "Best Overall", "Best Budget", "Best Specifications", "Best Value", "Best Compatibility"
    rank: int = 1
    recommendation_summary: str = ""
    best_for: str = ""
    field_verification_statuses: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name and self.normalized_name:
            self.name = self.normalized_name
        elif not self.normalized_name and self.name:
            self.normalized_name = self.name
        if not self.disadvantages and self.cons:
            self.disadvantages = list(self.cons)
        elif not self.cons and self.disadvantages:
            self.cons = list(self.disadvantages)
        if self.price is not None:
            if self.price_type == PriceType.SEARCH_RESULT_PRICE and self.search_result_price is None:
                self.search_result_price = self.price
            elif self.price_type == PriceType.VERIFIED_PRODUCT_PAGE_PRICE and self.product_page_price is None:
                self.product_page_price = self.price

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["prices"] = [p.to_dict() for p in self.prices]
        d["price_type"] = self.price_type.value if hasattr(self.price_type, "value") else str(self.price_type)
        return d

@dataclass
class ResearchCitation:
    index: int
    title: str
    url: str
    domain: str
    source_type: str
    retrieved_at: float
    excerpt: str
    publication_timestamp: Optional[float] = None
    verification_status: str = "UNVERIFIED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ResearchSession:
    research_id: str = field(default_factory=lambda: f"res_{int(time.time())}_{str(uuid.uuid4())[:6]}")
    query: str = ""
    normalized_query: str = ""
    intent: ResearchIntent = ResearchIntent.GENERAL_KNOWLEDGE
    constraints: ResearchConstraints = field(default_factory=ResearchConstraints)
    status: ResearchStatus = ResearchStatus.PLANNING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    sources: List[Source] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    products: List[ProductEntity] = field(default_factory=list)
    final_answer: str = ""
    comparison_table: Optional[Dict[str, Any]] = None
    citations: List[ResearchCitation] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_id": self.research_id,
            "query": self.query,
            "normalized_query": self.normalized_query,
            "intent": self.intent.value,
            "constraints": self.constraints.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "sources": [s.to_dict() for s in self.sources],
            "evidence": [e.to_dict() for e in self.evidence],
            "products": [p.to_dict() for p in self.products],
            "final_answer": self.final_answer,
            "comparison_table": self.comparison_table,
            "citations": [c.to_dict() for c in self.citations],
            "error_message": self.error_message
        }

