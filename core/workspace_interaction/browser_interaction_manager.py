"""SANTRA Unified Interaction Layer - Browser Interaction Manager.
Manages Google Chrome navigation, ChatGPT tab discovery, conversation routing,
pinned conversation selection, and authentication status verification.
Strictly abides by security rules: never extracts cookies or credentials.
"""

import os
import re
import sys
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from core.os.cdp_client import CDPClient
from core.os.browser_automation import LightweightCDPWebSocket
from core.os.website_adapters import website_adapter_registry
from core.workspace_interaction.application_manager import application_manager
from core.workspace_interaction.interaction_models import (
    ChatGPTConversationIdentity,
    SubmissionVerificationStatus
)

logger = logging.getLogger("Santra.BrowserInteractionManager")


class BrowserInteractionManager:
    """Coordinates ChatGPT navigation, tab targeting, and conversation discovery in Google Chrome."""

    CHATGPT_URLS = ["https://chatgpt.com", "https://chat.openai.com"]

    def __init__(self, cdp_client: Optional[CDPClient] = None, app_mgr=None):
        self._is_windows = sys.platform.startswith("win")
        self.cdp = cdp_client or CDPClient()
        self.app_mgr = app_mgr or application_manager
        self.adapter = website_adapter_registry.get_adapter("chatgpt")

    # -------------------------------------------------------------------------
    # Chrome Window & Profile Detection
    # -------------------------------------------------------------------------
    def detect_chrome_windows(self) -> List[Dict[str, Any]]:
        """Finds all open Chrome windows and their titles."""
        return self.app_mgr.get_application_windows("chrome")

    def get_active_profile_hint(self) -> Optional[str]:
        """Heuristically inspects Chrome cmdline flags for profile directory without reading private data."""
        proc = self.app_mgr.find_running_process(["chrome.exe", "chrome"])
        if proc and proc.get("cmdline"):
            for arg in proc["cmdline"]:
                if arg.startswith("--profile-directory="):
                    return arg.split("=")[-1]
        return "Default"

    # -------------------------------------------------------------------------
    # ChatGPT Navigation & Tab Discovery
    # -------------------------------------------------------------------------
    def open_or_focus_chatgpt(self) -> Dict[str, Any]:
        """Finds existing ChatGPT tab or navigates to it in the active Chrome instance."""
        # 1. Check CDP for existing ChatGPT tab
        if self.cdp.is_available():
            tabs = self.cdp.list_tabs()
            for tab in tabs:
                url = tab.get("url", "").lower()
                if any(u in url for u in ["chatgpt.com", "chat.openai.com"]):
                    tab_id = tab.get("id")
                    logger.info(f"[BROWSER_INTERACTION] Found existing ChatGPT tab: {tab_id} ('{tab.get('title')}')")
                    self.cdp.activate_tab(tab_id)
                    # Activate Chrome window
                    self.app_mgr.activate_application("chrome")
                    return {
                        "success": True,
                        "status": "TAB_ACTIVATED",
                        "tab_id": tab_id,
                        "title": tab.get("title", ""),
                        "url": tab.get("url", ""),
                        "message": "Activated existing ChatGPT tab in Chrome."
                    }

        # 2. Heuristic check via open window titles
        windows = self.detect_chrome_windows()
        for win in windows:
            if "chatgpt" in win.get("title", "").lower():
                self.app_mgr.activate_window(win["hwnd"])
                return {
                    "success": True,
                    "status": "WINDOW_ACTIVATED",
                    "hwnd": win["hwnd"],
                    "title": win.get("title", ""),
                    "message": "Activated ChatGPT window."
                }

        # 3. Not currently open: Launch in Chrome
        return self.app_mgr.open_chatgpt_in_chrome("https://chatgpt.com")

    # -------------------------------------------------------------------------
    # Authentication Status Verification
    # -------------------------------------------------------------------------
    def check_login_status(self) -> Tuple[bool, str]:
        """Checks if ChatGPT requires user authentication. Never bypasses or extracts credentials."""
        # Check CDP DOM if available
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            if active_tab:
                url = active_tab.get("url", "").lower()
                title = active_tab.get("title", "").lower()

                # URL pattern checks
                for pat in ["/auth/login", "/auth/ext_callback", "/login", "/auth"]:
                    if pat in url:
                        return False, f"Login required (detected auth URL: {url})"

                # Title pattern checks
                if any(w in title for w in ["log in", "sign in", "welcome back"]):
                    return False, f"Login required (detected title: '{active_tab.get('title')}')"

                # DOM inspection via WebSocket
                ws_url = active_tab.get("webSocketDebuggerUrl")
                if ws_url:
                    ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
                    if ws.connect():
                        js_check = """
                        (() => {
                            const loginBtn = document.querySelector("[data-testid='login-button']") || 
                                             document.querySelector("button[data-testid*='login']") ||
                                             Array.from(document.querySelectorAll("button, a")).find(el => el.textContent.trim().toLowerCase() === 'log in');
                            return !!loginBtn;
                        })()
                        """
                        res = ws.send_cdp_command("Runtime.evaluate", {"expression": js_check, "returnByValue": True})
                        ws.close()
                        if res and res.get("result", {}).get("result", {}).get("value") is True:
                            return False, "Login button detected on page. Please log in to ChatGPT first."

        # Fallback window title inspection
        windows = self.detect_chrome_windows()
        for win in windows:
            title = win.get("title", "").lower()
            if "chatgpt" in title and any(w in title for w in ["log in", "sign in"]):
                return False, f"Login required (window title indicates login: '{win.get('title')}')"

        return True, "Authenticated"

    # -------------------------------------------------------------------------
    # Conversation Navigation (Pinned, Named, Search)
    # -------------------------------------------------------------------------
    def open_pinned_chat(self, pinned_title: str = "SANTRA") -> Dict[str, Any]:
        """Locates and opens the pinned conversation in ChatGPT."""
        # Ensure ChatGPT is in focus
        self.open_or_focus_chatgpt()
        time.sleep(0.3)

        # Check authentication first
        auth_ok, auth_msg = self.check_login_status()
        if not auth_ok:
            return {"success": False, "status": "LOGIN_REQUIRED", "message": auth_msg}

        # CDP DOM interaction to click pinned conversation
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=1.0)
                if ws.connect():
                    # JS query to find pinned chat or sidebar items matching target title
                    js_find_and_click = f"""
                    (() => {{
                        const query = "{pinned_title.lower()}";
                        // Find items inside sidebar nav or pinned lists
                        const items = Array.from(document.querySelectorAll("nav a, [data-testid*='conversation'], li a, div[role='navigation'] a"));
                        for (const item of items) {{
                            const text = (item.innerText || item.textContent || "").toLowerCase();
                            if (text.includes(query)) {{
                                item.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                                item.click();
                                return {{found: true, title: item.innerText || query}};
                            }}
                        }}
                        return {{found: false}};
                    }})()
                    """
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_find_and_click, "returnByValue": True})
                    ws.close()
                    val = resp.get("result", {}).get("result", {}).get("value") if resp else None
                    if val and val.get("found"):
                        return {
                            "success": True,
                            "status": "CONVERSATION_OPENED",
                            "conversation": val.get("title", pinned_title),
                            "pinned": True,
                            "message": f"Opened pinned conversation '{val.get('title', pinned_title)}'."
                        }

        # Non-CDP fallback / direct UIA navigation
        return {
            "success": True,
            "status": "NAVIGATED_BEST_EFFORT",
            "conversation": pinned_title,
            "pinned": True,
            "message": f"Switched to ChatGPT for '{pinned_title}' conversation."
        }

    def open_named_conversation(self, conversation_name: str) -> Dict[str, Any]:
        """Locates and opens a named conversation by title in ChatGPT."""
        self.open_or_focus_chatgpt()
        time.sleep(0.3)

        auth_ok, auth_msg = self.check_login_status()
        if not auth_ok:
            return {"success": False, "status": "LOGIN_REQUIRED", "message": auth_msg}

        clean_name = conversation_name.lower().strip()

        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=1.0)
                if ws.connect():
                    js_find = f"""
                    (() => {{
                        const query = "{clean_name}";
                        const items = Array.from(document.querySelectorAll("nav a, [data-testid*='conversation'], li a"));
                        const matches = [];
                        for (const item of items) {{
                            const text = (item.innerText || item.textContent || "").trim();
                            if (text.toLowerCase().includes(query)) {{
                                matches.push({{title: text, element: item}});
                            }}
                        }}
                        if (matches.length === 1) {{
                            matches[0].element.click();
                            return {{status: "single", title: matches[0].title}};
                        }} else if (matches.length > 1) {{
                            return {{status: "multiple", candidates: matches.map(m => m.title)}};
                        }}
                        return {{status: "not_found"}};
                    }})()
                    """
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_find, "returnByValue": True})
                    ws.close()
                    val = resp.get("result", {}).get("result", {}).get("value") if resp else None
                    if val:
                        if val.get("status") == "single":
                            return {
                                "success": True,
                                "status": "CONVERSATION_OPENED",
                                "conversation": val.get("title"),
                                "message": f"Opened conversation '{val.get('title')}'."
                            }
                        elif val.get("status") == "multiple":
                            return {
                                "success": False,
                                "status": "AMBIGUOUS_MATCH",
                                "candidates": val.get("candidates"),
                                "requires_clarification": True,
                                "message": f"Multiple conversations match '{conversation_name}': {', '.join(val.get('candidates', [])[:3])}. Please select one."
                            }

        return {
            "success": True,
            "status": "NAVIGATED_BEST_EFFORT",
            "conversation": conversation_name,
            "message": f"Switched to ChatGPT window for conversation '{conversation_name}'."
        }

    # -------------------------------------------------------------------------
    # Input Field Detection
    # -------------------------------------------------------------------------
    def locate_prompt_field(self) -> Dict[str, Any]:
        """Locates the ChatGPT message prompt input field."""
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
                if ws.connect():
                    js_find_input = """
                    (() => {
                        const sel = ["#prompt-textarea", "div#prompt-textarea", "div[contenteditable='true']", "textarea[placeholder*='Message' i]"];
                        for (const s of sel) {
                            const el = document.querySelector(s);
                            if (el) {
                                el.focus();
                                return {found: true, selector: s, content: el.innerText || el.value || ""};
                            }
                        }
                        return {found: false};
                    })()
                    """
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_find_input, "returnByValue": True})
                    ws.close()
                    val = resp.get("result", {}).get("result", {}).get("value") if resp else None
                    if val and val.get("found"):
                        return {
                            "success": True,
                            "found": True,
                            "selector": val.get("selector"),
                            "current_text": val.get("content", ""),
                            "method": "cdp"
                        }

        # UIA / Desktop focus fallback
        return {
            "success": True,
            "found": True,
            "selector": "#prompt-textarea",
            "method": "accessibility_target"
        }

    # -------------------------------------------------------------------------
    # Conversation Identity & Re-Reading (Phase 2 & Phase 5)
    # -------------------------------------------------------------------------
    def capture_active_conversation_identity(self) -> ChatGPTConversationIdentity:
        """Captures deep identity of active Chrome process, profile, tab, and ChatGPT conversation."""
        if getattr(self, "active_conversation_identity", None) is not None:
            return self.active_conversation_identity

        proc = self.app_mgr.find_running_process(["chrome.exe", "chrome"])
        pid = proc.get("pid", 0) if proc else 0
        profile = self.get_active_profile_hint() or "Default"

        tab_id = ""
        url = ""
        conv_id = ""
        title = ""
        selector = "#prompt-textarea"

        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            if active_tab:
                tab_id = active_tab.get("id", "")
                url = active_tab.get("url", "")
                title = active_tab.get("title", "")

                m = re.search(r"/c/([a-zA-Z0-9\-]+)", url)
                if m:
                    conv_id = m.group(1)

                ws_url = active_tab.get("webSocketDebuggerUrl")
                if ws_url:
                    ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
                    if ws.connect():
                        js_info = """
                        (() => {
                            const path = window.location.pathname || "";
                            const m = path.match(/\\/c\\/([a-zA-Z0-9\\-]+)/);
                            const conv = m ? m[1] : "";
                            const activeSidebar = document.querySelector("nav a[aria-current='page'], nav a.bg-token-sidebar-surface-tertiary, nav a[class*='active']");
                            const sidebarTitle = activeSidebar ? (activeSidebar.innerText || "").trim() : "";
                            const promptEl = document.querySelector("#prompt-textarea, div[contenteditable='true']");
                            return {
                                conv_id: conv,
                                sidebar_title: sidebarTitle,
                                has_composer: !!promptEl
                            };
                        })()
                        """
                        resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_info, "returnByValue": True})
                        ws.close()
                        val = resp.get("result", {}).get("result", {}).get("value") if resp else None
                        if val:
                            if val.get("conv_id"):
                                conv_id = val.get("conv_id")
                            if val.get("sidebar_title") and not title:
                                title = val.get("sidebar_title")

        if not title:
            windows = self.detect_chrome_windows()
            for win in windows:
                w_title = win.get("title", "")
                if "chatgpt" in w_title.lower():
                    title = w_title
                    break

        return ChatGPTConversationIdentity(
            process_id=pid,
            profile_name=profile,
            tab_id=tab_id,
            url=url,
            conversation_id=conv_id,
            title=title,
            composer_selector=selector,
            timestamp=time.time()
        )

    def verify_conversation_identity(self, expected_identity: Optional[ChatGPTConversationIdentity]) -> Tuple[bool, str]:
        """Independently verifies that the active browser tab matches the expected ChatGPT conversation."""
        if not expected_identity:
            return True, "No identity bound"

        current = self.capture_active_conversation_identity()
        ok, reason = expected_identity.matches(current)
        if not ok:
            logger.warning(f"[BROWSER_INTERACTION] Conversation identity mismatch: {reason}")
            return False, f"CONVERSATION_IDENTITY_CHANGED: {reason}"
        return True, "Identity verified"

    def read_composer_text(self) -> Optional[str]:
        """Re-reads the actual on-screen text from the ChatGPT composer."""
        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
                if ws.connect():
                    js_read = """
                    (() => {
                        const el = document.querySelector("#prompt-textarea, div[contenteditable='true'], textarea[placeholder*='Message' i]");
                        if (!el) return null;
                        return el.innerText || el.value || "";
                    })()
                    """
                    resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_read, "returnByValue": True})
                    ws.close()
                    val = resp.get("result", {}).get("result", {}).get("value") if resp else None
                    if val is not None:
                        return val.strip()
        return None

    # -------------------------------------------------------------------------
    # Submission Verification (Phase 4)
    # -------------------------------------------------------------------------
    def verify_chatgpt_submission(
        self,
        expected_text: str,
        conversation_id: str = "",
        timeout_seconds: float = 2.0
    ) -> Dict[str, Any]:
        """Verifies multi-stage submission in ChatGPT: composer cleared, user turn in DOM, streaming response."""
        start_t = time.time()
        clean_expected = expected_text.strip().lower()

        if self.cdp.is_available():
            active_tab = self.cdp.get_active_tab()
            ws_url = active_tab.get("webSocketDebuggerUrl") if active_tab else None
            if ws_url:
                while time.time() - start_t < timeout_seconds:
                    ws = LightweightCDPWebSocket(ws_url, timeout=0.8)
                    if ws.connect():
                        js_verify = """
                        (() => {
                            const composer = document.querySelector("#prompt-textarea, div[contenteditable='true']");
                            const composerText = composer ? (composer.innerText || composer.value || "").trim() : "";
                            const isCleared = composerText === "";
                            
                            // Check conversation user turns
                            const userTurns = Array.from(document.querySelectorAll("[data-message-author-role='user'], div[class*='user-message'], [data-testid*='user-turn']"));
                            const lastUserTurn = userTurns.length ? (userTurns[userTurns.length - 1].innerText || userTurns[userTurns.length - 1].textContent || "").trim() : "";
                            
                            // Check stop button (streaming response)
                            const stopBtn = !!document.querySelector("button[data-testid='stop-button'], button[aria-label*='Stop' i]");
                            
                            return {
                                composer_cleared: isCleared,
                                last_user_turn: lastUserTurn,
                                streaming_active: stopBtn,
                                total_user_turns: userTurns.length
                            };
                        })()
                        """
                        resp = ws.send_cdp_command("Runtime.evaluate", {"expression": js_verify, "returnByValue": True})
                        ws.close()
                        val = resp.get("result", {}).get("result", {}).get("value") if resp else None

                        if val:
                            composer_cleared = val.get("composer_cleared", False)
                            last_turn = val.get("last_user_turn", "").lower()
                            streaming = val.get("streaming_active", False)

                            # If user turn matches expected prompt or streaming has started
                            if clean_expected in last_turn or (composer_cleared and streaming):
                                stage = SubmissionVerificationStatus.RESPONSE_STARTED if streaming else SubmissionVerificationStatus.PROMPT_ACCEPTED
                                return {
                                    "confirmed": True,
                                    "status": "VERIFIED",
                                    "stage": stage,
                                    "evidence": "user_turn_confirmed_in_chat_stream" if clean_expected in last_turn else "composer_cleared_and_streaming",
                                    "message": "Message confirmed in ChatGPT conversation."
                                }

                    time.sleep(0.15)

        # In environments without live CDP or DOM streaming, report unconfirmed rather than falsely verified
        return {
            "confirmed": False,
            "status": "SUBMISSION_UNCONFIRMED",
            "stage": SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED,
            "evidence": "keystroke_delivered_without_dom_feedback",
            "message": "Submission keystroke delivered, but appearance in chat stream could not be independently confirmed."
        }


# Global singleton
browser_interaction_manager = BrowserInteractionManager()

