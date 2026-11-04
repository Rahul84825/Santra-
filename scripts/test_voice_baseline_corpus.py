import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.command_normalizer import CommandNormalizer
from core.intent_engine import intent_engine

normalizer = CommandNormalizer()

test_corpus = [
    'Hey Santra',
    'Open Valorant',
    'Search for Valorant settings',
    'Open Antigravity',
    'Open the folder in Antigravity',
    'Open Brave',
    'Open Chrome',
    'Open Python',
    'Create a folder named Mini Project on Desktop',
    'Open my Mini Project folder',
    'Search YouTube for Python tutorials',
    'Explain machine learning',
    'What is the latest Valorant update?',
    'Stop'
]

print("=" * 80)
print("BASELINE CORPUS INTENT & NORMALIZATION AUDIT")
print("=" * 80)

for cmd in test_corpus:
    norm = normalizer.normalize(cmd)
    normalized_text = norm.get("normalized", "")
    intent = intent_engine.classify_intent(normalized_text)
    print(f"RAW:     {cmd}")
    print(f"NORM:    {normalized_text}")
    print(f"INTENT:  action={intent[0]} | target={intent[1] if len(intent) > 1 else ''}")
    print("-" * 60)
