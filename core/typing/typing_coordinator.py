"""Universal Voice Typing Coordinator.
Orchestrates dictation modes, continuous speech typing, corrections, and focus stability.
"""

import time
import uuid
import logging
from typing import Optional, List, Dict, Any, Callable

from core.typing.models import (
    TypingMode,
    TypingState,
    FocusInfo,
    DictationSegment,
    TypingSession
)
from core.typing.punctuation_formatter import punctuation_formatter
from core.typing.code_formatter import code_formatter
from core.typing.focus_detector import focus_detector
from core.typing.text_inserter import text_inserter

logger = logging.getLogger("Jarvis.TypingCoordinator")


class TypingCoordinator:
    """Coordinates universal voice typing across all supported applications."""

    def __init__(self, detector=None, inserter=None):
        self.detector = detector or focus_detector
        self.inserter = inserter or text_inserter
        self.active_session: Optional[TypingSession] = None
        self.last_completed_draft: str = ""
        self._state_callbacks: List[Callable[[TypingState, Dict[str, Any]], None]] = []

    def register_state_callback(self, cb: Callable[[TypingState, Dict[str, Any]], None]):
        """Registers a listener for typing state transitions (e.g. PyQt UI badges)."""
        self._state_callbacks.append(cb)

    def _set_state(self, state: TypingState, details: Optional[Dict[str, Any]] = None):
        """Updates internal state and notifies listeners."""
        if self.active_session:
            self.active_session.state = state
            self.active_session.last_activity = time.time()
        logger.info(f"[TYPING_STATE] State -> {state.value} ({details or {}})")
        for cb in self._state_callbacks:
            try:
                cb(state, details or {})
            except Exception as e:
                logger.debug(f"[TYPING_STATE] Callback error: {e}")

    @property
    def state(self) -> TypingState:
        return self.active_session.state if self.active_session else TypingState.INACTIVE

    def get_draft_text(self) -> str:
        """Returns the current accumulated draft text in the active session."""
        if self.active_session:
            return self.active_session.accumulated_draft
        return getattr(self, "last_completed_draft", "")

    def process_dictation(self, text: str) -> Dict[str, Any]:
        """Alias for feed_speech."""
        return self.feed_speech(text)

    def process_correction(self, command: str) -> Dict[str, Any]:
        """Alias for handle_correction."""
        return self.handle_correction(command)

    def is_typing_active(self) -> bool:
        """Returns True if dictation/typing mode is currently engaged."""
        return self.active_session is not None and self.active_session.state in [
            TypingState.ACTIVE,
            TypingState.LISTENING,
            TypingState.TRANSCRIBING,
            TypingState.TEXT_READY,
            TypingState.INSERTING
        ]

    def start_typing(
        self,
        mode: Any = TypingMode.CONTINUOUS,
        code_syntax: str = "python"
    ) -> Dict[str, Any]:
        """Activates universal typing mode into the currently focused window/control."""
        # Normalize mode
        if isinstance(mode, str):
            try:
                mode = TypingMode(mode.lower().strip())
            except ValueError:
                mode = TypingMode.CONTINUOUS

        # 1. Capture current focus
        focus = self.detector.get_focus_info()

        # 2. Check password security
        if focus.is_password:
            self._set_state(TypingState.ERROR, {"reason": "password_field"})
            return {
                "success": False,
                "reason": "password_field",
                "message": "I cannot type into password or secure fields for your security."
            }

        # 3. Create active typing session
        session_id = f"type-{uuid.uuid4().hex[:8]}"
        self.active_session = TypingSession(
            session_id=session_id,
            mode=mode,
            state=TypingState.ACTIVE,
            initial_focus=focus,
            current_focus=focus,
            code_syntax=code_syntax
        )

        app_name = focus.app_name or "active application"
        target_name = focus.target_name or app_name
        self._set_state(TypingState.LISTENING, {"app": app_name, "target": target_name, "mode": mode.value})

        msg = f"Typing mode active in {app_name}. I'm listening."
        if mode == TypingMode.CODE:
            msg = f"Code dictation mode active ({code_syntax}) in {app_name}. Speak your code."
        elif mode == TypingMode.DRAFT:
            msg = f"Draft mode active. I'll accumulate your dictation before inserting."

        return {
            "success": True,
            "session_id": session_id,
            "mode": mode.value,
            "target_app": app_name,
            "target_name": target_name,
            "message": msg
        }

    def stop_typing(self) -> Dict[str, Any]:
        """Deactivates typing mode and finalizes session."""
        if not self.active_session:
            return {"success": True, "message": "Typing mode was not active."}

        prev_session = self.active_session
        self.last_completed_draft = prev_session.accumulated_draft
        self._set_state(TypingState.INACTIVE, {"session_id": prev_session.session_id})
        self.active_session = None

        return {
            "success": True,
            "session_id": prev_session.session_id,
            "segments_count": len(prev_session.segments),
            "accumulated_draft": prev_session.accumulated_draft,
            "message": "Typing mode stopped."
        }

    def pause_typing(self) -> Dict[str, Any]:
        """Pauses dictation listening without destroying session."""
        if not self.active_session:
            return {"success": False, "message": "No active typing session to pause."}
        self._set_state(TypingState.PAUSED)
        return {"success": True, "message": "Typing paused."}

    def resume_typing(self) -> Dict[str, Any]:
        """Resumes a paused typing session."""
        if not self.active_session:
            return self.start_typing()
        self._set_state(TypingState.LISTENING)
        return {"success": True, "message": "Typing resumed."}

    def set_mode(self, mode: TypingMode) -> Dict[str, Any]:
        """Switches dictation mode on the fly."""
        if not self.active_session:
            return self.start_typing(mode=mode)
        self.active_session.mode = mode
        return {"success": True, "mode": mode.value, "message": f"Switched to {mode.value} typing mode."}

    def feed_speech(self, raw_transcript: str) -> Dict[str, Any]:
        """Processes a spoken sentence during active typing session."""
        if not self.active_session or not self.is_typing_active():
            return {"success": False, "reason": "not_active", "message": "Typing is not active."}

        clean = raw_transcript.strip().lower()

        # 0. Safety command preservation: Stop, Cancel, Abort MUST NEVER be swallowed into text!
        SAFETY_STOP_COMMANDS = {
            "stop", "cancel", "abort", "halt", "terminate",
            "stop typing", "stop dictation", "exit typing", "exit dictation",
            "quit typing", "quit dictation", "close typing", "close dictation",
            "done typing", "finish typing", "cancel typing", "cancel dictation",
            "abort typing", "abort dictation", "stop now", "cancel that",
            "abort process", "stop listening", "stop voice"
        }
        if clean in SAFETY_STOP_COMMANDS or any(clean == f"{cmd} {arg}" for cmd in ["stop", "cancel", "abort"] for arg in ["typing", "dictation", "now", "it", "that", "this"]):
            logger.info(f"[VOICE_TYPING] Safety stop command recognized: '{clean}'. Terminating typing session immediately.")
            return self.stop_typing()

        if clean in ["pause typing", "pause dictation", "pause"]:
            return self.pause_typing()

        if clean in ["resume typing", "continue typing"]:
            return self.resume_typing()

        # Check for correction commands
        if any(clean.startswith(p) for p in [
            "delete last", "undo", "replace last", "clear draft",
            "add comma", "new line", "no wait", "scratch that", "change that to"
        ]):
            return self.handle_correction(raw_transcript)

        # Check for mode switches
        if "switch to code mode" in clean or "code dictation mode" in clean or clean == "code mode":
            return self.set_mode(TypingMode.CODE)
        if "switch to continuous mode" in clean or "normal mode" in clean or clean == "continuous mode":
            return self.set_mode(TypingMode.CONTINUOUS)
        if "switch to draft mode" in clean or clean == "draft mode":
            return self.set_mode(TypingMode.DRAFT)

        self._set_state(TypingState.TRANSCRIBING)

        # Format transcript based on active mode
        if self.active_session.mode == TypingMode.CODE:
            formatted = code_formatter.format_code(raw_transcript, language=self.active_session.code_syntax)
        else:
            formatted = punctuation_formatter.format_text(raw_transcript)

        self._set_state(TypingState.TEXT_READY, {"text": formatted})

        # Process insertion based on mode
        session = self.active_session
        if session.mode in [TypingMode.CONTINUOUS, TypingMode.DIRECT, TypingMode.CODE]:
            self._set_state(TypingState.INSERTING)
            res = self.inserter.insert_text(
                text=formatted,
                focus_info=session.current_focus,
                expected_hwnd=session.initial_focus.hwnd if session.initial_focus else 0,
                expected_title=session.initial_focus.window_title if session.initial_focus else ""
            )

            if not res.get("success"):
                if res.get("reason") == "target_lost":
                    self._set_state(TypingState.TARGET_LOST, res)
                else:
                    self._set_state(TypingState.ERROR, res)
                return res

            segment = DictationSegment(
                segment_id=f"seg-{uuid.uuid4().hex[:6]}",
                raw_transcript=raw_transcript,
                formatted_text=formatted,
                mode=session.mode,
                inserted=True,
                target_app=session.initial_focus.app_name if session.initial_focus else "app",
                target_hwnd=session.initial_focus.hwnd if session.initial_focus else 0
            )
            session.segments.append(segment)
            session.last_inserted_text = formatted
            session.accumulated_draft = f"{session.accumulated_draft} {formatted}".strip()

            self._set_state(TypingState.LISTENING)
            return {
                "success": True,
                "inserted": True,
                "text": formatted,
                "app": session.initial_focus.app_name if session.initial_focus else "app",
                "message": f"Typed: {formatted}"
            }

        elif session.mode == TypingMode.DRAFT:
            segment = DictationSegment(
                segment_id=f"seg-{uuid.uuid4().hex[:6]}",
                raw_transcript=raw_transcript,
                formatted_text=formatted,
                mode=session.mode,
                inserted=False,
                target_app=session.initial_focus.app_name if session.initial_focus else "app",
                target_hwnd=session.initial_focus.hwnd if session.initial_focus else 0
            )
            session.segments.append(segment)
            session.accumulated_draft = f"{session.accumulated_draft} {formatted}".strip()
            self._set_state(TypingState.LISTENING)
            return {
                "success": True,
                "inserted": False,
                "draft": session.accumulated_draft,
                "new_segment": formatted,
                "message": f"Added to draft: '{formatted}'"
            }

        return {"success": True, "text": formatted}

    def handle_correction(self, command: str) -> Dict[str, Any]:
        """Handles spoken correction and undo actions."""
        if not self.active_session:
            return {"success": False, "message": "No active typing session."}

        clean = command.strip().lower()

        # 1. Undo last insertion or draft segment
        if clean in ["undo", "undo typing", "undo last insertion", "undo that"]:
            if self.active_session.mode == TypingMode.DRAFT:
                if self.active_session.segments:
                    popped = self.active_session.segments.pop()
                    self.active_session.accumulated_draft = " ".join(s.formatted_text for s in self.active_session.segments).strip()
                    return {"success": True, "message": f"Undid draft segment: '{popped.formatted_text}'"}
                else:
                    self.active_session.accumulated_draft = ""
                    return {"success": True, "message": "Draft is empty."}

            try:
                import pyautogui
                pyautogui.hotkey("ctrl", "z")
                if self.active_session.segments:
                    popped = self.active_session.segments.pop()
                    return {"success": True, "message": f"Undid insertion: '{popped.formatted_text}'"}
                return {"success": True, "message": "Undid last action."}
            except Exception as e:
                if "FailSafeException" in type(e).__name__:
                    logger.critical("[EMERGENCY_STOP] Fail-safe triggered during undo.")
                    return {"success": False, "reason": "emergency_stop", "message": "Emergency stop activated."}
                return {"success": False, "message": f"Failed to undo: {e}"}

        # 2. Clear draft
        if clean in ["clear draft", "clear the draft", "delete draft"]:
            self.active_session.accumulated_draft = ""
            return {"success": True, "message": "Draft cleared."}

        # 3. Add explicit punctuation
        if clean in ["add a comma", "add comma", "insert comma"]:
            return self.inserter.insert_text(text=", ")
        if clean in ["add a period", "add period", "full stop"]:
            return self.inserter.insert_text(text=". ")
        if clean in ["add a new line", "new line", "newline"]:
            return self.inserter.insert_text(text="\n")
        if clean in ["add a new paragraph", "new paragraph"]:
            return self.inserter.insert_text(text="\n\n")

        # 4. Delete last sentence
        if clean in ["delete the last sentence", "delete last sentence", "remove last sentence"]:
            try:
                import pyautogui
                # Standard undo on desktop text inputs
                pyautogui.hotkey("ctrl", "z")
                if self.active_session.segments:
                    self.active_session.segments.pop()
                return {"success": True, "message": "Deleted the last sentence."}
            except Exception as e:
                return {"success": False, "message": f"Could not delete last sentence: {e}"}

        # 5. Spoken replacement / Self-correction: e.g. "no wait, change that to Tuesday", "scratch that make it run.py"
        import re
        match_replace = re.search(r"^(?:no\s+wait[,\s]+|scratch\s+that[,\s]+|wait\s+no[,\s]+)?(?:change\s+that\s+to|replace\s+last\s+(?:word|sentence|segment)?\s+with|replace\s+that\s+with)\s+(.+)$", clean)
        if match_replace:
            replacement_raw = match_replace.group(1).strip()
            formatted_repl = punctuation_formatter.format_text(replacement_raw)
            if self.active_session.mode == TypingMode.DRAFT:
                if self.active_session.segments:
                    last_seg = self.active_session.segments[-1]
                    words = last_seg.formatted_text.split()
                    if len(words) > 1 and len(formatted_repl.split()) <= 2:
                        trail_punct = "." if (words[-1].endswith(".") or last_seg.formatted_text.endswith(".")) else ""
                        words[-1] = formatted_repl.rstrip(".,!?") + (trail_punct or ("." if words[-1].endswith(".") else ""))
                        last_seg.formatted_text = " ".join(words)
                    else:
                        self.active_session.segments.pop()
                        self.active_session.segments.append(DictationSegment(
                            segment_id=f"seg-{uuid.uuid4().hex[:6]}",
                            raw_transcript=replacement_raw,
                            formatted_text=formatted_repl,
                            mode=self.active_session.mode,
                            inserted=False
                        ))
                else:
                    self.active_session.segments.append(DictationSegment(
                        segment_id=f"seg-{uuid.uuid4().hex[:6]}",
                        raw_transcript=replacement_raw,
                        formatted_text=formatted_repl,
                        mode=self.active_session.mode,
                        inserted=False
                    ))
                self.active_session.accumulated_draft = " ".join(s.formatted_text for s in self.active_session.segments).strip()
                return {"success": True, "corrected": True, "draft": self.active_session.accumulated_draft, "message": f"Corrected to: '{formatted_repl}'"}
            else:
                try:
                    import pyautogui
                    pyautogui.hotkey("ctrl", "z")
                except Exception:
                    pass
                if self.active_session.segments:
                    self.active_session.segments.pop()
                self.inserter.insert_text(
                    text=formatted_repl,
                    focus_info=self.active_session.current_focus,
                    expected_hwnd=self.active_session.initial_focus.hwnd if self.active_session.initial_focus else 0
                )
                self.active_session.segments.append(DictationSegment(
                    segment_id=f"seg-{uuid.uuid4().hex[:6]}",
                    raw_transcript=replacement_raw,
                    formatted_text=formatted_repl,
                    mode=self.active_session.mode,
                    inserted=True
                ))
                return {"success": True, "corrected": True, "inserted": True, "text": formatted_repl, "message": f"Corrected to: '{formatted_repl}'"}

        return {"success": False, "message": f"Unrecognized correction command: '{command}'"}


typing_coordinator = TypingCoordinator()
