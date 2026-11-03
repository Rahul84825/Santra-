"""Stage 2 Domain Validation and Measurement Script for SANTRA Research Engine.
Tests all 7 research domains with truthful status reporting and latency measurements:
1. Shopping
2. Technology
3. Programming
4. Gaming
5. News
6. Comparison
7. General Knowledge
"""

import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.research.research_manager import ResearchManager
from core.research.research_models import PriceType, VerificationStatus

def run_domain_validation():
    print("=" * 80)
    print("SANTRA UNIVERSAL RESEARCH ENGINE — STAGE 2 DOMAIN VALIDATION")
    print("=" * 80)

    res_mgr = ResearchManager()

    domain_queries = [
        ("Shopping", "Find the best wireless gaming controller under ₹2,000 in India."),
        ("Technology", "What is the latest NVIDIA GPU architecture?"),
        ("Programming", "What is the latest stable Python version?"),
        ("Gaming", "What are the latest Valorant patch notes?"),
        ("News", "Give me the latest important technology news in India."),
        ("Comparison", "Compare React and Next.js."),
        ("General Knowledge", "Explain how database indexing works.")
    ]

    results_summary = []

    for domain, query in domain_queries:
        print(f"\n--- Testing Domain: {domain} ---")
        print(f"Query: \"{query}\"")
        t0 = time.time()
        try:
            result = res_mgr.execute_research(query)
            elapsed_sec = time.time() - t0
            
            session = res_mgr.active_session
            sources_count = len(session.sources) if session else 0
            evidence_count = len(session.evidence) if session else 0
            products_count = len(session.products) if session else 0
            citations_count = len(session.citations) if session else 0

            print(f"Status: {result.get('status')}")
            print(f"Elapsed: {elapsed_sec:.2f}s")
            print(f"Discovered Sources: {sources_count}")
            print(f"Extracted Evidence: {evidence_count}")
            print(f"Structured Products: {products_count}")
            print(f"Citations Generated: {citations_count}")

            if session and session.products:
                print("Extracted Products:")
                for p in session.products[:3]:
                    price_val = f"₹{p.price:,.0f}" if p.price else "Unlisted"
                    print(f"  * {p.name} | Price: {price_val} ({p.price_type.value}) | Retailer: {p.retailer} | Status: {p.extraction_status}")

            if session and session.citations:
                print("Citations:")
                for c in session.citations[:3]:
                    print(f"  [{c.index}] {c.title} ({c.domain})")

            results_summary.append({
                "domain": domain,
                "query": query,
                "status": result.get("status"),
                "latency_sec": round(elapsed_sec, 2),
                "sources_count": sources_count,
                "evidence_count": evidence_count,
                "products_count": products_count,
                "citations_count": citations_count,
                "answer_preview": (result.get("answer", "") or "")[:200]
            })

        except Exception as e:
            print(f"ERROR: {e}")
            results_summary.append({
                "domain": domain,
                "query": query,
                "status": "ERROR",
                "error": str(e)
            })

    output_path = os.path.join(os.path.dirname(__file__), "..", "stage2_domain_validation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2)

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY COMPLETE — Results written to stage2_domain_validation_results.json")
    print("=" * 80)

if __name__ == "__main__":
    run_domain_validation()
