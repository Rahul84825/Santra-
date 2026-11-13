"""
Patch Write Bridges and Scheduler Hook
"""

def patch():
    # 1. Patch core/research/research_manager.py
    with open('core/research/research_manager.py', 'r', encoding='utf-8') as f:
        r_content = f.read()

    target_r = '''        # Stage 8: Persistent Knowledge Storage
        try:
            research_memory.save_session(session)
        except Exception as me:
            logger.error(f"[ResearchManager] Failed to persist session to database: {me}")'''

    repl_r = '''        # Stage 8: Persistent Knowledge Storage
        try:
            research_memory.save_session(session)
        except Exception as me:
            logger.error(f"[ResearchManager] Failed to persist session to database: {me}")

        # Stage 8B: ALEE Automatic Research Capture
        try:
            from core.evolution.knowledge_explorer import knowledge_explorer
            src_urls = [s.url for s in session.sources if getattr(s, "url", None)]
            knowledge_explorer.ingest_research_knowledge(
                query=session.query,
                answer=session.final_answer,
                source_urls=src_urls,
                category="research"
            )
        except Exception as alee_err:
            logger.debug(f"[ALEE] Automatic research capture notice: {alee_err}")'''

    assert target_r in r_content, 'target_r not found'
    r_content = r_content.replace(target_r, repl_r, 1)
    with open('core/research/research_manager.py', 'w', encoding='utf-8') as f:
        f.write(r_content)
    print('Patched research_manager.py')

    # 2. Patch core/jarvis_runtime.py
    with open('core/jarvis_runtime.py', 'r', encoding='utf-8') as f:
        j_content = f.read()

    target_j = '''                self.memory.add_interaction(text, answer)
                # CRITICAL: Deliver the synthesized research answer to the UI conversation turn!'''

    repl_j = '''                self.memory.add_interaction(text, answer)
                # Stage 2: ALEE Automatic Research Knowledge Capture
                try:
                    from core.evolution.knowledge_explorer import knowledge_explorer
                    knowledge_explorer.ingest_research_knowledge(
                        query=text,
                        answer=answer,
                        source_urls=[res_res.get("research_id", "")],
                        category="research"
                    )
                except Exception as rke:
                    logger.debug(f"[EVOLUTION] Research knowledge capture error: {rke}")

                # CRITICAL: Deliver the synthesized research answer to the UI conversation turn!'''

    assert target_j in j_content, 'target_j not found'
    j_content = j_content.replace(target_j, repl_j, 1)
    with open('core/jarvis_runtime.py', 'w', encoding='utf-8') as f:
        f.write(j_content)
    print('Patched jarvis_runtime.py')

    # 3. Patch core/evolution/scheduler.py
    with open('core/evolution/scheduler.py', 'r', encoding='utf-8') as f:
        s_content = f.read()

    target_s = '''        # 1. Optimize full-text index
        self.storage.optimize_fts()'''

    repl_s = '''        # 1. Optimize full-text index
        self.storage.optimize_fts()

        # 1B. Index local documentation (docs/) during idle window
        try:
            from core.evolution.knowledge_explorer import knowledge_explorer
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            docs_dir = os.path.join(base_dir, "docs")
            if os.path.exists(docs_dir):
                knowledge_explorer.index_directory(docs_dir, category="architecture_docs")
        except Exception as de:
            logger.debug(f"[SCHEDULER] Local docs indexing notice: {de}")'''

    assert target_s in s_content, 'target_s not found'
    s_content = s_content.replace(target_s, repl_s, 1)
    with open('core/evolution/scheduler.py', 'w', encoding='utf-8') as f:
        f.write(s_content)
    print('Patched scheduler.py')

if __name__ == '__main__':
    patch()
