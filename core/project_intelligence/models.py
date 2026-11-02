"""Data models for Project Intelligence, Symbol Indexing, and File Engineering."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class SymbolType(str, Enum):
    """Categorization of code symbols."""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    ROUTE = "route"
    MODEL = "model"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    CONFIG = "config"
    TABLE = "table"
    VIEW = "view"
    MIDDLEWARE = "middleware"
    AUTH_GUARD = "auth_guard"


class AnalysisConfidence(str, Enum):
    """Rigorous epistemic status for discovered symbols and dependencies."""
    CONFIRMED = "CONFIRMED"                      # Static import, explicit AST decorator, foreign key
    INFERRED = "INFERRED"                        # Heuristic caller, naming match, API endpoint string
    PARTIALLY_ANALYZED = "PARTIALLY_ANALYZED"    # Dynamic import, eval, runtime resolved
    UNKNOWN = "UNKNOWN"                          # Unresolved external symbol
    UNSUPPORTED = "UNSUPPORTED"                  # Unsupported language or non-parsed construct


@dataclass
class CodeSymbol:
    """Represents an extracted code symbol (function, class, endpoint, etc.)."""
    name: str
    symbol_type: SymbolType
    file_path: str
    relative_path: str
    line_number: int
    end_line: int = 0
    docstring: str = ""
    parameters: List[str] = field(default_factory=list)
    return_type: str = ""
    signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "symbol_type": self.symbol_type.value,
            "file_path": self.file_path,
            "relative_path": self.relative_path,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "docstring": self.docstring,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "signature": self.signature
        }


@dataclass
class ProjectFile:
    """Represents a scanned source or document file within a project."""
    path: str
    relative_path: str
    extension: str
    language: str
    size_bytes: int
    line_count: int
    last_modified: float
    file_hash: str
    symbols: List[CodeSymbol] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    is_binary: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "extension": self.extension,
            "language": self.language,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "last_modified": self.last_modified,
            "file_hash": self.file_hash,
            "symbols_count": len(self.symbols),
            "dependencies": self.dependencies,
            "is_binary": self.is_binary
        }


@dataclass
class DependencyRelation:
    """Represents an import or caller/callee relationship between modules."""
    source_file: str
    target_module: str
    imported_symbol: str = ""
    line_number: int = 0
    dependency_kind: str = "static_import"  # static_import, dynamic_import, inferred_reference, foreign_key, include, route_handler, api_call, service_call, test_coverage, auth_guard, middleware
    is_inferred: bool = False
    confidence: float = 1.0
    confidence_level: str = AnalysisConfidence.CONFIRMED.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "target_module": self.target_module,
            "imported_symbol": self.imported_symbol,
            "line_number": self.line_number,
            "dependency_kind": self.dependency_kind,
            "is_inferred": self.is_inferred,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level
        }


@dataclass
class FilePatch:
    """Represents an atomic, reversible file modification record."""
    patch_id: str
    file_path: str
    original_content: str
    patched_content: str
    diff: str
    description: str
    timestamp: float = field(default_factory=time.time)
    verified: bool = False
    rolled_back: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "file_path": self.file_path,
            "description": self.description,
            "timestamp": self.timestamp,
            "verified": self.verified,
            "rolled_back": self.rolled_back
        }


@dataclass
class ProjectOverview:
    """High-level architectural summary of a scanned project."""
    project_name: str
    root_path: str
    total_files: int = 0
    total_lines: int = 0
    languages: Dict[str, int] = field(default_factory=dict)
    frameworks: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    test_files_count: int = 0
    documentation_files: List[str] = field(default_factory=list)
    last_scanned: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "root_path": self.root_path,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "entry_points": self.entry_points,
            "test_files_count": self.test_files_count,
            "documentation_files": self.documentation_files,
            "last_scanned": self.last_scanned
        }

