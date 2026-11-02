"""Phase 6: Multi-File Repair Safety in Live Execution Paths.
Tests:
1. Step 7 authorization gate halts live repair when user denies (authorized=False).
2. Patch failure halfway through a batch triggers automatic rollback.
3. Test failure post-patch triggers automatic rollback to pre-modification state.
4. External modification collision: rollback detects conflict and refuses to overwrite external edits.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.project_intelligence.code_repair_engine import CodeRepairEngine
from core.project_intelligence.file_engineer import FileEngineer
from core.project_intelligence.context_engine import ProjectContextEngine


class TestMultiFileRepairSafetyLive(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="santra_repair_test_")
        self.project_path = Path(self.test_dir)
        self.db_path = self.project_path / "project.db"

        self.context_engine = ProjectContextEngine(db_path=str(self.db_path))
        self.file_engineer = FileEngineer(journal_path=str(self.project_path / "journal.jsonl"))
        self.repair_engine = CodeRepairEngine(
            file_engineer=self.file_engineer,
            context_engine=self.context_engine
        )

        # Create sample project structure with 2 interdependent modules and a test
        self.math_file = self.project_path / "math_utils.py"
        self.math_file.write_text(
            "def calculate_total(a: int, b: int) -> int:\n    return a - b  # BUG: minus instead of plus\n",
            encoding="utf-8"
        )

        self.order_file = self.project_path / "order_service.py"
        self.order_file.write_text(
            "from math_utils import calculate_total\n\ndef get_order_total(qty: int, price: int) -> int:\n    return calculate_total(qty, price)\n",
            encoding="utf-8"
        )

        self.test_file = self.project_path / "test_order.py"
        self.test_file.write_text(
            "import unittest\nfrom order_service import get_order_total\n\n"
            "class TestOrder(unittest.TestCase):\n"
            "    def test_total(self):\n"
            "        self.assertEqual(get_order_total(10, 5), 15)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8"
        )

        # Index project
        self.context_engine.index_project(str(self.project_path), "test_repair_proj")

    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_01_step7_authorization_gate_halts_live_repair(self):
        """Verifies that when authorized=False, Step 7 halts repair and modifies zero files on disk."""
        patches = [
            {
                "file_path": str(self.math_file),
                "target": "return a - b  # BUG: minus instead of plus",
                "replacement": "return a + b"
            }
        ]

        original_math_content = self.math_file.read_text(encoding="utf-8")

        res = self.repair_engine.execute_verified_repair_14_step(
            project_path=str(self.project_path),
            issue_description="Fix minus bug",
            patches=patches,
            test_command="python -m unittest test_order.py",
            authorized=False  # User withholding authorization
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "AWAITING_AUTHORIZATION")
        self.assertEqual(res["current_step"], 7)

        # Verify disk content was NEVER altered
        current_content = self.math_file.read_text(encoding="utf-8")
        self.assertEqual(current_content, original_math_content)

    def test_02_halfway_patch_batch_failure_triggers_atomic_rollback(self):
        """Verifies that if patch 1 succeeds and patch 2 fails (e.g. invalid syntax),
        patch 1 is atomically rolled back, leaving disk in original state.
        """
        orig_math = self.math_file.read_text(encoding="utf-8")
        orig_order = self.order_file.read_text(encoding="utf-8")

        patches = [
            # Patch 1: valid patch on math_utils
            {
                "file_path": str(self.math_file),
                "target": "return a - b  # BUG: minus instead of plus",
                "replacement": "return a + b"
            },
            # Patch 2: invalid syntax patch on order_service
            {
                "file_path": str(self.order_file),
                "target": "return calculate_total(qty, price)",
                "replacement": "def invalid_syntax_broken((("
            }
        ]

        batch_res = self.repair_engine.apply_atomic_multi_file_patch(
            patches=patches,
            description="Attempt broken batch"
        )

        self.assertFalse(batch_res["success"])
        self.assertIn("Atomic batch aborted", batch_res["error"])

        # math_utils.py must have been rolled back to original content
        restored_math = self.math_file.read_text(encoding="utf-8")
        self.assertEqual(restored_math, orig_math, "math_utils.py must be cleanly rolled back.")

        # order_service.py must also remain in original state
        restored_order = self.order_file.read_text(encoding="utf-8")
        self.assertEqual(restored_order, orig_order)

    def test_03_post_patch_test_failure_triggers_automatic_rollback(self):
        """Verifies that if tests fail after applying patches, all files are automatically rolled back."""
        orig_math = self.math_file.read_text(encoding="utf-8")

        # Patch that introduces wrong behavior failing the test
        patches = [
            {
                "file_path": str(self.math_file),
                "target": "return a - b  # BUG: minus instead of plus",
                "replacement": "return a * b  # Multiplication fails the addition test (10*5 = 50 != 15)"
            }
        ]

        res = self.repair_engine.execute_verified_repair_14_step(
            project_path=str(self.project_path),
            issue_description="Apply wrong multiplication patch",
            patches=patches,
            test_command="python -m unittest test_order.py",
            authorized=True
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["current_step"], 13)
        self.assertIn("Changes safely rolled back", res["error"])

        # Verify math_utils.py content was restored to original
        current_math = self.math_file.read_text(encoding="utf-8")
        self.assertEqual(current_math, orig_math)

    def test_04_external_modification_collision_halts_rollback(self):
        """Verifies that if a user externally edits the file after a patch,
        the rollback engine detects the conflict and refuses to overwrite manual changes.
        """
        # 1. Apply a patch
        patch_res = self.file_engineer.apply_patch(
            file_path=str(self.math_file),
            target_content="return a - b  # BUG: minus instead of plus",
            replacement_content="return a + b",
            description="Initial patch"
        )
        self.assertTrue(patch_res["success"])
        patch_id = patch_res["patch_id"]

        # 2. Simulate external user modification while SANTRA was running
        external_user_code = "def calculate_total(a: int, b: int) -> int:\n    # User manually edited this line!\n    return a + b\n"
        self.math_file.write_text(external_user_code, encoding="utf-8")

        # 3. Attempt rollback
        rb_res = self.file_engineer.rollback_patch(patch_id)

        self.assertFalse(rb_res["success"])
        self.assertTrue(rb_res.get("conflict"))
        self.assertEqual(rb_res.get("reason"), "conflict")
        self.assertIn("was modified externally", rb_res["error"])

        # Verify user's manual edits were NOT overwritten
        current_disk = self.math_file.read_text(encoding="utf-8")
        self.assertEqual(current_disk, external_user_code)


if __name__ == "__main__":
    unittest.main()

