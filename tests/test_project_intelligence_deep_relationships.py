import unittest
import tempfile
import shutil
from pathlib import Path

from core.project_intelligence.scanner import ProjectScanner
from core.project_intelligence.context_engine import ProjectContextEngine
from core.project_intelligence.models import SymbolType

class TestProjectIntelligenceDeepRelationships(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="santra_test_proj_")
        self.proj_path = Path(self.temp_dir)
        self.scanner = ProjectScanner()
        self.engine = ProjectContextEngine(
            db_path=str(self.proj_path / "test_context.db"),
            scanner=self.scanner
        )

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def test_multi_tier_deep_extraction(self):
        # 1. Create a Flask/FastAPI backend file with Route, Controller, Service calls
        server_code = """
from flask import Flask, jsonify
from services.user_service import UserService

app = Flask(__name__)

@app.route('/api/v1/users', methods=['GET'])
def get_users():
    '''Fetches all user accounts.'''
    users = UserService.list_all()
    return jsonify(users)
"""
        (self.proj_path / "server.py").write_text(server_code, encoding="utf-8")

        # 2. Create Service & Model file with ForeignKey
        service_code = """
class UserService:
    @staticmethod
    def list_all():
        return User.query.all()
"""
        (self.proj_path / "services").mkdir(parents=True, exist_ok=True)
        (self.proj_path / "services" / "user_service.py").write_text(service_code, encoding="utf-8")

        model_code = """
from sqlalchemy import Column, Integer, String, ForeignKey
from database import Base

class User(Base):
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id'))
    username = Column(String)
"""
        (self.proj_path / "models").mkdir(parents=True, exist_ok=True)
        (self.proj_path / "models" / "user.py").write_text(model_code, encoding="utf-8")

        # 3. Create Frontend JS file with fetch call
        frontend_code = """
async function loadUserData() {
    const res = await fetch('/api/v1/users');
    return await res.json();
}
"""
        (self.proj_path / "frontend").mkdir(parents=True, exist_ok=True)
        (self.proj_path / "frontend" / "app.js").write_text(frontend_code, encoding="utf-8")

        # 4. Create Test file
        test_code = """
import unittest
from server import app

class TestServer(unittest.TestCase):
    def test_get_users(self):
        client = app.test_client()
        res = client.get('/api/v1/users')
        self.assertEqual(res.status_code, 200)
"""
        (self.proj_path / "tests").mkdir(parents=True, exist_ok=True)
        (self.proj_path / "tests" / "test_server.py").write_text(test_code, encoding="utf-8")

        # Index the project
        overview = self.engine.index_project(str(self.proj_path), project_name="FullStackApp")
        self.assertGreater(overview.total_files, 0)

        # Verify Route symbol extracted
        route_syms = [s for s in self.engine.find_symbol("GET /api/v1/users", project_name="FullStackApp")]
        self.assertTrue(any(s["symbol_type"] == "route" for s in route_syms))

        # Verify Model symbol extracted
        model_syms = [s for s in self.engine.find_symbol("User", project_name="FullStackApp")]
        self.assertTrue(any(s["symbol_type"] == "model" for s in model_syms))

        # Verify Deep Architecture Graph
        arch = self.engine.get_deep_architecture_graph(project_name="FullStackApp")
        self.assertGreater(arch["total_confirmed"], 0)
        self.assertGreater(arch["total_inferred"], 0)

        # Verify Test Coverage Mapping
        cov = self.engine.get_test_coverage_mapping("server.py")
        self.assertTrue(any("test_server" in c["test_file"].lower() for c in cov))

        # Verify Call Chain Trace from API endpoint to route handler
        chain = self.engine.trace_call_chain("/api/v1/users")
        self.assertGreater(len(chain), 0)
        self.assertTrue(any(step["to"] == "/api/v1/users" for step in chain))

    def test_auth_guard_and_middleware_extraction(self):
        auth_code = """
from functools import wraps

def login_required(f):
    '''Auth guard decorator.'''
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

class SessionAuthMiddleware:
    '''Custom session middleware.'''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)
"""
        (self.proj_path / "auth.py").write_text(auth_code, encoding="utf-8")
        self.engine.index_project(str(self.proj_path), project_name="AuthApp")

        arch = self.engine.get_deep_architecture_graph(project_name="AuthApp")
        guard_names = [g["name"] for g in arch["auth_guards"]]
        middleware_names = [m["name"] for m in arch["middleware"]]

        self.assertIn("login_required", guard_names)
        self.assertIn("SessionAuthMiddleware", middleware_names)

    def test_sensitive_file_exclusion_and_config_protection(self):
        # 1. Create sensitive .env and credentials.json files
        env_content = "DB_HOST=10.0.0.5\nDB_PASS=SuperSecretPassword123\nSTRIPE_KEY=sk_live_9988776655\nPORT=8080\n"
        (self.proj_path / ".env").write_text(env_content, encoding="utf-8")

        cred_content = '{"private_key_id": "abcdef123456", "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvgIBADANBgk..."}'
        (self.proj_path / "credentials.json").write_text(cred_content, encoding="utf-8")

        # 2. Create normal python file
        (self.proj_path / "main.py").write_text("print('Santra Core Running')", encoding="utf-8")

        self.engine.index_project(str(self.proj_path), project_name="SecuredApp")

        # Verify secrets are NOT in FTS code search
        fts_pass = self.engine.search_code("SuperSecretPassword123", project_name="SecuredApp")
        self.assertEqual(len(fts_pass), 0, "Secret password must NEVER be indexed into FTS!")

        fts_key = self.engine.search_code("sk_live_9988776655", project_name="SecuredApp")
        self.assertEqual(len(fts_key), 0, "Secret API key must NEVER be indexed into FTS!")

        # Verify config variable names ARE discovered as SymbolType.CONFIG
        arch = self.engine.get_deep_architecture_graph(project_name="SecuredApp")
        config_names = [c["name"] for c in arch["config_variables"]]
        self.assertIn("DB_HOST", config_names)
        self.assertIn("PORT", config_names)

        # Verify config signatures protect secret values
        db_pass_syms = self.engine.find_symbol("DB_PASS", project_name="SecuredApp")
        self.assertTrue(len(db_pass_syms) > 0)
        self.assertEqual(db_pass_syms[0]["symbol_type"], "config")

    def test_incremental_indexing_invalidation_lifecycle(self):
        # 1. Initial project setup
        (self.proj_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        self.engine.index_project(str(self.proj_path), project_name="CalcProject")

        syms = self.engine.find_symbol("add", project_name="CalcProject")
        self.assertEqual(len(syms), 1)

        # 2. Modify file: add subtract function
        (self.proj_path / "calc.py").write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n", encoding="utf-8")
        res_mod = self.engine.update_file("calc.py", project_name="CalcProject")
        self.assertEqual(res_mod["action"], "reindexed")
        self.assertEqual(res_mod["symbols_count"], 2)

        syms_sub = self.engine.find_symbol("sub", project_name="CalcProject")
        self.assertEqual(len(syms_sub), 1)

        # 3. Create new file and update/reindex it
        (self.proj_path / "mult.py").write_text("def multiply(a, b):\n    return a * b\n", encoding="utf-8")
        res_new = self.engine.update_file("mult.py", project_name="CalcProject")
        self.assertEqual(res_new["action"], "reindexed")
        syms_mult = self.engine.find_symbol("multiply", project_name="CalcProject")
        self.assertEqual(len(syms_mult), 1)

        # 4. Delete file and invalidate (purge) it
        (self.proj_path / "mult.py").unlink()
        res_del = self.engine.invalidate_file("mult.py", project_name="CalcProject")
        self.assertEqual(res_del["action"], "purged")

        syms_mult_after = self.engine.find_symbol("multiply", project_name="CalcProject")
        self.assertEqual(len(syms_mult_after), 0)

    def test_status_breakdown_epistemic_classification(self):
        code = """
import os
from math import sqrt
"""
        (self.proj_path / "epistemic.py").write_text(code, encoding="utf-8")
        self.engine.index_project(str(self.proj_path), project_name="EpistemicApp")

        arch = self.engine.get_deep_architecture_graph(project_name="EpistemicApp")
        breakdown = arch["status_breakdown"]
        self.assertIn("CONFIRMED", breakdown)
        self.assertIn("INFERRED", breakdown)
        self.assertIn("PARTIALLY_ANALYZED", breakdown)
        self.assertIn("UNKNOWN", breakdown)
        self.assertIn("UNSUPPORTED", breakdown)
        self.assertGreater(breakdown["CONFIRMED"], 0)


if __name__ == "__main__":
    unittest.main()

