"""
SANTRA Iteration 18: 100-Turn Conversational Stress Test
Evaluates 100 multi-turn conversational interactions using a reproducible, human-curated test set.
Validates:
- Topic continuation
- Detail expansions ("Explain in detail.")
- Re-explanations ("Re-explain.")
- Simplifications ("Simplify.")
- Code & Concrete Examples ("Give an example.")
- Comparative analysis ("Compare them.")
- Interrupted explanations
- Contextual topic switches
- Ambiguous pronoun / antecedent references ("How does it work?")
- Programming symbols: C++, C#, Node.js, React, Python, O(n log n)
- Long multi-turn dialogues & retroactive references ("Referring to your earlier answer...")
"""

import os
import sys
import time
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.abspath("."))

from core.conversation_manager import ConversationManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Iteration18.StressTest")

# Documented 100-Turn Evaluation Dataset (Structured into 12 Specialized Sessions)
DATASET_100_TURNS = [
    # Session 1: Programming Language Symbols & Polymorphism (Turns 1 - 8)
    ("Session 1: C++ Polymorphism & Inheritance", [
        ("Explain polymorphism in C++.", "polymorphism in c++"),
        ("Explain in detail.", "polymorphism in c++"),
        ("Give an example in C++ using virtual functions.", "polymorphism in c++"),
        ("How does the vtable work?", "vtable"),
        ("What about C#?", "c#"),
        ("Compare polymorphism in C++ and C#.", "c++ and c#"),
        ("Simplify.", "c++ and c#"),
        ("Give a C# code snippet.", "c#")
    ]),

    # Session 2: Data Structures & Multi-turn Continuations (Turns 9 - 18)
    ("Session 2: B-Trees & Database Indexing", [
        ("Explain B-Trees in database systems.", "b-tree"),
        ("Explain in detail.", "b-tree"),
        ("What is the time complexity of search?", "b-tree"),
        ("Give an example of node splitting.", "b-tree"),
        ("Re-explain using a real-world library catalog analogy.", "b-tree"),
        ("Now explain hash indexes.", "hash index"),
        ("Compare B-Trees with hash indexing.", "b-tree"),
        ("When should I choose hash over B-Tree?", "hash"),
        ("Simplify for a beginner.", "indexing"),
        ("Summarize the key differences.", "indexing")
    ]),

    # Session 3: Operating System Internals & Memory Management (Turns 19 - 28)
    ("Session 3: Virtual Memory & Page Replacement", [
        ("What is virtual memory in an operating system?", "virtual memory"),
        ("Explain the role of the MMU.", "mmu"),
        ("What is a page fault?", "page fault"),
        ("Explain in detail what happens during a page fault.", "page fault"),
        ("What is the LRU page replacement algorithm?", "lru"),
        ("Give an example with a 3-frame memory buffer.", "lru"),
        ("What is thrashing?", "thrashing"),
        ("How can an OS prevent thrashing?", "thrashing"),
        ("Simplify.", "thrashing"),
        ("Re-explain the concept of working set model.", "working set")
    ]),

    # Session 4: Modern Web Frameworks & Ambiguous References (Turns 29 - 38)
    ("Session 4: React vs Node.js Fullstack", [
        ("Explain React components and the Virtual DOM.", "react"),
        ("How does reconciliation work?", "reconciliation"),
        ("Give an example of a custom hook in React.", "react"),
        ("Now explain Node.js event loop.", "node.js"),
        ("Explain in detail the phases of the event loop.", "node.js"),
        ("What is libuv?", "libuv"),
        ("Compare client-side rendering with server-side rendering.", "rendering"),
        ("Which one is faster for initial load?", "rendering"),
        ("Why does it improve SEO?", "rendering"),
        ("Give a summary of best practices.", "rendering")
    ]),

    # Session 5: Computer Networking & Protocols (Turns 39 - 48)
    ("Session 5: TCP vs UDP & Socket Architecture", [
        ("Explain the TCP 3-way handshake.", "tcp"),
        ("Explain in detail what SYN and ACK packets contain.", "tcp"),
        ("What is TCP slow start?", "tcp"),
        ("Now explain UDP.", "udp"),
        ("Compare TCP and UDP for streaming anime.", "tcp and udp"),
        ("Why does voice chat use UDP instead of TCP?", "udp"),
        ("What is packet loss?", "packet loss"),
        ("How does QUIC solve head-of-line blocking?", "quic"),
        ("Simplify the concept of QUIC.", "quic"),
        ("Give an example of a protocol built on top of UDP.", "udp")
    ]),

    # Session 6: Concurrency, Deadlocks & Synchronization (Turns 49 - 58)
    ("Session 6: Concurrency & Mutex Primitives", [
        ("What is a race condition in multi-threaded programming?", "race condition"),
        ("Explain the four conditions for deadlock.", "deadlock"),
        ("Explain in detail Coffman condition four: circular wait.", "circular wait"),
        ("How does a mutex prevent race conditions?", "mutex"),
        ("Give an example in Python using threading.Lock.", "mutex"),
        ("What is a semaphore?", "semaphore"),
        ("Compare a binary semaphore with a mutex.", "semaphore"),
        ("What is priority inversion?", "priority inversion"),
        ("How does priority inheritance solve it?", "priority inheritance"),
        ("Re-explain using an airport analogy.", "priority")
    ]),

    # Session 7: Cloud & Distributed Systems (Turns 59 - 68)
    ("Session 7: CAP Theorem & Consistency", [
        ("Explain the CAP theorem in distributed databases.", "cap theorem"),
        ("What is eventual consistency?", "eventual consistency"),
        ("Give an example of an AP database.", "ap database"),
        ("What is Raft consensus?", "raft"),
        ("Explain in detail how leader election works in Raft.", "raft"),
        ("What happens during a split brain scenario?", "split brain"),
        ("How does a quorum prevent split brain?", "quorum"),
        ("Compare Paxos and Raft.", "paxos and raft"),
        ("Simplify.", "consensus"),
        ("Summarize the practical takeaway for a software engineer.", "consensus")
    ]),

    # Session 8: Compilers & Programming Syntax (Turns 69 - 76)
    ("Session 8: ASTs, Lexing & C# / .NET Runtime", [
        ("Explain the difference between a compiler and an interpreter.", "compiler"),
        ("What is an Abstract Syntax Tree (AST)?", "ast"),
        ("Explain in detail how lexical analysis produces tokens.", "lexical analysis"),
        ("What is the CLR in .NET and C#?", "clr"),
        ("How does JIT compilation work in C#?", "jit"),
        ("Give an example of Intermediate Language (IL) bytecode.", "il"),
        ("Compare JIT with AOT compilation.", "jit and aot"),
        ("Why does C++ typically compile directly to machine code?", "c++")
    ]),

    # Session 9: Cybersecurity & Cryptography (Turns 77 - 84)
    ("Session 9: Public Key Cryptography & Hashing", [
        ("Explain public key cryptography.", "public key"),
        ("What is the mathematical foundation of RSA?", "rsa"),
        ("Explain in detail why factoring large primes is hard.", "rsa"),
        ("What is SHA-256?", "sha-256"),
        ("Why is a hash function one-way?", "hash function"),
        ("Give an example of a digital signature workflow.", "digital signature"),
        ("What is a man-in-the-middle attack?", "mitm"),
        ("How does TLS prevent it?", "tls")
    ]),

    # Session 10: Interrupted Dialogues & Topic Recovery (Turns 85 - 90)
    ("Session 10: Interrupted Explanations & Recovery", [
        ("Explain quicksort.", "quicksort"),
        ("Wait, stop. What is time complexity?", "time complexity"),
        ("Now resume quicksort.", "quicksort"),
        ("Explain in detail the worst-case scenario.", "quicksort"),
        ("How does choosing a random pivot fix it?", "quicksort"),
        ("Give a concrete example of a sorted array causing O(n^2).", "quicksort")
    ]),

    # Session 11: System & Native Workstation Context (Turns 91 - 95)
    ("Session 11: Grounded System Awareness", [
        ("Who are you and what system are you running on?", "santra"),
        ("What can you do on Windows 11?", "windows 11"),
        ("Can you open Brave to watch HiAnime?", "brave"),
        ("What applications do I have installed?", "applications"),
        ("Can you monitor my battery and hardware?", "hardware")
    ]),

    # Session 12: Complex Multi-step Problem Solving (Turns 96 - 100)
    ("Session 12: Long Synthesis & Architectural Summary", [
        ("Design a scalable real-time chat application architecture.", "chat architecture"),
        ("What protocol should be used for real-time messaging?", "websocket"),
        ("How should message history be stored at scale?", "storage"),
        ("Compare PostgreSQL and Cassandra for chat messages.", "postgresql and cassandra"),
        ("Summarize the final architectural recommendation concisely.", "chat architecture")
    ])
]

