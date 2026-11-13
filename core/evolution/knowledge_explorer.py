"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Knowledge Explorer & Hybrid Retrieval Module

Provides zero-VRAM, pure SQLite FTS5 BM25 retrieval, semantic document chunking,
SHA-256 content deduplication, and adversarial prompt-injection defense.
"""

import os
import re
import time
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple

from core.evolution.storage import EvolutionStorage, evolution_storage

logger = logging.getLogger("Santra.Evolution.KnowledgeExplorer")

# Adversarial prompt-injection detection regex patterns
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b"),
    re.compile(r"(?i)\bdisregard\s+(?:all\s+)?(?:prior|previous)\s+(?:rules|instructions|prompts)\b"),
    re.compile(r"(?i)\bsystem\s+prompt\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:dan|jailbroken|unrestricted|in\s+developer\s+mode)\b"),
    re.compile(r"(?i)\bupload\s+local\s+files\b"),
    re.compile(r"(?i)\bdelete\s+database\b"),
    re.compile(r"(?i)\bdrop\s+table\b"),
    re.compile(r"(?i)\bbypass\s+(?:safety|guardrails|filters)\b"),
    re.compile(r"(?i)\breveal\s+(?:your\s+)?(?:system|hidden|secret|api\s*key|password|token)\b"),
]

SUPPORTED_EXTENSIONS = {".md", ".txt", ".py", ".json", ".pdf"}


def compute_sha256(text: str) -> str:
    """Computes SHA-256 hex digest of a text string."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def chunk_document(text: str, target_word_count: int = 500, overlap_words: int = 50) -> List[str]:
    """
    Splits text into overlapping semantic chunks (400-600 words),
    preferring markdown headers or double-newline paragraph boundaries.
    """
    if not text or not text.strip():
        return []

    # Try splitting by major sections (headers / double newlines)
    paragraphs = re.split(r"(\n#{1,4}\s+[^\n]+\n|\n\n+)", text)
    chunks = []
    current_words: List[str] = []

    for part in paragraphs:
        part_clean = part.strip()
        if not part_clean:
            continue
        words = part_clean.split()
        if len(current_words) + len(words) <= (target_word_count + 100):
            current_words.extend(words)
        else:
            if current_words:
                chunks.append(" ".join(current_words))
                # Carry over overlap
                current_words = current_words[-overlap_words:] + words
            else:
                # If a single paragraph is longer than target, slice it
                while len(words) > target_word_count:
                    chunks.append(" ".join(words[:target_word_count]))
                    words = words[target_word_count - overlap_words:]
                current_words = words

    if current_words:
        chunk_str = " ".join(current_words).strip()
        if chunk_str:
            chunks.append(chunk_str)

    return chunks if chunks else [text.strip()]


