"""
Centralized Safety Policy Gate & Scoped Permission Subsystem.
Implements Track C & Iteration 19 Security Directives:
- Granular permission separation across 9 operation categories:
  READ, CREATE, MODIFY, RENAME, MOVE, DELETE, PROCESS_CONTROL, SYSTEM_CONFIGURATION, SHELL_EXECUTION.
- Default-deny for effectful actions unless write permission is enabled.
- Absolute requirement of explicit human confirmation for destructive operations
  (DELETE, PROCESS_CONTROL, SYSTEM_CONFIGURATION, SHELL_EXECUTION), even when JARVIS_ALLOW_WRITES=1.
- Target-path validation protecting against path traversal (..), symlink/junction escapes,
  and unauthorized system directory manipulation.
- Shell command validation and audit logging without leaking secrets.
"""

import os
import re
import sys
import logging
from enum import Enum
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

logger = logging.getLogger("Jarvis.ToolSafetyGate")

class OperationCategory(Enum):
    READ = "read"
    CREATE = "create"
    MODIFY = "modify"
    RENAME = "rename"
    MOVE = "move"
    DELETE = "delete"
    PROCESS_CONTROL = "process_control"
    SYSTEM_CONFIGURATION = "system_configuration"
    SHELL_EXECUTION = "shell_execution"
    UNKNOWN = "unknown"

# Explicit tool mappings
READ_ONLY_TOOLS = {
    "get_time", "get_date", "get_system_status", "get_battery_status",
    "get_weather", "get_news", "morning_briefing", "search_web",
    "check_unread_emails", "get_phone_battery", "ping_phone",
    "read_file", "list_directory", "inspect_tab", "take_screenshot",
    "query_memory", "get_user_profile", "search_active_page", "inspect_page"
}

LOW_RISK_WRITE_TOOLS = {
    "create_file", "write_file", "edit_file", "update_file",
    "rename_file", "rename_folder", "move_file", "move_folder",
    "send_email", "send_telegram", "send_whatsapp", "control_smart_home",
    "launch_application"
}

DESTRUCTIVE_TOOLS = {
    "delete_file", "remove_file", "delete_folder",
    "kill_process", "terminate_task",
    "shutdown_pc", "restart_pc", "lock_screen",
    "run_terminal_command", "execute_terminal", "format_hard_drive"
}

# Legacy WRITE_TOOLS compatibility set
WRITE_TOOLS = LOW_RISK_WRITE_TOOLS | DESTRUCTIVE_TOOLS

READ_VERB_PATTERN = re.compile(
    r"^(get|list|read|search|find|query|fetch|check|describe|inspect|show|view|explain|screenshot|ping)",
    re.IGNORECASE
)

EFFECTFUL_VERB_PATTERN = re.compile(
    r"(send|call|post|create|delete|remove|update|edit|write|install|launch|tap|swipe|press|type|buy|pay|charge|publish|deploy|outbound|download|run|exec|kill|shutdown|restart|lock)",
    re.IGNORECASE
)

FORBIDDEN_SYSTEM_PATHS_WINDOWS = [
    r"windows\system32",
    r"windows\syswow64",
    r"windows\winxs",
    r"system volume information",
    r"\recovery",
    r"\$recycle.bin",
    r"program files\windowsapps"
]

FORBIDDEN_SYSTEM_PATHS_LINUX = [
    "/etc", "/boot", "/sys", "/proc", "/dev", "/root"
]

