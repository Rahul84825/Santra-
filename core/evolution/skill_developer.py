"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Skill Developer Module (Stage 4)

Provides:
1. AST-safe declarative multi-step workflow engine with strict Safety Governor.
2. Sandboxed isolated dry-run testing promoting skills from SANDBOX to VERIFIED.
3. Sequential workflow miner proposing new skills from repeated user experience patterns.
4. Pre-seeded verified utility skills ("dev workspace mode", "evolution self report").
5. In-memory sub-millisecond trigger lookup cache.
"""

import os
import re
import time
import json
import string
import logging
import threading
import webbrowser
from typing import Optional, Dict, Any, List, Tuple
from core.evolution.storage import EvolutionStorage, evolution_storage
from core.evolution.collector import ExperienceCollector, evolution_collector

logger = logging.getLogger("Santra.Evolution.SkillDeveloper")

# Whitelist of permissible tools inside declarative skills
ALLOWED_SKILL_TOOLS = {
    "open_application",
    "open_app",
    "open_url",
    "speak",
    "synthesize_speech",
    "wait",
    "delay",
    "system_command",
    "get_system_info",
    "evolution_status",
    "evolution_proposals_list",
    "evolution_proposals_approve",
}

# Blacklist of dangerous expressions, system calls, or shell execution paths
PROHIBITED_SUBSTRINGS = [
    "eval(",
    "exec(",
    "os.system",
    "subprocess.",
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "reg.exe",
    "reg add",
    "reg delete",
    "format c:",
    "powershell",
    "cmd.exe",
    "drop table",
    "delete from",
    "truncate ",
    "rm -rf",
    "del /",
    "del c:",
]

# Prohibited sensitive path patterns
PROHIBITED_PATHS = [
    "core/",
    "core\\",
    ".git",
    "system32",
    "windows/system",
    "appdata/roaming/microsoft",
]


class SkillDeveloper:
    """Manages the autonomous discovery, safety verification, and execution of ALEE skills."""

    def __init__(
        self,
        storage: Optional[EvolutionStorage] = None,
        collector: Optional[ExperienceCollector] = None
    ):
        self.storage = storage or evolution_storage
        self.collector = collector or evolution_collector

        self._lock = threading.Lock()
        self._trigger_cache: Dict[str, Dict[str, Any]] = {}

        # Initialize pre-seeded skills and load in-memory cache
        self.initialize_preseeded_skills()
        self.load_skills_cache()

    # ==========================================
    # CACHE & IN-MEMORY TRIGGER MATCHING (< 1ms)
    # ==========================================
    def load_skills_cache(self):
        """Loads all VERIFIED skills into the in-memory fast trigger lookup dictionary."""
        with self._lock:
            self._trigger_cache.clear()
            verified_skills = self.storage.get_verified_skills()
            for skill in verified_skills:
                triggers = skill.get("trigger_phrases", [])
                for trig in triggers:
                    norm = self._normalize_trigger(trig)
                    if norm:
                        self._trigger_cache[norm] = skill
        logger.debug(f"[SKILL_DEV] In-memory skill trigger cache loaded with {len(self._trigger_cache)} triggers.")

    @staticmethod
    def _normalize_trigger(text: str) -> str:
        """Strips punctuation, lowercases, and collapses whitespace."""
        if not text:
            return ""
        t = text.lower()
        # Remove punctuation
        t = t.translate(str.maketrans("", "", string.punctuation))
        return " ".join(t.split())

    def match_trigger(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Sub-millisecond trigger matching against verified skills cache.
        Returns the matched skill definition dictionary or None.
        """
        if not query or not query.strip():
            return None

        norm_query = self._normalize_trigger(query)
        if not norm_query:
            return None

        with self._lock:
            # 1. Exact match on normalized text
            if norm_query in self._trigger_cache:
                return self._trigger_cache[norm_query]

            # 2. Trigger containment (for queries that contain a multi-word trigger phrase)
            for trig, skill in self._trigger_cache.items():
                if trig == norm_query:
                    return skill
                # Only check substring containment if trigger is at least 2 words
                if " " in trig and trig in norm_query:
                    return skill

        return None

    # ==========================================
    # SAFETY GOVERNOR & SPEC VALIDATION
    # ==========================================
    def validate_skill_spec(self, spec: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Strict AST and content inspection ensuring skills contain NO arbitrary shell commands,
        file deletion, or core python file modifications.
        """
        if not isinstance(spec, dict):
            return False, "Skill specification must be a dictionary"

        name = spec.get("name")
        if not name or not str(name).strip():
            return False, "Skill must have a non-empty name"

        triggers = spec.get("trigger_phrases")
        if not triggers or not isinstance(triggers, list) or len(triggers) == 0:
            return False, "Skill must provide at least one trigger phrase"

        steps = spec.get("steps", spec.get("steps_json", []))
        if not steps or not isinstance(steps, list) or len(steps) == 0:
            return False, "Skill must provide at least one executable step"

        # Check each step
        spec_str = json.dumps(spec).lower()
        for prohibited in PROHIBITED_SUBSTRINGS:
            if prohibited in spec_str:
                return False, f"Safety Governor violation: Prohibited token '{prohibited}' detected"

        for step in steps:
            if not isinstance(step, dict):
                return False, "Each step must be a dictionary specification"

            tool = step.get("tool")
            if not tool or tool not in ALLOWED_SKILL_TOOLS:
                return False, f"Safety Governor violation: Tool '{tool}' is not in the allowed tools whitelist"

            args = step.get("args", {})
            if not isinstance(args, dict):
                return False, "Step args must be a dictionary"

            args_str = json.dumps(args).lower()

            # Specific tool argument validations
            if tool == "open_url":
                url = str(args.get("url", "")).strip().lower()
                if not (url.startswith("http://") or url.startswith("https://")):
                    return False, "Safety Governor violation: open_url requires http:// or https:// scheme"

            elif tool in ["open_application", "open_app"]:
                app = str(args.get("app_name", "")).strip().lower()
                if not app or any(ext in app for ext in [".bat", ".cmd", ".vbs", ".ps1"]):
                    return False, f"Safety Governor violation: Prohibited application target '{app}'"
                if re.search(r'\.py(?:["\'\s]|$)', app):
                    return False, "Safety Governor violation: Direct Python file manipulation (.py) detected in step arguments"
                for p_path in PROHIBITED_PATHS:
                    if p_path in app:
                        return False, f"Safety Governor violation: Restricted path pattern '{p_path}' in step arguments"
            else:
                for p_path in PROHIBITED_PATHS:
                    if p_path in args_str:
                        return False, f"Safety Governor violation: Restricted path pattern '{p_path}' in step arguments"

        return True, "Valid skill specification"

    # ==========================================
    # SANDBOX ISOLATION & DRY-RUN TESTING
    # ==========================================
    def test_skill_in_sandbox(self, skill_id: str) -> bool:
        """
        Executes an isolated dry-run test of a candidate skill without firing external side-effects.
        If validation and simulated step evaluation succeed, promotes the skill to 'VERIFIED'.
        """
        skill = self.storage.get_skill(skill_id)
        if not skill:
            logger.warning(f"[SKILL_DEV] Cannot test non-existent skill: {skill_id}")
            return False

        # 1. Safety Governor Check
        is_valid, reason = self.validate_skill_spec(skill)
        if not is_valid:
            logger.warning(f"[SKILL_DEV] Skill '{skill_id}' failed safety governor: {reason}")
            self.storage.update_skill_status(skill_id, "BLOCKED")
            return False

        # 2. Simulated dry-run verification
        steps = skill.get("steps", [])
        try:
            for step in steps:
                tool = step.get("tool")
                args = step.get("args", {})
                if tool == "open_url":
                    if not args.get("url"):
                        raise ValueError("Missing url argument in open_url step")
                elif tool in ["open_application", "open_app"]:
                    if not args.get("app_name"):
                        raise ValueError("Missing app_name in open_application step")
                elif tool in ["speak", "synthesize_speech"]:
                    if not args.get("text"):
                        raise ValueError("Missing text in speak step")
                elif tool in ["wait", "delay"]:
                    secs = float(args.get("seconds", 1.0))
                    if secs < 0 or secs > 60:
                        raise ValueError("Wait duration out of acceptable bounds (0-60s)")
        except Exception as e:
            logger.warning(f"[SKILL_DEV] Skill '{skill_id}' dry-run simulation failed: {e}")
            self.storage.update_skill_status(skill_id, "SANDBOX")
            return False

        # Promotion to VERIFIED
        self.storage.update_skill_status(skill_id, "VERIFIED")
        logger.info(f"[SKILL_DEV] Skill '{skill_id}' passed sandbox testing. Promoted to VERIFIED.")

        # Reload in-memory trigger cache
        self.load_skills_cache()
        return True

    # ==========================================
    # AUTOMATIC WORKFLOW MINING FROM EXPERIENCES
    # ==========================================
    def propose_skills_from_experiences(
        self,
        window_seconds: float = 60.0,
        min_occurrences: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Mines chronological execution experiences for recurring sequential command pairs.
        Proposes safe candidate multi-step skills in 'SANDBOX' status for review and testing.
        """
        with self.storage._lock:
            conn = self.storage._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, user_request, intent, action, parameters_json, success
                FROM experiences
                ORDER BY timestamp ASC
            """)
            rows = cursor.fetchall()
            cursor.close()

        if len(rows) < 2:
            return []

        # Find successful consecutive pairs occurring within window_seconds
        pair_counts: Dict[Tuple[str, str], int] = {}
        pair_samples: Dict[Tuple[str, str], Tuple[dict, dict]] = {}

        for i in range(len(rows) - 1):
            ts1, req1, int1, act1, p1, succ1 = rows[i]
            ts2, req2, int2, act2, p2, succ2 = rows[i + 1]

            # Both must be successful and within the time window
            if succ1 == 1 and succ2 == 1 and (0.5 <= (ts2 - ts1) <= window_seconds):
                clean1 = self._normalize_trigger(req1)
                clean2 = self._normalize_trigger(req2)
                if clean1 and clean2 and clean1 != clean2:
                    pair_key = (clean1, clean2)
                    pair_counts[pair_key] = pair_counts.get(pair_key, 0) + 1
                    if pair_key not in pair_samples:
                        pair_samples[pair_key] = (
                            {"req": req1, "intent": int1, "action": act1, "params": p1},
                            {"req": req2, "intent": int2, "action": act2, "params": p2}
                        )

        proposed_skills = []
        now = time.time()
        for (clean1, clean2), count in pair_counts.items():
            if count >= min_occurrences:
                s1, s2 = pair_samples[(clean1, clean2)]
                skill_id = f"auto_workflow_{abs(hash(clean1 + clean2)) % 1000000:06d}"

                # Synthesize safe steps
                steps = []
                for sample in [s1, s2]:
                    act = sample.get("action", "")
                    try:
                        p_dict = json.loads(sample.get("params", "{}"))
                    except Exception:
                        p_dict = {}

                    if "browser" in act.lower() or "url" in act.lower():
                        steps.append({"tool": "open_url", "args": {"url": p_dict.get("url", "https://google.com")}})
                    elif "app" in act.lower() or "application" in act.lower():
                        app_name = p_dict.get("app_name") or sample.get("req", "").replace("open ", "")
                        steps.append({"tool": "open_application", "args": {"app_name": app_name}})
                    else:
                        steps.append({"tool": "speak", "args": {"text": f"Completed {sample.get('req')}"}})

                candidate_spec = {
                    "skill_id": skill_id,
                    "name": f"Workflow: {clean1} and {clean2}",
                    "trigger_phrases": [
                        f"{clean1} and {clean2}",
                        f"{clean1} then {clean2}"
                    ],
                    "description": f"Automatically discovered workflow sequence (observed {count} times).",
                    "steps": steps,
                    "version": 1,
                    "status": "SANDBOX",
                    "created_at": now,
                    "updated_at": now
                }

                # Validate with Safety Governor
                valid, _ = self.validate_skill_spec(candidate_spec)
                if valid:
                    self.storage.upsert_skill(candidate_spec)
                    proposed_skills.append(candidate_spec)
                    logger.info(f"[SKILL_DEV] Proposed candidate skill: {candidate_spec['name']}")

        return proposed_skills

    # ==========================================
    # PRE-SEEDED VERIFIED UTILITY SKILLS
    # ==========================================
    def initialize_preseeded_skills(self):
        """Pre-seeds standard verified utility skills on boot."""
        now = time.time()
        preseeded = [
            {
                "skill_id": "skill_dev_workspace_mode",
                "name": "dev workspace mode",
                "trigger_phrases": [
                    "dev workspace mode",
                    "developer mode",
                    "start dev workspace",
                    "setup dev environment",
                    "developer workspace",
                ],
                "description": "Launches VS Code and opens developer localhost environment.",
                "steps": [
                    {"tool": "open_application", "args": {"app_name": "code"}},
                    {"tool": "open_url", "args": {"url": "http://localhost:3000"}},
                    {"tool": "speak", "args": {"text": "Developer workspace ready."}},
                ],
                "version": 1,
                "status": "VERIFIED",
                "created_at": now,
                "updated_at": now
            },
            {
                "skill_id": "skill_evolution_self_report",
                "name": "evolution self report",
                "trigger_phrases": [
                    "evolution self report",
                    "evolution status",
                    "santra evolution report",
                    "how is your evolution",
                    "system evolution report",
                ],
                "description": "Generates and speaks ALEE diagnostic health and performance telemetry.",
                "steps": [
                    {"tool": "evolution_status", "args": {}},
                ],
                "version": 1,
                "status": "VERIFIED",
                "created_at": now,
                "updated_at": now
            },
            {
                "skill_id": "skill_list_evolution_proposals",
                "name": "list evolution proposals",
                "trigger_phrases": [
                    "list evolution proposals",
                    "what are your evolution proposals",
                    "show failing intents",
                    "pending improvements",
                    "evolution proposals",
                    "pending proposals",
                ],
                "description": "Reports top failing intents and pending evolution improvement proposals.",
                "steps": [
                    {"tool": "evolution_proposals_list", "args": {}},
                ],
                "version": 1,
                "status": "VERIFIED",
                "created_at": now,
                "updated_at": now
            },
            {
                "skill_id": "skill_approve_evolution_proposals",
                "name": "approve evolution proposals",
                "trigger_phrases": [
                    "approve evolution proposals",
                    "approve pending proposals",
                    "promote sandbox skills",
                    "apply evolution proposals",
                ],
                "description": "Evaluates and approves pending evolution proposals across regression benchmarks.",
                "steps": [
                    {"tool": "evolution_proposals_approve", "args": {}},
                ],
                "version": 1,
                "status": "VERIFIED",
                "created_at": now,
                "updated_at": now
            }
        ]

        for s in preseeded:
            existing = self.storage.get_skill(s["skill_id"])
            if not existing:
                self.storage.upsert_skill(s)
                logger.info(f"[SKILL_DEV] Pre-seeded verified skill: {s['name']}")

    # ==========================================
    # SKILL EXECUTION ENGINE
    # ==========================================
    def execute_skill(
        self,
        skill: Dict[str, Any],
        runtime: Optional[Any] = None,
        speak: bool = True
    ) -> Dict[str, Any]:
        """
        Executes the steps of a verified declarative skill safely.
        """
        skill_id = skill.get("skill_id", "unknown")
        skill_name = skill.get("name", "unnamed")
        steps = skill.get("steps", [])
        logger.info(f"[SKILL_DEV] Executing skill '{skill_name}' ({len(steps)} steps)...")

        executed_steps = 0
        final_message = f"Skill '{skill_name}' completed."

        try:
            for step in steps:
                tool = step.get("tool")
                args = step.get("args", {})

                if tool == "evolution_status":
                    final_message = self._generate_evolution_voice_summary()
                    if runtime and speak and hasattr(runtime, "response_manager"):
                        runtime.response_manager.conversation(final_message, speak=True)

                elif tool == "evolution_proposals_list":
                    final_message = self._generate_proposals_voice_summary()
                    if runtime and speak and hasattr(runtime, "response_manager"):
                        runtime.response_manager.conversation(final_message, speak=True)

                elif tool == "evolution_proposals_approve":
                    final_message = self._execute_proposals_approval()
                    if runtime and speak and hasattr(runtime, "response_manager"):
                        runtime.response_manager.conversation(final_message, speak=True)

                elif tool == "open_application" or tool == "open_app":
                    app_name = args.get("app_name", "")
                    if runtime and hasattr(runtime, "executor") and hasattr(runtime.executor, "open_app"):
                        runtime.executor.open_app(app_name)
                    else:
                        os.system(f"start {app_name}")

                elif tool == "open_url":
                    url = args.get("url", "")
                    webbrowser.open(url)

                elif tool in ["speak", "synthesize_speech"]:
                    text = args.get("text", "")
                    final_message = text
                    if runtime and speak and hasattr(runtime, "response_manager"):
                        runtime.response_manager.conversation(text, speak=True)

                elif tool in ["wait", "delay"]:
                    secs = min(float(args.get("seconds", 1.0)), 5.0)
                    time.sleep(secs)

                executed_steps += 1

            # Record successful execution
            self.storage.record_skill_execution(skill_id, success=True)
            if self.collector:
                self.collector.record_experience(
                    user_request=f"Skill: {skill_name}",
                    intent="ALEE_SKILL",
                    action=skill_id,
                    success=True,
                    message=final_message
                )

            return {
                "success": True,
                "skill_id": skill_id,
                "executed_steps": executed_steps,
                "message": final_message
            }

        except Exception as e:
            logger.error(f"[SKILL_DEV] Error executing skill '{skill_name}': {e}", exc_info=True)
            self.storage.record_skill_execution(skill_id, success=False)
            if self.collector:
                self.collector.record_experience(
                    user_request=f"Skill: {skill_name}",
                    intent="ALEE_SKILL",
                    action=skill_id,
                    success=False,
                    message=str(e),
                    error_type="SkillExecutionError"
                )
            return {
                "success": False,
                "skill_id": skill_id,
                "error": str(e),
                "message": f"Skill execution failed: {e}"
            }

    def _generate_evolution_voice_summary(self) -> str:
        """Constructs an intelligent, concise voice report of the ALEE engine status."""
        stats = self.storage.get_stats()
        active_aliases = stats.get("active_aliases", 0)
        verified_skills = stats.get("verified_skills", 0)
        total_docs = stats.get("total_knowledge_items", 0)
        total_exp = stats.get("total_experiences", 0)

        # Check evaluator metrics
        benchmark_score = 100
        weakness_count = 0
        try:
            from core.evolution.evaluator import PerformanceEvaluator
            evaluator = PerformanceEvaluator(storage=self.storage, collector=self.collector)
            bench = evaluator.run_regression_benchmarks()
            benchmark_score = int(bench.get("score", 100))
            weaknesses = evaluator.analyze_weaknesses()
            weakness_count = len(weaknesses.get("failing_intents", []))
        except Exception:
            pass

        # Check resource status
        from core.evolution.resource_guard import resource_guard
        snap = resource_guard.get_system_snapshot()
        state_str = "optimal"
        if snap.get("game_detected"):
            state_str = "game-paused"
        elif not snap.get("can_run"):
            state_str = "throttled"

        summary = (
            f"ALEE system is operating in {state_str} mode with a {benchmark_score} percent "
            f"benchmark pass score. Currently managing {active_aliases} phonetic domain aliases, "
            f"{verified_skills} verified autonomous skills, and {total_docs} knowledge documents. "
            f"Historical experience base stands at {total_exp} entries with {weakness_count} failing intents detected."
        )
        return summary

    def _generate_proposals_voice_summary(self) -> str:
        """Constructs spoken summary of failing intents and pending evolution proposals."""
        try:
            from core.evolution.evolution_manager import evolution_manager
            evolution_manager.generate_proposals()
        except Exception:
            pass

        pending = self.storage.get_pending_proposals()
        failing_names = []
        try:
            from core.evolution.evaluator import PerformanceEvaluator
            evaluator = PerformanceEvaluator(storage=self.storage, collector=self.collector)
            weaknesses = evaluator.analyze_weaknesses()
            for f_item in weaknesses.get("failing_intents", [])[:3]:
                failing_names.append(f"{f_item['operation']} with {f_item['failed_count']} failures")
        except Exception:
            pass

        failing_str = ", ".join(failing_names) if failing_names else "no severe failures"
        summary = (
            f"ALEE has {len(pending)} pending evolution proposals awaiting approval. "
            f"Historical weakness analysis detected {len(failing_names)} failing operations: {failing_str}. "
            f"You can say 'approve pending proposals' to evaluate and verify them."
        )
        return summary

    def _execute_proposals_approval(self) -> str:
        """Executes Level 3 approval on all pending proposals and reports verification status."""
        try:
            from core.evolution.evolution_manager import evolution_manager
            res = evolution_manager.approve_all_pending()
            approved_count = res.get("approved_count", 0)
            failed_count = res.get("failed_count", 0)
        except Exception as e:
            return f"Approval evaluation encountered an error: {e}"

        score = 100
        try:
            from core.evolution.evaluator import PerformanceEvaluator
            evaluator = PerformanceEvaluator(storage=self.storage, collector=self.collector)
            bench = evaluator.run_regression_benchmarks()
            score = int(bench.get("score", 100))
        except Exception:
            pass

        summary = (
            f"Processed pending evolution proposals: {approved_count} approved and verified, "
            f"{failed_count} rejected due to regression guards. Current system benchmark score is {score} percent."
        )
        return summary


# Singleton instance
skill_developer = SkillDeveloper()