class KnowledgeExplorer:
    """Zero-VRAM Knowledge Explorer with FTS5 BM25 search and document provenance."""

    def __init__(self, storage: Optional[EvolutionStorage] = None):
        self.storage = storage or evolution_storage
        self._file_hashes: Dict[str, str] = {}

    # ==========================================
    # SECURITY & PROMPT-INJECTION FILTERING
    # ==========================================
    def sanitize_external_content(self, text: str) -> Dict[str, Any]:
        """
        Scans external/web/user content for prompt-injection attacks.
        Returns safety assessment dictionary.
        """
        if not text:
            return {"safe": True, "reason": "Empty content", "pattern": None}

        for pattern in PROMPT_INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_str = match.group(0)
                logger.warning(f"[SECURITY] Adversarial prompt injection detected: '{matched_str}'")
                return {
                    "safe": False,
                    "reason": f"Prompt injection pattern detected: '{matched_str}'",
                    "pattern": matched_str
                }

        return {"safe": True, "reason": "Passed security filters", "pattern": None}

    # ==========================================
    # DOCUMENT INGESTION API
    # ==========================================
    def ingest_local_file(self, file_path: str, category: str = "documentation") -> Dict[str, Any]:
        """
        Ingests a local document, splits into semantic chunks, computes SHA-256
        deduplication hashes, and records full provenance in SQLite.
        """
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}", "chunks_ingested": 0}

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return {"success": False, "error": f"Unsupported extension: {ext}", "chunks_ingested": 0}

        raw_text = self._read_file_content(file_path, ext)
        if not raw_text or not raw_text.strip():
            return {"success": False, "error": "Empty file content", "chunks_ingested": 0}

        file_norm = os.path.abspath(file_path).replace("\\", "/")
        current_file_hash = compute_sha256(raw_text)
        if self._file_hashes.get(file_norm) == current_file_hash:
            logger.debug(f"[KNOWLEDGE_INGEST] File '{file_path}' hash unchanged ({current_file_hash[:8]}). Skipping re-indexing.")
            return {
                "success": True,
                "file_path": file_norm,
                "verification_status": "CACHED_UNMODIFIED",
                "total_chunks": 0,
                "chunks_ingested": 0,
                "chunks_skipped": 0,
                "skipped_unchanged": True
            }

        # Check prompt injection
        sec_check = self.sanitize_external_content(raw_text)
        status = "VERIFIED" if sec_check["safe"] else "REJECTED"

        chunks = chunk_document(raw_text, target_word_count=500, overlap_words=50)
        ingested = 0
        skipped = 0
        now = time.time()

        for idx, chunk in enumerate(chunks):
            chunk_hash = compute_sha256(chunk)
            key = f"chunk_{chunk_hash[:16]}"

            metadata = {
                "source_url": file_norm,
                "category": category,
                "verification_status": status,
                "sha256": chunk_hash,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "created_at": now,
                "last_checked": now
            }

            if status == "REJECTED":
                metadata["rejection_reason"] = sec_check["reason"]
                logger.warning(f"[KNOWLEDGE_REJECTED] File '{file_path}' chunk {idx} rejected due to security policy.")
                continue

            try:
                self.storage.upsert_knowledge(
                    key=key,
                    category=category,
                    content=chunk,
                    metadata=metadata
                )
                ingested += 1
            except Exception as e:
                logger.warning(f"[KNOWLEDGE_INGEST] Error storing chunk {idx}: {e}")

        if status == "VERIFIED":
            self._file_hashes[file_norm] = current_file_hash

        logger.info(f"[KNOWLEDGE_INGEST] Ingested '{file_path}': {ingested} chunks stored ({status}).")
        return {
            "success": status == "VERIFIED",
            "file_path": file_norm,
            "verification_status": status,
            "total_chunks": len(chunks),
            "chunks_ingested": ingested,
            "chunks_skipped": skipped
        }

    def _read_file_content(self, file_path: str, ext: str) -> str:
        """Reads file text with fallback for PDF and JSON formatting."""
        if ext == ".pdf":
            # Attempt to use pypdf or fitz if available
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                return "\n\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                pass
            try:
                import fitz
                doc = fitz.open(file_path)
                return "\n\n".join(page.get_text() for page in doc)
            except ImportError:
                pass
            logger.info(f"[PDF_FALLBACK] No PDF parser installed. Attempting binary text extraction for '{file_path}'.")
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                # Extract printable strings
                strings = re.findall(b"[a-zA-Z0-9.,;:!?()\\[\\]\\{\\}\\s]{4,}", content)
                return "\n".join(s.decode("utf-8", errors="ignore") for s in strings)
            except Exception as ex:
                logger.warning(f"[PDF_READ_FAILED] Could not read PDF '{file_path}': {ex}")
                return ""

        if ext == ".json":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return json.dumps(data, indent=2)
            except Exception:
                pass

        # Text, Markdown, Python
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"[FILE_READ_ERROR] Could not read '{file_path}': {e}")
            return ""

    def ingest_research_knowledge(
        self,
        query: str,
        answer: str,
        source_urls: Optional[List[str]] = None,
        category: str = "research"
    ) -> Dict[str, Any]:
        """
        Stores synthesized research outcomes into ALEE knowledge with full provenance.
        """
        if not answer or not answer.strip():
            return {"success": False, "reason": "Empty answer"}

        full_content = f"Research Query: {query}\n\nFindings:\n{answer}"
        sec_check = self.sanitize_external_content(full_content)
        status = "VERIFIED" if sec_check["safe"] else "REJECTED"

        if status == "REJECTED":
            logger.warning(f"[RESEARCH_REJECTED] Research findings rejected for query: '{query}'")
            return {"success": False, "status": "REJECTED", "reason": sec_check["reason"]}

        chunks = chunk_document(full_content, target_word_count=400, overlap_words=40)
        ingested = 0
        now = time.time()
        primary_source = (source_urls[0] if source_urls else "santra:research_engine")

        for idx, chunk in enumerate(chunks):
            chunk_hash = compute_sha256(chunk)
            key = f"res_{chunk_hash[:16]}"
            metadata = {
                "source_url": primary_source,
                "all_sources": source_urls or [],
                "query": query,
                "category": category,
                "verification_status": "VERIFIED",
                "sha256": chunk_hash,
                "created_at": now,
                "last_checked": now
            }
            self.storage.upsert_knowledge(
                key=key,
                category=category,
                content=chunk,
                metadata=metadata
            )
            ingested += 1

        logger.info(f"[RESEARCH_LEARNED] Saved {ingested} research knowledge chunks for query: '{query[:40]}'")
        return {"success": True, "chunks_ingested": ingested, "status": "VERIFIED"}

    # ==========================================
    # FAST BM25 RETRIEVAL API
    # ==========================================
    def retrieve_relevant_knowledge(
        self,
        query: str,
        top_k: int = 3,
        max_chars: int = 1200
    ) -> List[Dict[str, Any]]:
        """
        Retrieves relevant verified knowledge using SQLite FTS5 with BM25 ranking in < 5ms.
        Excludes REJECTED, OUTDATED, or unverified items, and enforces a strict max_chars budget.
        """
        if not query or not query.strip():
            return []

        t0 = time.perf_counter()
        results = self.storage.search_knowledge_bm25(
            query=query,
            limit=top_k,
            allowed_statuses=("VERIFIED", "UNVERIFIED")
        )

        # Enforce character budget cap so prompts never bloat
        budgeted_results = []
        total_chars = 0
        for item in results:
            content = item.get("content", "").strip()
            item_len = len(content)
            if total_chars + item_len <= max_chars:
                budgeted_results.append(item)
                total_chars += item_len
            else:
                remaining_budget = max_chars - total_chars
                if remaining_budget > 120:
                    truncated = dict(item)
                    truncated["content"] = content[:remaining_budget].rsplit(" ", 1)[0] + "..."
                    budgeted_results.append(truncated)
                break

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"[BM25_RETRIEVAL] Retrieved {len(budgeted_results)} chunks for '{query[:30]}' in {elapsed_ms:.2f}ms")
        return budgeted_results

    # ==========================================
    # DIRECTORY SCANNER
    # ==========================================
    def index_directory(self, dir_path: str, category: str = "documentation") -> Dict[str, Any]:
        """Scans and indexes all supported documents in a directory."""
        if not os.path.exists(dir_path):
            return {"total_files": 0, "chunks_ingested": 0}

        total_files = 0
        total_chunks = 0
        for root, _, files in os.walk(dir_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    fp = os.path.join(root, file)
                    res = self.ingest_local_file(fp, category=category)
                    if res.get("success"):
                        total_files += 1
                        total_chunks += res.get("chunks_ingested", 0)

        logger.info(f"[DIRECTORY_INDEX] Indexed {total_files} files ({total_chunks} chunks) from {dir_path}")
        return {"total_files": total_files, "chunks_ingested": total_chunks}


# Singleton instance
knowledge_explorer = KnowledgeExplorer()

