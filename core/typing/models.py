"""Data models for Universal Voice Typing Engine."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class TypingMode(str, Enum):
    """Supported universal voice typing modes."""
    CONTINUOUS = "continuous"  # Speaks -> transcribes -> types immediately into focused field
    DRAFT = "draft"            # Accumulates speech into a preview draft before insertion
    DIRECT = "direct"          # Direct instant key-level or value insertion
    CODE = "code"              # Code dictation (symbols, brackets, camelCase, snake_case, indentation)
    CORRECTION = "correction"  # Dictation editing/correcting mode


class TypingState(str, Enum):
    """Visible and audible state indicators for typing engine."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    TEXT_READY = "text_ready"
    INSERTING = "inserting"
    PAUSED = "paused"
    TARGET_LOST = "target_lost"
    ERROR = "error"


@dataclass
class FocusInfo:
    """Detailed metadata about the active foreground window and focused control."""
    app_name: str = "unknown"
    window_title: str = ""
    hwnd: int = 0
    process_name: str = "unknown"
    is_text_field: bool = False
    is_editable: bool = True
    is_password: bool = False  # Critical security flag: True for password/pin inputs
    control_type: str = "edit"
    class_name: str = ""
    automation_id: str = ""
    target_name: str = ""
    confidence: float = 0.5
    raw_element: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_name": self.app_name,
            "window_title": self.window_title,
            "hwnd": self.hwnd,
            "process_name": self.process_name,
            "is_text_field": self.is_text_field,
            "is_editable": self.is_editable,
            "is_password": self.is_password,
            "control_type": self.control_type,
            "class_name": self.class_name,
            "automation_id": self.automation_id,
            "target_name": self.target_name,
            "confidence": self.confidence
        }


@dataclass
class DictationSegment:
    """Represents a single transcribed and formatted speech segment."""
    segment_id: str
    raw_transcript: str
    formatted_text: str
    mode: TypingMode = TypingMode.CONTINUOUS
    timestamp: float = field(default_factory=time.time)
    inserted: bool = False
    target_app: str = ""
    target_hwnd: int = 0
    undoable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "raw_transcript": self.raw_transcript,
            "formatted_text": self.formatted_text,
            "mode": self.mode.value,
            "timestamp": self.timestamp,
            "inserted": self.inserted,
            "target_app": self.target_app,
            "target_hwnd": self.target_hwnd,
            "undoable": self.undoable
        }


@dataclass
class TypingSession:
    """Maintains active dictation session context across multiple spoken sentences."""
    session_id: str
    mode: TypingMode = TypingMode.CONTINUOUS
    state: TypingState = TypingState.INACTIVE
    initial_focus: Optional[FocusInfo] = None
    current_focus: Optional[FocusInfo] = None
    accumulated_draft: str = ""
    segments: List[DictationSegment] = field(default_factory=list)
    last_inserted_text: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    auto_punctuate: bool = True
    code_syntax: str = "python"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "state": self.state.value,
            "initial_focus": self.initial_focus.to_dict() if self.initial_focus else None,
            "current_focus": self.current_focus.to_dict() if self.current_focus else None,
            "accumulated_draft": self.accumulated_draft,
            "segments_count": len(self.segments),
            "last_inserted_text": self.last_inserted_text,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "auto_punctuate": self.auto_punctuate,
            "code_syntax": self.code_syntax
        }

