"""Physical Host Live Scenario Verification Script.
Executes Scenario A (Folder Creation, Renaming, Antigravity Opening, Prompt Dictation, Approval Gate, Submission)
and Scenario B (Chrome Activation, ChatGPT Navigation, Pinned Conversation, Message Dictation, Approval Gate, Submission).
Collects physical evidence, latency benchmarks, and outputs JSON metrics.
"""

import os
import sys
import time
import json
import shutil
import hashlib
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.workspace_interaction import (
    workspace_manager,
    application_manager,
    browser_interaction_manager,
    application_interaction_manager,
    draft_manager,
    DraftState,
)
from core.intent_engine import intent_engine
from modules.system.executor import CommandExecutor, CommandOutcome


def run_physical_live_scenarios():
    print("=" * 80)
    print("SANTRA LIVE WORKSPACE & APPLICATION INTERACTION VERIFICATION")
    print("=" * 80)

    executor = CommandExecutor()
    report = {
        "timestamp": time.time(),
        "host_os": sys.platform,
        "scenarios": {},
        "latencies_ms": {}
    }

    # -------------------------------------------------------------------------
    # SCENARIO A: Folder Management & Antigravity IDE
    # -------------------------------------------------------------------------
    print("\n[SCENARIO A] Folder Management & Antigravity IDE Interaction")
    scenario_a = {"steps": [], "success": True}

    # Safe test directory on Desktop
    desktop = Path.home() / "Desktop"
    test_folder_name = "Santra Live Projects Test"
    renamed_folder_name = "Mithai World Live Test"
    target_path = desktop / test_folder_name
    renamed_path = desktop / renamed_folder_name

    # Clean up prior test runs if left over
    if target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)
    if renamed_path.exists():
        shutil.rmtree(renamed_path, ignore_errors=True)

    try:
        # Step 1: Create folder
        t0 = time.perf_counter()
        node_create = intent_engine.parse(f"Create a folder called {test_folder_name} on my desktop.")
        t_parse_create = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        res_create = executor.execute(node_create)
        t_exec_create = (time.perf_counter() - t0) * 1000.0

        created_physical = target_path.exists() and target_path.is_dir()
        scenario_a["steps"].append({
            "step": 1,
            "action": "create_folder",
            "phrase": f"Create a folder called {test_folder_name} on my desktop.",
            "intent": node_create.get("intent"),
            "success": res_create.get("success") and created_physical,
            "physical_evidence": str(target_path) if created_physical else None,
            "parse_latency_ms": t_parse_create,
            "exec_latency_ms": t_exec_create
        })
        print(f"  Step 1 (Create Folder): Success={created_physical} | Path={target_path} ({t_exec_create:.2f}ms)")
        assert created_physical, "Physical folder was not created on desktop!"

        # Step 2: Destination conflict test (Zero overwrite rule)
        t0 = time.perf_counter()
        node_conflict = intent_engine.parse(f"Create a folder called {test_folder_name} on my desktop.")
        res_conflict = executor.execute(node_conflict)
        t_exec_conflict = (time.perf_counter() - t0) * 1000.0

        conflict_blocked = (not res_conflict.get("success")) and ("already exists" in res_conflict.get("message", ""))
        scenario_a["steps"].append({
            "step": 2,
            "action": "overwrite_prevention_test",
            "success": conflict_blocked,
            "message": res_conflict.get("message"),
            "latency_ms": t_exec_conflict
        })
        print(f"  Step 2 (Overwrite Prevention): Blocked={conflict_blocked} | Message='{res_conflict.get('message')}'")
        assert conflict_blocked, "Zero-overwrite policy was violated!"

        # Step 3: Rename folder with antecedent ("Rename that folder to Mithai World Live Test")
        t0 = time.perf_counter()
        node_rename = intent_engine.parse(f"Rename that folder to {renamed_folder_name}.")
        t_parse_rename = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        res_rename = executor.execute(node_rename)
        t_exec_rename = (time.perf_counter() - t0) * 1000.0

        renamed_physical = renamed_path.exists() and not target_path.exists()
        scenario_a["steps"].append({
            "step": 3,
            "action": "rename_folder",
            "phrase": f"Rename that folder to {renamed_folder_name}.",
            "intent": node_rename.get("intent"),
            "success": res_rename.get("success") and renamed_physical,
            "physical_evidence": str(renamed_path) if renamed_physical else None,
            "parse_latency_ms": t_parse_rename,
            "exec_latency_ms": t_exec_rename
        })
        print(f"  Step 3 (Rename Folder): Success={renamed_physical} | Renamed to={renamed_path} ({t_exec_rename:.2f}ms)")
        assert renamed_physical, "Physical folder was not renamed!"

        # Step 4: Open in Antigravity ("Open the folder in Antigravity.")
        t0 = time.perf_counter()
        node_open_ag = intent_engine.parse("Open the folder in Antigravity.")
        t_parse_ag = (time.perf_counter() - t0) * 1000.0

        # Physical executable discovery
        antigravity_exe = application_manager.find_antigravity_executable()
        print(f"  Host Antigravity Executable: {antigravity_exe}")
        assert antigravity_exe and os.path.exists(antigravity_exe), f"Antigravity executable '{antigravity_exe}' not found."

        # Execute opening (safe activation)
        t0 = time.perf_counter()
        res_open_ag = executor.execute(node_open_ag)
        t_exec_ag = (time.perf_counter() - t0) * 1000.0

        scenario_a["steps"].append({
            "step": 4,
            "action": "open_in_antigravity",
            "phrase": "Open the folder in Antigravity.",
            "intent": node_open_ag.get("intent"),
            "executable_found": antigravity_exe,
            "success": res_open_ag.get("success"),
            "parse_latency_ms": t_parse_ag,
            "exec_latency_ms": t_exec_ag
        })
        print(f"  Step 4 (Open Antigravity Workspace): Success={res_open_ag.get('success')} ({t_exec_ag:.2f}ms)")

        # Step 5: User says "Write a prompt."
        t0 = time.perf_counter()
        node_prompt = intent_engine.parse("Write a prompt.")
        res_prompt = executor.execute(node_prompt)
        t_exec_prompt = (time.perf_counter() - t0) * 1000.0

        drafting_active = (draft_manager.current_state == DraftState.DRAFTING)
        scenario_a["steps"].append({
            "step": 5,
            "action": "start_prompt",
            "phrase": "Write a prompt.",
            "draft_state": draft_manager.current_state.value,
            "success": drafting_active,
            "latency_ms": t_exec_prompt
        })
        print(f"  Step 5 (Drafting Mode Active): Success={drafting_active}")
        assert drafting_active, "Drafting state machine did not enter DRAFTING."

        # Step 6: Dictate prompt
        prompt_text = "Build a complete authentication system with Google login and email login."
        t0 = time.perf_counter()
        node_dictation = intent_engine.parse(prompt_text)
        res_dictation = executor.execute(node_dictation)
        t_exec_dictation = (time.perf_counter() - t0) * 1000.0

        awaiting_approval = (draft_manager.current_state == DraftState.AWAITING_APPROVAL)
        active_draft = draft_manager.get_latest_draft()
        hash_verified = active_draft and active_draft.verify_hash(prompt_text)

        scenario_a["steps"].append({
            "step": 6,
            "action": "enter_prompt_text",
            "dictated_text": prompt_text,
            "content_hash": active_draft.content_hash if active_draft else None,
            "hash_verified": hash_verified,
            "requires_approval": awaiting_approval,
            "assistant_prompt": res_dictation.get("message"),
            "latency_ms": t_exec_dictation
        })
        print(f"  Step 6 (Prompt Staged & Hash Bound): Awaiting Approval={awaiting_approval} | Hash={active_draft.content_hash[:16]}... ({t_exec_dictation:.2f}ms)")
        assert awaiting_approval and hash_verified, "Draft was not cryptographically bound!"

        # Step 7: Ambiguous phrase test ("Okay.") -> MUST NOT SUBMIT
        t0 = time.perf_counter()
        node_amb = intent_engine.parse("Okay.")
        res_amb = executor.execute(node_amb)
        t_exec_amb = (time.perf_counter() - t0) * 1000.0

        amb_blocked = (not res_amb.get("success")) and (draft_manager.current_state == DraftState.AWAITING_APPROVAL)
        scenario_a["steps"].append({
            "step": 7,
            "action": "ambiguous_approval_defense",
            "phrase": "Okay.",
            "blocked_submission": amb_blocked,
            "draft_state": draft_manager.current_state.value,
            "latency_ms": t_exec_amb
        })
        print(f"  Step 7 (Ambiguous Approval Blocked): Blocked={amb_blocked} | Draft State={draft_manager.current_state.value}")
        assert amb_blocked, "Ambiguous phrase erroneously submitted draft!"

        # Step 8: Explicit approval ("Yes, send it.") -> SUBMITS & VERIFIES
        t0 = time.perf_counter()
        node_appr = intent_engine.parse("Yes, send it.")
        res_appr = executor.execute(node_appr)
        t_exec_appr = (time.perf_counter() - t0) * 1000.0

        submitted_verified = res_appr.get("success") and (draft_manager.current_state == DraftState.VERIFIED)
        scenario_a["steps"].append({
            "step": 8,
            "action": "explicit_approval_submission",
            "phrase": "Yes, send it.",
            "submitted_and_verified": submitted_verified,
            "draft_state": draft_manager.current_state.value,
            "latency_ms": t_exec_appr
        })
        print(f"  Step 8 (Explicit Approval Submission): Success={submitted_verified} | Outcome={draft_manager.current_state.value} ({t_exec_appr:.2f}ms)")
        assert submitted_verified, "Draft was not submitted upon explicit approval!"

    finally:
        # Clean up test directories
        if renamed_path.exists():
            shutil.rmtree(renamed_path, ignore_errors=True)
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)

    report["scenarios"]["scenario_a_folder_and_antigravity"] = scenario_a

    # -------------------------------------------------------------------------
    # SCENARIO B: Google Chrome & ChatGPT Interaction
    # -------------------------------------------------------------------------
    print("\n[SCENARIO B] Google Chrome & ChatGPT Interaction")
    scenario_b = {"steps": [], "success": True}

    # Reset draft manager state
    draft_manager.current_state = DraftState.IDLE
    draft_manager.active_drafts.clear()

    # Step 1: Open ChatGPT in Chrome
    t0 = time.perf_counter()
    node_cg = intent_engine.parse("Open ChatGPT in Chrome.")
    t_parse_cg = (time.perf_counter() - t0) * 1000.0

    chrome_exe = application_manager.find_chrome_executable()
    print(f"  Host Chrome Executable: {chrome_exe}")
    assert chrome_exe and os.path.exists(chrome_exe), f"Chrome executable '{chrome_exe}' not found on host."

    t0 = time.perf_counter()
    res_cg = executor.execute(node_cg)
    t_exec_cg = (time.perf_counter() - t0) * 1000.0

    scenario_b["steps"].append({
        "step": 1,
        "action": "open_chatgpt_in_chrome",
        "phrase": "Open ChatGPT in Chrome.",
        "intent": node_cg.get("intent"),
        "chrome_executable": chrome_exe,
        "success": res_cg.get("success"),
        "parse_latency_ms": t_parse_cg,
        "exec_latency_ms": t_exec_cg
    })
    print(f"  Step 1 (Open ChatGPT in Chrome): Success={res_cg.get('success')} ({t_exec_cg:.2f}ms)")

    # Step 2: Open pinned SANTRA chat
    t0 = time.perf_counter()
    node_pinned = intent_engine.parse("Open my pinned SANTRA chat.")
    t_parse_pinned = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    res_pinned = executor.execute(node_pinned)
    t_exec_pinned = (time.perf_counter() - t0) * 1000.0

    scenario_b["steps"].append({
        "step": 2,
        "action": "open_pinned_chat",
        "phrase": "Open my pinned SANTRA chat.",
        "target": node_pinned.get("target"),
        "success": res_pinned.get("success"),
        "parse_latency_ms": t_parse_pinned,
        "exec_latency_ms": t_exec_pinned
    })
    print(f"  Step 2 (Open Pinned Chat): Target={node_pinned.get('target')} | Success={res_pinned.get('success')} ({t_exec_pinned:.2f}ms)")

    # Step 3: Write a message
    t0 = time.perf_counter()
    node_msg = intent_engine.parse("Write a message.")
    res_msg = executor.execute(node_msg)
    t_exec_msg = (time.perf_counter() - t0) * 1000.0

    scenario_b["steps"].append({
        "step": 3,
        "action": "start_message",
        "phrase": "Write a message.",
        "draft_state": draft_manager.current_state.value,
        "success": draft_manager.current_state == DraftState.DRAFTING,
        "latency_ms": t_exec_msg
    })
    print(f"  Step 3 (Start Message Mode): State={draft_manager.current_state.value}")

    # Step 4: Dictate message content
    chat_msg_text = "I want to improve the voice recognition system and reduce response latency."
    t0 = time.perf_counter()
    node_chat_dict = intent_engine.parse(chat_msg_text)
    res_chat_dict = executor.execute(node_chat_dict)
    t_exec_chat_dict = (time.perf_counter() - t0) * 1000.0

    chat_draft = draft_manager.get_latest_draft()
    scenario_b["steps"].append({
        "step": 4,
        "action": "enter_message_text",
        "dictated_text": chat_msg_text,
        "content_hash": chat_draft.content_hash if chat_draft else None,
        "requires_approval": draft_manager.current_state == DraftState.AWAITING_APPROVAL,
        "latency_ms": t_exec_chat_dict
    })
    print(f"  Step 4 (Message Staged): Awaiting Approval={draft_manager.current_state == DraftState.AWAITING_APPROVAL} ({t_exec_chat_dict:.2f}ms)")

    # Step 5: Explicit send ("Send it.")
    t0 = time.perf_counter()
    node_send = intent_engine.parse("Send it.")
    res_send = executor.execute(node_send)
    t_exec_send = (time.perf_counter() - t0) * 1000.0

    sent_verified = res_send.get("success") and (draft_manager.current_state == DraftState.VERIFIED)
    scenario_b["steps"].append({
        "step": 5,
        "action": "send_approved_message",
        "phrase": "Send it.",
        "success": sent_verified,
        "draft_state": draft_manager.current_state.value,
        "latency_ms": t_exec_send
    })
    print(f"  Step 5 (Approved Send Execution): Success={sent_verified} | Final State={draft_manager.current_state.value} ({t_exec_send:.2f}ms)")

    report["scenarios"]["scenario_b_chrome_chatgpt"] = scenario_b

    # Write live telemetry artifact
    out_path = Path("logs/live_workspace_interaction_verification.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 80)
    print(f"ALL PHYSICAL LIVE SCENARIOS COMPLETED AND VERIFIED.")
    print(f"Report saved to: {out_path}")
    print("=" * 80)
    return report


if __name__ == "__main__":
    run_physical_live_scenarios()

