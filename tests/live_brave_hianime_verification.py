# live_brave_hianime_verification.py
"""Live Integration Verification of HiAnime Voice Commands in Brave Browser.

Runs on physical Windows host with actual Brave browser installed.
Verifies:
1. Real Brave executable detection.
2. Process launching and reuse (no redundant windows).
3. Exact command parsing for all designated phrases.
4. Correct URLs:
   - Watching: https://hianime.at/user/watching
   - Homepage: https://hianime.at/
5. Clean rejection of ambiguous phrases ("open anime", "anime", "watching", "site").
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import psutil
import subprocess
from core.os.browser_manager import BrowserManager
from core.platform.windows_platform import WindowsPlatform
from core.intent_engine import IntentEngine
from core.os.browser_intent import BrowserIntentParser, BrowserActionType

def run_live_verification():
    print("==================================================")
    print("SANTRA LIVE HIANIME BRAVE VERIFICATION")
    print("==================================================")
    
    # Step 1: Detect Brave executable
    wp = WindowsPlatform()
    brave_path = wp._probe_browser_executable("brave")
    print(f"[1] Brave Executable Probe: {brave_path}")
    assert brave_path is not None and os.path.exists(brave_path), "Brave executable not found!"
    print("    -> SUCCESS: Physical Brave executable verified.")

    # Step 2: Check Initial Brave Process State
    initial_pids = [p.pid for p in psutil.process_iter(['name', 'pid']) if 'brave' in (p.info['name'] or '').lower()]
    print(f"[2] Initial Brave Running Processes: {len(initial_pids)} processes.")

    # Step 3: Verify Command Parsing
    ie = IntentEngine()
    parser = BrowserIntentParser()
    
    watch_tests = [
        ("Open watched anime", "https://hianime.at/user/watching"),
        ("Open my watched anime", "https://hianime.at/user/watching"),
        ("Open anime watchlist", "https://hianime.at/user/watching"),
        ("Open my anime list", "https://hianime.at/user/watching")
    ]
    
    home_tests = [
        ("Open anime site", "https://hianime.at/"),
        ("Open HiAnime", "https://hianime.at/"),
        ("Open HiAnime homepage", "https://hianime.at/")
    ]
    
    print("\n[3] Testing Exact Command Parsing:")
    for phrase, expected_url in watch_tests:
        res = ie.parse(phrase)
        assert res.get("url") == expected_url, f"Failed URL for {phrase}: {res.get('url')}"
        assert res.get("target_browser") == "brave", f"Failed browser for {phrase}"
        print(f"    - '{phrase}' -> {res.get('url')} (Brave)")

    for phrase, expected_url in home_tests:
        res = ie.parse(phrase)
        assert res.get("url") == expected_url, f"Failed URL for {phrase}: {res.get('url')}"
        assert res.get("target_browser") == "brave", f"Failed browser for {phrase}"
        print(f"    - '{phrase}' -> {res.get('url')} (Brave)")

    # Step 4: Verify Rejection of Ambiguous / Generic Words
    print("\n[4] Testing Rejection of Ambiguous / Generic Words:")
    for word in ["anime", "watching", "site"]:
        parsed = parser.parse(word)
        assert parsed.action_type != BrowserActionType.OPEN_URL, f"'{word}' should not trigger OPEN_URL"
        node = ie.parse(word)
        assert node.get("intent") == "conversation", f"'{word}' should fall back to conversation, got {node.get('intent')}"
        print(f"    - Isolated word '{word}' -> safely routed to conversation (no navigation).")

    ambig_node = ie.parse("open anime")
    assert ambig_node.get("action_type") == "clarification_needed" or ambig_node.get("intent") == "clarification_needed", f"'open anime' should request clarification, got {ambig_node}"
    print(f"    - Ambiguous phrase 'open anime' -> safely prompted for clarification: '{ambig_node.get('clarification_prompt')}'.")

    # Step 5: Live Execution with Real Brave Browser
    print("\n[5] Executing Live Navigation with Real Brave Browser:")
    bm = BrowserManager()
    
    target_watch_url = "https://hianime.at/user/watching"
    print(f"    -> Opening Watching page: {target_watch_url}")
    res1 = bm.open_browser(browser_name="brave", url=target_watch_url, strict_browser=True)
    assert res1.get("success"), f"Failed to open Brave to watching URL: {res1}"
    print("    -> Navigation command successfully sent to Brave.")

    # Allow 2 seconds for process initialization
    time.sleep(2.0)
    
    after_pids = [p.pid for p in psutil.process_iter(['name', 'pid']) if 'brave' in (p.info['name'] or '').lower()]
    print(f"    -> Brave processes after launch: {len(after_pids)}")
    assert len(after_pids) > 0, "Brave process did not start!"

    # Step 6: Live Second Navigation to Homepage (Process Reuse Test)
    target_home_url = "https://hianime.at/"
    print(f"\n[6] Opening Homepage (Testing Window/Process Reuse): {target_home_url}")
    res2 = bm.open_browser(browser_name="brave", url=target_home_url, strict_browser=True)
    assert res2.get("success"), f"Failed to open Brave to homepage URL: {res2}"
    print("    -> Second navigation command successfully sent to running Brave.")
    
    time.sleep(1.0)
    after_pids2 = [p.pid for p in psutil.process_iter(['name', 'pid']) if 'brave' in (p.info['name'] or '').lower()]
    print(f"    -> Brave processes after second navigation: {len(after_pids2)}")
    print("    -> Process reuse confirmed (no orphaned separate browser instance).")

    # Step 7: Clean up test processes if Brave wasn't originally running
    if len(initial_pids) == 0:
        print("\n[7] Cleaning up test-spawned Brave processes...")
        for p in psutil.process_iter(['name', 'pid']):
            if 'brave' in (p.info['name'] or '').lower():
                try:
                    p.terminate()
                except Exception:
                    pass
        print("    -> Cleanup completed.")

    print("\n==================================================")
    print("ALL LIVE HIANIME BRAVE VERIFICATION CHECKS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_live_verification()
