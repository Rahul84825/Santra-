import unittest
import tempfile
import shutil
from pathlib import Path

from core.project_intelligence.scanner import ProjectScanner
from core.project_intelligence.context_engine import ProjectContextEngine
from core.project_intelligence.file_engineer import FileEngineer
from core.project_intelligence.code_repair_engine import CodeRepairEngine

class TestAutonomousMultiFileEngineering(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="santra_polyglot_repair_")
        self.proj_path = Path(self.temp_dir)
        self.scanner = ProjectScanner()
        self.context_engine = ProjectContextEngine(
            db_path=str(self.proj_path / "repair_test.db"),
            scanner=self.scanner
        )
        self.file_engineer = FileEngineer(
            journal_path=str(self.proj_path / "journal.jsonl")
        )
        self.repair_engine = CodeRepairEngine(
            context_engine=self.context_engine,
            file_eng=self.file_engineer
        )

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def test_end_to_end_autonomous_repair_and_rollback(self):
        # 1. Setup disposable multi-file codebase
        calc_code = """
def calculate_tax(amount, rate):
    # BUG: Multiplying instead of adding tax to amount
    return amount * rate
"""
        (self.proj_path / "calculator.py").write_text(calc_code, encoding="utf-8")

        order_code = """
from calculator import calculate_tax

def process_order(price, tax_rate):
    total = calculate_tax(price, tax_rate)
    return {"total": total}
"""
        (self.proj_path / "order_processor.py").write_text(order_code, encoding="utf-8")

        test_code = """
import unittest
from order_processor import process_order

class TestOrders(unittest.TestCase):
    def test_total_calculation(self):
        res = process_order(100.0, 0.10)
        # Expected: 100 + 10 = 110.0
        self.assertEqual(res["total"], 110.0)

if __name__ == "__main__":
    unittest.main()
"""
        (self.proj_path / "tests").mkdir(parents=True, exist_ok=True)
        (self.proj_path / "tests" / "test_orders.py").write_text(test_code, encoding="utf-8")

        # Index codebase
        self.context_engine.index_project(str(self.proj_path), project_name="OrderApp")

        # 2. Diagnose bug
        diag = self.repair_engine.diagnose_bug(str(self.proj_path), "calculate_tax")
        self.assertTrue(diag["success"])
        self.assertIn("calculator.py", [s["relative_path"] for s in diag["symbols"]])

        # 3. Baseline tests must FAIL
        baseline_res = self.repair_engine.run_tests(str(self.proj_path), test_command="python -m unittest tests/test_orders.py")
        self.assertFalse(baseline_res["passed"])

        # 4. Propose coordinated multi-file patch
        patches = [
            {
                "file_path": str(self.proj_path / "calculator.py"),
                "target": "return amount * rate",
                "replacement": "return amount + (amount * rate)"
            },
            {
                "file_path": str(self.proj_path / "order_processor.py"),
                "target": 'return {"total": total}',
                "replacement": 'return {"total": round(total, 2)}'
            }
        ]

        # 5. Execute verified repair
        repair_res = self.repair_engine.execute_verified_repair(
            project_path=str(self.proj_path),
            patches=patches,
            test_command="python -m unittest tests/test_orders.py",
            description="Fix tax calculation bug across calculator and processor"
        )

        self.assertTrue(repair_res["success"])
        self.assertTrue(repair_res["post_tests_passed"])
        self.assertEqual(repair_res["files_modified"], 2)
        patch_ids = repair_res["patch_ids"]

        # 6. Verify safe rollback restores original state
        rb_res = self.repair_engine.rollback_batch(patch_ids)
        self.assertTrue(rb_res["success"])
        self.assertEqual(rb_res["rolled_back_count"], 2)

        # Baseline tests should fail again after rollback
        post_rb_tests = self.repair_engine.run_tests(str(self.proj_path), test_command="python -m unittest tests/test_orders.py")
        self.assertFalse(post_rb_tests["passed"])

    def test_complete_14_step_workflow_and_authorization_gate(self):
        # 1. Setup files
        (self.proj_path / "tests").mkdir(parents=True, exist_ok=True)
        calc = self.proj_path / "calc_v2.py"
        calc.write_text("def multiply(a, b): return a + b\n", encoding="utf-8") # bug: returns addition

        test_f = self.proj_path / "tests" / "test_calc_v2.py"
        test_f.write_text("""
import unittest
from calc_v2 import multiply

class TestCalc(unittest.TestCase):
    def test_mul(self):
        self.assertEqual(multiply(2, 3), 6)
""", encoding="utf-8")

        patches = [{
            "file_path": str(calc),
            "target": "return a + b",
            "replacement": "return a * b"
        }]

        # 2. Gate check: unauthorized request must halt at step 7 without writing
        unauth_res = self.repair_engine.execute_verified_repair_14_step(
            project_path=str(self.proj_path),
            issue_description="Fix multiplication bug",
            patches=patches,
            test_command="python -m unittest tests/test_calc_v2.py",
            authorized=False
        )
        self.assertFalse(unauth_res["success"])
        self.assertEqual(unauth_res["status"], "AWAITING_AUTHORIZATION")
        self.assertEqual(unauth_res["current_step"], 7)
        self.assertIn("return a * b", str(unauth_res["previews"]))
        # Verify file on disk was NOT modified
        self.assertIn("return a + b", calc.read_text(encoding="utf-8"))

        # 3. Authorized run executes all 14 steps
        auth_res = self.repair_engine.execute_verified_repair_14_step(
            project_path=str(self.proj_path),
            issue_description="Fix multiplication bug",
            patches=patches,
            test_command="python -m unittest tests/test_calc_v2.py",
            authorized=True
        )
        self.assertTrue(auth_res["success"])
        self.assertEqual(auth_res["status"], "PRODUCTION_VERIFIED")
        self.assertEqual(len(auth_res["workflow_steps"]), 14)
        report = auth_res["report"]
        self.assertTrue(report["focused_passed"])
        self.assertIn("return a * b", calc.read_text(encoding="utf-8"))

    def test_rollback_conflict_protection(self):
        # Verify rollback aborts if file was modified externally after patch
        test_file = self.proj_path / "data_service.py"
        test_file.write_text("def get_data(): return 'v1'\n", encoding="utf-8")

        p_res = self.file_engineer.apply_patch(
            file_path=str(test_file),
            target_content="return 'v1'",
            replacement_content="return 'v2'",
            description="Update data version"
        )
        self.assertTrue(p_res["success"])
        patch_id = p_res["patch_id"]

        # Simulate external edit after patch
        test_file.write_text("def get_data(): return 'v2_external_edit'\n", encoding="utf-8")

        # Rollback attempt must fail with conflict
        rb_res = self.file_engineer.rollback_patch(patch_id)
        self.assertFalse(rb_res["success"])
        self.assertEqual(rb_res["reason"], "conflict")
        self.assertIn("modified externally", rb_res["error"])

    def test_sensitive_file_and_secret_redaction(self):
        # 1. Sensitive file creation/modification blocked
        env_file = self.proj_path / ".env"
        blocked_res = self.file_engineer.create_file(str(env_file), "SECRET_KEY=12345")
        self.assertFalse(blocked_res["success"])
        self.assertEqual(blocked_res["reason"], "security_blocklist")

        # 2. Secret redaction in journal
        dummy_code = self.proj_path / "api_client.py"
        dummy_code.write_text("api_key = 'initial'\n", encoding="utf-8")
        patch_res = self.file_engineer.apply_patch(
            file_path=str(dummy_code),
            target_content="api_key = 'initial'",
            replacement_content="api_key = 'sk-1234567890abcdef1234567890'",
            description="Set production key"
        )
        self.assertTrue(patch_res["success"])

        # Check journal file content for redaction
        journal_text = Path(self.file_engineer.journal_path).read_text(encoding="utf-8")
        self.assertNotIn("sk-1234567890abcdef1234567890", journal_text)
        self.assertIn("[REDACTED]", journal_text)

        # Test standalone OpenAI key and JWT redaction
        sanitized = self.file_engineer._redact_secrets("token = sk-abc12345678901234567890 and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSignature")
        self.assertNotIn("sk-abc12345678901234567890", sanitized)
        self.assertNotIn("doNotLeakThisSignature", sanitized)
        self.assertIn("[REDACTED", sanitized)

if __name__ == "__main__":
    unittest.main()
