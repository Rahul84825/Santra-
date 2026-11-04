with open('core/intent_engine.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if '"browser_action"' in l or '"stop"' in l:
        print(f"{i+1}: {l.strip()}")

