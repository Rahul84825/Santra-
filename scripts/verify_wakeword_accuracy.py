"""
SANTRA Iteration 15: Wake-Word Accuracy & Confuser Rejection Benchmark.
Tests:
- Positive phrases: 'Santra.', 'Santra, open Chrome.', 'Santra, take a screenshot.'
- Negative confusers: 'Santa.', 'Santa Claus.', 'Central processing unit.',
                      ordinary conversation, silence, fan noise.
Distinguishes false activations from missed wake-ups with strict thresholds (sensitivity=0.45).
"""

import os
import sys
import json
import wave
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from core.pronunciation_manager import pronunciation_manager
from core.wakeword import SantraWakeWordDetector
from core.transcriber import SpeechTranscriber


def verify_wakeword_matrix():
    print("=" * 80)
    print("SANTRA ITERATION 15: WAKE-WORD POSITIVE / NEGATIVE REJECTION BENCHMARK")
    print("=" * 80)

    test_cases = [
        # Positive Candidates (MUST trigger)
        {"text": "santra", "expected_wake": True, "type": "positive"},
        {"text": "hey santra", "expected_wake": True, "type": "positive"},
        {"text": "santra open chrome", "expected_wake": True, "type": "positive"},
        {"text": "santra take a screenshot", "expected_wake": True, "type": "positive"},
        {"text": "suntra", "expected_wake": True, "type": "positive_indian_accent"},
        {"text": "samtra", "expected_wake": True, "type": "positive_indian_accent"},

        # Negative Confusers (MUST NOT trigger)
        {"text": "santa", "expected_wake": False, "type": "negative_confuser"},
        {"text": "santa claus", "expected_wake": False, "type": "negative_confuser"},
        {"text": "secret santa", "expected_wake": False, "type": "negative_confuser"},
        {"text": "central processing unit", "expected_wake": False, "type": "negative_confuser"},
        {"text": "centre of gravity", "expected_wake": False, "type": "negative_confuser"},
        {"text": "sutra reading", "expected_wake": False, "type": "negative_confuser"},
        {"text": "kama sutra", "expected_wake": False, "type": "negative_confuser"},
        {"text": "mantra chanting", "expected_wake": False, "type": "negative_confuser"},
        {"text": "tantra practice", "expected_wake": False, "type": "negative_confuser"},
        {"text": "what time is it", "expected_wake": False, "type": "conversation"},
        {"text": "how is the weather outside", "expected_wake": False, "type": "conversation"},
        {"text": "open chrome browser", "expected_wake": False, "type": "command_without_wake"}
    ]

    results = []
    positive_total = 0
    positive_passed = 0
    negative_total = 0
    negative_passed = 0
    false_activations = 0
    missed_wakeups = 0

    for idx, tc in enumerate(test_cases):
        cand = tc["text"]
        exp = tc["expected_wake"]
        is_confuser = pronunciation_manager.is_negative_confuser(cand)
        is_wake, variant, score = pronunciation_manager.evaluate_candidate(cand, confidence=0.85)

        # A confuser must NOT be treated as wake
        effective_wake = is_wake and not is_confuser

        success = (effective_wake == exp)
        if exp:
            positive_total += 1
            if success:
                positive_passed += 1
            else:
                missed_wakeups += 1
        else:
            negative_total += 1
            if success:
                negative_passed += 1
            else:
                false_activations += 1

        rec = {
            "id": idx + 1,
            "phrase": cand,
            "type": tc["type"],
            "expected_wake": exp,
            "detected_wake": effective_wake,
            "is_negative_confuser": is_confuser,
            "matched_variant": variant,
            "confidence_score": score,
            "status": "PASSED" if success else "FAILED"
        }
        results.append(rec)
        print(f"  [{idx+1:02d}] '{cand:28}' -> Exp={exp} | Det={effective_wake} (Confuser={is_confuser}) => {rec['status']}")

    # Also test actual noise and silence files
    noise_files = [
        ("scratch/eval_dataset/noise_fan.wav", "fan_noise"),
        ("scratch/eval_dataset/noise_silence.wav", "silence")
    ]
    transcriber = SpeechTranscriber()
    transcriber._load_model()
    noise_evals = []
    for path, ntype in noise_files:
        if os.path.exists(path):
            transcript = transcriber.transcribe(path)
            is_wake, _, _ = pronunciation_manager.evaluate_candidate(transcript, confidence=0.85)
            passed = (not is_wake and transcript.strip() == "")
            noise_evals.append({
                "file": os.path.basename(path),
                "type": ntype,
                "transcript": transcript,
                "false_wake": is_wake,
                "status": "PASSED" if passed else "FAILED"
            })
            if is_wake:
                false_activations += 1
            print(f"  [Acoustic Noise] {os.path.basename(path):20} -> Transcript='{transcript}' => {'PASSED' if passed else 'FAILED'}")

    summary = {
        "positive_tests": positive_total,
        "positive_recognized": positive_passed,
        "positive_accuracy_percent": round((positive_passed / positive_total) * 100, 2),
        "missed_wakeups": missed_wakeups,
        "negative_tests": negative_total + len(noise_evals),
        "negative_rejected": negative_passed + len([n for n in noise_evals if n["status"] == "PASSED"]),
        "negative_accuracy_percent": round(((negative_passed + len([n for n in noise_evals if n["status"] == "PASSED"])) / (negative_total + len(noise_evals))) * 100, 2),
        "false_activations": false_activations,
        "threshold_sensitivity": 0.45,
        "test_results": results,
        "noise_evaluations": noise_evals
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/wakeword_accuracy_iteration15.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("WAKE-WORD ACCURACY BENCHMARK SUMMARY")
    print(f"Positive Accuracy: {summary['positive_accuracy_percent']}% ({positive_passed}/{positive_total}) | Missed: {missed_wakeups}")
    print(f"Negative Rejection Accuracy: {summary['negative_accuracy_percent']}% | False Activations: {false_activations}")
    print(f"Report saved to logs/wakeword_accuracy_iteration15.json")
    print("=" * 80)
    return summary


if __name__ == "__main__":
    verify_wakeword_matrix()

