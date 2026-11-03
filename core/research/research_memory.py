"""SQLite Knowledge and Research Persistence for SANTRA Research Engine.
Houses research sessions, sources, evidence provenance, product cataloging,
price observations, and user research preferences inside memory/jarvis_memory.db.
"""

import json
import time
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.research.research_models import (
    ResearchSession, Source, EvidenceItem, ProductEntity, PriceObservation,
    ResearchCitation, ResearchIntent, ResearchStatus, SourceType, VerificationStatus, ConflictStatus
)
from memory.persistent_memory import persistent_memory

logger = logging.getLogger("Jarvis.ResearchMemory")

class ResearchMemory:
    """Manages SQLite storage and historical query retrieval for research artifacts."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or persistent_memory.db_path
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Initializes research tables and indexes with safe idempotency."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Research Sessions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_sessions (
                    research_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    normalized_query TEXT,
                    category TEXT,
                    market TEXT DEFAULT 'India',
                    language TEXT DEFAULT 'en',
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    status TEXT NOT NULL,
                    final_answer TEXT,
                    comparison_table_json TEXT
                )
            """)

            # 2. Research Sources
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_sources (
                    source_id TEXT PRIMARY KEY,
                    research_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    title TEXT,
                    source_type TEXT,
                    publication_date TEXT,
                    retrieved_at REAL NOT NULL,
                    content_hash TEXT,
                    verification_status TEXT,
                    authority_score REAL,
                    raw_snippet TEXT,
                    adapter_identity TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_sources_session ON research_sources(research_id)")

            # 3. Evidence Items
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    research_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    claim_text TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_domain TEXT,
                    source_type TEXT,
                    publication_date TEXT,
                    retrieval_date REAL NOT NULL,
                    evidence_excerpt TEXT,
                    confidence REAL,
                    verification_status TEXT,
                    conflict_status TEXT,
                    entity_name TEXT,
                    metric_name TEXT,
                    metric_value TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_evidence_session ON research_evidence(research_id)")

            # 4. Product Entities
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_products (
                    product_id TEXT PRIMARY KEY,
                    research_id TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    brand TEXT,
                    category TEXT,
                    specifications_json TEXT,
                    compatibility_json TEXT,
                    rank INTEGER DEFAULT 1,
                    best_for TEXT
                )
            """)

            # 5. Price Observations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    seller TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT DEFAULT 'INR',
                    product_url TEXT,
                    availability TEXT,
                    observed_at REAL NOT NULL,
                    is_verified INTEGER DEFAULT 0,
                    rating REAL,
                    review_count INTEGER,
                    warranty_info TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_prices_product ON research_prices(product_id)")

            # 6. User Research Preferences
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_user_preferences (
                    pref_key TEXT PRIMARY KEY,
                    pref_value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()
            logger.info("[ResearchMemory] Schema successfully initialized.")

    def save_session(self, session: ResearchSession):
        """Persists a complete research session with all sources, evidence, and products."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Upsert Session
            cursor.execute("""
                INSERT OR REPLACE INTO research_sessions
                (research_id, query, normalized_query, category, market, language, created_at, completed_at, status, final_answer, comparison_table_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.research_id,
                session.query,
                session.normalized_query,
                session.intent.value,
                session.constraints.market,
                session.constraints.language,
                session.created_at,
                session.completed_at,
                session.status.value,
                session.final_answer,
                json.dumps(session.comparison_table) if session.comparison_table else None
            ))

            # Insert Sources
            for s in session.sources:
                cursor.execute("""
                    INSERT OR REPLACE INTO research_sources
                    (source_id, research_id, url, domain, title, source_type, publication_date, retrieved_at, content_hash, verification_status, authority_score, raw_snippet, adapter_identity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s.source_id, session.research_id, s.url, s.domain, s.title,
                    s.source_type.value, s.publication_date, s.retrieved_at, s.content_hash,
                    s.verification_status.value, s.authority_score, s.raw_snippet, s.adapter_identity
                ))

            # Insert Evidence
            for e in session.evidence:
                cursor.execute("""
                    INSERT OR REPLACE INTO research_evidence
                    (evidence_id, research_id, source_id, claim_text, source_url, source_domain, source_type, publication_date, retrieval_date, evidence_excerpt, confidence, verification_status, conflict_status, entity_name, metric_name, metric_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    e.evidence_id, session.research_id, e.source_id, e.claim_text,
                    e.source_url, e.source_domain, e.source_type.value, e.publication_date,
                    e.retrieval_date, e.evidence_excerpt, e.confidence, e.verification_status.value,
                    e.conflict_status.value, e.entity_name, e.metric_name, e.metric_value
                ))

            # Insert Products & Prices
            for p in session.products:
                cursor.execute("""
                    INSERT OR REPLACE INTO research_products
                    (product_id, research_id, normalized_name, brand, category, specifications_json, compatibility_json, rank, best_for)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p.product_id, session.research_id, p.normalized_name, p.brand, p.category,
                    json.dumps(p.specifications), json.dumps(p.compatibility), p.rank, p.best_for
                ))

                for price in p.prices:
                    cursor.execute("""
                        INSERT INTO research_prices
                        (product_id, seller, price, currency, product_url, availability, observed_at, is_verified, rating, review_count, warranty_info)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        p.product_id, price.seller, price.price, price.currency,
                        price.product_url, price.availability, price.observed_at,
                        1 if price.is_verified else 0, price.rating, price.review_count, price.warranty_info
                    ))

            conn.commit()
            logger.info(f"[ResearchMemory] Persisted session '{session.research_id}' with {len(session.sources)} sources and {len(session.evidence)} evidence items.")

    def get_latest_session(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent research session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_sessions ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def get_price_history(self, product_name: str) -> List[Dict[str, Any]]:
        """Queries recorded price observations for a given product name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.normalized_name, pr.* FROM research_prices pr
                JOIN research_products p ON pr.product_id = p.product_id
                WHERE p.normalized_name LIKE ?
                ORDER BY pr.observed_at ASC
            """, (f"%{product_name}%",))
            return [dict(r) for r in cursor.fetchall()]

# Singleton instance
research_memory = ResearchMemory()

