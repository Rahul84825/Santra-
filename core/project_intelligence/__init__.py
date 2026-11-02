"""Project Intelligence & File Engineering Package."""

from core.project_intelligence.models import (
    ProjectFile,
    CodeSymbol,
    SymbolType,
    DependencyRelation,
    FilePatch,
    ProjectOverview
)
from core.project_intelligence.scanner import project_scanner, ProjectScanner
from core.project_intelligence.context_engine import project_context_engine, ProjectContextEngine
from core.project_intelligence.file_engineer import file_engineer, FileEngineer
from core.project_intelligence.watcher import project_watcher, ProjectWatcher

__all__ = [
    "ProjectFile",
    "CodeSymbol",
    "SymbolType",
    "DependencyRelation",
    "FilePatch",
    "ProjectOverview",
    "project_scanner",
    "ProjectScanner",
    "project_context_engine",
    "ProjectContextEngine",
    "file_engineer",
    "FileEngineer",
    "project_watcher",
    "ProjectWatcher"
]

