"""SANTRA Unified Interaction Layer - Domain Models.
Defines strong identity structures, multi-stage submission lifecycle states,
and cryptographic binding records.
"""

import time
import re
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple


class SubmissionVerificationStatus(str, Enum):
    """Granular multi-stage verification states distinguishing physical events."""
    IDLE = "IDLE"
    KEYSTROKE_SENT = "KEYSTROKE_SENT"
    PROMPT_ACCEPTED = "PROMPT_ACCEPTED"
    AGENT_PROCESSING = "AGENT_PROCESSING"
    RESPONSE_STARTED = "RESPONSE_STARTED"
    RESPONSE_COMPLETED = "RESPONSE_COMPLETED"
    SUBMISSION_UNCONFIRMED = "SUBMISSION_UNCONFIRMED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass
class ChatGPTConversationIdentity:
    """Strong identity model for ChatGPT browser sessions preventing cross-conversation leakage."""
    process_id: int = 0
    profile_name: str = "Default"
    tab_id: str = ""
    url: str = ""
    conversation_id: str = ""
    title: str = ""
    composer_selector: str = "#prompt-textarea"
    timestamp: float = field(default_factory=time.time)

    def extract_conv_id(self, url_str: str) -> Optional[str]:
        if not url_str:
            return None
        m = re.search(r"/c/([a-zA-Z0-9\-]+)", url_str)
        return m.group(1) if m else None

    def matches(self, other: "ChatGPTConversationIdentity") -> Tuple[bool, str]:
        """Strictly verifies whether live browser state matches the draft's target conversation."""
        # 1. Process identity
        if self.process_id and other.process_id and self.process_id != other.process_id:
            return False, f"Chrome process mismatch: expected PID {self.process_id}, got {other.process_id}"

        # 2. Browser profile
        if self.profile_name and other.profile_name and self.profile_name.lower() != other.profile_name.lower():
            return False, f"Browser profile mismatch: expected '{self.profile_name}', got '{other.profile_name}'"

        # 3. Tab identifier
        if self.tab_id and other.tab_id and self.tab_id != other.tab_id:
            return False, f"Chrome tab mismatch: expected tab ID '{self.tab_id}', got '{other.tab_id}'"

        # 4. Conversation identifier (URL or DOM ID)
        self_c = self.conversation_id or self.extract_conv_id(self.url)
        other_c = other.conversation_id or self.extract_conv_id(other.url)

        if self_c and other_c and self_c != other_c:
            return False, f"ChatGPT conversation mismatch: expected '{self_c}', got '{other_c}'"

        # 5. URL verification (when conversation is bound to specific URL path)
        if self.url and other.url:
            c1 = self.extract_conv_id(self.url)
            c2 = self.extract_conv_id(other.url)
            if c1 and c2 and c1 != c2:
                return False, f"URL conversation ID mismatch: expected '{c1}', got '{c2}'"

        # 6. Title verification as secondary sanity check
        if self.title and other.title:
            # If one title explicitly specifies conversation name and other doesn't match
            s_t = self.title.lower().strip()
            o_t = other.title.lower().strip()
            if "chatgpt" not in s_t and "chatgpt" not in o_t and s_t != o_t:
                return False, f"Conversation title changed: expected '{self.title}', got '{other.title}'"

        return True, "Conversation identity verified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_id": self.process_id,
            "profile_name": self.profile_name,
            "tab_id": self.tab_id,
            "url": self.url,
            "conversation_id": self.conversation_id or self.extract_conv_id(self.url) or "",
            "title": self.title,
            "composer_selector": self.composer_selector,
            "timestamp": self.timestamp
        }


@dataclass
class WorkspaceIdentity:
    """Strong identity model for Antigravity IDE and local workspace targets."""
    workspace_path: str = ""
    workspace_name: str = ""
    window_title: str = ""
    process_id: int = 0
    target_control: str = ""
    timestamp: float = field(default_factory=time.time)

    def matches(self, other: "WorkspaceIdentity") -> Tuple[bool, str]:
        """Strictly verifies whether live IDE state matches the draft's target workspace."""
        if self.workspace_path and other.workspace_path:
            import os
            if os.path.normpath(self.workspace_path).lower() != os.path.normpath(other.workspace_path).lower():
                return False, f"Workspace path mismatch: expected '{self.workspace_path}', got '{other.workspace_path}'"

        if self.process_id and other.process_id and self.process_id != other.process_id:
            return False, f"Antigravity process mismatch: expected PID {self.process_id}, got {other.process_id}"

        return True, "Workspace identity verified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "workspace_name": self.workspace_name,
            "window_title": self.window_title,
            "process_id": self.process_id,
            "target_control": self.target_control,
            "timestamp": self.timestamp
        }

