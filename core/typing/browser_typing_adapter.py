"""Browser Voice Typing & AI Prompt Interaction Adapter.
Implements the 10-step verified typing workflow for web applications (ChatGPT, Gemini, Claude)
combining Windows UI Automation, CDP DOM accessibility, authentication guards, and the Ask-Before-Send workflow.
"""

import time
import logging
from typing import Optional, Dict, Any, Tuple, List
from enum import Enum

from core.os.website_adapters import website_adapter_registry, BaseWebsiteAdapter
from core.os.cdp_client import CDPClient
from core.os.browser_automation import LightweightCDPWebSocket
from core.interaction.message_workflow import message_workflow_manager, PendingApproval, MessageWorkflowState

logger = logging.getLogger("Jarvis.BrowserTypingAdapter")


class BrowserSubmissionOutcome(str, Enum):
    """Truthful state machine outcomes for web AI submissions."""
    DRAFT_INSERTED = "DRAFT_INSERTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUBMISSION_TRIGGERED = "SUBMISSION_TRIGGERED"
    APPLICATION_ACCEPTED = "APPLICATION_ACCEPTED"
    MESSAGE_VISIBLE = "MESSAGE_VISIBLE"
    RESPONSE_STARTED = "RESPONSE_STARTED"
    RESPONSE_COMPLETED = "RESPONSE_COMPLETED"
    RESPONSE_GENERATED = "RESPONSE_GENERATED"  # Retained as alias for backward compatibility
    DELIVERY_UNCONFIRMED = "DELIVERY_UNCONFIRMED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class BrowserTypingAdapter:
    """Orchestrates accessible, safe, verified message drafting and submission in web AI interfaces."""

    SUPPORTED_AI_APPS = {
        "chatgpt": ["chatgpt.com", "chat.openai.com"],
        "gemini": ["gemini.google.com"],
        "claude": ["claude.ai"]
    }

    def __init__(self, cdp_client: Optional[CDPClient] = None, workflow_mgr=None):
        self.cdp = cdp_client or CDPClient()
        self.workflow_mgr = workflow_mgr or message_workflow_manager
        self.adapter_registry = website_adapter_registry

    # -------------------------------------------------------------------------
    # STEP 1: Identify Active Browser
    # -------------------------------------------------------------------------
    def identify_active_browser(self) -> Dict[str, Any]:
        """Detects if a supported browser is currently the foreground window."""
        try:
            import win32gui
            import win32process
            import psutil

            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {"is_browser": False, "reason": "no_foreground_window"}

            title = win32gui.GetWindowText(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name().lower() if pid else ""

            browser_type = None
            if "chrome" in proc_name:
                browser_type = "chrome"
            elif "msedge" in proc_name or "edge" in proc_name:
                browser_type = "edge"
            elif "brave" in proc_name:
                browser_type = "brave"
            elif "firefox" in proc_name:
                browser_type = "firefox"

            if not browser_type:
                return {
                    "is_browser": False,
                    "hwnd": hwnd,
                    "process_name": proc_name,
                    "title": title
                }

            return {
                "is_browser": True,
                "browser_type": browser_type,
                "hwnd": hwnd,
                "pid": pid,
                "process_name": proc_name,
                "title": title
            }
        except Exception as e:
            logger.debug(f"[BROWSER_TYPING] Browser identification error: {e}")
            return {"is_browser": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # STEP 2: Identify Active Tab and Target Service
    # -------------------------------------------------------------------------
    def identify_active_tab(self, browser_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Identifies the current active tab and whether it matches an AI interface."""
        b_info = browser_info or self.identify_active_browser()
        if not b_info.get("is_browser"):
            return {
                "success": False,
                "status": "NO_BROWSER",
                "message": "Foreground application is not a recognized browser."
            }

        title = b_info.get("title", "")
        detected_app = None
        target_url = None

        # 1. Check CDP if available
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            if active_tab:
                target_url = active_tab.get("url", "")
                title = active_tab.get("title", title)
                for app_name, domains in self.SUPPORTED_AI_APPS.items():
                    if any(d in target_url.lower() for d in domains):
                        detected_app = app_name
                        break

        # 2. Heuristic match on window title if CDP is not available
        if not detected_app:
            title_lower = title.lower()
            if "chatgpt" in title_lower:
                detected_app = "chatgpt"
                target_url = target_url or "https://chatgpt.com"
            elif "gemini" in title_lower or "bard" in title_lower:
                detected_app = "gemini"
                target_url = target_url or "https://gemini.google.com"
            elif "claude" in title_lower:
                detected_app = "claude"
                target_url = target_url or "https://claude.ai"

        adapter = self.adapter_registry.get_adapter(target_url or detected_app)

        return {
            "success": True,
            "browser_info": b_info,
            "title": title,
            "url": target_url or "",
            "service_name": detected_app or "web",
            "is_ai_app": detected_app is not None,
            "adapter": adapter
        }

    # -------------------------------------------------------------------------
    # STEP 3: Verify Authentication Status
    # -------------------------------------------------------------------------
    def check_authentication_status(self, tab_info: Dict[str, Any]) -> Tuple[bool, str]:
        """Detects whether user is blocked by a login screen or auth wall.
        Returns: (is_authenticated: bool, status_message: str)
        """
        adapter: BaseWebsiteAdapter = tab_info.get("adapter")
        url = tab_info.get("url", "")
        title = tab_info.get("title", "")
        service = tab_info.get("service_name", "web")

        if not adapter or not adapter.requires_login:
            return True, "Authentication not required for target."

        # Check URL against login patterns
        if adapter.is_auth_blocked(url):
            msg = f"BLOCKED: User is not authenticated on {service.title()} (Login URL detected: '{url}')."
            logger.warning(f"[BROWSER_TYPING] {msg}")
            return False, msg

        # Check window title for login markers
        login_titles = ["log in", "sign in", "welcome back", "login", "continue with"]
        if any(w in title.lower() for w in login_titles) and service in ["chatgpt", "gemini", "claude"]:
            msg = f"BLOCKED: User is not authenticated on {service.title()} (Auth title detected: '{title}')."
            logger.warning(f"[BROWSER_TYPING] {msg}")
            return False, msg

        # Check CDP DOM if online
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
                if ws.connect():
                    indicators = adapter.get_auth_indicators()
                    js_checks = " || ".join([f"!!document.querySelector('{ind}')" for ind in indicators]) if indicators else "false"
                    js = f"(() => {{ return ({js_checks}); }})()"
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
                    ws.close()
                    if resp and resp.get("result", {}).get("result", {}).get("value") is True:
                        msg = f"BLOCKED: User is not authenticated on {service.title()} (Login button/prompt active on page)."
                        logger.warning(f"[BROWSER_TYPING] {msg}")
                        return False, msg

        return True, "Authenticated"

    # -------------------------------------------------------------------------
    # STEP 4 & 5: Locate Field & Verify Security
    # -------------------------------------------------------------------------
    def locate_and_verify_prompt_field(self, tab_info: Dict[str, Any]) -> Dict[str, Any]:
        """Locates the editable prompt field and verifies it is not protected or disabled."""
        adapter: BaseWebsiteAdapter = tab_info.get("adapter")
        prompt_selectors = adapter.get_prompt_selectors() if adapter else [
            "textarea[placeholder*='message' i]",
            "div[contenteditable='true']",
            "textarea"
        ]

        field_info = {
            "found": False,
            "selector": "",
            "is_editable": False,
            "is_password": False,
            "method": "none"
        }

        # 1. Try CDP DOM locating
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=1.0)
                if ws.connect():
                    for sel in prompt_selectors:
                        escaped_sel = sel.replace("'", "\\'")
                        js = f"""
                        (() => {{
                            const el = document.querySelector('{escaped_sel}');
                            if (!el) return null;
                            const isPassword = el.type === 'password';
                            const isEditable = !el.disabled && !el.readOnly && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.isContentEditable);
                            return {{
                                found: true,
                                isPassword: isPassword,
                                isEditable: isEditable,
                                tag: el.tagName.toLowerCase(),
                                currentLength: (el.value || el.innerText || '').length
                            }};
                        }})()
                        """
                        resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
                        if resp and resp.get("result", {}).get("result", {}).get("value"):
                            data = resp["result"]["result"]["value"]
                            ws.close()
                            if data.get("isPassword"):
                                return {"found": True, "is_password": True, "is_editable": False, "reason": "password_field"}
                            return {
                                "found": True,
                                "selector": sel,
                                "is_editable": data.get("isEditable", True),
                                "is_password": False,
                                "method": "cdp_dom",
                                "ws_url": ws_url
                            }
                    ws.close()

        # 2. Try Windows UIAutomation
        try:
            from core.typing.focus_detector import focus_detector
            focus_info = focus_detector.get_focus_info()
            if focus_info.is_password:
                return {"found": True, "is_password": True, "is_editable": False, "reason": "password_field"}
            if focus_info.is_editable:
                return {
                    "found": True,
                    "selector": "uia_focused_control",
                    "is_editable": True,
                    "is_password": False,
                    "method": "ui_automation",
                    "focus_context": focus_info
                }
        except Exception as e:
            logger.debug(f"[BROWSER_TYPING] UIA prompt locating exception: {e}")

        return field_info

    # -------------------------------------------------------------------------
    # STEP 6 & 7: Insert Draft Message & Verify (Leave Unsent)
    # -------------------------------------------------------------------------
    def insert_draft_message(
        self,
        tab_info: Dict[str, Any],
        field_info: Dict[str, Any],
        message_text: str
    ) -> Dict[str, Any]:
        """Inserts message into prompt box and verifies appearance WITHOUT sending."""
        if not field_info.get("found") or not field_info.get("is_editable"):
            return {"success": False, "error": "Prompt field not editable or not found."}

        method = field_info.get("method")
        insertion_success = False

        # Method 1: CDP DOM Value Injection
        if method == "cdp_dom" and field_info.get("ws_url"):
            ws = LightweightCDPWebSocket(field_info["ws_url"], timeout=1.2)
            if ws.connect():
                sel = field_info["selector"].replace("'", "\\'")
                import json
                payload_json = json.dumps(message_text)
                js = f"""
                (() => {{
                    const el = document.querySelector('{sel}');
                    if (!el) return false;
                    el.focus();
                    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {{
                        el.value = {payload_json};
                    }} else {{
                        el.innerText = {payload_json};
                    }}
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    const currentVal = el.value || el.innerText || '';
                    return currentVal.includes({payload_json});
                }})()
                """
                resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
                ws.close()
                if resp and resp.get("result", {}).get("result", {}).get("value") is True:
                    insertion_success = True

        # Method 2: UI Automation / Safe Clipboard Fallback
        if not insertion_success:
            from core.typing.text_inserter import text_inserter
            focus_ctx = field_info.get("focus_context")
            ins_res = text_inserter.insert_text(message_text, focus_info=focus_ctx)
            insertion_success = ins_res.get("success", False)

        if not insertion_success:
            return {"success": False, "error": "Failed to enter message into browser prompt box."}

        # Step 8: Create pending approval in Ask-Before-Send workflow
        app_name = tab_info.get("service_name", "Chrome AI")
        browser_info = tab_info.get("browser_info", {})
        approval = self.workflow_mgr.create_draft(
            target_app=app_name,
            content=message_text,
            target_hwnd=browser_info.get("hwnd", 0),
            context={"tab_title": tab_info.get("title"), "url": tab_info.get("url"), "field": field_info}
        )

        return {
            "success": True,
            "draft_inserted": True,
            "verified_in_field": True,
            "approval_id": approval.draft_id,
            "status": BrowserSubmissionOutcome.AWAITING_APPROVAL.value,
            "outcome": BrowserSubmissionOutcome.DRAFT_INSERTED.value,
            "message": f"Draft inserted into {app_name.title()}. Ask user: 'Should I send it?'"
        }

    # -------------------------------------------------------------------------
    # STEP 9 & 10: Submit on Explicit Approval & Truthful Evidence Verification
    # -------------------------------------------------------------------------
    def process_send_approval(
        self,
        approval_id: str,
        user_utterance: str,
        stt_confidence: float = 1.0
    ) -> Dict[str, Any]:
        """Executes strict approval gating, application submission, and evidence collection."""
        draft = self.workflow_mgr.get_draft(approval_id)
        current_content = None
        if draft:
            field_info = draft.context.get("field", {})
            if field_info.get("method") == "cdp_dom" and field_info.get("ws_url"):
                try:
                    ws = LightweightCDPWebSocket(field_info["ws_url"], timeout=1.0)
                    if ws.connect():
                        sel = field_info["selector"].replace("'", "\\'")
                        js = f"(() => {{ const el = document.querySelector('{sel}'); return el ? (el.value || el.innerText || '') : ''; }})()"
                        resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
                        ws.close()
                        if resp and resp.get("result", {}).get("result", {}).get("value") is not None:
                            current_content = resp["result"]["result"]["value"]
                except Exception as e:
                    logger.debug(f"[BROWSER_TYPING] Content read error: {e}")

        res = self.workflow_mgr.process_approval_response(
            user_utterance=user_utterance,
            confidence=stt_confidence,
            draft_id=approval_id,
            current_content=current_content
        )

        if not res.get("sent"):
            outcome = BrowserSubmissionOutcome.AWAITING_APPROVAL.value if res.get("requires_explicit_approval") else BrowserSubmissionOutcome.FAILED.value
            return {
                "success": False,
                "approved": False,
                "outcome": outcome,
                "reason": res.get("reason", "not_approved"),
                "requires_explicit_approval": res.get("requires_explicit_approval", False),
                "message": res.get("message", "Message was not approved for sending.")
            }

        target_app = draft.target_app if draft else "AI App"
        field_info = draft.context.get("field", {}) if draft and draft.context else {}

        # STEP 10: Collect Evidence & Transition Outcome State Machine
        time.sleep(0.35)
        outcome = BrowserSubmissionOutcome.SUBMISSION_TRIGGERED.value
        verification = "DELIVERY_UNCONFIRMED"
        evidence = {
            "field_cleared": False,
            "message_visible": False,
            "response_generated": False,
            "error_detected": False
        }

        if field_info.get("method") == "cdp_dom" and field_info.get("ws_url"):
            try:
                ws = LightweightCDPWebSocket(field_info["ws_url"], timeout=1.5)
                if ws.connect():
                    adapter = self.adapter_registry.get_adapter(target_app)
                    prompt_sel = (field_info.get("selector") or "#prompt-textarea").replace("'", "\\'")
                    user_sels = adapter.get_user_turn_selectors() if adapter else []
                    resp_sels = adapter.get_response_indicators() if adapter else []
                    err_sels = adapter.get_error_indicators() if adapter else []

                    import json
                    js_payload = json.dumps(draft.content or "")
                    js_user_sels = json.dumps(user_sels)
                    js_resp_sels = json.dumps(resp_sels)
                    js_err_sels = json.dumps(err_sels)

                    js = f"""
                    (() => {{
                        const promptEl = document.querySelector('{prompt_sel}');
                        const promptVal = promptEl ? (promptEl.value || promptEl.innerText || '').trim() : '';
                        const fieldCleared = !promptEl || !promptVal;

                        let errorDetected = false;
                        let errorText = '';
                        const errSels = {js_err_sels};
                        for (const sel of errSels) {{
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null && (el.innerText || '').trim()) {{
                                errorDetected = true;
                                errorText = (el.innerText || '').trim().slice(0, 100);
                                break;
                            }}
                        }}

                        let messageVisible = false;
                        const userSels = {js_user_sels};
                        const targetPayload = {js_payload};
                        for (const sel of userSels) {{
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {{
                                const txt = (el.innerText || el.textContent || '').trim();
                                if (txt && targetPayload && txt.includes(targetPayload.slice(0, 30))) {{
                                    messageVisible = true;
                                    break;
                                }}
                            }}
                            if (messageVisible) break;
                        }}

                        let responseStarted = false;
                        let responseCompleted = false;
                        // Stop button indicators indicating ongoing streaming
                        const stopSels = ["button[aria-label*='Stop' i]", "button[data-testid*='stop' i]", ".result-streaming", "[data-is-streaming='true']"];
                        for (const sel of stopSels) {{
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null) {{
                                responseStarted = true;
                                break;
                            }}
                        }}

                        // Response content indicators
                        const respSels = {js_resp_sels};
                        let hasResponseContent = false;
                        for (const sel of respSels) {{
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null && (el.innerText || el.textContent || '').trim().length > 0) {{
                                hasResponseContent = true;
                                break;
                            }}
                        }}

                        if (responseStarted) {{
                            // Active streaming
                        }} else if (hasResponseContent) {{
                            responseCompleted = true;
                        }}

                        return {{
                            fieldCleared: fieldCleared,
                            errorDetected: errorDetected,
                            errorText: errorText,
                            messageVisible: messageVisible,
                            responseStarted: responseStarted,
                            responseCompleted: responseCompleted,
                            responseGenerated: (responseStarted || responseCompleted)
                        }};
                    }})()
                    """
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js, "returnByValue": True})
                    ws.close()

                    val = resp.get("result", {}).get("result", {}).get("value") if resp else None
                    if isinstance(val, dict):
                        ev = val
                        evidence = ev
                        if ev.get("errorDetected"):
                            outcome = BrowserSubmissionOutcome.FAILED.value
                            verification = f"FAILED: {ev.get('errorText', 'Application error detected')}"
                        elif ev.get("responseCompleted"):
                            outcome = BrowserSubmissionOutcome.RESPONSE_COMPLETED.value
                            verification = "DELIVERY_VERIFIED"
                        elif ev.get("responseStarted"):
                            outcome = BrowserSubmissionOutcome.RESPONSE_STARTED.value
                            verification = "DELIVERY_VERIFIED"
                        elif ev.get("responseGenerated"):
                            outcome = BrowserSubmissionOutcome.RESPONSE_GENERATED.value
                            verification = "DELIVERY_VERIFIED"
                        elif ev.get("messageVisible"):
                            outcome = BrowserSubmissionOutcome.MESSAGE_VISIBLE.value
                            verification = "DELIVERY_VERIFIED"
                        elif ev.get("fieldCleared"):
                            outcome = BrowserSubmissionOutcome.APPLICATION_ACCEPTED.value
                            verification = "DELIVERY_VERIFIED"
                        else:
                            outcome = BrowserSubmissionOutcome.DELIVERY_UNCONFIRMED.value
                            verification = "DELIVERY_UNCONFIRMED"
                    elif val is True:
                        outcome = BrowserSubmissionOutcome.APPLICATION_ACCEPTED.value
                        verification = "DELIVERY_VERIFIED"
                        evidence["field_cleared"] = True
            except Exception as e:
                logger.debug(f"[BROWSER_TYPING] Evidence verification error: {e}")

        return {
            "success": outcome != BrowserSubmissionOutcome.FAILED.value,
            "approved": True,
            "submitted": True,
            "method": res.get("method", "enter_chat"),
            "outcome": outcome,
            "verification": verification,
            "evidence": evidence,
            "message": f"Message submitted to {target_app} ({outcome} - {verification})."
        }

    # -------------------------------------------------------------------------
    # High-Level Orchestrator: Complete Draft Flow
    # -------------------------------------------------------------------------
    def execute_browser_typing_workflow(self, message_text: str) -> Dict[str, Any]:
        """Executes full 10-step browser typing sequence up to awaiting user approval.
        Returns BLOCKED if not authenticated or not in an AI interface.
        """
        # Step 1: Active browser check
        browser_info = self.identify_active_browser()
        if not browser_info.get("is_browser"):
            return {
                "success": False,
                "status": "NO_BROWSER",
                "message": "Foreground application is not a supported web browser."
            }

        # Step 2: Tab & AI app identification
        tab_info = self.identify_active_tab(browser_info)
        if not tab_info.get("is_ai_app"):
            return {
                "success": False,
                "status": "NOT_AI_APP",
                "message": f"Active tab ('{tab_info.get('title', '')}') is not a recognized AI service."
            }

        # Step 3: Authentication check (Fail-closed)
        is_auth, auth_msg = self.check_authentication_status(tab_info)
        if not is_auth:
            return {
                "success": False,
                "status": BrowserSubmissionOutcome.BLOCKED.value,
                "outcome": BrowserSubmissionOutcome.BLOCKED.value,
                "reason": "unauthenticated",
                "message": auth_msg
            }

        # Step 4 & 5: Field location & editable check
        field_info = self.locate_and_verify_prompt_field(tab_info)
        if not field_info.get("found"):
            return {
                "success": False,
                "status": "FIELD_NOT_FOUND",
                "message": f"Could not find an editable prompt field on {tab_info.get('service_name')}."
            }

        if field_info.get("is_password"):
            return {
                "success": False,
                "status": BrowserSubmissionOutcome.BLOCKED.value,
                "outcome": BrowserSubmissionOutcome.BLOCKED.value,
                "reason": "password_field",
                "message": "Blocked: Target input field is a password or secure field."
            }

        if not field_info.get("is_editable"):
            return {
                "success": False,
                "status": "FIELD_DISABLED",
                "message": "Target prompt field is currently disabled or read-only."
            }

        # Step 6, 7 & 8: Insert draft without sending and create approval draft
        return self.insert_draft_message(tab_info, field_info, message_text)


browser_typing_adapter = BrowserTypingAdapter()
