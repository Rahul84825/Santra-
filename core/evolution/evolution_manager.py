"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Controlled Evolution Manager Module (Stage 5)

Implements the Observe -> Propose -> Evaluate -> Approve -> Rollback pipeline:
1. Automated proposal generation from failing intents, pending aliases, and sandbox skills.
2. Level 3 (L3) Approval Gate with deterministic pre/post benchmark regression gating.
3. Automatic rollback guard on benchmark degradation.
4. Versioned audit snapshot logging and instant manual rollback mechanism.
"""

import os
import json
import time
import logging
import threading
from typing import Optional, Dict, Any, List, Tuple

from core.evolution.storage import EvolutionStorage, evolution_storage
from core.evolution.evaluator import PerformanceEvaluator, performance_evaluator
from core.evolution.skill_developer import SkillDeveloper, skill_developer
from core.evolution.collector import ExperienceCollector, evolution_collector

logger = logging.getLogger("Santra.Evolution.Manager")

# Categorized Proposal Risk Classes & Security Enforcement Levels
PROPOSAL_RISK_MAP = {
    "ALIAS_PROMOTION": "PHONETIC_ALIAS",     # Low Risk
    "SKILL_PROMOTION": "SKILL_PROMOTION",     # Medium Risk
    "INTENT_RULE": "INTENT_RULE",             # High Risk
    "TIMEOUT_TUNING": "TIMEOUT_TUNING",       # Medium Risk
    "RUNTIME_CONFIG": "RUNTIME_CONFIG",       # High Risk
}

RISK_LEVELS = {
    "PHONETIC_ALIAS": "LOW",
    "SKILL_PROMOTION": "MEDIUM",
    "INTENT_RULE": "HIGH",
    "TIMEOUT_TUNING": "MEDIUM",
    "RUNTIME_CONFIG": "HIGH",
}


class EvolutionManager:
    """Orchestrates controlled autonomous evolution with versioned rollback and approval gates."""

    def __init__(
        self,
        storage: Optional[EvolutionStorage] = None,
        evaluator: Optional[PerformanceEvaluator] = None,
        skill_dev: Optional[SkillDeveloper] = None,
        collector: Optional[ExperienceCollector] = None
    ):
        self.storage = storage or evolution_storage
        self.evaluator = evaluator or performance_evaluator
        self.skill_developer = skill_dev or skill_developer
        self.collector = collector or evolution_collector
        self._lock = threading.RLock()
        self._active_rules_cache: Dict[str, Dict[str, Any]] = {}
        self.load_active_rules_cache()

    def load_active_rules_cache(self):
        """Loads all active approved rules into in-memory dictionary for sub-millisecond lookup."""
        with self._lock:
            self._active_rules_cache.clear()
            try:
                with self.storage._lock:
                    conn = self.storage._get_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT target_key, proposed_value_json, proposal_type
                        FROM evolution_proposals
                        WHERE status = 'APPROVED' AND proposal_type IN ('INTENT_RULE', 'TIMEOUT_TUNING')
                    """)
                    rows = cur.fetchall()
                    cur.close()

                for target_key, val_json, p_type in rows:
                    try:
                        val = json.loads(val_json)
                    except Exception:
                        val = {"raw": val_json}
                    self._active_rules_cache[target_key.lower().strip()] = val
            except Exception as e:
                logger.debug(f"[EVOLUTION_MGR] Rule cache load note: {e}")

    def get_active_rule(self, target_key: str) -> Dict[str, Any]:
        """
        Sub-millisecond (< 0.05ms) in-memory lookup for runtime intent rules & timeout configurations.
        """
        if not target_key:
            return {}
        k = target_key.lower().strip()
        with self._lock:
            return dict(self._active_rules_cache.get(k, {}))

    # ==========================================
    # 1. PROPOSAL GENERATOR
    # ==========================================
    def generate_proposals(self) -> List[Dict[str, Any]]:
        """
        Analyzes weakness reports, pending phonetic aliases, and sandbox skills.
        Drafts structured PENDING proposals for human or policy review.
        """
        with self._lock:
            all_proposals = {p["proposal_id"]: p for p in self.storage.get_all_proposals(limit=500)}
            existing_pending = {pid: p for pid, p in all_proposals.items() if p.get("status") == "PENDING"}
            existing_approved = {pid: p for pid, p in all_proposals.items() if p.get("status") == "APPROVED"}
            created_proposals = []

            # 1. Failing Intents & Slow Operations Proposals
            try:
                weaknesses = self.evaluator.analyze_weaknesses()
                failing = weaknesses.get("failing_intents", [])
                for f_item in failing:
                    op = f_item.get("operation")
                    if not op:
                        continue
                    prop_id = f"prop_intent_{op}"
                    if prop_id in existing_pending or prop_id in existing_approved:
                        continue

                    failed_count = f_item.get("failed_count", 0)
                    succ_rate = f_item.get("success_rate", 0.0)
                    most_common = f_item.get("most_common_error", "execution_failure")

                    # Formulate targeted mitigation rule
                    if op == "open_app":
                        proposed_val = {
                            "strategy": "app_discovery_fuzzy_fallback",
                            "timeout_s": 5.0,
                            "auto_verify": True
                        }
                        reason = f"Intent 'open_app' exhibits {failed_count} failures ({succ_rate:.1f}% success). Route via fuzzy discovery fallback."
                    elif op == "create_file":
                        proposed_val = {
                            "strategy": "atomic_write_fallback",
                            "ensure_parent_dirs": True
                        }
                        reason = f"Intent 'create_file' exhibits {failed_count} failures ({succ_rate:.1f}% success). Add atomic parent directory validation."
                    elif op == "close_application":
                        proposed_val = {
                            "grace_period_s": 3.0,
                            "force_kill_fallback": True
                        }
                        reason = f"Intent 'close_application' exhibits {failed_count} failures ({succ_rate:.1f}% success). Add grace period before force kill."
                    else:
                        proposed_val = {
                            "strategy": "retry_with_delay",
                            "retries": 2,
                            "delay_s": 1.0
                        }
                        reason = f"Failing intent '{op}' detected ({failed_count} failures, {succ_rate:.1f}% success, most common error: '{most_common}')."

                    spec = {
                        "proposal_id": prop_id,
                        "proposal_type": "INTENT_RULE",
                        "target_key": op,
                        "proposed_value": proposed_val,
                        "reason": reason,
                        "evidence_count": failed_count,
                        "status": "PENDING",
                        "created_at": time.time()
                    }
                    self.storage.upsert_proposal(spec)
                    created_proposals.append(spec)
                    existing_pending[prop_id] = spec

                # Slow operations tuning
                slow_ops = weaknesses.get("slow_operations", [])
                for s_item in slow_ops:
                    op = s_item.get("operation")
                    avg_ms = s_item.get("avg_latency_ms", 0.0)
                    if not op or avg_ms < 2000:
                        continue
                    prop_id = f"prop_timeout_{op}"
                    if prop_id in existing_pending or prop_id in existing_approved:
                        continue

                    proposed_val = {"timeout_threshold_ms": max(3000, avg_ms * 1.5)}
                    spec = {
                        "proposal_id": prop_id,
                        "proposal_type": "TIMEOUT_TUNING",
                        "target_key": op,
                        "proposed_value": proposed_val,
                        "reason": f"Operation '{op}' has high latency ({avg_ms:.1f}ms). Tune timeout threshold.",
                        "evidence_count": s_item.get("total_executions", 1),
                        "status": "PENDING",
                        "created_at": time.time()
                    }
                    self.storage.upsert_proposal(spec)
                    created_proposals.append(spec)
                    existing_pending[prop_id] = spec

            except Exception as we:
                logger.warning(f"[EVOLUTION_MGR] Weakness proposal generation error: {we}")

            # 2. Phonetic Alias Promotion Proposals
            try:
                with self.storage._lock:
                    conn = self.storage._get_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT misheard_phrase, intended_phrase, confidence_count
                        FROM phonetic_aliases
                        WHERE confidence_count >= 2 AND auto_apply = 0
                    """)
                    unpromoted = cur.fetchall()
                    cur.close()

                for misheard, intended, conf in unpromoted:
                    prop_id = f"prop_alias_{misheard.replace(' ', '_')}"
                    if prop_id in existing_pending or prop_id in existing_approved:
                        continue

                    spec = {
                        "proposal_id": prop_id,
                        "proposal_type": "ALIAS_PROMOTION",
                        "target_key": misheard,
                        "proposed_value": {
                            "misheard_phrase": misheard,
                            "intended_phrase": intended,
                            "auto_apply": 1
                        },
                        "reason": f"Phonetic alias '{misheard}' -> '{intended}' verified with confidence count {conf}.",
                        "evidence_count": conf,
                        "status": "PENDING",
                        "created_at": time.time()
                    }
                    self.storage.upsert_proposal(spec)
                    created_proposals.append(spec)
                    existing_pending[prop_id] = spec

            except Exception as ae:
                logger.warning(f"[EVOLUTION_MGR] Alias proposal generation error: {ae}")

            # 3. Sandbox Skill Promotion Proposals
            try:
                all_skills = self.storage.get_all_skills()
                sandbox_skills = [s for s in all_skills if s.get("status") == "SANDBOX"]

                for sk in sandbox_skills:
                    s_id = sk["skill_id"]
                    prop_id = f"prop_skill_{s_id}"
                    if prop_id in existing_pending or prop_id in existing_approved:
                        continue

                    # Validate skill with Safety Governor before proposing
                    is_valid, reason = self.skill_developer.validate_skill_spec(sk)
                    if is_valid:
                        spec = {
                            "proposal_id": prop_id,
                            "proposal_type": "SKILL_PROMOTION",
                            "target_key": s_id,
                            "proposed_value": {
                                "skill_id": s_id,
                                "name": sk["name"],
                                "target_status": "VERIFIED"
                            },
                            "reason": f"Candidate skill '{sk['name']}' passed Safety Governor dry-run evaluation.",
                            "evidence_count": sk.get("success_count", 0) + 1,
                            "status": "PENDING",
                            "created_at": time.time()
                        }
                        self.storage.upsert_proposal(spec)
                        created_proposals.append(spec)
                        existing_pending[prop_id] = spec

            except Exception as se:
                logger.warning(f"[EVOLUTION_MGR] Skill proposal generation error: {se}")

            logger.info(f"[EVOLUTION_MGR] Generated {len(created_proposals)} new proposals ({len(existing_pending)} total pending).")
            return self.storage.get_pending_proposals()

    @classmethod
    def get_proposal_risk(cls, prop_type: str) -> Tuple[str, str]:
        """Returns (risk_class, risk_level) for a given proposal type."""
        category = PROPOSAL_RISK_MAP.get(prop_type, "RUNTIME_CONFIG")
        level = RISK_LEVELS.get(category, "HIGH")
        return category, level

    # ==========================================
    # 2. APPROVAL GATE & REGRESSION CHECK
    # ==========================================
    def approve_proposal(
        self,
        proposal_id: str,
        simulated_regression_score: Optional[float] = None,
        confirmed_by_user: bool = False
    ) -> Tuple[bool, str]:
        """
        Enforces Level 3 (L3) Controlled Autonomy:
        1. Verifies explicit human-in-the-loop confirmation for Medium/High risk classes.
        2. Captures pre-state and baseline benchmark score.
        3. Applies proposed change.
        4. Measures post-change benchmark score.
        5. Triggers automatic rollback if score degrades.
        6. Writes versioned snapshot upon success.
        """
        with self._lock:
            proposal = self.storage.get_proposal(proposal_id)
            if not proposal:
                return False, f"Proposal '{proposal_id}' not found."
            if proposal.get("status") != "PENDING":
                return False, f"Proposal '{proposal_id}' is not in PENDING status ({proposal.get('status')})."

            prop_type = proposal.get("proposal_type", "")
            target_key = proposal.get("target_key")
            proposed_val = proposal.get("proposed_value") or {}

            # Strict Human-in-the-Loop Risk Gate
            risk_class, risk_level = self.get_proposal_risk(prop_type)
            if risk_level in ("MEDIUM", "HIGH") and not confirmed_by_user:
                return False, f"Proposal '{proposal_id}' has risk level {risk_level} ({risk_class}). Explicit user confirmation is required."

            logger.info(f"[EVOLUTION_MGR] Evaluating proposal '{proposal_id}' ({prop_type}, Risk: {risk_level})...")

            # 1. Capture Previous State
            prev_state: Dict[str, Any] = {}
            new_state: Dict[str, Any] = {}

            if prop_type == "SKILL_PROMOTION":
                sk = self.storage.get_skill(target_key)
                prev_state = {"status": sk.get("status", "SANDBOX") if sk else "SANDBOX"}
                new_state = {"status": "VERIFIED"}

            elif prop_type == "ALIAS_PROMOTION":
                prev_state = {"auto_apply": 0}
                new_state = {"auto_apply": 1}

            elif prop_type in ["INTENT_RULE", "TIMEOUT_TUNING"]:
                prev_state = {"active": False}
                new_state = {"active": True, "config": proposed_val}

            # 2. Baseline Benchmark Score
            score_before = 100.0
            try:
                bench_before = self.evaluator.run_regression_benchmarks()
                score_before = float(bench_before.get("score", 100.0))
            except Exception as be:
                logger.warning(f"[EVOLUTION_MGR] Pre-benchmark calculation warning: {be}")

            # 3. Apply the Change
            try:
                if prop_type == "SKILL_PROMOTION":
                    self.storage.update_skill_status(target_key, "VERIFIED")
                    self.skill_developer.load_skills_cache()

                elif prop_type == "ALIAS_PROMOTION":
                    with self.storage._lock:
                        conn = self.storage._get_connection()
                        cur = conn.cursor()
                        cur.execute("UPDATE phonetic_aliases SET auto_apply = 1 WHERE misheard_phrase = ?", (target_key,))
                        conn.commit()
                        cur.close()
                    self.collector._load_alias_cache()

                elif prop_type in ["INTENT_RULE", "TIMEOUT_TUNING"]:
                    self.storage.upsert_knowledge(
                        key=f"active_rule:{target_key}",
                        category="evolution_rules",
                        content=json.dumps(new_state),
                        metadata={"proposal_id": proposal_id}
                    )

            except Exception as apply_err:
                logger.error(f"[EVOLUTION_MGR] Failed applying proposal '{proposal_id}': {apply_err}")
                self.storage.update_proposal_status(proposal_id, "FAILED")
                return False, f"Application error: {apply_err}"

            # 4. Post-Change Benchmark Evaluation
            score_after = score_before
            try:
                if simulated_regression_score is not None:
                    score_after = float(simulated_regression_score)
                else:
                    bench_after = self.evaluator.run_regression_benchmarks()
                    score_after = float(bench_after.get("score", 100.0))
            except Exception as be2:
                logger.warning(f"[EVOLUTION_MGR] Post-benchmark calculation warning: {be2}")

            # 5. Auto-Rollback Guard: Detect Benchmark Regression
            if score_after < score_before:
                logger.warning(
                    f"[AUTO_ROLLBACK_GUARD] Proposal '{proposal_id}' caused regression! "
                    f"Score dropped from {score_before:.1f}% -> {score_after:.1f}%. Rolling back..."
                )
                self._execute_state_reversion(prop_type, target_key, prev_state)
                self.storage.update_proposal_status(proposal_id, "FAILED")
                return False, f"Regression detected: score dropped {score_before:.1f}% -> {score_after:.1f}%. Rolled back."

            # 6. Success: Create Snapshot & Mark Approved
            snapshot_id = self.storage.record_snapshot(
                proposal_id=proposal_id,
                previous_state=prev_state,
                new_state=new_state,
                score_before=score_before,
                score_after=score_after
            )
            self.storage.update_proposal_status(proposal_id, "APPROVED")
            self.load_active_rules_cache()
            logger.info(
                f"[EVOLUTION_MGR] Proposal '{proposal_id}' APPROVED successfully. "
                f"Snapshot: {snapshot_id} (Score: {score_after:.1f}%)."
            )
            return True, f"Approved and verified (Snapshot: {snapshot_id}, Score: {score_after:.1f}%)."

    # ==========================================
    # 3. INSTANT VERSIONED ROLLBACK
    # ==========================================
    def rollback_proposal(self, proposal_id: str) -> Tuple[bool, str]:
        """
        Reverts an approved change back to its exact previous state using the audit snapshot.
        """
        with self._lock:
            proposal = self.storage.get_proposal(proposal_id)
            if not proposal:
                return False, f"Proposal '{proposal_id}' not found."

            snapshot = self.storage.get_snapshot_for_proposal(proposal_id)
            if not snapshot:
                return False, f"No audit snapshot found for proposal '{proposal_id}'."

            prop_type = proposal.get("proposal_type")
            target_key = proposal.get("target_key")
            prev_state = snapshot.get("previous_state", {})

            logger.info(f"[EVOLUTION_MGR] Rolling back proposal '{proposal_id}' ({prop_type})...")
            try:
                self._execute_state_reversion(prop_type, target_key, prev_state)
                self.storage.mark_snapshot_rolled_back(snapshot["snapshot_id"])
                self.storage.update_proposal_status(proposal_id, "ROLLED_BACK")
                self.load_active_rules_cache()
                logger.info(f"[EVOLUTION_MGR] Proposal '{proposal_id}' ROLLED BACK successfully.")
                return True, f"Proposal '{proposal_id}' rolled back successfully."
            except Exception as e:
                logger.error(f"[EVOLUTION_MGR] Rollback error for '{proposal_id}': {e}", exc_info=True)
                return False, f"Rollback failed: {e}"

    def _execute_state_reversion(self, prop_type: str, target_key: str, prev_state: Dict[str, Any]):
        """Helper restoring prior state across storage and in-memory caches."""
        if prop_type == "SKILL_PROMOTION":
            prior_status = prev_state.get("status", "SANDBOX")
            self.storage.update_skill_status(target_key, prior_status)
            self.skill_developer.load_skills_cache()

        elif prop_type == "ALIAS_PROMOTION":
            prior_auto = int(prev_state.get("auto_apply", 0))
            with self.storage._lock:
                conn = self.storage._get_connection()
                cur = conn.cursor()
                cur.execute("UPDATE phonetic_aliases SET auto_apply = ? WHERE misheard_phrase = ?", (prior_auto, target_key))
                conn.commit()
                cur.close()
            self.collector._load_alias_cache()

        elif prop_type in ["INTENT_RULE", "TIMEOUT_TUNING"]:
            self.storage.upsert_knowledge(
                key=f"active_rule:{target_key}",
                category="evolution_rules",
                content=json.dumps(prev_state),
                metadata={"status": "reverted"}
            )

    # ==========================================
    # 4. BATCH APPROVAL WITH HUMAN-IN-THE-LOOP GATE
    # ==========================================
    def approve_all_pending(self, confirmed_by_user: bool = False) -> Dict[str, Any]:
        """
        Iterates through and safely approves pending proposals.
        If confirmed_by_user is False, only LOW-risk proposals (PHONETIC_ALIAS) are approved;
        MEDIUM and HIGH risk proposals are deferred until explicit human approval.
        """
        pending = self.storage.get_pending_proposals()
        approved = []
        failed = []

        for p in pending:
            p_id = p["proposal_id"]
            p_type = p.get("proposal_type", "")
            risk_class, risk_level = self.get_proposal_risk(p_type)

            if risk_level in ("MEDIUM", "HIGH") and not confirmed_by_user:
                failed.append({
                    "proposal_id": p_id,
                    "error": f"Requires explicit user confirmation (Risk: {risk_level}, Class: {risk_class})"
                })
                continue

            ok, msg = self.approve_proposal(p_id, confirmed_by_user=confirmed_by_user)
            if ok:
                approved.append({"proposal_id": p_id, "message": msg})
            else:
                failed.append({"proposal_id": p_id, "error": msg})

        return {
            "total_pending": len(pending),
            "approved_count": len(approved),
            "failed_count": len(failed),
            "approved": approved,
            "failed": failed
        }


# Singleton instance
evolution_manager = EvolutionManager()