def run_100_turn_stress_test():
    print("=" * 80)
    print("SANTRA ITERATION 18: 100-TURN CONVERSATIONAL STRESS TEST")
    print("=" * 80)

    total_turns = sum(len(turns) for _, turns in DATASET_100_TURNS)
    print(f"Total Sessions: {len(DATASET_100_TURNS)} | Total Planned Turns: {total_turns}")

    results = {
        "timestamp_start": datetime.now().isoformat(),
        "total_planned_turns": total_turns,
        "turns_executed": 0,
        "turns_passed": 0,
        "turns_failed": 0,
        "accuracy_rate_percent": 0.0,
        "sessions": [],
        "failures": []
    }

    turn_counter = 0
    passed_counter = 0

    for session_name, turns in DATASET_100_TURNS:
        print(f"\n--- {session_name} ({len(turns)} turns) ---")
        cm = ConversationManager()
        session_turns = []

        for q_idx, (query, expected_topic_keyword) in enumerate(turns, start=1):
            turn_counter += 1
            t0 = time.perf_counter()
            res = cm.process_query(query)
            latency_ms = (time.perf_counter() - t0) * 1000

            text = res.get("text", "")
            current_topic = cm.task_context.current_topic or ""
            source = res.get("source", "Unknown")

            # Topic validation criteria:
            # 1. Expected keyword in current topic or answer text
            # 2. Response is non-empty (>15 chars)
            kw = expected_topic_keyword.lower()
            topic_matched = kw in current_topic.lower() or kw in text.lower() or any(w in text.lower() for w in kw.split())
            length_ok = len(text.strip()) > 20

            turn_ok = topic_matched and length_ok
            if turn_ok:
                passed_counter += 1
            else:
                failure_entry = {
                    "turn": turn_counter,
                    "session": session_name,
                    "query": query,
                    "expected_keyword": expected_topic_keyword,
                    "current_topic": current_topic,
                    "response_length": len(text),
                    "snippet": text[:100]
                }
                results["failures"].append(failure_entry)
                print(f"  [FAIL] Turn {turn_counter}: '{query}' -> Expected '{expected_topic_keyword}', Got topic='{current_topic}'")

            session_turns.append({
                "turn_overall": turn_counter,
                "turn_in_session": q_idx,
                "query": query,
                "expected_keyword": expected_topic_keyword,
                "current_topic": current_topic,
                "status": "PASS" if turn_ok else "FAIL",
                "latency_ms": round(latency_ms, 2),
                "source": source,
                "response_len": len(text)
            })

            status_str = "PASS" if turn_ok else "FAIL"
            print(f"  [{status_str}] Turn {turn_counter:03d}: '{query[:35]}' -> Topic='{current_topic[:20]}' ({latency_ms:.1f}ms, {len(text)} chars)")

        results["sessions"].append({
            "name": session_name,
            "turns_count": len(turns),
            "turns": session_turns
        })

    accuracy = (passed_counter / total_turns) * 100.0 if total_turns > 0 else 0.0
    results["turns_executed"] = turn_counter
    results["turns_passed"] = passed_counter
    results["turns_failed"] = turn_counter - passed_counter
    results["accuracy_rate_percent"] = round(accuracy, 2)
    results["timestamp_end"] = datetime.now().isoformat()

    out_file = "logs/iteration18_conversational_stress_test.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 80)
    print(f"STRESS TEST COMPLETE: {passed_counter}/{total_turns} Turns Passed ({accuracy:.1f}% Accuracy)")
    print(f"Results saved to: {out_file}")
    print("=" * 80)
    return passed_counter == total_turns

if __name__ == "__main__":
    success = run_100_turn_stress_test()
    sys.exit(0 if success else 1)

