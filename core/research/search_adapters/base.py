"""Base Search Adapter Interface for SANTRA Research Engine.
Defines standardized search signatures, result containers, and error telemetry.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class SearchResult:
    title: str
    url: str
    domain: str
    snippet: str
    publication_date: Optional[str] = None
    retrieved_at: float = field(default_factory=time.time)
    adapter_identity: str = "base"
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class BaseSearchAdapter(ABC):
    """Abstract base class for all search adapters."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def search(
        self,
        query: str,
        region: str = "in-en",
        language: str = "en",
        limit: int = 5,
        time_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """Executes a search query and returns standardized SearchResult objects."""
        pass

    def is_available(self) -> bool:
        """Indicates if the search adapter is currently operational."""
        return True

