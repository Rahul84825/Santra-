"""Project Context Engine with SQLite and FTS5 Full-Text Retrieval."""

import os
import sqlite3
import json
import hashlib
import logging
import contextlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from config import BASE_DIR
from core.project_intelligence.models import (
    ProjectFile,
    CodeSymbol,
    SymbolType,
    DependencyRelation,
    ProjectOverview
)
from core.project_intelligence.scanner import project_scanner, ProjectScanner

logger = logging.getLogger("Jarvis.ProjectContextEngine")


class ProjectContextEngine:
    """Manages SQLite and FTS5 indexed project knowledge for layered context retrieval."""

    def __init__(self, db_path: Optional[str] = None, scanner: Optional[ProjectScanner] = None):
        self.db_path = Path(db_path) if db_path else BASE_DIR / "logs" / "project_intelligence.db"
        self.scanner = scanner or project_scanner
        self._init_database()

    @contextlib.contextmanager
    def _get_connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.db_path), timeout=10.0)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def _init_database(self):
        """Initializes relational tables and FTS5 virtual tables."""
        with self._get_connection() as con:
            cur = con.cursor()

            # Projects metadata
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT UNIQUE NOT NULL,
                    last_scanned REAL NOT NULL,
                    overview_json TEXT NOT NULL
                )
            """)

            # Files index
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    line_count INTEGER NOT NULL,
                    file_hash TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # Symbol index (functions, classes, methods, endpoints)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    docstring TEXT,
                    parameters_json TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # Dependencies / Import graph
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    target_module TEXT NOT NULL,
                    imported_symbol TEXT,
                    line_number INTEGER,
                    dependency_kind TEXT DEFAULT 'static_import',
                    is_inferred INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 1.0,
                    status TEXT DEFAULT 'CONFIRMED',
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)

            # Ensure columns exist if migrating existing database
            try:
                cur.execute("ALTER TABLE dependencies ADD COLUMN dependency_kind TEXT DEFAULT 'static_import'")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE dependencies ADD COLUMN is_inferred INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE dependencies ADD COLUMN confidence REAL DEFAULT 1.0")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE dependencies ADD COLUMN status TEXT DEFAULT 'CONFIRMED'")
            except sqlite3.OperationalError:
                pass

            # Virtual FTS5 Full-Text Search Table for fast BM25 code indexing
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_code USING fts5(
                    project_id UNINDEXED,
                    file_path UNINDEXED,
                    relative_path,
                    content,
                    tokenize = 'porter unicode61'
                )
            """)

            con.commit()

    def index_project(self, project_path: str, project_name: Optional[str] = None) -> ProjectOverview:
        """Scans and indexes the target project into SQLite and FTS5."""
        overview, files, dependencies = self.scanner.scan_directory(project_path, project_name=project_name)
        p_id = (project_name or overview.project_name).lower().strip()

        with self._get_connection() as con:
            cur = con.cursor()

            # Clear existing data for this project
            cur.execute("DELETE FROM fts_code WHERE project_id = ?", (p_id,))
            cur.execute("DELETE FROM dependencies WHERE project_id = ?", (p_id,))
            cur.execute("DELETE FROM symbols WHERE project_id = ?", (p_id,))
            cur.execute("DELETE FROM files WHERE project_id = ?", (p_id,))
            cur.execute("DELETE FROM projects WHERE id = ?", (p_id,))

            # Insert Project
            cur.execute("""
                INSERT INTO projects (id, name, root_path, last_scanned, overview_json)
                VALUES (?, ?, ?, ?, ?)
            """, (p_id, overview.project_name, overview.root_path, overview.last_scanned, json.dumps(overview.to_dict())))

            # Insert Files & FTS
            for f in files:
                cur.execute("""
                    INSERT INTO files (project_id, path, relative_path, language, size_bytes, line_count, file_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (p_id, f.path, f.relative_path, f.language, f.size_bytes, f.line_count, f.file_hash))

                # Index symbols
                for sym in f.symbols:
                    cur.execute("""
                        INSERT INTO symbols (project_id, file_path, relative_path, name, symbol_type, line_number, end_line, docstring, parameters_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        p_id, sym.file_path, sym.relative_path, sym.name, sym.symbol_type.value,
                        sym.line_number, sym.end_line, sym.docstring, json.dumps(sym.parameters)
                    ))

                # Index content into FTS if not binary
                if not f.is_binary and Path(f.path).exists():
                    try:
                        with open(f.path, "r", encoding="utf-8", errors="replace") as content_file:
                            code_text = content_file.read()

                        # Privacy & Prompt-Injection Neutralization
                        try:
                            from core.security.privacy_guard import privacy_guard
                            sanitized_text, _, _ = privacy_guard.redact_text(code_text)
                            sanitized_text = privacy_guard.sanitize_external_output(sanitized_text)
                        except Exception:
                            sanitized_text = code_text

                        cur.execute("""
                            INSERT INTO fts_code (project_id, file_path, relative_path, content)
                            VALUES (?, ?, ?, ?)
                        """, (p_id, f.path, f.relative_path, sanitized_text))
                    except Exception:
                        pass

            # Insert Dependencies
            for d in dependencies:
                conf_level = getattr(d, 'confidence_level', 'CONFIRMED')
                cur.execute("""
                    INSERT INTO dependencies (project_id, source_file, target_module, imported_symbol, line_number, dependency_kind, is_inferred, confidence, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (p_id, d.source_file, d.target_module, d.imported_symbol, d.line_number, d.dependency_kind, 1 if d.is_inferred else 0, getattr(d, 'confidence', 1.0), conf_level))

            con.commit()

        logger.info(f"[CONTEXT_ENGINE] Successfully indexed project '{overview.project_name}' into database.")
        return overview

    def search_code(self, query: str, project_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Full-Text BM25 Code Search across project files using SQLite FTS5."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Sanitize query for FTS5:
        # Wrap in double quotes to safely handle symbols like '.', ':', '*', '(', ')', '-', '/', '\'
        # and escape any embedded double quotes as '""'
        escaped_query = clean_query.replace('"', '""')
        safe_query = f'"{escaped_query}"'

        results = []
        with self._get_connection() as con:
            cur = con.cursor()
            if project_name:
                sql = """
                    SELECT relative_path, file_path, snippet(fts_code, 3, '<b>', '</b>', '...', 20) as match_snippet
                    FROM fts_code
                    WHERE project_id = ? AND fts_code MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
                params = (project_name.lower().strip(), safe_query, limit)
            else:
                sql = """
                    SELECT relative_path, file_path, snippet(fts_code, 3, '<b>', '</b>', '...', 20) as match_snippet
                    FROM fts_code
                    WHERE fts_code MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
                params = (safe_query, limit)

            try:
                cur.execute(sql, params)
                for r in cur.fetchall():
                    snippet_text = r["match_snippet"]
                    try:
                        from core.security.privacy_guard import privacy_guard
                        snippet_text, _, _ = privacy_guard.redact_text(snippet_text)
                    except Exception:
                        pass
                    results.append({
                        "relative_path": r["relative_path"],
                        "file_path": r["file_path"],
                        "snippet": snippet_text
                    })
            except Exception as e:
                logger.debug(f"[CONTEXT_ENGINE] FTS search error: {e}")

        return results

    def find_symbol(self, symbol_name: str, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds definition file, line number, and docstring for a function, class, or method."""
        clean_sym = symbol_name.strip()
        results = []
        with self._get_connection() as con:
            cur = con.cursor()
            if project_name:
                cur.execute("""
                    SELECT name, symbol_type, relative_path, file_path, line_number, end_line, docstring
                    FROM symbols
                    WHERE project_id = ? AND (name = ? OR name LIKE ?)
                    LIMIT 20
                """, (project_name.lower().strip(), clean_sym, f"%.{clean_sym}"))
            else:
                cur.execute("""
                    SELECT name, symbol_type, relative_path, file_path, line_number, end_line, docstring
                    FROM symbols
                    WHERE name = ? OR name LIKE ?
                    LIMIT 20
                """, (clean_sym, f"%.{clean_sym}"))

            for r in cur.fetchall():
                results.append({
                    "name": r["name"],
                    "symbol_type": r["symbol_type"],
                    "relative_path": r["relative_path"],
                    "file_path": r["file_path"],
                    "line_number": r["line_number"],
                    "end_line": r["end_line"],
                    "docstring": r["docstring"] or ""
                })
        return results

    def get_dependencies(self, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves dependencies for a project or across all projects."""
        results = []
        with self._get_connection() as con:
            cur = con.cursor()
            if project_name:
                cur.execute("""
                    SELECT source_file, target_module, imported_symbol, line_number, dependency_kind, is_inferred
                    FROM dependencies
                    WHERE project_id = ?
                    LIMIT 100
                """, (project_name.lower().strip(),))
            else:
                cur.execute("""
                    SELECT source_file, target_module, imported_symbol, line_number, dependency_kind, is_inferred
                    FROM dependencies
                    LIMIT 100
                """)
            for r in cur.fetchall():
                results.append({
                    "source_file": r["source_file"],
                    "target_module": r["target_module"],
                    "imported_symbol": r["imported_symbol"],
                    "line_number": r["line_number"],
                    "dependency_kind": r["dependency_kind"] if "dependency_kind" in r.keys() else "static_import",
                    "is_inferred": bool(r["is_inferred"]) if "is_inferred" in r.keys() else False
                })
        return results

    def find_dependents(self, module_name_or_file: str, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Identifies which project files import or depend on a given module or file."""
        clean_target = Path(module_name_or_file).stem.lower()
        results = []
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT source_file, target_module, imported_symbol, line_number, dependency_kind, is_inferred
                FROM dependencies
                WHERE target_module = ? OR target_module LIKE ?
                LIMIT 50
            """, (clean_target, f"%{clean_target}%"))

            for r in cur.fetchall():
                results.append({
                    "source_file": r["source_file"],
                    "target_module": r["target_module"],
                    "imported_symbol": r["imported_symbol"],
                    "line_number": r["line_number"],
                    "dependency_kind": r["dependency_kind"] if "dependency_kind" in r.keys() else "static_import",
                    "is_inferred": bool(r["is_inferred"]) if "is_inferred" in r.keys() else False
                })
        return results

    def invalidate_file(self, file_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Removes all indexed records (files, symbols, dependencies, fts_code) for a deleted or modified file."""
        norm_path = str(Path(file_path).resolve())
        rel_clean = Path(file_path).as_posix().lstrip("./")
        p_id = project_name.lower().strip() if project_name else None

        with self._get_connection() as con:
            cur = con.cursor()
            if p_id:
                cur.execute("""
                    DELETE FROM fts_code 
                    WHERE project_id = ? AND (file_path = ? OR relative_path = ? OR file_path LIKE ?)
                """, (p_id, norm_path, rel_clean, f"%{rel_clean}"))
                cur.execute("""
                    DELETE FROM dependencies 
                    WHERE project_id = ? AND (source_file = ? OR source_file = ? OR source_file LIKE ?)
                """, (p_id, norm_path, rel_clean, f"%{rel_clean}"))
                cur.execute("""
                    DELETE FROM symbols 
                    WHERE project_id = ? AND (file_path = ? OR relative_path = ? OR file_path LIKE ?)
                """, (p_id, norm_path, rel_clean, f"%{rel_clean}"))
                cur.execute("""
                    DELETE FROM files 
                    WHERE project_id = ? AND (path = ? OR relative_path = ? OR path LIKE ?)
                """, (p_id, norm_path, rel_clean, f"%{rel_clean}"))
            else:
                cur.execute("""
                    DELETE FROM fts_code 
                    WHERE file_path = ? OR relative_path = ? OR file_path LIKE ?
                """, (norm_path, rel_clean, f"%{rel_clean}"))
                cur.execute("""
                    DELETE FROM dependencies 
                    WHERE source_file = ? OR source_file = ? OR source_file LIKE ?
                """, (norm_path, rel_clean, f"%{rel_clean}"))
                cur.execute("""
                    DELETE FROM symbols 
                    WHERE file_path = ? OR relative_path = ? OR file_path LIKE ?
                """, (norm_path, rel_clean, f"%{rel_clean}"))
                cur.execute("""
                    DELETE FROM files 
                    WHERE path = ? OR relative_path = ? OR path LIKE ?
                """, (norm_path, rel_clean, f"%{rel_clean}"))
            con.commit()
        logger.info(f"[CONTEXT_ENGINE] Stale index invalidated for file: '{file_path}'")
        return {"action": "purged", "file_path": file_path, "project_id": p_id}

    def update_file(self, file_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Incrementally re-indexes a single file upon modification without full project re-scan."""
        p = Path(file_path)
        p_id = project_name.lower().strip() if project_name else None
        root_path = None

        if not p.is_absolute():
            with self._get_connection() as con:
                cur = con.cursor()
                if p_id:
                    cur.execute("SELECT root_path FROM projects WHERE id = ?", (p_id,))
                    row = cur.fetchone()
                    if row:
                        root_path = Path(row["root_path"])
                else:
                    cur.execute("SELECT root_path FROM projects LIMIT 1")
                    row = cur.fetchone()
                    if row:
                        root_path = Path(row["root_path"])
            if root_path:
                p = (root_path / file_path).resolve()
            else:
                p = p.resolve()
        else:
            p = p.resolve()

        if not p.exists():
            return self.invalidate_file(str(p), project_name=p_id)

        # Invalidate existing records first
        self.invalidate_file(str(p), project_name=p_id)

        # Look up project_id and root_path from database if not supplied
        if not p_id:
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute("SELECT id, root_path FROM projects")
                for row in cur.fetchall():
                    try:
                        p.relative_to(Path(row["root_path"]))
                        p_id = row["id"]
                        root_path = Path(row["root_path"])
                        break
                    except ValueError:
                        continue

        if not root_path:
            with self._get_connection() as con:
                cur = con.cursor()
                if p_id:
                    cur.execute("SELECT root_path FROM projects WHERE id = ?", (p_id,))
                    row = cur.fetchone()
                    if row:
                        root_path = Path(row["root_path"])

        root_path = root_path or p.parent
        p_id = p_id or "default"

        p_file, deps = self.scanner.scan_single_file(p, root_path)
        if not p_file:
            return {"action": "purged", "file_path": str(p), "project_id": p_id}

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO files (project_id, path, relative_path, language, size_bytes, line_count, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (p_id, p_file.path, p_file.relative_path, p_file.language, p_file.size_bytes, p_file.line_count, p_file.file_hash))

            for sym in p_file.symbols:
                cur.execute("""
                    INSERT INTO symbols (project_id, file_path, relative_path, name, symbol_type, line_number, end_line, docstring, parameters_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p_id, sym.file_path, sym.relative_path, sym.name, sym.symbol_type.value,
                    sym.line_number, sym.end_line, sym.docstring, json.dumps(sym.parameters)
                ))

            if not p_file.is_binary and p.exists():
                try:
                    with open(p_file.path, "r", encoding="utf-8", errors="replace") as content_file:
                        code_text = content_file.read()
                    cur.execute("""
                        INSERT INTO fts_code (project_id, file_path, relative_path, content)
                        VALUES (?, ?, ?, ?)
                    """, (p_id, p_file.path, p_file.relative_path, code_text))
                except Exception:
                    pass

            for d in deps:
                conf_level = getattr(d, 'confidence_level', 'CONFIRMED')
                cur.execute("""
                    INSERT INTO dependencies (project_id, source_file, target_module, imported_symbol, line_number, dependency_kind, is_inferred, confidence, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (p_id, d.source_file, d.target_module, d.imported_symbol, d.line_number, d.dependency_kind, 1 if d.is_inferred else 0, getattr(d, 'confidence', 1.0), conf_level))

            con.commit()

        logger.info(f"[CONTEXT_ENGINE] Incrementally re-indexed '{p_file.relative_path}' into project '{p_id}'.")
        return {
            "action": "reindexed",
            "relative_path": p_file.relative_path,
            "project_id": p_id,
            "symbols_count": len(p_file.symbols),
            "dependencies_count": len(deps)
        }

    def get_project_overview(self, project_path_or_name: str) -> Optional[ProjectOverview]:
        """Retrieves cached project overview from SQLite."""
        p_id = Path(project_path_or_name).name.lower().strip()
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT overview_json FROM projects WHERE id = ? OR root_path = ?", (p_id, project_path_or_name))
            row = cur.fetchone()
            if row:
                data = json.loads(row["overview_json"])
                return ProjectOverview(
                    project_name=data["project_name"],
                    root_path=data["root_path"],
                    total_files=data["total_files"],
                    total_lines=data["total_lines"],
                    languages=data["languages"],
                    frameworks=data["frameworks"],
                    entry_points=data["entry_points"],
                    test_files_count=data["test_files_count"],
                    documentation_files=data["documentation_files"],
                    last_scanned=data["last_scanned"]
                )
        return None

    def explain_project(self, project_path: str) -> str:
        """Generates an architectural summary and high-level explanation of the project."""
        overview = self.get_project_overview(project_path)
        if not overview:
            overview = self.index_project(project_path)

        lang_str = ", ".join(f"{lang} ({cnt} files)" for lang, cnt in sorted(overview.languages.items(), key=lambda x: -x[1])[:4])
        fw_str = ", ".join(overview.frameworks) if overview.frameworks else "Standard library / custom architecture"
        entry_str = ", ".join(overview.entry_points) if overview.entry_points else "None detected"

        explanation = (
            f"Project '{overview.project_name}' contains {overview.total_files} files and approximately {overview.total_lines:,} lines of code. "
            f"Primary languages include: {lang_str}. "
            f"Detected frameworks: {fw_str}. "
            f"Key entry points: {entry_str}. "
            f"The project includes {overview.test_files_count} test files."
        )
        return explanation

    def trace_call_chain(self, start_point: str, end_point: Optional[str] = None, max_depth: int = 5) -> List[Dict[str, Any]]:
        """Traces deep multi-hop relationship chains (API -> Route -> Controller -> Service -> Model -> DB Table)."""
        chain = []
        visited = set()
        queue = [(start_point, 0, [])]

        with self._get_connection() as con:
            cur = con.cursor()
            while queue:
                curr, depth, path = queue.pop(0)
                if curr in visited or depth > max_depth:
                    continue
                visited.add(curr)

                clean_curr = curr.strip()
                cur.execute("""
                    SELECT source_file, target_module, imported_symbol, dependency_kind, is_inferred, confidence
                    FROM dependencies
                    WHERE source_file LIKE ? OR target_module = ? OR target_module LIKE ? OR imported_symbol = ?
                """, (f"%{clean_curr}%", clean_curr, f"%{clean_curr}%", clean_curr))

                rows = cur.fetchall()
                for r in rows:
                    step = {
                        "from": Path(r["source_file"]).name,
                        "to": r["target_module"],
                        "symbol": r["imported_symbol"] or "",
                        "kind": r["dependency_kind"],
                        "is_inferred": bool(r["is_inferred"]),
                        "confidence": float(r["confidence"]) if "confidence" in r.keys() else 1.0,
                        "depth": depth
                    }
                    new_path = path + [step]
                    if end_point and (end_point.lower() in r["target_module"].lower() or (r["imported_symbol"] and end_point.lower() in r["imported_symbol"].lower())):
                        return new_path
                    chain.append(step)
                    if depth < max_depth:
                        nxt = r["target_module"]
                        if nxt and nxt not in visited:
                            queue.append((nxt, depth + 1, new_path))
        return chain

    def get_test_coverage_mapping(self, source_file: str) -> List[Dict[str, Any]]:
        """Returns all test files covering a given source file with confidence scores."""
        target_stem = Path(source_file).stem.lower()
        results = []
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT source_file, target_module, imported_symbol, confidence
                FROM dependencies
                WHERE (dependency_kind = 'test_coverage' OR source_file LIKE '%test%')
                  AND (target_module LIKE ? OR source_file LIKE ?)
            """, (f"%{target_stem}%", f"%{target_stem}%"))
            for r in cur.fetchall():
                results.append({
                    "test_file": r["source_file"],
                    "target_module": r["target_module"],
                    "confidence": float(r["confidence"]) if "confidence" in r.keys() else 0.95
                })
        return results

    def get_deep_architecture_graph(self, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Summarizes multi-tier architectural layers and confirmed vs inferred relationships."""
        p_id = project_name.lower().strip() if project_name else None
        with self._get_connection() as con:
            cur = con.cursor()
            if p_id:
                cur.execute("""
                    SELECT dependency_kind, is_inferred, COUNT(*) as cnt, AVG(confidence) as avg_conf
                    FROM dependencies
                    WHERE project_id = ?
                    GROUP BY dependency_kind, is_inferred
                """, (p_id,))
            else:
                cur.execute("""
                    SELECT dependency_kind, is_inferred, COUNT(*) as cnt, AVG(confidence) as avg_conf
                    FROM dependencies
                    GROUP BY dependency_kind, is_inferred
                """)
            breakdown = []
            confirmed_count = 0
            inferred_count = 0
            for r in cur.fetchall():
                kind = r["dependency_kind"]
                is_inf = bool(r["is_inferred"])
                cnt = r["cnt"]
                if is_inf:
                    inferred_count += cnt
                else:
                    confirmed_count += cnt
                breakdown.append({
                    "kind": kind,
                    "is_inferred": is_inf,
                    "count": cnt,
                    "avg_confidence": round(r["avg_conf"] or 1.0, 2)
                })

            routes = []
            models = []
            auth_guards = []
            middleware_list = []
            config_vars = []

            sym_query = "SELECT name, symbol_type, relative_path FROM symbols WHERE symbol_type IN ('route', 'model', 'table', 'view', 'auth_guard', 'middleware', 'config')"
            sym_params = ()
            if p_id:
                sym_query += " AND project_id = ?"
                sym_params = (p_id,)
            cur.execute(sym_query, sym_params)
            for s in cur.fetchall():
                item = {"name": s["name"], "path": s["relative_path"]}
                st = s["symbol_type"]
                if st == "route":
                    routes.append(item)
                elif st in ["model", "table", "view"]:
                    models.append(item)
                elif st == "auth_guard":
                    auth_guards.append(item)
                elif st == "middleware":
                    middleware_list.append(item)
                elif st == "config":
                    config_vars.append(item)

            # Epistemic status counts: CONFIRMED, INFERRED, PARTIALLY_ANALYZED, UNKNOWN, UNSUPPORTED
            status_query = "SELECT status, COUNT(*) as cnt FROM dependencies"
            status_params = ()
            if p_id:
                status_query += " WHERE project_id = ?"
                status_params = (p_id,)
            status_query += " GROUP BY status"
            cur.execute(status_query, status_params)
            status_counts = {"CONFIRMED": 0, "INFERRED": 0, "PARTIALLY_ANALYZED": 0, "UNKNOWN": 0, "UNSUPPORTED": 0}
            for s_row in cur.fetchall():
                st_name = s_row["status"] or "UNKNOWN"
                status_counts[st_name] = s_row["cnt"]

            return {
                "total_confirmed": confirmed_count,
                "total_inferred": inferred_count,
                "status_breakdown": status_counts,
                "relationship_breakdown": breakdown,
                "routes": routes,
                "models_and_tables": models,
                "auth_guards": auth_guards,
                "middleware": middleware_list,
                "config_variables": config_vars
            }


project_context_engine = ProjectContextEngine()
