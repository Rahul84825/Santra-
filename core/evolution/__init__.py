"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Stage 1: Lean Learning & Experience Foundation
Stage 2: Zero-VRAM Knowledge Explorer & Hybrid Retrieval
"""

from core.evolution.storage import EvolutionStorage, evolution_storage
from core.evolution.resource_guard import ResourceGuard, resource_guard
from core.evolution.collector import ExperienceCollector, evolution_collector
from core.evolution.scheduler import EvolutionScheduler, evolution_scheduler
from core.evolution.knowledge_explorer import KnowledgeExplorer, knowledge_explorer

__all__ = [
    "EvolutionStorage",
    "evolution_storage",
    "ResourceGuard",
    "resource_guard",
    "ExperienceCollector",
    "evolution_collector",
    "EvolutionScheduler",
    "evolution_scheduler",
    "KnowledgeExplorer",
    "knowledge_explorer",
]
