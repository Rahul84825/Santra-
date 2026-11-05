"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Evolution Scheduler Module

Runs 15-minute periodic background maintenance under ResourceGuard supervision.
Maintains FTS indexes, compiles execution health reports, and logs system telemetry.
"""

import os
import json
import time
import logging
import datetime
import threading
from typing import Optional, Dict, Any, Callable
from core.evolution.storage import EvolutionStorage, evolution_storage
from core.evolution.resource_guard import ResourceGuard, resource_guard
from core.evolution.collector import ExperienceCollector, evolution_collector

logger = logging.getLogger("Santra.Evolution.Scheduler")


class EvolutionScheduler:
    """Resource-governed background scheduler for ALEE idle maintenance."""

    def __init__(
        self,
        interval_seconds: float = 900.0,  # 15 minutes
        storage: Optional[EvolutionStorage] = None,
        guard: Optional[ResourceGuard] = None,
        collector: Optional[ExperienceCollector] = None,
        report_path: Optional[str] = None
    ):
        self.interval_seconds = interval_seconds
        self.storage = storage or evolution_storage
        self.guard = guard or resource_guard
        self.collector = collector or evolution_collector

        if report_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_dir = os.path.join(base_dir, "logs", "evolution")
            os.makedirs(log_dir, exist_ok=True)
            self.report_path = os.path.join(log_dir, "health_report.json")
        else:
            self.report_path = report_path
            os.makedirs(os.path.dirname(os.path.abspath(self.report_path)), exist_ok=True)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_run_time: float = 0.0
        self.on_maintenance_complete: Optional[Callable[[Dict[str, Any]], None]] = None

    def start(self):
        """Starts the scheduler thread if not already running."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="ALEE-Scheduler",
            daemon=True
        )
        self._thread.start()
        logger.info("[SCHEDULER] Evolution background scheduler started (15m interval).")

    def stop(self, timeout: float = 3.0):
        """Stops the scheduler thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("[SCHEDULER] Evolution scheduler stopped.")

    def _scheduler_loop(self):
        """Periodic maintenance loop."""
        # Initial short grace period (30 seconds) after boot before first check
        if self._stop_event.wait(timeout=30.0):
            return

        while not self._stop_event.is_set():
            try:
                # Check ResourceGuard before performing maintenance
                if self.guard.can_run_background_tasks():
                    logger.info("[SCHEDULER] System idle and healthy. Executing maintenance cycle...")
                    self.run_maintenance_now()
                    self._last_run_time = time.time()
                else:
                    snap = self.guard.get_system_snapshot()
                    reasons = ", ".join(snap.get("reasons", [])) or "Resource constraints"
                    logger.debug(f"[SCHEDULER] Deferring maintenance cycle: {reasons}")
            except Exception as e:
                logger.warning(f"[SCHEDULER] Maintenance cycle error: {e}", exc_info=True)

            # Sleep in 5-second increments to allow responsive shutdown
            slept = 0.0
            while slept < self.interval_seconds and not self._stop_event.is_set():
                time.sleep(5.0)
                slept += 5.0

    def run_maintenance_now(self) -> Dict[str, Any]:
        """
        Executes an immediate maintenance cycle:
        1. Optimizes FTS5 index.
        2. Compiles database stats.
        3. Collects system resource snapshot.
        4. Writes health report JSON atomically.
        """
        logger.info("[SCHEDULER] Running ALEE maintenance tasks...")

        # 1. Optimize full-text index
        self.storage.optimize_fts()

        # 1B. Index local documentation (docs/) during idle window
        try:
            from core.evolution.knowledge_explorer import knowledge_explorer
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            docs_dir = os.path.join(base_dir, "docs")
            if os.path.exists(docs_dir):
                knowledge_explorer.index_directory(docs_dir, category="architecture_docs")
        except Exception as de:
            logger.debug(f"[SCHEDULER] Local docs indexing notice: {de}")

        # 2. Gather database stats
        db_stats = self.storage.get_stats()

        # 3. Gather system snapshot
        sys_snap = self.guard.get_system_snapshot()

        # 4. Fetch active aliases
        active_aliases = self.storage.get_active_aliases(min_confidence=3)

        # 4B. Run Actionable Weakness Detection & Self-Benchmarks
        weakness_analysis = {}
        benchmarks = {}
        try:
            from core.evolution.evaluator import PerformanceEvaluator
            evaluator = PerformanceEvaluator(
                storage=self.storage,
                collector=self.collector
            )
            weakness_analysis = evaluator.analyze_weaknesses()
            benchmarks = evaluator.run_regression_benchmarks()
        except Exception as ee:
            logger.warning(f"[SCHEDULER] Evaluator execution error: {ee}")

        # 4C. Generate / Refresh Evolution Proposals (Stage 5)
        proposals_summary = {}
        try:
            from core.evolution.evolution_manager import EvolutionManager
            evo_mgr = EvolutionManager(
                storage=self.storage,
                evaluator=evaluator if 'evaluator' in locals() else None,
                collector=self.collector
            )
            pending_props = evo_mgr.generate_proposals()
            proposals_summary = {
                "pending_count": len(pending_props),
                "proposals": [
                    {
                        "id": p["proposal_id"],
                        "type": p["proposal_type"],
                        "target": p["target_key"],
                        "reason": p["reason"]
                    } for p in pending_props[:5]
                ]
            }
            # Refresh stats to reflect newly drafted proposals
            db_stats = self.storage.get_stats()
        except Exception as pe:
            logger.warning(f"[SCHEDULER] Proposal generation error: {pe}")

        # 5. Determine system health status
        status = "HEALTHY"
        if sys_snap.get("voice_active"):
            status = "PAUSED_VOICE"
        elif sys_snap.get("game_detected"):
            status = "PAUSED_GAMING"
        elif not sys_snap.get("battery_plugged", True) and sys_snap.get("battery_percent", 100) < 50:
            status = "PAUSED_BATTERY"
        elif sys_snap.get("cpu_percent", 0) > self.guard.max_cpu_percent or sys_snap.get("memory_percent", 0) > self.guard.max_ram_percent:
            status = "PAUSED_HIGH_LOAD"
        elif not sys_snap.get("can_run", True):
            status = "PAUSED_CONSTRAINTS"
        elif db_stats.get("total_experiences", 0) > 10 and db_stats.get("success_rate", 1.0) < 0.6:
            status = "DEGRADED"

        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "status": status,
            "database_stats": db_stats,
            "system_resources": sys_snap,
            "active_aliases_count": len(active_aliases),
            "active_aliases": active_aliases,
            "weakness_analysis": weakness_analysis,
            "benchmarks": benchmarks,
            "pending_proposals_count": db_stats.get("pending_proposals_count", 0),
            "approved_improvements_count": db_stats.get("approved_proposals_count", 0),
            "proposals_summary": proposals_summary,
            "last_maintenance_unix": time.time()
        }

        # 6. Write health report atomically via temporary file
        try:
            temp_path = f"{self.report_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            if os.path.exists(self.report_path):
                os.remove(self.report_path)
            os.rename(temp_path, self.report_path)
            logger.info(f"[SCHEDULER] Health report updated at: {self.report_path}")
        except Exception as e:
            logger.warning(f"[SCHEDULER] Failed to write health report: {e}")

        # Trigger maintenance complete observer
        if self.on_maintenance_complete:
            try:
                self.on_maintenance_complete(report)
            except Exception as ce:
                logger.debug(f"[SCHEDULER] Maintenance complete callback error: {ce}")

        return report


# Singleton instance
evolution_scheduler = EvolutionScheduler()
