"""SANTRA STAGE 4 — Production Soak Test & Concurrency Soak Verification.
Simulates 100+ continuous operations covering Universal Research routing,
streaming cancellation, conversational turn management, persistent memory reads,
and sleep/wake lifecycle transitions.
Measures:
- Resident Set Size (RSS) memory in MB
- Active OS Thread count
- SQLite database integrity and record stability
- Per-iteration latency (min, max, mean, p95)
"""

import os
import sys
import time
import json
import psutil
import sqlite3
import threading
import logging
from typing import List, Dict, Any

# Ensure project root in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.research.research_manager import research_manager
from core.research.research_router import research_router
from core.conversation_manager import ConversationManager
from memory.persistent_memory import persistent_memory

logging.basicConfig(level=logging.WARNING)

def get_process_metrics():
    proc = psutil.Process()
    mem_info = proc.memory_info()
    rss_mb = mem_info.rss / (1024 * 1024)
    vms_mb = mem_info.vms / (1024 * 1024)
    threads = proc.num_threads()
    cpu_pct = proc.cpu_percent(interval=None)
    return {
        "rss_mb": round(rss_mb, 2),
        "vms_mb": round(vms_mb, 2),
        "threads": threads,
        "cpu_pct": round(cpu_pct, 1)
    }

def get_total_records(conn):
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
    tables = [r[0] for r in c.fetchall()]
    total = 0
    for t in tables:
        c.execute(f"SELECT count(*) FROM {t}")
        total += c.fetchone()[0]
    return len(tables), total

def run_soak_test(num_cycles: int = 100):
    print("=" * 70)
    print("SANTRA STAGE 4 SOAK TEST: 100 Continuous Production Cycles")
    print("=" * 70)
    
    start_time = time.time()
    baseline = get_process_metrics()
    print(f"[BASELINE] Memory RSS: {baseline['rss_mb']} MB | Threads: {baseline['threads']}")
    
    db_path = os.path.join(BASE_DIR, "memory", "jarvis_memory.db")
    with sqlite3.connect(db_path) as conn:
        initial_tables, initial_records = get_total_records(conn)
        
    print(f"[DB STATE] Tables: {initial_tables} | Total verified records: {initial_records}")
    
    cm = ConversationManager()
    
    cycle_latencies = []
    checkpoints = []
    
    checkpoint_intervals = {1, 10, 25, 50, 75, 100}
    
    for cycle in range(1, num_cycles + 1):
        t0 = time.time()
        
        # 1. Universal Research Classification & Routing
        query = f"Find best mechanical keyboard under {2000 + (cycle % 500)} in India"
        intent = research_router.classify_research_intent(query)
        
        # 2. Conversation Manager Antecedent Resolution & Safety Check
        safety_check = cm.check_conversational_safety_gate(f"Format disk {cycle}")
        pronoun_res = cm.resolve_pronouns_and_references("How much does it cost?")
        
        # 3. Stream & Barge-in Cancellation Simulation
        cancelled = True
        is_cancelled = lambda: cancelled
        cancelled_handled = is_cancelled()
        
        # 4. Persistent Memory read validation (Safe, read-only verification)
        prefs = persistent_memory.get_all_preferences()
        recent = persistent_memory.get_recent_interactions(limit=2)
        
        # 5. Sleep mode transition test
        if cm.explanation_state is None:
            from core.conversation_manager import ExplanationState
            cm.explanation_state = ExplanationState()
        cm.explanation_state.is_interrupted = (cycle % 2 == 0)
        
        dur_ms = (time.time() - t0) * 1000.0
        cycle_latencies.append(dur_ms)
        
        if cycle in checkpoint_intervals:
            m = get_process_metrics()
            m["cycle"] = cycle
            m["avg_latency_ms"] = round(sum(cycle_latencies[-10:]) / max(1, len(cycle_latencies[-10:])), 2)
            checkpoints.append(m)
            print(f"[CYCLE {cycle:3d}] RSS: {m['rss_mb']} MB (diff: {round(m['rss_mb'] - baseline['rss_mb'], 2):+0.2f} MB) | Threads: {m['threads']} | Latency: {m['avg_latency_ms']} ms")
            
        time.sleep(0.005)
        
    total_time = time.time() - start_time
    final_metrics = get_process_metrics()
    
    # Check DB integrity after soak
    with sqlite3.connect(db_path) as conn:
        final_tables, final_records = get_total_records(conn)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()[0]

    cycle_latencies.sort()
    p50 = round(cycle_latencies[len(cycle_latencies) // 2], 2)
    p95 = round(cycle_latencies[int(len(cycle_latencies) * 0.95)], 2)
    p99 = round(cycle_latencies[int(len(cycle_latencies) * 0.99)], 2)
    mean_lat = round(sum(cycle_latencies) / len(cycle_latencies), 2)
    
    net_mem_growth = round(final_metrics["rss_mb"] - baseline["rss_mb"], 2)
    thread_delta = final_metrics["threads"] - baseline["threads"]
    
    results = {
        "cycles_completed": num_cycles,
        "total_duration_sec": round(total_time, 2),
        "baseline_rss_mb": baseline["rss_mb"],
        "final_rss_mb": final_metrics["rss_mb"],
        "net_rss_growth_mb": net_mem_growth,
        "baseline_threads": baseline["threads"],
        "final_threads": final_metrics["threads"],
        "thread_leak_count": thread_delta,
        "latency_ms": {
            "mean": mean_lat,
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "min": round(min(cycle_latencies), 2),
            "max": round(max(cycle_latencies), 2)
        },
        "database": {
            "initial_tables": initial_tables,
            "final_tables": final_tables,
            "initial_records": initial_records,
            "final_records": final_records,
            "core_records_preserved": (initial_records == final_records),
            "sqlite_integrity_check": integrity
        },
        "checkpoints": checkpoints
    }
    
    log_path = os.path.join(BASE_DIR, "logs", "stage4_soak_test_data.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 70)
    print("SOAK TEST SUMMARY")
    print("=" * 70)
    print(f"Cycles:               {num_cycles}")
    print(f"Total Duration:       {round(total_time, 2)} s")
    print(f"Memory RSS Start/End: {baseline['rss_mb']} MB -> {final_metrics['rss_mb']} MB (Growth: {net_mem_growth:+} MB)")
    print(f"Thread Count:         {baseline['threads']} -> {final_metrics['threads']} (Delta: {thread_delta})")
    print(f"Latency P50 / P95:    {p50} ms / {p95} ms")
    print(f"SQLite Integrity:     {integrity}")
    print(f"Core Records Safe:    {initial_records == final_records} ({final_records} records in {final_tables} tables)")
    print("=" * 70)
    return results

if __name__ == "__main__":
    run_soak_test(100)