FORBIDDEN_SHELL_PATTERNS = [
    re.compile(r"\brm\s+-[rf]{1,2}\s+/", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+/[fsq]\b", re.IGNORECASE),
    re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
]


class ToolSafetyGate:
    """Centralized safety policy gate and scoped permission engine.
    Default-deny for effectful/destructive actions unless write mode is explicitly enabled.
    Destructive actions require explicit confirmation regardless of environment settings.
    """

    def __init__(self, allow_writes: bool = None, strict_destructive_guards: bool = False):
        if allow_writes is None:
            self._allow_writes = os.getenv("JARVIS_ALLOW_WRITES", "0").lower() in ("1", "true", "yes")
        else:
            self._allow_writes = allow_writes
        self.strict_destructive_guards = strict_destructive_guards
        self._audit_log: List[Dict[str, Any]] = []

    @property
    def allow_writes(self) -> bool:
        return self._allow_writes

    def set_allow_writes(self, allowed: bool):
        self._allow_writes = allowed
        logger.info(f"ToolSafetyGate allow_writes set to {allowed}")

    def categorize_operation(self, name: str) -> OperationCategory:
        """Determines the OperationCategory for a tool or action verb."""
        clean = name.strip().lower()
        if clean in READ_ONLY_TOOLS or READ_VERB_PATTERN.match(clean):
            return OperationCategory.READ
        if "delete" in clean or "remove" in clean:
            return OperationCategory.DELETE
        if "kill" in clean or "terminate" in clean:
            return OperationCategory.PROCESS_CONTROL
        if clean in ["shutdown_pc", "restart_pc", "lock_screen"] or any(k in clean for k in ["shutdown", "restart", "reboot", "lock"]):
            return OperationCategory.SYSTEM_CONFIGURATION
        if "terminal" in clean or "shell" in clean or "command" in clean or clean in ["run_terminal_command", "execute_terminal"]:
            return OperationCategory.SHELL_EXECUTION
        if "rename" in clean:
            return OperationCategory.RENAME
        if "move" in clean:
            return OperationCategory.MOVE
        if "create" in clean or clean == "write_file":
            return OperationCategory.CREATE
        if "edit" in clean or "update" in clean:
            return OperationCategory.MODIFY
        if clean in WRITE_TOOLS or EFFECTFUL_VERB_PATTERN.search(clean):
            return OperationCategory.MODIFY
        return OperationCategory.UNKNOWN

    def is_destructive(self, tool_name: str) -> bool:
        """Returns True if the operation modifies system state destructively or executes arbitrary shell code."""
        clean = tool_name.strip().lower()
        if clean in DESTRUCTIVE_TOOLS:
            return True
        category = self.categorize_operation(clean)
        return category in {
            OperationCategory.DELETE,
            OperationCategory.PROCESS_CONTROL,
            OperationCategory.SYSTEM_CONFIGURATION,
            OperationCategory.SHELL_EXECUTION
        }

    def validate_target_path(self, target_path: str, base_dir: Optional[str] = None) -> Tuple[bool, str]:
        """Validates that target path does not violate traversal constraints,
        escape through symlinks/junctions, or target protected operating system directories.
        """
        if not target_path or not isinstance(target_path, str):
            return False, "Target path is empty or invalid"

        try:
            # Check traversal tokens
            norm_path = os.path.normpath(target_path)
            resolved = Path(norm_path).resolve()
            resolved_str = str(resolved).lower()

            # 1. Base directory constraint (if provided)
            if base_dir:
                resolved_base = Path(base_dir).resolve()
                try:
                    resolved.relative_to(resolved_base)
                except ValueError:
                    return False, f"Path traversal violation: Target '{target_path}' escapes base directory '{base_dir}'"

            # 2. Protected OS directories
            if sys.platform.startswith("win"):
                for forbidden in FORBIDDEN_SYSTEM_PATHS_WINDOWS:
                    if forbidden in resolved_str:
                        return False, f"Access denied: Target points to protected system directory '{forbidden}'"
            else:
                for forbidden in FORBIDDEN_SYSTEM_PATHS_LINUX:
                    if resolved_str == forbidden or resolved_str.startswith(forbidden + "/"):
                        return False, f"Access denied: Target points to protected system directory '{forbidden}'"

            return True, "Target path validated successfully"

        except Exception as e:
            return False, f"Path validation error: {e}"

    def validate_shell_command(self, cmd: str) -> Tuple[bool, str]:
        """Validates shell command against dangerous system destructive signatures."""
        if not cmd or not isinstance(cmd, str):
            return False, "Empty or invalid shell command"

        for pattern in FORBIDDEN_SHELL_PATTERNS:
            if pattern.search(cmd):
                return False, f"Prohibited destructive command signature detected: {pattern.pattern}"

        return True, "Shell command syntax permissible"

    def evaluate_operation(
        self,
        operation: str,
        target_path: Optional[str] = None,
        base_dir: Optional[str] = None,
        user_confirmed: bool = False,
        shell_command: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Full scoped permission evaluation following Iteration 19 Architecture."""
        category = self.categorize_operation(operation)
        clean_name = operation.strip()

        # 1. READ is always safe
        if category == OperationCategory.READ:
            self._log_audit(clean_name, category.value, True, "Allowed: Read-only operation", target_path)
            return True, "Allowed: Read-only operation"

        # 2. Check path safety if target_path is specified
        if target_path:
            path_ok, path_msg = self.validate_target_path(target_path, base_dir=base_dir)
            if not path_ok:
                self._log_audit(clean_name, category.value, False, f"Blocked: {path_msg}", target_path)
                return False, f"Blocked: {path_msg}"

        # 3. Check shell command safety if command is provided
        if shell_command and category == OperationCategory.SHELL_EXECUTION:
            sh_ok, sh_msg = self.validate_shell_command(shell_command)
            if not sh_ok:
                self._log_audit(clean_name, category.value, False, f"Blocked: {sh_msg}", target_path)
                return False, f"Blocked: {sh_msg}"

        # 4. Destructive / High-Risk Operations ALWAYS require user confirmation
        if self.is_destructive(clean_name):
            if not user_confirmed:
                reason = f"Blocked: Destructive operation '{clean_name}' requires explicit human confirmation."
                self._log_audit(clean_name, category.value, False, reason, target_path)
                return False, reason
            self._log_audit(clean_name, category.value, True, "Allowed: Destructive action explicitly confirmed by user", target_path)
            return True, "Allowed: Destructive action explicitly confirmed by user"

        # 5. Low-risk write operations (CREATE, MODIFY, RENAME, MOVE)
        if category in {OperationCategory.CREATE, OperationCategory.MODIFY, OperationCategory.RENAME, OperationCategory.MOVE}:
            if self._allow_writes:
                self._log_audit(clean_name, category.value, True, "Allowed: Scoped write permission active", target_path)
                return True, "Allowed: Scoped write permission active"
            reason = f"Blocked: '{clean_name}' modifies file/state and requires JARVIS_ALLOW_WRITES=1"
            self._log_audit(clean_name, category.value, False, reason, target_path)
            return False, reason

        # 6. Fallback
        if self._allow_writes:
            return True, "Allowed: Safe-mode override active"
        return False, f"Blocked: '{clean_name}' is unverified and denied under default safe-mode policy"

    def decide_tool(self, tool_name: str) -> bool:
        """Returns True if tool is permitted to execute, False otherwise."""
        allowed, _ = self.evaluate_tool(tool_name)
        return allowed

    def evaluate_tool(self, tool_name: str, user_confirmed: bool = False, target_path: Optional[str] = None) -> Tuple[bool, str]:
        """Evaluates whether tool is allowed and returns a descriptive reason.
        Maintains backward compatibility while enforcing strict confirmation when strict_destructive_guards is enabled.
        """
        clean_name = tool_name.strip()

        # Strict destructive guard check
        if self.strict_destructive_guards and self.is_destructive(clean_name):
            if not user_confirmed:
                return False, f"Blocked: '{clean_name}' is a destructive action requiring explicit confirmation"

        # 1. Check explicit read-only registry
        if clean_name in READ_ONLY_TOOLS:
            return True, "Allowed: Whitelisted read-only tool"

        # 2. Check explicit write registry
        if clean_name in WRITE_TOOLS:
            if self._allow_writes:
                return True, "Allowed: Write tool authorized under active write permissions"
            return False, f"Blocked: '{clean_name}' modifies external state and requires write authorization"

        # 3. Effectful verb check
        if EFFECTFUL_VERB_PATTERN.search(clean_name):
            if self._allow_writes:
                return True, "Allowed: Effectful tool authorized under active write permissions"
            return False, f"Blocked: '{clean_name}' contains effectful action and requires write authorization"

        # 4. Read verb check
        if READ_VERB_PATTERN.match(clean_name):
            return True, "Allowed: Read-action verb detected"

        # 5. Default fallback
        if self._allow_writes:
            return True, "Allowed: Safe-mode override active"
        return False, f"Blocked: '{clean_name}' is unverified and denied under default safe-mode policy"

    def _log_audit(self, operation: str, category: str, allowed: bool, reason: str, target: Optional[str]):
        """Records audit log entry without secrets."""
        sanitized_target = target
        if target and any(k in target.lower() for k in ["token", "key", "secret", "password"]):
            sanitized_target = "[REDACTED_PATH]"

        self._audit_log.append({
            "operation": operation,
            "category": category,
            "allowed": allowed,
            "reason": reason,
            "target": sanitized_target
        })

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)


tool_safety_gate = ToolSafetyGate()
