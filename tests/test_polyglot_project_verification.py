"""Phase 6 Verification: Polyglot Project Parsing, Symbol Lookup, and Architectural Tracing."""

import shutil
import tempfile
import unittest
from pathlib import Path

from core.project_intelligence.scanner import ProjectScanner
from core.project_intelligence.context_engine import ProjectContextEngine


class TestPolyglotProjectVerification(unittest.TestCase):
    """Verifies Project Intelligence against a real multi-language project: Python, TS, Java, C++, SQL."""

    def setUp(self):
        self.proj_dir = Path(tempfile.mkdtemp(prefix="santra_polyglot_"))
        self.meta_dir = Path(tempfile.mkdtemp(prefix="santra_polyglot_meta_"))
        self.db_path = self.meta_dir / "polyglot_intel.db"
        self.engine = ProjectContextEngine(db_path=str(self.db_path))
        self.scanner = ProjectScanner()

        # Build directory structure
        (self.proj_dir / "src" / "services").mkdir(parents=True, exist_ok=True)
        (self.proj_dir / "src" / "controllers").mkdir(parents=True, exist_ok=True)
        (self.proj_dir / "src" / "models").mkdir(parents=True, exist_ok=True)
        (self.proj_dir / "src" / "native").mkdir(parents=True, exist_ok=True)
        (self.proj_dir / "db").mkdir(parents=True, exist_ok=True)

        # 1. Python Service
        (self.proj_dir / "src" / "services" / "UserService.py").write_text('''"""User Business Logic Service."""

class UserService:
    """Core domain service for user account management."""

    def __init__(self, db_conn):
        self.db = db_conn

    def calculate_user_metrics(self, user_id: int) -> dict:
        """Calculates algorithmic activity score for a given user."""
        return {"score": 98.5, "active": True}
''', encoding="utf-8")

        # 2. TypeScript Controller
        (self.proj_dir / "src" / "controllers" / "UserController.ts").write_text('''import { UserService } from "../services/UserService";

export interface UserResponse {
    userId: number;
    score: number;
}

export class UserController {
    async getUserMetrics(userId: number): Promise<UserResponse> {
        return { userId, score: 98.5 };
    }
}
''', encoding="utf-8")

        # 3. Java Model
        (self.proj_dir / "src" / "models" / "UserEntity.java").write_text('''package com.santra.models;

import java.io.Serializable;

public class UserEntity implements Serializable {
    private Long id;
    private String username;

    public Long getId() {
        return this.id;
    }
}
''', encoding="utf-8")

        # 4. C++ Native Module
        (self.proj_dir / "src" / "native" / "crypto_engine.cpp").write_text('''#include <iostream>
#include "crypto_engine.h"

class CryptoEngine {
public:
    void hash_password() {
    }
};
''', encoding="utf-8")

        # 5. SQL Schema
        (self.proj_dir / "db" / "schema.sql").write_text('''CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(100) NOT NULL
);

CREATE TABLE user_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
''', encoding="utf-8")

        # Index the project
        self.overview = self.engine.index_project(str(self.proj_dir), project_name="sample_polyglot")

    def tearDown(self):
        shutil.rmtree(self.proj_dir, ignore_errors=True)
        shutil.rmtree(self.meta_dir, ignore_errors=True)

    def test_overview_statistics(self):
        """Verifies high-level project metrics."""
        self.assertEqual(self.overview.total_files, 5)
        self.assertIn("python", self.overview.languages)
        self.assertIn("typescript", self.overview.languages)
        self.assertIn("java", self.overview.languages)
        self.assertIn("cpp", self.overview.languages)
        self.assertIn("sql", self.overview.languages)

    def test_query_1_function_lookup(self):
        """Q1: Where is calculate_user_metrics defined?"""
        results = self.engine.find_symbol("calculate_user_metrics", project_name="sample_polyglot")
        self.assertTrue(len(results) >= 1)
        res = results[0]
        self.assertIn("UserService.py", res["relative_path"])
        self.assertEqual(res["symbol_type"], "method")
        self.assertEqual(res["line_number"], 9)
        self.assertIn("Calculates algorithmic activity score", res["docstring"])

    def test_query_2_caller_and_import_lookup(self):
        """Q2: What imports UserService?"""
        dependents = self.engine.find_dependents("UserService", project_name="sample_polyglot")
        self.assertTrue(len(dependents) >= 1)
        dep_sources = [d["source_file"] for d in dependents]
        self.assertTrue(any("UserController.ts" in src for src in dep_sources))

    def test_query_3_cross_language_symbols(self):
        """Q3: What are the main classes and entities in the project?"""
        # Class lookup
        user_service = self.engine.find_symbol("UserService", project_name="sample_polyglot")
        user_controller = self.engine.find_symbol("UserController", project_name="sample_polyglot")
        user_entity = self.engine.find_symbol("UserEntity", project_name="sample_polyglot")
        crypto_engine = self.engine.find_symbol("CryptoEngine", project_name="sample_polyglot")
        users_table = self.engine.find_symbol("users", project_name="sample_polyglot")

        self.assertEqual(len(user_service), 1)
        self.assertEqual(len(user_controller), 1)
        self.assertEqual(len(user_entity), 1)
        self.assertEqual(len(crypto_engine), 1)
        self.assertEqual(len(users_table), 1)
        self.assertEqual(users_table[0]["symbol_type"], "table")

    def test_query_4_foreign_key_and_code_search(self):
        """Q4: Find code that references foreign key user_id."""
        search_results = self.engine.search_code("FOREIGN KEY(user_id)", project_name="sample_polyglot")
        self.assertTrue(len(search_results) >= 1)
        self.assertIn("schema.sql", search_results[0]["relative_path"])

    def test_query_5_explain_project_output(self):
        """Q5: High-level architectural explanation."""
        summary = self.engine.explain_project(str(self.proj_dir))
        self.assertIn("sample_polyglot", summary)
        self.assertIn("5 files", summary)


if __name__ == "__main__":
    unittest.main()

