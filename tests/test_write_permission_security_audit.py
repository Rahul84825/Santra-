"""
Iteration 19: Comprehensive Write Permission & Scoped Security Audit Test Suite
Tests:
1. All 9 operation categories (READ, CREATE, MODIFY, RENAME, MOVE, DELETE, PROCESS_CONTROL, SYSTEM_CONFIGURATION, SHELL_EXECUTION)
2. Default vs Elevated (JARVIS_ALLOW_WRITES=1) permissions
3. Destructive actions requiring explicit confirmation regardless of env setting
4. Target-path validation against path traversal and system directory manipulation
5. Shell command validation against dangerous commands
6. Audit logging without secrets leakage
"""

import unittest
from core.tool_safety_gate import ToolSafetyGate, OperationCategory

class TestWritePermissionSecurityAudit(unittest.TestCase):
    def setUp(self):
        self.gate_default = ToolSafetyGate(allow_writes=False)
        self.gate_elevated = ToolSafetyGate(allow_writes=True)

    def test_read_operations_allowed_in_all_modes(self):
        read_ops = ["read_file", "list_directory", "get_time", "get_system_status"]
        for op in read_ops:
            allowed_def, _ = self.gate_default.evaluate_operation(op)
            allowed_elev, _ = self.gate_elevated.evaluate_operation(op)
            self.assertTrue(allowed_def, f"{op} should be allowed by default")
            self.assertTrue(allowed_elev, f"{op} should be allowed when elevated")

    def test_low_risk_writes_blocked_by_default_allowed_when_elevated(self):
        low_risk = [
            ("create_file", OperationCategory.CREATE),
            ("edit_file", OperationCategory.MODIFY),
            ("rename_file", OperationCategory.RENAME),
            ("move_file", OperationCategory.MOVE)
        ]
        for op, cat in low_risk:
            # Default
            allowed_def, reason_def = self.gate_default.evaluate_operation(op)
            self.assertFalse(allowed_def, f"{op} should be blocked by default")
            self.assertIn("requires JARVIS_ALLOW_WRITES=1", reason_def)

            # Elevated
            allowed_elev, reason_elev = self.gate_elevated.evaluate_operation(op)
            self.assertTrue(allowed_elev, f"{op} should be allowed when elevated")
            self.assertIn("Allowed", reason_elev)

    def test_destructive_operations_blocked_even_when_elevated_without_confirmation(self):
        destructive_ops = [
            ("delete_file", OperationCategory.DELETE),
            ("kill_process", OperationCategory.PROCESS_CONTROL),
            ("shutdown_pc", OperationCategory.SYSTEM_CONFIGURATION),
            ("restart_pc", OperationCategory.SYSTEM_CONFIGURATION),
            ("run_terminal_command", OperationCategory.SHELL_EXECUTION)
        ]
        for op, cat in destructive_ops:
            # Blocked by default
            allowed_def, _ = self.gate_default.evaluate_operation(op, user_confirmed=False)
            self.assertFalse(allowed_def)

            # STILL blocked when elevated if user has not explicitly confirmed
            allowed_elev, reason_elev = self.gate_elevated.evaluate_operation(op, user_confirmed=False)
            self.assertFalse(allowed_elev, f"Destructive operation {op} must be blocked without confirmation even if elevated")
            self.assertIn("explicit human confirmation", reason_elev)

            # Allowed only when user explicitly confirmed
            allowed_confirmed, reason_conf = self.gate_elevated.evaluate_operation(op, user_confirmed=True)
            self.assertTrue(allowed_confirmed, f"{op} should be allowed when explicitly confirmed")
            self.assertIn("explicitly confirmed", reason_conf)

    def test_target_path_validation_traversal_and_system_protection(self):
        # 1. Path traversal escaping base
        allowed, msg = self.gate_elevated.evaluate_operation(
            "edit_file",
            target_path="c:\\workspace\\my_app\\..\\..\\..\\Windows\\System32\\calc.exe",
            base_dir="c:\\workspace\\my_app"
        )
        self.assertFalse(allowed)
        self.assertIn("escapes base directory", msg)

        # 2. System directory protection
        allowed_sys, msg_sys = self.gate_elevated.evaluate_operation(
            "write_file",
            target_path="C:\\Windows\\System32\\drivers\\etc\\hosts"
        )
        self.assertFalse(allowed_sys)
        self.assertIn("protected system directory", msg_sys)

        # 3. Legitimate workspace path
        allowed_legit, _ = self.gate_elevated.evaluate_operation(
            "write_file",
            target_path="c:\\workspace\\project\\src\\main.py",
            base_dir="c:\\workspace\\project"
        )
        self.assertTrue(allowed_legit)

    def test_shell_command_validation_blocks_dangerous_patterns(self):
        dangerous_cmds = [
            "rm -rf /",
            "format c: /fs:ntfs",
            "del /f /q C:\\*",
            "DROP DATABASE production;"
        ]
        for cmd in dangerous_cmds:
            allowed, msg = self.gate_elevated.evaluate_operation(
                "run_terminal_command",
                user_confirmed=True,
                shell_command=cmd
            )
            self.assertFalse(allowed, f"Dangerous command '{cmd}' must be blocked")
            self.assertIn("Prohibited destructive command", msg)

        # Safe command passes
        allowed_safe, _ = self.gate_elevated.evaluate_operation(
            "run_terminal_command",
            user_confirmed=True,
            shell_command="git status"
        )
        self.assertTrue(allowed_safe)

    def test_audit_logging_sanitizes_secrets(self):
        gate = ToolSafetyGate(allow_writes=True)
        gate.evaluate_operation("read_file", target_path="C:\\Users\\user\\Documents\\api_secret_token.txt")
        audit_trail = gate.get_audit_trail()
        self.assertEqual(len(audit_trail), 1)
        self.assertEqual(audit_trail[0]["target"], "[REDACTED_PATH]")

if __name__ == "__main__":
    unittest.main()

