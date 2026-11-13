"""
Patch retrieve_relevant_knowledge in knowledge_explorer.py
"""

def patch():
    with open('core/evolution/knowledge_explorer.py', 'r', encoding='utf-8') as f:
        content = f.read()

    target = '''    # ==========================================
    # FAST BM25 RETRIEVAL API
    # ==========================================
    def retrieve_relevant_knowledge(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves relevant verified knowledge using SQLite FTS5 with BM25 ranking in < 5ms.
        Excludes REJECTED, OUTDATED, or unverified items.
        """
        if not query or not query.strip():
            return []

        t0 = time.perf_counter()
        results = self.storage.search_knowledge_bm25(
            query=query,
            limit=top_k,
            allowed_statuses=("VERIFIED", "UNVERIFIED")
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"[BM25_RETRIEVAL] Retrieved {len(results)} chunks for '{query[:30]}' in {elapsed_ms:.2f}ms")
        return results'''

    replacement = '''    # ==========================================
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
        return budgeted_results'''

    assert target in content, 'Target in knowledge_explorer.py not found'
    content = content.replace(target, replacement, 1)

    with open('core/evolution/knowledge_explorer.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Successfully patched knowledge_explorer.py retrieve_relevant_knowledge")

if __name__ == '__main__':
    patch()
