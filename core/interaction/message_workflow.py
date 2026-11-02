"""The Ask-Before-Send Conversation Workflow Engine.
Strictly separates draft composition from message submission with explicit user approval gates.
"""

import re
import time
import uuid
import hashlib
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from core.interaction.desktop_context_service import desktop_context_service
from core.interaction.text_entry_service import text_entry_service
from core.interaction.models import ControlType, TargetControl

logger = logging.getLogger("Jarvis.MessageWorkflow")


class MessageWorkflowState(str, Enum):
    """Explicit lifecycle states for message preparation and submission."""
    IDLE = "idle"
    TARGET_DETECTED = "target_detected"
    DICTATION_ACTIVE = "dictation_active"
    TRANSCRIBING = "transcribing"
    DRAFT_READY = "draft_ready"
    AWAITING_SEND_APPROVAL = "awaiting_send_approval"
    SENDING = "sending"
    SENT = "sent"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class PendingApproval:
    """Represents a bound message draft awaiting explicit user confirmation."""
    draft_id: str
    target_app: str
    content: str
    content_hash: str
    created_at: float
    target_hwnd: int = 0
    target_window: str = ""
    target_control: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    state: MessageWorkflowState = MessageWorkflowState.AWAITING_SEND_APPROVAL
    submitted: bool = False
    verification: str = "unverified"
    SENDING = "sending"
    SENT = "sent"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    ERROR = "error"


