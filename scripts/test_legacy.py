import sqlite3

def test():
    conn = sqlite3.connect('memory/jarvis_memory.db')
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print("Tables:", tables)
    for t in ['knowledge_notes', 'learned_procedures', 'execution_experiences']:
        if t in tables:
            c.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"  {t}: {c.fetchone()[0]}")
    conn.close()

if __name__ == '__main__':
    test()
