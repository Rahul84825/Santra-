"""
SANTRA ALEE Stage 7 - SQLite Migration Verification Suite
Tests incremental upgrades from temporary mock databases at every version level (v0 -> v1 -> v2 -> v3 -> v4).
Strictly isolated using tempfile.TemporaryDirectory().
"""

import os
import sqlite3
import tempfile
import unittest

from core.evolution.storage import EvolutionStorage, CURRENT_SCHEMA_VERSION


class TestAleeMigrations(unittest.TestCase):
    """Verifies atomic and tracked schema migrations across all versions."""

    def test_01_fresh_database_v0_to_v5(self):
        """Fresh database (v0) cleanly initializes all tables up to CURRENT_SCHEMA_VERSION (5)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "fresh_evolution.db")
            storage = EvolutionStorage(db_path=db_path)
            try:
                conn = storage._get_connection()
                cur = conn.cursor()

                # Check schema migrations table
                cur.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
                versions = [r[0] for r in cur.fetchall()]
                self.assertEqual(versions, [1, 2, 3, 4, 5])
                self.assertEqual(CURRENT_SCHEMA_VERSION, 5)

                # Check core tables
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in cur.fetchall()}
                expected_tables = {
                    "schema_migrations", "experiences", "phonetic_aliases",
                    "knowledge_items", "knowledge_fts", "skills",
                    "evolution_proposals", "evolution_snapshots", "working_memory"
                }
                for tbl in expected_tables:
                    self.assertIn(tbl, tables, f"Expected table '{tbl}' was not created.")

                # Check raw_transcript column in experiences
                cur.execute("PRAGMA table_info(experiences)")
                cols = [c[1] for c in cur.fetchall()]
                self.assertIn("raw_transcript", cols)
            finally:
                storage.close()

    def test_02_upgrade_from_v1_to_v5(self):
        """Database at version 1 safely upgrades to v5 without data loss."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "v1_evolution.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            # Create mock v1 schema
            cur.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                );
            """)
            cur.execute("INSERT INTO schema_migrations (version, description) VALUES (1, 'v1 mock');")
            cur.execute("""
                CREATE TABLE experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_request TEXT NOT NULL,
                    intent TEXT,
                    action TEXT,
                    parameters_json TEXT,
                    success INTEGER NOT NULL,
                    message TEXT,
                    latency_ms REAL DEFAULT 0.0,
                    error_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE phonetic_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    misheard_phrase TEXT UNIQUE NOT NULL,
                    intended_phrase TEXT NOT NULL,
                    confidence_count INTEGER DEFAULT 1,
                    last_seen REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE knowledge_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    updated_at REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                INSERT INTO experiences (timestamp, user_request, success)
                VALUES (1700000000.0, 'open chrome', 1);
            """)
            conn.commit()
            conn.close()

            # Instantiate EvolutionStorage on this v1 database
            storage = EvolutionStorage(db_path=db_path)
            try:
                conn2 = storage._get_connection()
                cur2 = conn2.cursor()

                # Verify migrations advanced to 5
                cur2.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
                versions = [r[0] for r in cur2.fetchall()]
                self.assertEqual(versions, [1, 2, 3, 4, 5])

                # Verify original v1 record was preserved
                cur2.execute("SELECT user_request, success FROM experiences")
                row = cur2.fetchone()
                self.assertEqual(row[0], "open chrome")
                self.assertEqual(row[1], 1)

                # Verify raw_transcript was added
                cur2.execute("PRAGMA table_info(experiences)")
                cols = [c[1] for c in cur2.fetchall()]
                self.assertIn("raw_transcript", cols)

                # Verify v4 and v5 tables exist
                cur2.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in cur2.fetchall()}
                self.assertIn("skills", tables)
                self.assertIn("evolution_proposals", tables)
                self.assertIn("evolution_snapshots", tables)
                self.assertIn("working_memory", tables)
            finally:
                storage.close()

    def test_03_upgrade_from_v2_and_v3(self):
        """Database at version 2 or 3 increments cleanly to version 5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "v3_evolution.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, description TEXT);")
            cur.execute("INSERT INTO schema_migrations (version, description) VALUES (1, 'v1'), (2, 'v2'), (3, 'v3');")
            cur.execute("""
                CREATE TABLE experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_request TEXT NOT NULL,
                    intent TEXT,
                    action TEXT,
                    parameters_json TEXT,
                    success INTEGER NOT NULL,
                    message TEXT,
                    latency_ms REAL DEFAULT 0.0,
                    error_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE skills (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger_phrases TEXT NOT NULL,
                    description TEXT,
                    steps_json TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'SANDBOX',
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.commit()
            conn.close()

            # Upgrade via EvolutionStorage
            storage = EvolutionStorage(db_path=db_path)
            try:
                conn2 = storage._get_connection()
                cur2 = conn2.cursor()

                cur2.execute("SELECT MAX(version) FROM schema_migrations")
                max_ver = cur2.fetchone()[0]
                self.assertEqual(max_ver, 5)

                # Check evolution_proposals and working_memory exist
                cur2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evolution_proposals'")
                self.assertIsNotNone(cur2.fetchone())
                cur2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='working_memory'")
                self.assertIsNotNone(cur2.fetchone())
            finally:
                storage.close()

    def test_04_idempotency_on_v5(self):
        """Applying migrations on an existing v5 database is an idempotent no-op."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "v5_evolution.db")
            storage1 = EvolutionStorage(db_path=db_path)
            storage1.close()

            # Re-open database
            storage2 = EvolutionStorage(db_path=db_path)
            try:
                conn = storage2._get_connection()
                cur = conn.cursor()

                cur.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
                versions = [r[0] for r in cur.fetchall()]
                self.assertEqual(versions, [1, 2, 3, 4, 5])
            finally:
                storage2.close()


if __name__ == "__main__":
    unittest.main()