class MessageWorkflowManager:
    """Manages the preparation, safe insertion, and gated approval of external messages."""

    # Explicit send approval triggers
    EXPLICIT_APPROVALS = {
        "yes send it", "send it", "send", "submit", "go ahead and send",
        "yes please send", "go ahead", "send the message", "send this message",
        "yes please", "yes", "please send", "submit it"
    }

    # Ambiguous phrases that approve the draft content but do NOT grant send permission
    AMBIGUOUS_RESPONSES = {
        "okay", "ok", "looks good", "nice", "that's fine", "thats fine",
        "alright", "sure", "cool", "fine", "perfect", "great"
    }

    # Explicit rejection triggers
    EXPLICIT_REJECTIONS = {
        "don't send", "dont send", "leave it", "only type", "wait", "cancel",
        "no", "don't send it", "dont send it", "leave it there", "do not send",
        "just leave it", "keep it as draft", "keep as draft", "stop"
    }

    def __init__(self, context_service=None, entry_service=None, draft_ttl_seconds: float = 180.0):
        self.context_service = context_service or desktop_context_service
        self.entry_service = entry_service or text_entry_service
        self.draft_ttl_seconds = draft_ttl_seconds
        self.state = MessageWorkflowState.IDLE
        self.current_draft: str = ""
        self.target_app: str = ""
        self.target_window: str = ""
        self.target_control: Optional[str] = None
        self.created_at: float = 0.0
        self.active_approvals: Dict[str, PendingApproval] = {}
        self.latest_draft_id: Optional[str] = None

    def create_draft(
        self,
        target_app: str,
        content: str,
        context: Optional[Dict[str, Any]] = None,
        target_hwnd: int = 0
    ) -> PendingApproval:
        """Explicitly registers a pending approval draft with cryptographic content binding."""
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        approval = PendingApproval(
            draft_id=draft_id,
            target_app=target_app,
            content=content,
            content_hash=content_hash,
            created_at=time.time(),
            target_hwnd=target_hwnd,
            target_window=context.get("tab_title", "") if context else "",
            context=context or {},
            state=MessageWorkflowState.AWAITING_SEND_APPROVAL
        )
        self.active_approvals[draft_id] = approval
        self.latest_draft_id = draft_id
        self.current_draft = content
        self.target_app = target_app.lower()
        self.created_at = approval.created_at
        self.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
        return approval

    def get_draft(self, draft_id: Optional[str] = None) -> Optional[PendingApproval]:
        """Retrieves a pending approval by ID or returns the latest active draft."""
        d_id = draft_id or self.latest_draft_id
        return self.active_approvals.get(d_id) if d_id else None

    def verify_draft_unaltered(self, draft_id: str, current_content: Any) -> bool:
        """Verifies that the content of the message has not been altered since draft preparation."""
        draft = self.active_approvals.get(draft_id)
        if not draft:
            return False
        if not isinstance(current_content, str):
            return False
        curr_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
        return curr_hash == draft.content_hash

    def prepare_message(
        self,
        message_text: str,
        target_app: Optional[str] = None,
        destination: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepares a message, inserts the draft into the target application, and awaits approval."""
        if not message_text or not message_text.strip():
            self.state = MessageWorkflowState.ERROR
            return {"success": False, "message": "No message text provided."}

        clean_text = message_text.strip()
        self.current_draft = clean_text
        self.created_at = time.time()
        self.state = MessageWorkflowState.TARGET_DETECTED

        # 1. Resolve desktop context
        ctx = self.context_service.get_current_context(explicit_destination=destination or target_app)
        resolved_app = target_app or ctx.foreground_app or "the active application"
        self.target_app = resolved_app.lower()
        self.target_window = ctx.window_title

        # Register pending approval record
        approval = self.create_draft(
            target_app=self.target_app,
            content=clean_text,
            context={"destination": destination, "window_title": self.target_window}
        )

        # 2. Insert draft safely (WITHOUT submitting)
        self.state = MessageWorkflowState.DRAFT_READY
        insert_res = self.entry_service.enter_text(
            text=clean_text,
            action="write_reply",
            explicit_destination=destination or target_app,
            submit=False  # Mandatory: NEVER submit automatically
        )

        if not insert_res.get("success"):
            self.state = MessageWorkflowState.ERROR
            return insert_res

        # 3. Transition to AWAITING_SEND_APPROVAL
        self.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
        self.target_control = insert_res.get("target", "message field")
        approval.target_control = self.target_control

        target_display = target_app.title() if target_app else (ctx.foreground_app.title() if ctx.foreground_app else "the current application")
        prompt = f"I've entered the message into {target_display}. Should I send it?"

        logger.info(f"[MESSAGE_WORKFLOW] Draft ready in {target_display} ({len(clean_text)} chars). Awaiting send approval.")
        return {
            "success": True,
            "draft_id": approval.draft_id,
            "state": self.state.value,
            "target_app": target_display,
            "target_control": self.target_control,
            "draft_text": clean_text,
            "requires_approval": True,
            "message": prompt
        }

    def process_approval_response(
        self,
        user_utterance: str,
        confidence: float = 1.0,
        draft_id: Optional[str] = None,
        current_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Evaluates user feedback on a pending message draft with expiration, uncertainty, changed draft, and focus checks."""
        d_id = draft_id or self.latest_draft_id
        draft = self.active_approvals.get(d_id) if d_id else None

        if self.state == MessageWorkflowState.SENT or (draft and draft.submitted):
            return {
                "success": False,
                "sent": False,
                "reason": "already_sent",
                "message": "This message draft has already been sent."
            }

        if self.state != MessageWorkflowState.AWAITING_SEND_APPROVAL:
            return {
                "success": False,
                "sent": False,
                "message": "There is no pending message draft awaiting send approval."
            }

        # Check TTL expiration
        effective_created_at = draft.created_at if draft else self.created_at
        if effective_created_at and (time.time() - effective_created_at > self.draft_ttl_seconds):
            self.state = MessageWorkflowState.CANCELLED
            if draft:
                draft.state = MessageWorkflowState.CANCELLED
            logger.warning(f"[MESSAGE_WORKFLOW] Message draft expired after {self.draft_ttl_seconds}s.")
            return {
                "success": False,
                "sent": False,
                "reason": "draft_expired",
                "message": "The pending message draft has expired after 3 minutes. Please dictate your message again before sending."
            }

        # Check changed draft content
        if draft and current_content is not None:
            if not self.verify_draft_unaltered(draft.draft_id, current_content):
                logger.warning(f"[MESSAGE_WORKFLOW] Draft content altered externally. Aborting approval.")
                return {
                    "success": False,
                    "sent": False,
                    "reason": "draft_content_changed",
                    "message": "The draft text was modified externally since preparation. Please review the updated text before sending."
                }

        # Check speech recognition uncertainty
        if confidence < 0.60:
            logger.info(f"[MESSAGE_WORKFLOW] Low STT confidence ({confidence:.2f}) on approval response. Requesting clarification.")
            return {
                "success": True,
                "state": self.state.value,
                "sent": False,
                "requires_explicit_approval": True,
                "message": "I heard your response with low audio confidence. Could you please clearly say 'Yes, send it' or 'Cancel'?"
            }

        clean_input = user_utterance.strip().lower()
        # Normalize internal and trailing punctuation for robust matching
        norm_input = re.sub(r'[,.?!;:\-_"]', ' ', clean_input)
        norm_input = re.sub(r'\s+', ' ', norm_input).strip()

        # 1. Check for EXPLICIT APPROVAL
        if (norm_input in self.EXPLICIT_APPROVALS or
            clean_input in self.EXPLICIT_APPROVALS or
            any(norm_input.startswith(a) for a in ["yes send", "send", "submit", "go ahead and send"]) or
            any(clean_input.startswith(a) for a in ["yes send", "send", "submit", "go ahead and send"])):
            return self._execute_send(draft_id=d_id)

        # 2. Check for EXPLICIT REJECTION
        if (norm_input in self.EXPLICIT_REJECTIONS or
            clean_input in self.EXPLICIT_REJECTIONS or
            any(norm_input.startswith(r) for r in ["don't send", "dont send", "leave it", "no", "cancel"]) or
            any(clean_input.startswith(r) for r in ["don't send", "dont send", "leave it", "no", "cancel"])):
            self.state = MessageWorkflowState.CANCELLED
            if draft:
                draft.state = MessageWorkflowState.CANCELLED
            logger.info("[MESSAGE_WORKFLOW] User explicitly cancelled sending. Leaving draft in place.")
            return {
                "success": True,
                "state": self.state.value,
                "sent": False,
                "message": "Understood, Sir. I'll leave the draft there without sending."
            }

        # 3. Check for AMBIGUOUS RESPONSE (Rejection of send permission, requesting clarification)
        if (norm_input in self.AMBIGUOUS_RESPONSES or
            clean_input in self.AMBIGUOUS_RESPONSES or
            any(norm_input == a for a in ["okay", "ok", "fine", "nice", "looks good"]) or
            any(clean_input == a for a in ["okay", "ok", "fine", "nice", "looks good"])):
            logger.info(f"[MESSAGE_WORKFLOW] Ambiguous user response '{clean_input}'. Send permission withheld.")
            return {
                "success": True,
                "state": self.state.value,
                "sent": False,
                "requires_explicit_approval": True,
                "message": "I've left the draft in place. Would you like me to send it now, or leave it as a draft?"
            }

        # Fallback clarification
        return {
            "success": True,
            "state": self.state.value,
            "sent": False,
            "requires_explicit_approval": True,
            "message": f"I didn't quite catch that. Should I go ahead and send the message, or leave it there?"
        }

    def _execute_send(self, draft_id: Optional[str] = None) -> Dict[str, Any]:
        """Executes application-appropriate send action with foreground verification and honest submission status."""
        self.state = MessageWorkflowState.SENDING
        d_id = draft_id or self.latest_draft_id
        draft = self.active_approvals.get(d_id) if d_id else None

        # Focus & Application Verification Guard
        try:
            # Check target HWND if bound to draft
            if draft and draft.target_hwnd:
                try:
                    import ctypes
                    fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if fg_hwnd and fg_hwnd != draft.target_hwnd:
                        self.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
                        logger.warning(f"[MESSAGE_WORKFLOW] Foreground HWND shifted from {draft.target_hwnd} to {fg_hwnd}. Send aborted.")
                        return {
                            "success": False,
                            "state": self.state.value,
                            "sent": False,
                            "reason": "target_hwnd_changed",
                            "message": "The active window changed. I paused sending so your message is not sent to the wrong window."
                        }
                except Exception as e:
                    logger.debug(f"[MESSAGE_WORKFLOW] HWND verification check error: {e}")

            ctx = self.context_service.get_current_context()
            curr_app = (ctx.foreground_app or "").lower()
            if self.target_app and curr_app and "unknown" not in curr_app:
                if self.target_app not in curr_app and curr_app not in self.target_app:
                    self.state = MessageWorkflowState.AWAITING_SEND_APPROVAL
                    logger.warning(f"[MESSAGE_WORKFLOW] Active window changed from '{self.target_app}' to '{curr_app}'. Send aborted.")
                    return {
                        "success": False,
                        "state": self.state.value,
                        "sent": False,
                        "reason": "target_app_changed",
                        "message": f"The active window changed to '{curr_app.title()}'. I paused sending so your message is not sent to the wrong window."
                    }
        except Exception as e:
            logger.debug(f"[MESSAGE_WORKFLOW] Context verification check error: {e}")

        app_low = self.target_app.lower()

        try:
            import pyautogui
            time.sleep(0.05)

            # Application-Specific Send Logic
            if any(k in app_low for k in ["email", "gmail", "outlook", "thunderbird"]):
                # In email clients, Enter adds a newline! Ctrl+Enter sends!
                pyautogui.hotkey("ctrl", "enter")
                method = "ctrl_enter_email"
            elif any(k in app_low for k in ["chatgpt", "gemini", "claude", "whatsapp", "telegram", "discord", "slack"]):
                # In chat & AI interfaces, Enter sends message
                pyautogui.press("enter")
                method = "enter_chat"
            else:
                # Default submit
                pyautogui.press("enter")
                method = "default_enter"

            self.state = MessageWorkflowState.SENT
            if draft:
                draft.state = MessageWorkflowState.SENT
                draft.submitted = True
            logger.info(f"[MESSAGE_WORKFLOW] Message sent via {method} to {self.target_app}.")
            return {
                "success": True,
                "state": self.state.value,
                "sent": True,
                "method": method,
                "app": self.target_app,
                "outcome": "SUBMISSION_TRIGGERED",
                "verification": "DELIVERY_UNCONFIRMED",
                "message": "Message sent, Sir."
            }
        except Exception as e:
            if "FailSafeException" in type(e).__name__:
                self.state = MessageWorkflowState.CANCELLED
                logger.critical("[EMERGENCY_STOP] Fail-safe triggered during send key press. Aborted.")
                return {
                    "success": False,
                    "state": self.state.value,
                    "sent": False,
                    "reason": "emergency_stop",
                    "message": "Emergency stop activated. Message sending cancelled."
                }
            self.state = MessageWorkflowState.ERROR
            logger.error(f"[MESSAGE_WORKFLOW] Send execution failed: {e}")
            return {
                "success": False,
                "state": self.state.value,
                "sent": False,
                "error": str(e),
                "message": f"Failed to send the message: {e}"
            }

    def cancel(self) -> Dict[str, Any]:
        """Cancels any pending message workflow."""
        self.state = MessageWorkflowState.CANCELLED
        self.current_draft = ""
        return {"success": True, "message": "Message workflow cancelled."}


message_workflow_manager = MessageWorkflowManager()
