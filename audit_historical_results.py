# audit_historical_results.py
import json
import shutil
import os

src = 'logs/expanded_benchmark_results.json'
dst = 'logs/historical_iteration7_expanded_benchmark_results.json'

if os.path.exists(src):
    shutil.copy2(src, dst)
    print(f"Preserved historical benchmark to {dst}")
    with open(src, 'r', encoding='utf-8') as f:
        data = json.load(f)
    summary = data.get('summary', {})
    print(f"Total test cases in summary: {summary.get('total_test_cases')}")
    print(f"Speech items: {summary.get('speech_items')}")
    print(f"Noise items: {summary.get('noise_items')}")
    print(f"Exact matches: {summary.get('exact_matches')}")
    print(f"Exact match pct: {summary.get('exact_match_pct')}%")
    print(f"Intent matches: {summary.get('intent_matches')}")
    print(f"Intent accuracy pct: {summary.get('intent_accuracy_pct')}%")
    print(f"Mean WER: {summary.get('mean_wer')}")
    print(f"Mean CER: {summary.get('mean_cer')}")
    print(f"False command triggers on noise: {summary.get('false_command_triggers')}")
    print(f"Dangerous confusions: {summary.get('dangerous_confusions')}")
    
    print("\nCategory breakdown in summary:")
    for cat, stats in summary.get('category_breakdown', {}).items():
        print(f"  - {cat:28s}: total={stats.get('total')}, exact_pct={stats.get('exact_match_pct')}%, intent_pct={stats.get('intent_accuracy_pct')}%, wer={stats.get('mean_wer')}")

    items = data.get('items', [])
    print(f"\nTotal items in data['items']: {len(items)}")
    
    # Categorize items
    cat_counts = {}
    exact_by_cat = {}
    for item in items:
        cat = item.get('category', 'unknown')
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if item.get('exact_match'):
            exact_by_cat[cat] = exact_by_cat.get(cat, 0) + 1

    print("\nActual item counts and exact matches from items array:")
    for cat, count in cat_counts.items():
        exact = exact_by_cat.get(cat, 0)
        pct = (exact / count) * 100 if count else 0
        print(f"  - {cat:28s}: {count:3d} items | {exact:3d} exact ({pct:5.1f}%)")

    # Mismatched items
    print("\nNon-exact matching items in items array:")
    for item in items:
        if not item.get('exact_match'):
            print(f"  [{item.get('category')}] {item.get('id')}:")
            print(f"      Expected: '{item.get('ground_truth')}'")
            print(f"      Hypothesis: '{item.get('hypothesis')}'")
            print(f"      WER: {item.get('wer')}, CER: {item.get('cer')}")
else:
    print(f"Error: {src} not found!")

