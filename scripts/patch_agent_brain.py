"""
Patch core/ai/agent_brain.py with ALEE Knowledge Read Bridge
"""

def patch():
    with open('core/ai/agent_brain.py', 'r', encoding='utf-8') as f:
        content = f.read()

    target1 = '        mem_context = persistent_memory.build_memory_context_prompt(user_query)\n'
    repl1 = '''        mem_context = persistent_memory.build_memory_context_prompt(user_query)

        # Stage 2: ALEE Knowledge Explorer Read Bridge
        alee_context = ""
        try:
            from core.evolution.knowledge_explorer import knowledge_explorer
            items = knowledge_explorer.retrieve_relevant_knowledge(user_query, top_k=3)
            if items:
                snippets = []
                for it in items:
                    src = it.get("source_url") or it.get("category", "local_doc")
                    snippets.append(f"Source: {src}\n{it.get('content', '').strip()[:400]}")
                alee_context = "VERIFIED KNOWLEDGE & DOCUMENT CONTEXT:\n" + "\n---\n".join(snippets) + "\n"
        except Exception as ke:
            logger.debug(f"Knowledge bridge retrieval error: {ke}")
'''
    assert target1 in content, 'target1 not found'
    content = content.replace(target1, repl1, 1)

    target2 = '''{rules}

{mem_context}

{tools_section}"""'''
    repl2 = '''{rules}

{mem_context}

{alee_context}

{tools_section}"""'''
    assert target2 in content, 'target2 not found'
    content = content.replace(target2, repl2, 1)

    with open('core/ai/agent_brain.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print('Successfully patched core/ai/agent_brain.py with Read Bridge')

if __name__ == '__main__':
    patch()
