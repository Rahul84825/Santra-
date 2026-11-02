"""Unit tests for Project Intelligence, SQLite FTS5 Code Search, and Safe File Engineering."""

import os
import time
import shutil
import tempfile
import unittest
from pathlib import Path

from core.project_intelligence.scanner import ProjectScanner
from core.project_intelligence.context_engine import ProjectContextEngine
from core.project_intelligence.file_engineer import FileEngineer
from core.project_intelligence.watcher import ProjectWatcher


class TestProjectIntelligenceAndFileEngineering(unittest.TestCase):
    """Verifies project scanning, AST symbol indexing, FTS5 search, and atomic patching."""

    def setUp(self):
        # Create an isolated temporary test directory for project files
        self.test_dir = Path(tempfile.mkdtemp(prefix="santra_test_proj_"))
        # Create a separate isolated directory for index database and journal
        self.meta_dir = Path(tempfile.mkdtemp(prefix="santra_test_meta_"))

        # Setup isolated database path
        self.db_path = self.meta_dir / "test_project_intel.db"
        self.context_engine = ProjectContextEngine(db_path=str(self.db_path))

        # Setup isolated journal path
        self.journal_path = self.meta_dir / "test_file_journal.jsonl"
        self.file_engineer = FileEngineer(journal_path=str(self.journal_path))
        self.scanner = ProjectScanner()

    def tearDown(self):
        # Cleanup temporary files
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.meta_dir, ignore_errors=True)

    def test_scanner_and_symbol_extraction(self):
        # Create python file with classes, functions, and imports
        py_file = self.test_dir / "sample_service.py"
        py_file.write_text('''"""Sample service module."""
import json
import os
from math import sqrt

class UserService:
    """Manages user state."""
    def __init__(self, db_conn):
        self.db = db_conn

    def calculate_metric(self, value):
        return sqrt(value)

def standalone_helper():
    """Helper function."""
    return True
''', encoding="utf-8")

        # Create ignored folder (.venv) and file inside
        venv_dir = self.test_dir / ".venv" / "lib"
        venv_dir.mkdir(parents=True, exist_ok=True)
        (venv_dir / "ignored.py").write_text("x = 1\n", encoding="utf-8")

        overview, files, deps = self.scanner.scan_directory(str(self.test_dir), project_name="test_proj")
        symbols = [s for f in files for s in f.symbols]

        # Verify exclusions
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].relative_path, "sample_service.py")

        # Verify symbols
        symbol_names = [s.name for s in symbols]
        self.assertIn("UserService", symbol_names)
        self.assertIn("UserService.calculate_metric", symbol_names)
        self.assertIn("standalone_helper", symbol_names)

        # Verify dependencies
        dep_modules = [d.target_module for d in deps]
        self.assertIn("json", dep_modules)
        self.assertIn("os", dep_modules)
        self.assertIn("math", dep_modules)

    def test_fts5_code_search_and_symbol_query(self):
        src_file = self.test_dir / "calculator.py"
        src_file.write_text('''import math

class Calculator:
    """Mathematical computation engine."""
    def compute(self, x):
        return math.sqrt(x) * 2.0
''', encoding="utf-8")

        # Index project
        overview = self.context_engine.index_project(str(self.test_dir), project_name="calc_project")
        self.assertEqual(overview.total_files, 1)

        # 1. Search code for complex tokens and punctuation
        search_results = self.context_engine.search_code("math.sqrt", project_name="calc_project")
        self.assertTrue(len(search_results) > 0)
        self.assertEqual(search_results[0]["relative_path"], "calculator.py")

        # 2. Search symbols
        symbols = self.context_engine.find_symbol("Calculator", project_name="calc_project")
        self.assertTrue(len(symbols) > 0)
        self.assertEqual(symbols[0]["name"], "Calculator")
        self.assertEqual(symbols[0]["symbol_type"], "class")

        # 3. Query dependencies
        deps = self.context_engine.get_dependencies(project_name="calc_project")
        self.assertTrue(len(deps) > 0)
        self.assertEqual(deps[0]["target_module"], "math")

    def test_file_engineer_atomic_create_and_syntax_validation(self):
        target_file = self.test_dir / "valid_code.py"

        # 1. Successful file creation
        res = self.file_engineer.create_or_update_file(
            file_path=str(target_file),
            content="def valid_function():\n    return 42\n"
        )
        self.assertTrue(res["success"])
        self.assertTrue(target_file.exists())
        self.assertIn("return 42", target_file.read_text(encoding="utf-8"))

        # 2. Syntax error validation prevents broken file write
        invalid_file = self.test_dir / "broken_code.py"
        res_fail = self.file_engineer.create_or_update_file(
            file_path=str(invalid_file),
            content="def syntax_error(:\n    broken = True"
        )
        self.assertFalse(res_fail["success"])
        self.assertEqual(res_fail["reason"], "syntax_error")
        # File must not have been created
        self.assertFalse(invalid_file.exists())

    def test_file_patch_and_rollback(self):
        file_to_patch = self.test_dir / "config.json"
        file_to_patch.write_text('{\n  "version": "1.0.0",\n  "debug": false\n}\n', encoding="utf-8")

        # 1. Apply patch
        patch_res = self.file_engineer.patch_file(
            file_path=str(file_to_patch),
            target_content='"version": "1.0.0"',
            replacement_content='"version": "1.1.0"',
            description="Bump version to 1.1.0"
        )
        self.assertTrue(patch_res["success"])
        self.assertIn('"version": "1.1.0"', file_to_patch.read_text(encoding="utf-8"))

        # 2. Conflict rejection (target content missing)
        conflict_res = self.file_engineer.patch_file(
            file_path=str(file_to_patch),
            target_content='"version": "1.0.0"',
            replacement_content='"version": "2.0.0"'
        )
        self.assertFalse(conflict_res["success"])
        self.assertEqual(conflict_res["reason"], "conflict")

        # 3. Rollback patch
        rollback_res = self.file_engineer.rollback_patch(patch_res["patch_id"])
        self.assertTrue(rollback_res["success"])
        content_after_rollback = file_to_patch.read_text(encoding="utf-8")
        self.assertIn('"version": "1.0.0"', content_after_rollback)
        self.assertNotIn('"version": "1.1.0"', content_after_rollback)

    def test_multilanguage_scanning_ts_java_cpp_sql(self):
        """Verifies multi-language symbol extraction across TS, Java, C++, and SQL."""
        # 1. TypeScript file
        ts_file = self.test_dir / "user_controller.ts"
        ts_file.write_text('''
import { UserService } from "./user_service";
const authModule = require("auth-lib");

export interface UserDTO {
    id: string;
    username: string;
}

export type AuthToken = string;

export class UserController {
    async getUser(id: string): Promise<UserDTO> {
        const dynamicMod = await import("./analytics");
        return { id, username: "activ" };
    }
}

export const helperArrow = (x: number) => x * 2;
''', encoding="utf-8")

        # 2. Java file
        java_file = self.test_dir / "UserEntity.java"
        java_file.write_text('''
package com.santra.models;

import java.util.Date;
import java.io.Serializable;

public class UserEntity implements Serializable {
    private String username;

    public String getUsername() {
        return this.username;
    }
}
''', encoding="utf-8")

        # 3. C++ file
        cpp_file = self.test_dir / "crypto_native.cpp"
        cpp_file.write_text('''
#include <iostream>
#include "crypto_native.h"

class HashEngine {
public:
    void compute_sha() {
    }
};

void global_cpp_fn() {
}
''', encoding="utf-8")

        # 4. SQL file
        sql_file = self.test_dir / "schema.sql"
        sql_file.write_text('''
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE VIEW user_order_view AS
SELECT u.username, o.order_id FROM users u JOIN orders o ON u.id = o.user_id;
''', encoding="utf-8")

        overview, files, deps = self.scanner.scan_directory(str(self.test_dir), project_name="polyglot_proj")
        symbols = [s for f in files for s in f.symbols]
        symbol_names = [s.name for s in symbols]

        # Verify TypeScript symbols & dependencies
        self.assertIn("UserController", symbol_names)
        self.assertIn("UserDTO", symbol_names)
        self.assertIn("AuthToken", symbol_names)
        self.assertIn("helperArrow", symbol_names)

        # Verify Java symbols & dependencies
        self.assertIn("UserEntity", symbol_names)
        self.assertIn("UserEntity.getUsername", symbol_names)

        # Verify C++ symbols
        self.assertIn("HashEngine", symbol_names)
        self.assertIn("HashEngine::compute_sha", symbol_names)
        self.assertIn("global_cpp_fn", symbol_names)

        # Verify SQL symbols
        self.assertIn("users", symbol_names)
        self.assertIn("orders", symbol_names)
        self.assertIn("user_order_view", symbol_names)

        # Verify dependency kinds
        dep_modules = [d.target_module for d in deps]
        self.assertIn("./user_service", dep_modules)
        self.assertIn("java.util.Date", dep_modules)
        self.assertIn("crypto_native.h", dep_modules)
        self.assertIn("users", dep_modules)  # SQL foreign key reference

        dep_kinds = {d.target_module: d.dependency_kind for d in deps}
        self.assertEqual(dep_kinds.get("crypto_native.h"), "include")
        self.assertEqual(dep_kinds.get("users"), "foreign_key")

    def test_file_engineer_security_blocklist(self):
        """Verifies that sensitive configuration and secret files cannot be modified."""
        env_file = self.test_dir / ".env"
        res_env = self.file_engineer.create_or_update_file(
            file_path=str(env_file),
            content="SECRET_KEY=12345\n"
        )
        self.assertFalse(res_env["success"])
        self.assertEqual(res_env["reason"], "security_blocklist")
        self.assertFalse(env_file.exists())

        cred_file = self.test_dir / "credentials.json"
        res_cred = self.file_engineer.create_or_update_file(
            file_path=str(cred_file),
            content='{"token": "xyz"}\n'
        )
        self.assertFalse(res_cred["success"])
        self.assertEqual(res_cred["reason"], "security_blocklist")

        # Null byte traversal protection
        res_null = self.file_engineer.create_or_update_file(
            file_path=str(self.test_dir / "test\x00bad.py"),
            content="print(1)\n"
        )
        self.assertFalse(res_null["success"])

    def test_file_engineer_rollback_conflict_detection(self):
        """Verifies rollback rejects if file was changed externally after patching."""
        test_file = self.test_dir / "service.py"
        test_file.write_text("status = 'initial'\n", encoding="utf-8")

        patch_res = self.file_engineer.patch_file(
            file_path=str(test_file),
            target_content="status = 'initial'",
            replacement_content="status = 'patched'"
        )
        self.assertTrue(patch_res["success"])

        # External modification occurs after patch
        test_file.write_text("status = 'externally_modified'\n", encoding="utf-8")

        rollback_res = self.file_engineer.rollback_patch(patch_res["patch_id"])
        self.assertFalse(rollback_res["success"])
        self.assertEqual(rollback_res["reason"], "conflict")
        # Current file must preserve the external edit
        self.assertEqual(test_file.read_text(encoding="utf-8").strip(), "status = 'externally_modified'")

    def test_file_engineer_secret_redaction(self):
        """Verifies secrets (API keys, tokens, passwords) are redacted before persisting in journal."""
        secret_file = self.test_dir / "api_client.py"
        secret_file.write_text("api_key = 'sk-1234567890abcdef1234567890abcdef'\n", encoding="utf-8")

        patch_res = self.file_engineer.patch_file(
            file_path=str(secret_file),
            target_content="sk-1234567890abcdef1234567890abcdef",
            replacement_content="sk-0987654321fedcba0987654321fedcba"
        )
        self.assertTrue(patch_res["success"])

        # Inspect journal file on disk
        journal_text = self.journal_path.read_text(encoding="utf-8")
        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", journal_text)
        self.assertNotIn("sk-0987654321fedcba0987654321fedcba", journal_text)
        self.assertTrue("[REDACTED]" in journal_text or "[REDACTED_API_KEY]" in journal_text)

    def test_incremental_invalidation_and_update(self):
        """Verifies incremental update_file and invalidate_file in context engine."""
        src_file = self.test_dir / "module_a.py"
        src_file.write_text("def initial_func():\n    return 1\n", encoding="utf-8")

        self.context_engine.index_project(str(self.test_dir), project_name="inc_proj")
        syms_before = self.context_engine.find_symbol("initial_func", project_name="inc_proj")
        self.assertEqual(len(syms_before), 1)

        # Update file with new function
        src_file.write_text("def updated_func():\n    return 2\n", encoding="utf-8")
        self.context_engine.update_file(str(src_file), project_name="inc_proj")

        syms_after_old = self.context_engine.find_symbol("initial_func", project_name="inc_proj")
        syms_after_new = self.context_engine.find_symbol("updated_func", project_name="inc_proj")
        self.assertEqual(len(syms_after_old), 0)  # Invalidation cleared old symbol
        self.assertEqual(len(syms_after_new), 1)  # New symbol present

        # Invalidate file (e.g. deletion)
        self.context_engine.invalidate_file(str(src_file))
        syms_final = self.context_engine.find_symbol("updated_func", project_name="inc_proj")
        self.assertEqual(len(syms_final), 0)

    def test_watcher_creation_modification_and_deletion(self):
        """Verifies ProjectWatcher correctly detects creation, modification, and deletion events."""
        watcher = ProjectWatcher()
        events = []
        watcher.on_file_changed(lambda path, action: events.append((Path(path).name, action)))

        watcher.add_watch(str(self.test_dir))

        # 1. Created file
        f1 = self.test_dir / "observed.txt"
        f1.write_text("initial content", encoding="utf-8")
        watcher.check_changes_once()
        self.assertIn(("observed.txt", "created"), events)

        # 2. Modified file
        time.sleep(0.05)
        f1.write_text("updated content", encoding="utf-8")
        # Ensure mtime is higher on filesystems with low timestamp resolution
        os.utime(str(f1), (time.time() + 1.0, time.time() + 1.0))
        watcher.check_changes_once()
        self.assertIn(("observed.txt", "modified"), events)

        # 3. Deleted file
        f1.unlink()
        watcher.check_changes_once()
        self.assertIn(("observed.txt", "deleted"), events)


if __name__ == "__main__":
    unittest.main()
