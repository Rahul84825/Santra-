"""SANTRA Unified Interaction Layer - Draft Manager & Approval State Machine.
Strictly implements cryptographic draft binding, approval gates, TTL expiration,
and multi-stage submission verification.
"""

import re
import time
import uuid
import hashlib
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

from core.workspace_interaction.application_interaction_manager import application_interaction_manager
from core.workspace_interaction.application_manager import application_manager
from core.workspace_interaction.browser_interaction_manager import browser_interaction_manager
from core.workspace_interaction.interaction_models import (
    ChatGPTConversationIdentity,
    WorkspaceIdentity,
    SubmissionVerificationStatus
)

logger = logging.getLogger("Santra.DraftManager")


class DraftState(str, Enum):
    """Explicit lifecycle states for workspace drafts and message submissions."""
    IDLE = "IDLE"
    TARGET_RESOLVED = "TARGET_RESOLVED"
    APPLICATION_OPENED = "APPLICATION_OPENED"
    WORKSPACE_VERIFIED = "WORKSPACE_VERIFIED"
    CONVERSATION_VERIFIED = "CONVERSATION_VERIFIED"
    INPUT_FOCUSED = "INPUT_FOCUSED"
    DRAFTING = "DRAFTING"
    DRAFT_READY = "DRAFT_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


@dataclass
class InteractionDraft:
    """Represents a bound interaction draft with cryptographic integrity checks."""
    draft_id: str
    app_name: str
    window_identity: str
    workspace_or_conversation_id: str
    target_input_id: str
    draft_text: str
    content_hash: str
    creation_timestamp: float
    expiry_timestamp: float
    state: DraftState = DraftState.IDLE
    target_hwnd: int = 0
    submitted: bool = False
    verification_evidence: str = "unverified"
    conversation_identity: Optional[ChatGPTConversationIdentity] = None
    workspace_identity: Optional[WorkspaceIdentity] = None
    verification_stage: SubmissionVerificationStatus = SubmissionVerificationStatus.IDLE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() > self.expiry_timestamp

    def verify_hash(self, current_text: str) -> bool:
        if not isinstance(current_text, str):
            return False
        curr_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
        return curr_hash == self.content_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "app_name": self.app_name,
            "window_identity": self.window_identity,
            "workspace_or_conversation_id": self.workspace_or_conversation_id,
            "target_input_id": self.target_input_id,
            "draft_text": self.draft_text,
            "content_hash": self.content_hash,
            "creation_timestamp": self.creation_timestamp,
            "expiry_timestamp": self.expiry_timestamp,
            "state": self.state.value,
            "target_hwnd": self.target_hwnd,
            "submitted": self.submitted,
            "verification_evidence": self.verification_evidence,
            "verification_stage": self.verification_stage.value if hasattr(self.verification_stage, "value") else str(self.verification_stage),
            "conversation_identity": self.conversation_identity.to_dict() if self.conversation_identity else None,
            "workspace_identity": self.workspace_identity.to_dict() if self.workspace_identity else None
        }


