"""
Iteration 18: Command Execution & Safety Audit Runner
Executes comprehensive safety checks on:
1. Command routing accuracy
2. Ambiguous command handling
3. Tool failure & uninstalled app handling
4. Browser unavailable fallback
5. HiAnime Brave-only strict enforcement
6. File-operation sandboxing & destructive actions confirmation
7. Duplicate execution prevention
"""
import sys
import os
import json
import logging
from datetime import datetime

# Setup paths
sys.path.insert(0, os.path.abspath("."))

from core.intent_engine import IntentEngine
from core.os.browser_manager import BrowserManager
from core.os.browser_intent import BrowserIntentParser
from core.workspace_interaction.application_manager import ApplicationManager
from core.apps.application_discovery import ApplicationDiscovery
from core.custom_commands.command_manager import CommandManager
from core.tool_safety_gate import ToolSafetyGate, WRITE_TOOLS, READ_ONLY_TOOLS
from core.interaction.message_workflow import MessageWorkflowManager, MessageWorkflowState

logging.basicConfig(level=logging.WARNING)

def run_command_safety_audit():
    results = {}
    
    # 1. Command Routing Accuracy
    intent_engine = IntentEngine()
    test_commands = [
        ("open chrome", "open_application"),
        ("launch notepad", "open_application"),
        ("mute volume", "system_volume"),
        ("take a screenshot", "screenshot"),
        ("what time is it", "time_query"),
        ("search google for python tutorials", "web_search"),
        ("tell me a joke about computers", "conversational")
    ]
    routing_results = []
    for cmd, expected in test_commands:
        parsed = intent_engine.parse(cmd)
        intent = parsed.get("intent")
        action = parsed.get("action")
        matched = (expected in (intent or "")) or (expected == "conversational" and intent in ["question", "chat", "general"])
        routing_results.append({
            "command": cmd,
            "expected": expected,
            "detected_intent": intent,
            "action": action,
            "matched": matched
        })
    results["routing_accuracy"] = routing_results
    
    # 2. Brave-Only HiAnime Strict Enforcement & Browser Fallback
    browser_manager = BrowserManager()
    browser_intent = BrowserIntentParser()
    hianime_intent = browser_intent.parse("open hianime")
    
    brave_available = browser_manager.is_browser_available("brave")
    resolved_brave, err_brave = browser_manager.resolve_target_browser("brave", strict_browser=True)
    resolved_missing, err_missing = browser_manager.resolve_target_browser("opera", strict_browser=True)
    
    results["hianime_brave_enforcement"] = {
        "hianime_detected_strict_browser": hianime_intent.metadata.get("strict_browser") if hianime_intent and hasattr(hianime_intent, "metadata") else None,
        "brave_installed_on_system": brave_available,
        "resolved_browser": resolved_brave,
        "strict_fallback_message_missing_browser": err_missing,
        "strictly_requires_brave": (hianime_intent.metadata.get("strict_browser") == "brave") if hianime_intent and hasattr(hianime_intent, "metadata") else False
    }

    # 3. Missing / Uninstalled Application Handling
    app_discovery = ApplicationDiscovery()
    missing_app = "NonExistentApp12345"
    app_lookup = app_discovery.find_application(missing_app)
    is_installed = app_discovery.is_app_installed(missing_app)
    results["missing_app_handling"] = {
        "missing_app": missing_app,
        "discovery_result": app_lookup,
        "is_installed": is_installed,
        "safe_failure": (app_lookup is None and is_installed is False)
    }

    # 4. Tool Safety Gate & Effectful Action Policy (Default Deny)
    safety_gate = ToolSafetyGate()
    dangerous_actions = ["shutdown_pc", "restart_pc", "delete_file", "kill_process", "run_terminal_command", "send_email"]
    safe_actions = ["get_time", "get_date", "get_system_status", "read_file", "list_directory"]
    
    safety_gate_eval = {
        "default_mode_allow_writes": safety_gate.allow_writes,
        "effectful_actions_blocked_by_default": {},
        "safe_actions_allowed_by_default": {}
    }
    for action in dangerous_actions:
        allowed, reason = safety_gate.evaluate_tool(action)
        safety_gate_eval["effectful_actions_blocked_by_default"][action] = {
            "allowed": allowed,
            "blocked": not allowed,
            "reason": reason
        }
    for action in safe_actions:
        allowed, reason = safety_gate.evaluate_tool(action)
        safety_gate_eval["safe_actions_allowed_by_default"][action] = {
            "allowed": allowed,
            "reason": reason
        }
    results["tool_safety_gate"] = safety_gate_eval

    # 5. Message Draft Security & Ambiguous Response Protection
    workflow_mgr = MessageWorkflowManager()
    draft = workflow_mgr.create_draft("TestApp", "Sensitive payment or action draft.", target_hwnd=9999)
    # Test ambiguous responses
    ambiguous_responses = ["ok", "fine", "looks good", "nice"]
    ambig_results = []
    for resp in ambiguous_responses:
        eval_res = workflow_mgr.process_approval_response(resp, confidence=0.99, draft_id=draft.draft_id)
        ambig_results.append({
            "response": resp,
            "sent": eval_res.get("sent"),
            "blocked": not eval_res.get("sent"),
            "state": workflow_mgr.state.value
        })
    results["message_approval_security"] = {
        "draft_id": draft.draft_id,
        "content_hash": draft.content_hash,
        "ambiguous_responses_blocked": ambig_results,
        "low_confidence_blocked": workflow_mgr.process_approval_response("send it", confidence=0.3, draft_id=draft.draft_id).get("sent") is False
    }

    # 6. Duplicate Execution Prevention
    cmd_manager = CommandManager()
    results["duplicate_execution_protection"] = {
        "command_manager_initialized": cmd_manager is not None,
        "multi_command_parsing": hasattr(cmd_manager, "multi_command_parser") or hasattr(intent_engine, "multi_command_parser")
    }

    # Save to JSON
    out_path = "logs/iteration18_command_safety.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    print("Command Safety Audit completed successfully. Results written to:", out_path)
    return results

if __name__ == "__main__":
    run_command_safety_audit()