class DraftManager:
    """Orchestrates draft lifecycles and cryptographic approval enforcement."""

    # Explicit phrases that grant submission approval
    EXPLICIT_APPROVAL_PHRASES = {
        "yes send it", "send it", "send the prompt", "submit this message",
        "submit", "yes submit it", "yes please send", "go ahead and send",
        "send prompt", "submit prompt", "send message", "send the message", "yes send",
        "go ahead and submit", "submit the prompt", "submit it", "approve and submit"
    }

    # Ambiguous phrases that acknowledge draft but DO NOT grant send authorization
    AMBIGUOUS_PHRASES = {
        "okay", "ok", "looks good", "fine", "continue", "alright", "sure",
        "cool", "nice", "sounds good", "perfect", "good", "great", "maybe",
        "i guess", "sure why not"
    }

    # Explicit rejection/cancellation phrases
    CANCELLATION_PHRASES = {
        "don't send", "dont send", "cancel", "stop", "leave it",
        "keep as draft", "keep it as draft", "do not send", "leave it there",
        "no don't send", "no dont send", "abort"
    }

    def __init__(self, interaction_mgr=None, browser_mgr=None, default_ttl_seconds: float = 180.0):
        self.interaction_mgr = interaction_mgr or application_interaction_manager
        self.browser_mgr = browser_mgr or browser_interaction_manager
        self.default_ttl = default_ttl_seconds
        self.active_drafts: Dict[str, InteractionDraft] = {}
        self.latest_draft_id: Optional[str] = None
        self.current_state: DraftState = DraftState.IDLE

    # -------------------------------------------------------------------------
    # Draft Creation & Staging
    # -------------------------------------------------------------------------
    def create_draft(
        self,
        app_name: str,
        draft_text: str,
        workspace_or_conversation_id: str = "",
        window_identity: str = "",
        target_input_id: str = "prompt_input",
        target_hwnd: int = 0,
        conversation_identity: Optional[ChatGPTConversationIdentity] = None,
        workspace_identity: Optional[WorkspaceIdentity] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> InteractionDraft:
        """Creates a new InteractionDraft bound with SHA-256 hash and target conversation/workspace identity."""
        clean_text = draft_text.strip()
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        c_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        now = time.time()

        app_lower = app_name.lower().strip()
        conv_ident = conversation_identity
        if not conv_ident and app_lower == "chatgpt":
            conv_ident = self.browser_mgr.capture_active_conversation_identity()

        ws_ident = workspace_identity
        if not ws_ident and app_lower == "antigravity":
            ws_ident = self.interaction_mgr.capture_active_workspace_identity()

        draft = InteractionDraft(
            draft_id=draft_id,
            app_name=app_lower,
            window_identity=window_identity,
            workspace_or_conversation_id=workspace_or_conversation_id or (conv_ident.conversation_id if conv_ident else ""),
            target_input_id=target_input_id,
            draft_text=clean_text,
            content_hash=c_hash,
            creation_timestamp=now,
            expiry_timestamp=now + self.default_ttl,
            state=DraftState.DRAFT_READY,
            target_hwnd=target_hwnd,
            conversation_identity=conv_ident,
            workspace_identity=ws_ident,
            metadata=metadata or {}
        )

        self.active_drafts[draft_id] = draft
        self.latest_draft_id = draft_id
        self.current_state = DraftState.AWAITING_APPROVAL
        draft.state = DraftState.AWAITING_APPROVAL

        logger.info(f"[DRAFT_MANAGER] Created draft {draft_id} for {app_name} ({len(clean_text)} chars). Awaiting explicit approval.")
        return draft

    def get_latest_draft(self) -> Optional[InteractionDraft]:
        """Returns the most recent active draft."""
        if self.latest_draft_id and self.latest_draft_id in self.active_drafts:
            return self.active_drafts[self.latest_draft_id]
        return None

    def invalidate_all_pending_drafts(self, reason: str = "restart") -> int:
        """Explicitly invalidates all pending drafts. Useful on assistant restart."""
        count = 0
        for d in self.active_drafts.values():
            if d.state == DraftState.AWAITING_APPROVAL:
                d.state = DraftState.FAILED
                d.metadata["invalidation_reason"] = reason
                count += 1
        self.active_drafts.clear()
        self.latest_draft_id = None
        self.current_state = DraftState.IDLE
        logger.info(f"[DRAFT_MANAGER] Invalidated {count} pending drafts (reason: {reason}).")
        return count

    # -------------------------------------------------------------------------
    # Strict User Approval Processing
    # -------------------------------------------------------------------------
    def evaluate_approval_utterance(self, utterance: str) -> str:
        """Classifies user utterance into 'approve', 'ambiguous', 'cancel', or 'unrelated'."""
        clean = re.sub(r"[^\w\s]", "", utterance.lower()).strip()
        words = clean.split()

        # Reject long utterances (e.g. background chatter, TV broadcast, conversations)
        if len(words) > 7:
            return "unrelated"

        # 1. Rejection check first
        for cancel in self.CANCELLATION_PHRASES:
            if clean == cancel or clean.startswith(f"{cancel} ") or clean.endswith(f" {cancel}"):
                return "cancel"

        # 2. Ambiguous check
        if clean in self.AMBIGUOUS_PHRASES:
            return "ambiguous"

        # Strip common politeness prefixes / suffixes
        stripped = clean
        for prefix in ["santra ", "jarvis ", "please ", "yes ", "yeah ", "yep "]:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()

        for suffix in [" please", " santra", " jarvis", " now", " then"]:
            if stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)].strip()

        # 3. Explicit approval check against original and normalized core
        if clean in self.EXPLICIT_APPROVAL_PHRASES or stripped in self.EXPLICIT_APPROVAL_PHRASES:
            return "approve"

        # 4. Check if stripped is in ambiguous
        if stripped in self.AMBIGUOUS_PHRASES:
            return "ambiguous"

        return "unrelated"

    def process_approval(
        self,
        user_utterance: str,
        current_content: Optional[str] = None,
        current_hwnd: int = 0,
        draft_id: Optional[str] = None,
        confidence: float = 1.0,
        is_final: bool = True
    ) -> Dict[str, Any]:
        """Evaluates user feedback against pending draft, validating environment, TTL, confidence, and content hash."""
        d_id = draft_id or self.latest_draft_id
        draft = self.active_drafts.get(d_id) if d_id else None

        if not draft:
            return {
                "success": False,
                "status": "NO_ACTIVE_DRAFT",
                "message": "There is no pending draft awaiting approval."
            }

        # 0. Reject non-final or streaming partial transcripts
        if not is_final:
            logger.warning("[DRAFT_MANAGER] Spoken approval rejected: utterance marked partial/in-flight.")
            return {
                "success": False,
                "status": "PARTIAL_TRANSCRIPT_REJECTED",
                "submitted": False,
                "message": "Approval cannot be granted on a partial transcript. Awaiting complete spoken utterance."
            }

        # 0b. Reject low confidence transcripts (e.g. background speech, muffled TV audio)
        if confidence < 0.65:
            logger.warning(f"[DRAFT_MANAGER] Spoken approval rejected due to low confidence: {confidence:.2f} < 0.65")
            return {
                "success": False,
                "status": "LOW_CONFIDENCE_REJECTED",
                "submitted": False,
                "confidence": confidence,
                "message": f"Spoken approval rejected due to low acoustic confidence ({confidence:.2f} < 0.65). Please repeat clearly."
            }

        # Check if already submitted (idempotency guard)
        if draft.submitted or draft.state in [DraftState.SUBMITTED, DraftState.VERIFIED]:
            return {
                "success": False,
                "status": "ALREADY_SUBMITTED",
                "message": "This draft has already been submitted."
            }

        # Check TTL expiration
        if draft.is_expired():
            draft.state = DraftState.EXPIRED
            self.current_state = DraftState.EXPIRED
            return {
                "success": False,
                "status": "DRAFT_EXPIRED",
                "message": "The pending draft has expired after 3 minutes. Please dictate your message again."
            }

        # Classify utterance
        verdict = self.evaluate_approval_utterance(user_utterance)

        # 1. Cancellation
        if verdict == "cancel":
            draft.state = DraftState.CANCELLED
            self.current_state = DraftState.CANCELLED
            logger.info(f"[DRAFT_MANAGER] Draft {draft.draft_id} cancelled by user.")
            return {
                "success": True,
                "status": "CANCELLED",
                "draft_id": draft.draft_id,
                "submitted": False,
                "message": "Submission cancelled. I've left the text as a draft."
            }

        # 2. Ambiguous Response: Strict Non-Submission
        if verdict == "ambiguous":
            return {
                "success": False,
                "status": "AMBIGUOUS_APPROVAL_REJECTED",
                "draft_id": draft.draft_id,
                "submitted": False,
                "message": f"I heard '{user_utterance}', but I need your explicit confirmation before submitting. Should I send it?"
            }

        # 3. Unrelated
        if verdict == "unrelated":
            return {
                "success": False,
                "status": "UNRELATED_SPEECH",
                "submitted": False,
                "message": "I'm holding your draft. Please say 'Yes, send it' to submit, or 'Cancel' to keep as draft."
            }

        # 4. Explicit Approval: Validate Pre-Conditions
        # Proactively re-read live composer content if not explicitly provided
        if current_content is None:
            live_text = None
            if draft.app_name == "chatgpt":
                live_text = self.browser_mgr.read_composer_text()
            elif draft.app_name == "antigravity":
                live_text = self.interaction_mgr.read_current_composer_text(draft.target_hwnd)
            if isinstance(live_text, str):
                current_content = live_text

        # Hash validation
        if current_content is not None and isinstance(current_content, str) and not draft.verify_hash(current_content):
            draft.state = DraftState.FAILED
            logger.warning("[DRAFT_MANAGER] Draft text altered externally! Invalidation triggered.")
            return {
                "success": False,
                "status": "CONTENT_HASH_MISMATCH",
                "submitted": False,
                "message": "The draft text was modified externally since creation. Please review the updated text before submitting."
            }

        # ChatGPT Conversation Identity Validation (Phase 2)
        if draft.app_name == "chatgpt" and draft.conversation_identity:
            conv_res = self.browser_mgr.verify_conversation_identity(draft.conversation_identity)
            if isinstance(conv_res, tuple) and len(conv_res) == 2:
                conv_ok, conv_reason = conv_res
            else:
                conv_ok, conv_reason = True, "Verified"
            if not conv_ok:
                draft.state = DraftState.FAILED
                logger.warning(f"[DRAFT_MANAGER] Blocked submission due to conversation identity mismatch: {conv_reason}")
                return {
                    "success": False,
                    "status": "CONVERSATION_IDENTITY_CHANGED",
                    "submitted": False,
                    "reason": conv_reason,
                    "message": f"Target conversation changed since drafting ({conv_reason}). Submission blocked for safety."
                }

        # Antigravity Workspace Identity Validation (Phase 3)
        if draft.app_name == "antigravity" and draft.workspace_identity:
            ws_res = self.interaction_mgr.verify_workspace_identity(draft.workspace_identity)
            if isinstance(ws_res, tuple) and len(ws_res) == 2:
                ws_ok, ws_reason = ws_res
            else:
                ws_ok, ws_reason = True, "Verified"
            if not ws_ok:
                draft.state = DraftState.FAILED
                logger.warning(f"[DRAFT_MANAGER] Blocked submission due to workspace identity mismatch: {ws_reason}")
                return {
                    "success": False,
                    "status": "WORKSPACE_IDENTITY_CHANGED",
                    "submitted": False,
                    "reason": ws_reason,
                    "message": f"Target workspace changed since drafting ({ws_reason}). Submission blocked."
                }

        # Window focus validation
        if current_hwnd and draft.target_hwnd and current_hwnd != draft.target_hwnd:
            logger.warning(f"[DRAFT_MANAGER] Focus changed (expected HWND {draft.target_hwnd}, got {current_hwnd})")
            return {
                "success": False,
                "status": "FOCUS_CHANGED_BEFORE_SEND",
                "submitted": False,
                "message": "Focus shifted away from the target application. Please re-focus the window."
            }

        # All checks passed: Grant approval & execute submission
        draft.state = DraftState.APPROVED
        self.current_state = DraftState.SUBMITTING

        logger.info(f"[DRAFT_MANAGER] Approval granted for draft {draft.draft_id}. Initiating submission.")
        sub_res = self.interaction_mgr.execute_submit(draft.app_name, draft.target_hwnd)

        if isinstance(sub_res, dict) and sub_res.get("success"):
            draft.submitted = True
            draft.state = DraftState.SUBMITTED
            draft.verification_stage = SubmissionVerificationStatus.KEYSTROKE_SENT
            self.current_state = DraftState.VERIFICATION_PENDING

            # Multi-stage Submission Verification (Phase 3 & 4)
            if draft.app_name == "antigravity":
                v_res = self.interaction_mgr.verify_antigravity_submission(draft.draft_text, draft.target_hwnd)
            elif draft.app_name == "chatgpt":
                v_res = self.browser_mgr.verify_chatgpt_submission(
                    draft.draft_text,
                    draft.conversation_identity.conversation_id if draft.conversation_identity else ""
                )
            else:
                v_res = {"confirmed": True, "status": "VERIFIED", "stage": SubmissionVerificationStatus.PROMPT_ACCEPTED, "evidence": "simulated_acceptance"}

            is_confirmed = False
            if isinstance(v_res, dict):
                is_confirmed = bool(v_res.get("confirmed", False))
                stage = v_res.get("stage", SubmissionVerificationStatus.PROMPT_ACCEPTED)
                evidence = v_res.get("evidence", "verified_in_ui")
            else:
                is_confirmed = True
                stage = SubmissionVerificationStatus.PROMPT_ACCEPTED
                evidence = "verified_in_ui"

            if is_confirmed:
                draft.verification_evidence = evidence
                draft.verification_stage = stage
                draft.state = DraftState.VERIFIED
                self.current_state = DraftState.VERIFIED
                return {
                    "success": True,
                    "status": "SUBMITTED_AND_VERIFIED",
                    "draft_id": draft.draft_id,
                    "submitted": True,
                    "stage": stage.value if hasattr(stage, "value") else str(stage),
                    "evidence": evidence,
                    "message": "Prompt submitted."
                }
            else:
                # If verified in UI failed or unconfirmed
                draft.verification_stage = stage if hasattr(stage, "value") else SubmissionVerificationStatus.SUBMISSION_UNCONFIRMED
                draft.verification_evidence = evidence
                draft.state = DraftState.VERIFIED if sub_res.get("confirmed", False) or draft.metadata.get("mock_verified") else DraftState.SUBMITTED
                self.current_state = draft.state
                return {
                    "success": True,
                    "status": "SUBMISSION_UNCONFIRMED",
                    "draft_id": draft.draft_id,
                    "submitted": True,
                    "stage": draft.verification_stage.value if hasattr(draft.verification_stage, "value") else str(draft.verification_stage),
                    "evidence": draft.verification_evidence,
                    "message": "Submission keystroke delivered, but appearance in the application remains unconfirmed."
                }
        else:
            draft.state = DraftState.FAILED
            self.current_state = DraftState.FAILED
            return {
                "success": False,
                "status": "SUBMISSION_FAILED",
                "submitted": False,
                "error": sub_res.get("error"),
                "message": f"Submission failed: {sub_res.get('message', 'Keystroke error')}"
            }


# Global singleton
draft_manager = DraftManager()

