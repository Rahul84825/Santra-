import os
import re
import time
import uuid
import logging
import threading
from pathlib import Path
from collections import deque
from typing import Callable, Optional, List, Dict, Any

from config import config
from core.brain import Brain
from core.wakeword import WakeWordDetectorFactory
from core.listener import SpeechListener
from core.transcriber import SpeechTranscriber
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.response_manager import ResponseManager
from core.tts.tts_manager import TTSManager
from core.conversation_manager import ConversationManager
from memory.session_memory import SessionMemory
from memory.execution_history import ExecutionHistory
from modules.system.executor import CommandExecutor
from core.tracing import tracer
from core.response_registry import response_registry, CommandOutcome

from core.speech_sanitizer import sanitize_speech_text
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL, MODE_CONTEXT, MODE_REASONING, MODE_QUESTION
from core.proactive_daemon import proactive_daemon

try:
    from core.evolution.collector import evolution_collector
    from core.evolution.scheduler import evolution_scheduler
    from core.evolution.resource_guard import resource_guard
except ImportError:
    evolution_collector = None
    evolution_scheduler = None
    resource_guard = None

logger = logging.getLogger("Jarvis.Runtime")

VALID_STATES = {
    "STANDBY", "ACTIVE", "LISTENING", "TRANSCRIBING", "VALIDATING_INPUT", "ROUTING",
    "WAITING_FOR_NVIDIA", "GENERATING_RESPONSE", "STREAMING_RESPONSE",
    "UNDERSTANDING", "EXECUTING", "THINKING", "PROCESSING", "SYNTHESIZING", "SPEAKING",
    "COMPLETED", "CANCELLED", "TIMED_OUT",
    "SLEEPING", "WAKING", "STOPPED", "ERROR"
}

LEGAL_TRANSITIONS = {
    "STANDBY": {"LISTENING", "TRANSCRIBING", "THINKING", "UNDERSTANDING", "EXECUTING", "PROCESSING", "SYNTHESIZING", "SPEAKING", "STANDBY", "ACTIVE", "SLEEPING", "STOPPED", "ERROR"},
    "ACTIVE": {"LISTENING", "TRANSCRIBING", "THINKING", "UNDERSTANDING", "EXECUTING", "PROCESSING", "SYNTHESIZING", "SPEAKING", "STANDBY", "ACTIVE", "SLEEPING", "STOPPED", "ERROR"},
    "LISTENING": {"TRANSCRIBING", "UNDERSTANDING", "THINKING", "PROCESSING", "EXECUTING", "SYNTHESIZING", "SPEAKING", "STANDBY", "ACTIVE", "SLEEPING", "STOPPED", "ERROR"},
    "TRANSCRIBING": {"UNDERSTANDING", "THINKING", "PROCESSING", "EXECUTING", "SYNTHESIZING", "SPEAKING", "LISTENING", "STANDBY", "ACTIVE", "SLEEPING", "STOPPED", "ERROR"},
    "UNDERSTANDING": {"EXECUTING", "THINKING", "PROCESSING", "SYNTHESIZING", "SPEAKING", "LISTENING", "STANDBY", "ACTIVE", "SLEEPING", "STOPPED", "ERROR"},
    "EXECUTING": {"EXECUTING", "SYNTHESIZING", "SPEAKING", "STANDBY", "ACTIVE", "THINKING", "PROCESSING", "LISTENING", "SLEEPING", "STOPPED", "ERROR"},
    "PROCESSING": {"EXECUTING", "SYNTHESIZING", "SPEAKING", "STANDBY", "ACTIVE", "THINKING", "PROCESSING", "LISTENING", "SLEEPING", "STOPPED", "ERROR"},
    "THINKING": {"EXECUTING", "SYNTHESIZING", "SPEAKING", "STANDBY", "ACTIVE", "LISTENING", "PROCESSING", "SLEEPING", "STOPPED", "ERROR"},
    "SYNTHESIZING": {"SPEAKING", "STANDBY", "ACTIVE", "LISTENING", "SLEEPING", "STOPPED", "ERROR"},
    "SPEAKING": {"SPEAKING", "SYNTHESIZING", "STANDBY", "ACTIVE", "LISTENING", "TRANSCRIBING", "PROCESSING", "UNDERSTANDING", "THINKING", "EXECUTING", "SLEEPING", "STOPPED", "ERROR"},
    "SLEEPING": {"WAKING", "SLEEPING", "STOPPED", "ERROR"},
    "WAKING": {"ACTIVE", "STANDBY", "LISTENING", "SLEEPING", "WAKING", "STOPPED", "ERROR"},
    "STOPPED": {"STANDBY", "ACTIVE"},
    "ERROR": {"STANDBY", "ACTIVE", "LISTENING", "SLEEPING", "STOPPED"}
}
 
 
def find_ide_executable(ide_name: str, fallback_to_active: bool = False) -> Optional[str]:
    """Exhaustively locates an IDE executable on Windows across CLI PATH, common install locations,
    Windows Registry App Paths, and running process trees.

    Args:
        ide_name: Name or alias of the IDE (e.g. 'vscode', 'code', 'antigravity', 'cursor').
        fallback_to_active: If True, falls back to currently active/running IDE if requested IDE is absent.

    Returns:
        Optional[str]: Absolute path to the IDE executable, or None if not found.
    """
    if not ide_name:
        return None

    import shutil
    import sys
    ide = ide_name.lower().strip()

    # 1. Check CLI PATH via shutil.which
    if ide in ["vscode", "code", "visual studio code", "vs_code"]:
        for candidate in ["code", "code.cmd", "code.exe"]:
            w = shutil.which(candidate)
            if w:
                return w
    elif ide in ["antigravity", "agy", "antigravity ide", "anti gravity"]:
        for candidate in ["antigravity", "antigravity.exe", "agy", "agy.cmd", "agy.exe"]:
            w = shutil.which(candidate)
            if w:
                return w
    elif ide in ["cursor"]:
        for candidate in ["cursor", "cursor.cmd", "cursor.exe"]:
            w = shutil.which(candidate)
            if w:
                return w
    else:
        w = shutil.which(ide)
        if w:
            return w

    # 2. Check common Windows user and system install locations
    locations = []
    if ide in ["vscode", "code", "visual studio code", "vs_code"]:
        locations = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
        ]
    elif ide in ["antigravity", "agy", "antigravity ide", "anti gravity"]:
        locations = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe"),
            os.path.expandvars(r"%ProgramFiles%\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%ProgramFiles%\Antigravity IDE\Antigravity IDE.exe"),
        ]
    elif ide in ["cursor"]:
        locations = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe"),
            os.path.expandvars(r"%ProgramFiles%\Cursor\Cursor.exe"),
        ]

    for loc in locations:
        if loc and os.path.exists(loc):
            return loc

    # 3. Check Windows Registry App Paths (HKLM and HKCU)
    if os.name == "nt":
        try:
            import winreg
            app_subkeys = []
            if ide in ["vscode", "code", "visual studio code", "vs_code"]:
                app_subkeys = [r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Code.exe"]
            elif ide in ["antigravity", "agy", "antigravity ide", "anti gravity"]:
                app_subkeys = [
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Antigravity.exe",
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Antigravity IDE.exe",
                ]
            elif ide in ["cursor"]:
                app_subkeys = [r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Cursor.exe"]

            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for sub in app_subkeys:
                    try:
                        with winreg.OpenKey(hive, sub) as k:
                            val, _ = winreg.QueryValueEx(k, "")
                            if val and os.path.exists(val):
                                return val
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. Check running process tree via psutil
    try:
        import psutil
        for p in psutil.process_iter(['name', 'exe']):
            p_name = (p.info.get('name') or '').lower()
            p_exe = p.info.get('exe')
            if p_exe and os.path.exists(p_exe):
                if ide in ["antigravity", "agy", "antigravity ide", "anti gravity"] and "antigravity" in p_name:
                    return p_exe
                elif ide in ["vscode", "code", "visual studio code", "vs_code"] and p_name == "code.exe":
                    return p_exe
                elif ide in ["cursor"] and p_name == "cursor.exe":
                    return p_exe
    except Exception:
        pass

    # 5. Fallback for Antigravity if running under python/sys.executable
    if ide in ["antigravity", "agy", "antigravity ide", "anti gravity"] and sys.executable:
        return sys.executable

    # 6. Optional fallback to currently active IDE if requested IDE is not installed
    if fallback_to_active:
        for alt_ide in ["antigravity", "cursor", "vscode"]:
            if alt_ide != ide:
                alt_exe = find_ide_executable(alt_ide, fallback_to_active=False)
                if alt_exe:
                    return alt_exe

    return None


def get_greeting_reflex_response(text: str = "") -> str:
    """Generates authentic, dynamic JARVIS/F.R.I.D.A.Y. greetings conditioned on the system clock.

    Time Breakdown:
      Morning (05:00 - 12:00): Good morning, Sir. All systems and telemetry online. How may I assist you?
      Afternoon (12:00 - 17:00): Good afternoon, Sir. Standing by for your commands.
      Evening/Night (17:00 - 05:00): Good evening, Sir. Holographic core active. What are we building today?
    """
    import datetime
    now_hour = datetime.datetime.now().hour
    txt = (text or "").lower()

    if "morning" in txt:
        return "Good morning, Sir. All systems and telemetry online. How may I assist you?"
    if "afternoon" in txt:
        return "Good afternoon, Sir. Standing by for your commands."
    if "evening" in txt or "night" in txt:
        return "Good evening, Sir. Holographic core active. What are we building today?"

    if 5 <= now_hour < 12:
        return "Good morning, Sir. All systems and telemetry online. How may I assist you?"
    elif 12 <= now_hour < 17:
        return "Good afternoon, Sir. Standing by for your commands."
    else:
        return "Good evening, Sir. Holographic core active. What are we building today?"


class JarvisRuntime:
    """Headless Central Voice Core Coordinator with Transaction Tracking,
    Authoritative State Machine, and Performance Telemetry.
    """

    def __init__(self):
        logger.info("[JARVIS_INITIALIZING] Starting Voice Core Coordinator...")

        # System state
        self.current_status = "STANDBY"
        self.current_speech_text = "Standby. Say 'Santra' or speak into microphone."
        self.muted = False
        self.pending_intent = None
        self._pending_confirmation: Optional[Dict[str, Any]] = None
        self._tts_speaking_lock = False
        self._state_lock = threading.Lock()
        self._active_utterance_id: Optional[str] = None
        self._last_manual_talk_time: float = 0.0
        self._last_wakeword_time: float = 0.0
        self._speech_end_lock = threading.Lock()
        self._recent_wav_paths = []

        # Transaction & Deduplication Cache
        self._dedup_cache: Dict[str, float] = {}
        self._dedup_lock = threading.Lock()
        self._executed_utterance_ids = set()
        self._executed_utterances_order = []
        self._utterance_exec_lock = threading.Lock()
        self._sleep_cancel_event = threading.Event()
        self._cancelled_utterance_ids = set()
        self._cancelled_lock = threading.Lock()
        self._last_raw_transcript: str = ""
        self._last_normalized_transcript: str = ""
        self._last_filesystem_target: Optional[Path] = None
        self._pending_confirmation: Optional[Dict[str, Any]] = None

        # Observers / Callbacks
        self.on_status_change_cb: Optional[Callable[[str], None]] = None
        self.on_speech_text_cb: Optional[Callable[[str], None]] = None
        self.on_pipeline_stage_cb: Optional[Callable] = None
        self.on_action_complete_cb: Optional[Callable] = None
        self.on_history_update_cb: Optional[Callable] = None
        self.on_permission_dialog_cb: Optional[Callable] = None
        self.on_speech_debug_cb: Optional[Callable] = None
        self.on_audio_amplitude_cb: Optional[Callable[[float], None]] = None
        self.on_camera_state_cb: Optional[Callable] = None
        self.on_gesture_cb: Optional[Callable] = None
        self.panel_visibility_cb: Optional[Callable[[str], None]] = None
        self.on_ai_mode_changed_cb: Optional[Callable[[bool], None]] = None
        self.on_evolution_update_cb: Optional[Callable[[Dict[str, Any]], None]] = None
        self.ai_mode: bool = False

        # Core Engines
        self.history_tracker = ExecutionHistory(limit=100)
        self.executor = CommandExecutor(history_tracker=self.history_tracker)
        self.brain = Brain(executor=self.executor)
        self.transcriber = SpeechTranscriber(cpu_threads=getattr(config, "whisper_threads", 4))
        try:
            from core.os.domain_manager import domain_manager
            domain_vocab = domain_manager.get_vocabulary_prompt()
            self.transcriber.initial_prompt = (
                f"Santra, Hey Santra, Samtra, Suntra, San-tra, Jarvis, open VS Code, YouTube, Chrome, "
                f"{domain_vocab}, Spotify, Notepad, Calculator, lock computer, take a screenshot, calculate, "
                f"system status, shutdown, restart, volume up, volume down, mute, unmute, minimize, maximize, "
                f"what time is it, what is the date, play music."
            ) 
        except Exception as pe:
            logger.debug(f"Could not initialize domain prompt on transcriber: {pe}")
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.memory = SessionMemory(max_turns=20)
        self.conversation_manager = ConversationManager(max_turns=20, session_timeout=60.0)
        self.proactive_daemon = proactive_daemon

        from core.multi_step_planner import multi_step_planner
        self.multi_step_planner = multi_step_planner
        self.multi_step_planner.set_dependencies(self.intent_engine, self.executor)

        # Audio Output Engine
        self.tts_manager = TTSManager()
        self.response_registry = response_registry
        self.response_manager = ResponseManager(speaker=self.tts_manager)

        # Perception & Camera Engine
        from core.perception.camera_manager import camera_manager
        self.camera_manager = camera_manager

        # Audio Input Engine
        self.listener = SpeechListener(
            sample_rate=getattr(config, "audio_sample_rate", 16000),
            threshold=getattr(config, "vad_threshold", 0.015),
            silence_duration=getattr(config, "silence_duration", 0.8),
            max_duration=getattr(config, "max_duration", 5.0),
            enable_vad_onset=True
        )

        # Wake Word Detector
        self.wakeword_detector = WakeWordDetectorFactory.create_detector(
            getattr(config, "wakeword_engine", "mock"),
            wake_words=getattr(config, "wake_words", ["santra"]),
            api_key=getattr(config, "porcupine_api_key", ""),
            model_path=getattr(config, "openwakeword_model_path", ""),
            sensitivity=getattr(config, "wakeword_sensitivity", 0.5)
        )

        # Wire Subsystem Callbacks
        self._wire_subsystems()

        # Wire ALEE ResourceGuard activity observer
        if resource_guard:
            try:
                resource_guard.register_activity_check(
                    lambda: self.current_status in [
                        "LISTENING", "TRANSCRIBING", "ROUTING", "THINKING",
                        "SYNTHESIZING", "SPEAKING", "STREAMING_RESPONSE",
                        "RESEARCH_PLANNING", "WAITING_FOR_NVIDIA"
                    ]
                )
            except Exception as ge:
                logger.debug(f"Could not register resource guard check: {ge}")

        logger.info("[JARVIS_ONLINE] Voice Core Subsystems Initialized & Ready.")

    def _wire_subsystems(self):
        self.listener.on_speech_start_cb = self._on_speech_start
        self.listener.on_speech_end_cb = self._on_speech_end
        self.listener.on_barge_in_cb = self._on_barge_in

        self.tts_manager.on_start_synthesizing_cb = self._on_speaker_synthesizing
        self.tts_manager.on_start_speaking_cb = self._on_speaker_started
        self.tts_manager.on_stop_speaking_cb = self._on_speaker_stopped
        self.tts_manager.on_sentence_progress_cb = self._on_sentence_progress
        self.tts_manager.on_audio_amplitude_cb = lambda amp: self._trigger_cb(self.on_audio_amplitude_cb, amp)

        self.camera_manager.on_state_change_cb = lambda event: self._trigger_cb(self.on_camera_state_cb, event)
        self.camera_manager.on_gesture_cb = lambda event: self._trigger_cb(self.on_gesture_cb, event)

        # Wire Executor Panel Visibility callback
        self.executor.panel_visibility_cb = self._on_panel_visibility

        # Wire Audio Device Dynamic Hot-Swap Observer
        self.listener.on_device_switched_cb = self._on_audio_device_switched

        # Share single coordinated microphone stream with wake word detector
        if hasattr(self.wakeword_detector, "feed_pcm_frame"):
            self.listener.add_audio_consumer(self.wakeword_detector.feed_pcm_frame)

        # Allow wake word detector to share transcriber's Whisper model to prevent duplicate memory usage
        if hasattr(self.wakeword_detector, "set_shared_model"):
            self.wakeword_detector._get_shared_model_fn = lambda: getattr(self.transcriber, "_model", None)

    def start(self):
        """Starts background loops (VAD listener, TTS worker, WakeWord detector, STT prewarm, Resource Monitor)."""
        logger.info("Starting background services...")
        try:
            from core.system_resource_manager import system_resource_manager
            system_resource_manager.start()
            system_resource_manager.set_profile("STANDBY")
        except Exception as re:
            logger.debug(f"Resource manager start error: {re}")

        self.transcriber.preload_in_background()
        self.tts_manager.start(
            on_start_speaking=self._on_speaker_started,
            on_stop_speaking=self._on_speaker_stopped,
            on_start_synthesizing=self._on_speaker_synthesizing,
            on_audio_amplitude=lambda amp: self._trigger_cb(self.on_audio_amplitude_cb, amp)
        )
        try:
            self.listener.start(self._on_speech_start, self._on_speech_end)
        except Exception as mic_err:
            logger.warning(f"Microphone listener startup warning: {mic_err}. System continuing in degraded mode.")

        try:
            self.wakeword_detector.start(self._on_wakeword)
        except Exception as ww_err:
            logger.warning(f"Wake-word detector startup warning: {ww_err}.")

        self.proactive_daemon.start(self._on_proactive_alert)

        if evolution_scheduler:
            try:
                evolution_scheduler.on_maintenance_complete = lambda rep: self._trigger_cb(self.on_evolution_update_cb, rep)
                evolution_scheduler.start()
                # Defer eager boot maintenance: only run on boot if resources are strictly healthy and idle, else defer
                if hasattr(evolution_scheduler, "guard") and evolution_scheduler.guard.can_run_background_tasks():
                    initial_rep = evolution_scheduler.run_maintenance_now()
                    self._trigger_cb(self.on_evolution_update_cb, initial_rep)
                else:
                    logger.info("[EVOLUTION] Deferring eager startup maintenance: system under load or battery constraints. Handing off to scheduler loop.")
            except Exception as se:
                logger.warning(f"Could not start evolution scheduler: {se}")

        self._update_status("STANDBY")
        logger.info("[JARVIS_ONLINE] Standing by for wake word...")

    def get_startup_health(self) -> Dict[str, Any]:
        """Provides internal health and readiness check for Santra's background services."""
        mic_listening = getattr(self.listener, "is_listening", lambda: False)()
        mic_name = getattr(self.listener, "active_input_device_name", "Unknown")
        ww_listening = getattr(self.wakeword_detector, "is_listening", lambda: False)()
        ww_avail = getattr(self.wakeword_detector, "is_available", lambda: False)()
        ww_diag = getattr(self.wakeword_detector, "get_diagnostic", lambda: "Ready")()
        tts_name = self.tts_manager.provider.get_name() if hasattr(self.tts_manager, "provider") else "Default TTS"
        tools_count = len(self.brain.tool_registry.list_tools()) if (hasattr(self, "brain") and hasattr(self.brain, "tool_registry")) else 0

        actionable_errors = []
        if not mic_listening:
            actionable_errors.append(f"Microphone listener is not active (device: {mic_name}). Check audio device connection.")
        if not ww_listening and not self.muted:
            actionable_errors.append(f"Wake-word detection loop is not running ({ww_diag}).")

        is_healthy = mic_listening and (ww_listening or self.muted)

        return {
            "healthy": is_healthy,
            "status": self.current_status,
            "muted": self.muted,
            "microphone": {
                "active": mic_listening,
                "device": mic_name,
                "index": getattr(self.listener, "active_input_device_index", None),
                "stream_health": self.listener.get_stream_health() if hasattr(self.listener, "get_stream_health") else {}
            },
            "wakeword": {
                "active": ww_listening,
                "available": ww_avail,
                "diagnostic": ww_diag,
                "engine": getattr(config, "wakeword_engine", "mock")
            },
            "tts": {
                "provider": tts_name
            },
            "tools_registered": tools_count,
            "ai_mode": self.ai_mode,
            "actionable_errors": actionable_errors
        }

    def set_ai_mode(self, enabled: bool) -> str:
        """Explicitly enables or disables deep AI reasoning mode."""
        self.ai_mode = bool(enabled)
        msg = "AI mode activated. Deep reasoning with Nemotron is online." if self.ai_mode else "AI mode deactivated. Returned to standard hybrid mode."
        logger.info(f"[AI_MODE] Switched to {'AI_MODE' if self.ai_mode else 'NORMAL_MODE'}")
        if self.on_ai_mode_changed_cb:
            self._trigger_cb(self.on_ai_mode_changed_cb, self.ai_mode)
        return msg

    def toggle_ai_mode(self) -> str:
        """Toggles AI mode."""
        return self.set_ai_mode(not self.ai_mode)

    def stop(self):
        """Halts all background threads cleanly."""
        logger.info("Shutting down Jarvis Voice Core...")
        self._update_status("STOPPED")
        try:
            from core.system_resource_manager import system_resource_manager
            system_resource_manager.stop()
        except Exception:
            pass
        self.camera_manager.force_stop()
        self.proactive_daemon.stop()
        self.wakeword_detector.stop()
        self.listener.stop()
        self.tts_manager.stop()

        if evolution_scheduler:
            try:
                evolution_scheduler.stop()
            except Exception:
                pass
        if evolution_collector:
            try:
                evolution_collector.shutdown()
            except Exception:
                pass

        logger.info("Jarvis Voice Core terminated cleanly.")

    def _on_proactive_alert(self, title: str, message: str, speak: bool = False):
        """Handles proactive alerts from the background daemon without blocking voice core."""
        logger.info(f"[PROACTIVE_EVENT] [{title}] {message}")
        self._update_speech_text(f"Notice: {message}")
        if speak and not self.muted and not self.tts_manager.is_speaking():
            self.response_manager.conversation(message, speak=True)

    # ==========================================
    # OBSERVER / CALLBACK REGISTRATION
    # ==========================================
    def register_observers(
        self,
        on_status_change=None,
        on_speech_text=None,
        on_pipeline_stage=None,
        on_action_complete=None,
        on_history_update=None,
        on_permission_dialog=None,
        on_speech_debug=None,
        on_audio_amplitude=None,
        on_camera_state=None,
        on_gesture=None,
        on_ai_mode_changed=None,
        on_evolution_update=None
    ):
        if on_status_change: self.on_status_change_cb = on_status_change
        if on_speech_text: self.on_speech_text_cb = on_speech_text
        if on_pipeline_stage: self.on_pipeline_stage_cb = on_pipeline_stage
        if on_action_complete: self.on_action_complete_cb = on_action_complete
        if on_history_update: self.on_history_update_cb = on_history_update
        if on_permission_dialog: self.on_permission_dialog_cb = on_permission_dialog
        if on_speech_debug: self.on_speech_debug_cb = on_speech_debug
        if on_audio_amplitude: self.on_audio_amplitude_cb = on_audio_amplitude
        if on_camera_state: self.on_camera_state_cb = on_camera_state
        if on_gesture: self.on_gesture_cb = on_gesture
        if on_ai_mode_changed: self.on_ai_mode_changed_cb = on_ai_mode_changed
        if on_evolution_update: self.on_evolution_update_cb = on_evolution_update

    def _on_panel_visibility(self, action: str):
        if self.panel_visibility_cb:
            self._trigger_cb(self.panel_visibility_cb, action)

    def _update_status(self, status: str, utterance_id: Optional[str] = None):
        with self._state_lock:
            if self.current_status == status:
                return
            allowed = LEGAL_TRANSITIONS.get(self.current_status, VALID_STATES)
            if status not in allowed and status not in VALID_STATES:
                logger.warning(f"Illegal state transition attempted: {self.current_status} -> {status}. Ignoring.")
                return

            self.current_status = status
            if utterance_id:
                self._active_utterance_id = utterance_id
            elif status == "STANDBY":
                self._active_utterance_id = None
            prefix = f"[UTTERANCE {utterance_id}] " if utterance_id else ""
            logger.info(f"{prefix}Pipeline State -> [{status}]")

        if self.on_status_change_cb:
            self._trigger_cb(self.on_status_change_cb, status)

    def _update_speech_text(self, text: str):
        self.current_speech_text = text
        if self.on_speech_text_cb:
            self._trigger_cb(self.on_speech_text_cb, text)

    def _trigger_cb(self, cb, *args):
        if cb:
            try:
                cb(*args)
            except Exception as e:
                logger.error(f"Error in observer callback: {e}")

    # ==========================================
    # DETECTOR & MANUAL TALK EVENT CALLBACKS
    # ==========================================
    def trigger_manual_talk(self):
        """Dedicated handler for the manual Talk button in UI.
        - Works independently of wake-word detector.
        - Debounces rapid repeated clicks (< 250ms) to prevent audio buffer corruption.
        - If actively recording speech, toggles recording off to immediately finalize and process speech.
        - If speaking or generating response (THINKING/SYNTHESIZING), invalidates stale output,
          halts playback, and transitions immediately to capture the new utterance.
        - If idle/standby, ensures listener is running, transitions to LISTENING, plays chime,
          and begins manual capture preserving pre-roll.
        """
        now = time.time()
        # 0. Debounce rapid double-clicks (< 250ms)
        if (now - self._last_manual_talk_time) < 0.25:
            logger.debug("[MANUAL_TALK] Ignored rapid repeated click (<250ms).")
            return
        self._last_manual_talk_time = now

        # 0b. If in SLEEPING mode, manual talk button acts as manual wake
        if self.current_status == "SLEEPING":
            logger.info("[MANUAL_TALK] Manual talk button pressed while in SLEEPING mode. Waking JARVIS.")
            self.wake_up(source="manual_click")
            return

        # 1. If listener is actively recording speech -> Toggle stop to finalize and process
        is_rec = False
        if hasattr(self.listener, "is_recording"):
            rec_val = self.listener.is_recording()
            is_rec = (rec_val is True)
        if is_rec:
            logger.info("[MANUAL_TALK] Button clicked while actively recording. Stopping recording to process command.")
            self.listener.stop_manual_recording()
            return

        # 1b. Ignore if busy in non-interruptible critical stages (transcribing, intent understanding, tool execution)
        if self.current_status in ("TRANSCRIBING", "UNDERSTANDING", "EXECUTING"):
            logger.info(f"[MANUAL_TALK_IGNORED] Ignoring manual talk during busy state: {self.current_status}")
            return

        # 2. Interrupt TTS playback and generation if active or thinking
        if self._tts_speaking_lock or self.tts_manager.is_speaking() or self.current_status in ("SPEAKING", "SYNTHESIZING", "THINKING"):
            logger.info(f"[MANUAL_TALK] Button clicked while Jarvis is {self.current_status}. Interrupting and invalidating stale generation.")
            self.tts_manager.new_generation()
            self.tts_manager.interrupt(force=True)
            self._tts_speaking_lock = False
            self.listener.set_speaking_active(False)
            self.conversation_manager.mark_interrupted()

        # 3. Ensure listener is running
        if not self.listener.is_listening():
            try:
                self.listener.start(self._on_speech_start, self._on_speech_end)
            except Exception as e:
                logger.error(f"[MANUAL_TALK] Failed to start microphone listener: {e}")
                self._update_status("ERROR")
                self._update_speech_text("Microphone error. Check audio device.")
                return

        # 4. Start manual recording session
        utterance_id = uuid.uuid4().hex[:6].upper()
        self._active_utterance_id = utterance_id
        logger.info(f"[UTTERANCE {utterance_id}][MANUAL_TALK_ACTIVATED] Manual talk button pressed.")
        self._update_status("LISTENING", utterance_id)
        self._update_speech_text("Listening...")
        if hasattr(self.listener, "suppress_chime_feedback"):
            self.listener.suppress_chime_feedback(0.22)
        self.tts_manager.play_wake_chime()
        self.listener.trigger_manual_recording(manual=True)

    def _on_wakeword(self, word: str):
        """Callback from WakeWordDetector when wake phrase is detected in microphone stream."""
        if self.current_status == "SLEEPING":
            logger.info(f"[WAKE_FROM_SLEEP] Wake phrase '{word}' detected while in SLEEPING mode. Restoring pipeline.")
            self.wake_up(source="wakeword")
            return

        # State machine guard: Do not interrupt ongoing critical pipeline processing
        if self.current_status in ("LISTENING", "TRANSCRIBING", "UNDERSTANDING", "EXECUTING", "THINKING"):
            logger.info(f"[WAKEWORD_SUPPRESSED] Ignoring wake word '{word}' while assistant is busy in state '{self.current_status}'.")
            return

        now = time.time()
        # Cooldown guard: debounce rapid duplicate wake word triggers (< 1.2s)
        if (now - getattr(self, "_last_wakeword_time", 0.0)) < 1.2:
            logger.debug(f"[WAKEWORD_DEBOUNCED] Ignored rapid duplicate wake callback within 1.2s.")
            return
        self._last_wakeword_time = now

        if self._tts_speaking_lock or self.tts_manager.is_speaking():
            if self.tts_manager.is_playing() or word in ("manual_click", "button", "force"):
                logger.info(f"[BARGE_IN] Wake word '{word}' detected during active playback. Interrupting TTS.")
                self.tts_manager.interrupt(force=True)
                self._tts_speaking_lock = False
                self.listener.set_speaking_active(False)
            else:
                logger.info("Suppressing wake word trigger during TTS synthesis.")
                return

        utterance_id = uuid.uuid4().hex[:6].upper()
        self._active_utterance_id = utterance_id
        logger.info(f"[UTTERANCE {utterance_id}][WAKE_WORD_DETECTED] Keyword: '{word}'")
        self._update_status("LISTENING", utterance_id)
        self._update_speech_text("Listening...")

        # Suppress chime feedback from entering speech recording buffer
        if hasattr(self.listener, "suppress_chime_feedback"):
            self.listener.suppress_chime_feedback(0.22)

        # Play instantaneous acoustic earcon chime acknowledging wake word
        self.tts_manager.play_wake_chime()
        self.listener.trigger_manual_recording(manual=True)

    def _on_audio_device_switched(self, old_device: str, new_device: str, latency_ms: float):
        """Observer invoked when microphone input endpoint dynamically hot-swaps."""
        logger.info(f"[AUDIO_DYNAMIC_HOTSWAP] Input stream transitioned: '{old_device}' -> '{new_device}' in {latency_ms:.1f}ms.")
        if hasattr(self.wakeword_detector, "reset_audio_state"):
            self.wakeword_detector.reset_audio_state()
        if hasattr(self.wakeword_detector, "release_standalone_stream"):
            self.wakeword_detector.release_standalone_stream()
        self._update_speech_text(f"Mic switched to: {new_device}")

    def _on_barge_in(self):
        t0 = time.time()
        logger.info("[VOICE_BARGE_IN] Immediate user speech barge-in activated. Terminating TTS output immediately.")
        self.tts_manager.interrupt(force=True, from_vad=True)
        self._tts_speaking_lock = False
        self.listener.set_speaking_active(False)
        self.conversation_manager.mark_interrupted()
        self._update_status("LISTENING")
        self._update_speech_text("Listening...")
        barge_ms = (time.time() - t0) * 1000
        logger.info(f"[BARGE_IN_TIMING] Speech playback silenced and state synchronized in {barge_ms:.2f}ms.")

    def _on_sentence_progress(self, sentence_idx: int, total_sentences: int, text: str):
        self.conversation_manager.update_sentence_progress(sentence_idx, total_sentences, text)

    def _on_speech_start(self):
        if self._tts_speaking_lock or self.tts_manager.is_speaking():
            logger.info("[BARGE_IN] Voice onset confirmed during playback. Triggering immediate barge-in interruption.")
            self._on_barge_in()
            return

        utterance_id = uuid.uuid4().hex[:6].upper()
        logger.info(f"[UTTERANCE {utterance_id}][RECORDING_STARTED] Voice onset confirmed by VAD.")
        self._update_status("LISTENING", utterance_id)
        self._update_speech_text("Listening...")

    def _on_speech_end(self, wav_path: str):
        # Discard empty, non-existent, or sub-threshold audio files immediately without running STT
        if not wav_path or not os.path.exists(wav_path):
            self._update_status("STANDBY")
            self._update_speech_text("Standby. Say 'Santra' or speak into microphone.")
            return

        # Deduplicate WAV segments to prevent identical audio file reprocessing
        with self._speech_end_lock:
            if wav_path in self._recent_wav_paths:
                logger.info(f"[DEDUPLICATION] Discarding duplicate WAV segment already processed: {wav_path}")
                return
            self._recent_wav_paths.append(wav_path)
            if len(self._recent_wav_paths) > 20:
                self._recent_wav_paths.pop(0)

        utterance_id = uuid.uuid4().hex[:6].upper()
        t_speech_end = time.time()
        trace = tracer.start_trace()
        trace.record_timestamp("speech_end", t_speech_end)
        trace.record_timestamp("vad_complete", t_speech_end)
        logger.info(f"[UTTERANCE {utterance_id}][RECORDING_FINISHED] Speech audio saved: {wav_path}")
        self._update_status("TRANSCRIBING", utterance_id)

        text = ""
        meta = {}
        whisper_duration_s = 0.0
        audio_dur_s = 0.0
        t_stt_start = time.time()
        try:
            t0_whisper = time.time()
            text = self.transcriber.transcribe(wav_path)
            if evolution_collector and text:
                try:
                    text = evolution_collector.apply_known_aliases(text)
                except Exception as ae:
                    logger.debug(f"Alias resolution error in on_speech_end: {ae}")
            whisper_duration_s = time.time() - t0_whisper
            meta = getattr(self.transcriber, "last_metadata", {}) or {}
            audio_dur_s = meta.get("duration", 0.0)
            logger.info(f"[UTTERANCE {utterance_id}][WHISPER_RESULT] '{text}' (Confidence={meta.get('confidence', 0.0):.2f})")
            if self.on_speech_debug_cb:
                self._trigger_cb(
                    self.on_speech_debug_cb,
                    text,
                    meta.get("confidence", 0.0),
                    meta.get("language", "en"),
                    audio_dur_s
                )
        except Exception as e:
            logger.error(f"[UTTERANCE {utterance_id}] Transcriber error: {e}", exc_info=True)
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception as ex:
                    logger.warning(f"Could not remove temporary WAV file: {ex}")

        # Empty speech early exit
        if not text or not text.strip():
            logger.info(f"[UTTERANCE {utterance_id}][EMPTY_TRANSCRIPT] Silence or noise discarded. Returning to STANDBY.")
            tracer.end_trace(trace.correlation_id, status="SILENCE_DETECTED")
            self._update_status("STANDBY", utterance_id)
            self._update_speech_text("Standby. Say 'Santra' or speak into microphone.")
            return

        self._update_speech_text(f"You: {text}")
        self.process_command(text, utterance_id=utterance_id, t0_start=t_speech_end, whisper_ms=whisper_duration_s * 1000, audio_dur_s=audio_dur_s)

    def resolve_permission(self, confirmed: bool):
        """Resolves a pending safety-restricted action from UI dialog confirmation."""
        if self.pending_intent:
            intent_kind = self.pending_intent.get("intent")
            if intent_kind == "workspace_optional_confirmation":
                ws_id = self.pending_intent.get("workspace_id") or self.pending_intent.get("target")
                opt_id = self.pending_intent.get("optional_id")
                from core.os.workspace_manager import workspace_manager
                self.pending_intent = None
                if confirmed:
                    res = workspace_manager.execute_workspace(ws_id, confirmed_optional_ids=[opt_id])
                else:
                    res = workspace_manager.execute_workspace(ws_id, declined_optional_ids=[opt_id])
                msg = res.get("message", "Workspace launched.")
                if res.get("success"):
                    self.response_manager.success(msg, spoken_text=msg, speak=True)
                else:
                    self.response_manager.failure(msg, spoken_text=msg, speak=True)
                self._update_status("STANDBY")
                self._update_speech_text(msg)
                return

            task_id = self.pending_intent.get("task_id")
            if confirmed:
                logger.info("Safety confirmation accepted via UI permission dialog.")
                if task_id:
                    from core.agent.task_models import TaskStatus
                    self.pending_intent = None
                    res_task = self.multi_step_planner.continue_task(confirm=True)
                    summary = res_task.execution_summary or "Resumed task completed."
                    if res_task.status == TaskStatus.COMPLETED:
                        self.response_manager.success(summary, spoken_text=summary, speak=True)
                    else:
                        self.response_manager.failure(summary, spoken_text=summary, speak=True)
                    self._update_status("STANDBY")
                    self._update_speech_text(summary)
                else:
                    pending = self.pending_intent
                    self.pending_intent = None
                    self._execute_intent(pending, confirm=True)
            else:
                logger.info("Safety confirmation rejected via UI permission dialog.")
                if task_id:
                    self.multi_step_planner.cancel_active_task()
                self.pending_intent = None
                self.response_manager.cancellation()
                self._update_status("STANDBY")
                self._update_speech_text("Action canceled. Standby.")

    # ==========================================
    # COMMAND PIPELINE & EXECUTION
    # ==========================================
    def process_command(self, text: str, utterance_id: Optional[str] = None, t0_start: Optional[float] = None, whisper_ms: float = 0.0, audio_dur_s: float = 0.0):
        """Dispatches command execution asynchronously."""
        if not text or not text.strip():
            logger.info(f"[UTTERANCE {utterance_id or 'NONE'}][EMPTY_COMMAND] Discarding empty command string.")
            return

        actual_uid = utterance_id or uuid.uuid4().hex[:6].upper()
        with self._utterance_exec_lock:
            if actual_uid in self._executed_utterance_ids:
                logger.warning(f"[RATE_LIMIT_WARNING][DUPLICATE_UTTERANCE] Utterance {actual_uid} already executed or executing. Rejecting duplicate dispatch.")
                return
            self._executed_utterance_ids.add(actual_uid)
            self._executed_utterances_order.append(actual_uid)
            if len(self._executed_utterances_order) > 200:
                old = self._executed_utterances_order.pop(0)
                self._executed_utterance_ids.discard(old)

        self._active_utterance_id = actual_uid
        t0 = t0_start or time.time()
        logger.info(f"[UTTERANCE {actual_uid}][DISPATCH] text='{text}'")
        threading.Thread(
            target=self._process_command_worker,
            args=(text, actual_uid, t0, whisper_ms, audio_dur_s),
            name=f"CmdWorker-{actual_uid}",
            daemon=True
        ).start()

    def _is_duplicate_request(self, normalized_text: str, utterance_id: Optional[str] = None) -> bool:
        """Prevent rapid duplicate callback executions for the same utterance or rapid identical bursts
        without a distinct utterance ID (< 1.2s window), while allowing genuinely distinct spoken utterances
        to repeat earlier commands normally.
        """
        now = time.time()
        last_text = getattr(self, "_last_req_text", None)
        last_time = getattr(self, "_last_req_time", 0.0)
        last_uid = getattr(self, "_last_req_uid", None)

        # If it's a distinctly registered new utterance ID, it's a new spoken request
        if utterance_id is not None and last_uid is not None and utterance_id != last_uid:
            self._last_req_text = normalized_text
            self._last_req_time = now
            self._last_req_uid = utterance_id
            return False

        if last_text == normalized_text and (now - last_time) < 1.2:
            return True

        self._last_req_text = normalized_text
        self._last_req_time = now
        self._last_req_uid = utterance_id
        return False

    def _process_command_worker(self, text: str, utterance_id: Optional[str] = None, t0_start: Optional[float] = None, whisper_ms: float = 0.0, audio_dur_s: float = 0.0):
        if utterance_id is None:
            utterance_id = uuid.uuid4().hex[:6].upper()
        if t0_start is None:
            t0_start = time.time()

        # Guard against processing an utterance that was superseded by newer speech or manual talk
        if self._active_utterance_id and utterance_id != self._active_utterance_id:
            logger.info(f"[UTTERANCE {utterance_id}] Discarding stale command worker execution (active utterance: {self._active_utterance_id}).")
            return

        self._active_utterance_id = utterance_id

        if evolution_collector and text:
            try:
                text = evolution_collector.apply_known_aliases(text)
            except Exception as ae:
                logger.debug(f"Alias resolution error in process_command_worker: {ae}")

        # Guard against processing in SLEEPING mode (suppress background speech, allow wake phrases)
        if self.current_status == "SLEEPING":
            from core.pronunciation_manager import pronunciation_manager
            clean_text = text.lower().strip()
            is_wake, var, conf = pronunciation_manager.evaluate_candidate(clean_text)
            if is_wake or any(w in clean_text for w in ["santra", "samtra", "suntra", "santhra", "jarvis", "wake up"]):
                logger.info(f"[SLEEP_WAKE_UTTERANCE] Wake command spoken while in SLEEPING mode: '{text}' (variant: '{var}')")
                self.wake_up(source="voice")
                # Extract trailing command after wake phrase (preserving command arguments and casing)
                is_addr, canon, trailing = pronunciation_manager.extract_wake_and_command(text)
                if not trailing:
                    m = re.match(r"^\s*(?:(?:hey|hello|hi)?\s*(?:santra|samtra|suntra|jarvis)\s*[,:]?\s*|wake\s+up\s*[,:]?\s*)(.+)$", text, re.IGNORECASE)
                    if m:
                        trailing = m.group(1).strip()
                    else:
                        norm = self.normalizer.normalize(text)["normalized"].strip()
                        if norm:
                            trailing = norm
                if trailing and len(trailing) > 1:
                    logger.info(f"[SLEEP_TRAILING_COMMAND] Dispatching trailing command: '{trailing}'")
                    self.process_command(trailing)
                if self._active_utterance_id == utterance_id:
                    self._active_utterance_id = None
                return
            else:
                logger.info(f"[SLEEP_REJECTED] Discarding background speech while in SLEEPING mode: '{text}'")
                if self._active_utterance_id == utterance_id:
                    self._active_utterance_id = None
                return

        clean_text = text.lower().strip()

        # Defense-in-depth: STT & fragment validation gate
        from core.transcript_validator import transcript_validator, ValidationStatus
        val = transcript_validator.validate(text)
        if not val.is_valid:
            if val.status == ValidationStatus.WAKEWORD_ONLY:
                logger.info(f"[UTTERANCE {utterance_id}][WAKE_ACK] Pure wake-word address received: '{text}'")
                self.response_manager.conversation("I'm listening, Sir.", speak=True)
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text("I'm listening, Sir.")
            else:
                logger.info(f"[UTTERANCE {utterance_id}][DISCARDED] Discarding invalid speech input (status={val.status}): '{text}'")
                self._update_status("STANDBY", utterance_id)
            if self._active_utterance_id == utterance_id:
                self._active_utterance_id = None
            return

        # -------------------------------------------------------------
        # 0A. Universal Voice Typing Interception
        # -------------------------------------------------------------
        try:
            from core.typing.typing_coordinator import typing_coordinator
            if typing_coordinator.is_typing_active():
                t_res = typing_coordinator.feed_speech(text)
                msg = t_res.get("message", "")
                if t_res.get("success"):
                    if t_res.get("state") in ["inactive", "paused", "error"]:
                        if msg:
                            self.response_manager.success(msg, spoken_text=msg, speak=True)
                    else:
                        typed_txt = t_res.get("text") or t_res.get("draft") or msg
                        self._update_speech_text(f"Typed: {typed_txt}")
                    self._update_status("STANDBY", utterance_id)
                    if self._active_utterance_id == utterance_id:
                        self._active_utterance_id = None
                    return
                elif t_res.get("reason") in ["target_lost", "password_field_blocked", "password_field"]:
                    if msg:
                        self.response_manager.warning(msg, spoken_text=msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    if self._active_utterance_id == utterance_id:
                        self._active_utterance_id = None
                    return
        except Exception as te:
            logger.debug(f"[VOICE_TYPING] Typing interception pass-through: {te}")

        # -------------------------------------------------------------
        # 0B. Message Send Gated Approval Interception
        # -------------------------------------------------------------
        try:
            from core.interaction.message_workflow import message_workflow_manager, MessageWorkflowState
            if message_workflow_manager.state == MessageWorkflowState.AWAITING_SEND_APPROVAL:
                m_res = message_workflow_manager.process_approval_response(text)
                m_msg = m_res.get("message", "")
                if m_res.get("sent"):
                    self.response_manager.success(m_msg, spoken_text=m_msg, speak=True)
                elif m_res.get("requires_explicit_approval"):
                    self.response_manager.conversation(m_msg, speak=True)
                else:
                    self.response_manager.conversation(m_msg, speak=True)

                self._update_status("STANDBY", utterance_id)
                self._update_speech_text(m_msg)
                if self._active_utterance_id == utterance_id:
                    self._active_utterance_id = None
                return
        except Exception as me:
            logger.debug(f"[MESSAGE_WORKFLOW] Approval interception pass-through: {me}")

        # 0. Active Conversational PendingActionContext (Follow-up & Clarification Resolution)
        pending_act = self.conversation_manager.get_pending_action()
        if pending_act:
            if pending_act.can_resolve(clean_text):
                logger.info(f"[UTTERANCE {utterance_id}][PENDING_RESOLVED] Resolving pending clarification for '{pending_act.target}' with response: '{clean_text}'")
                self.conversation_manager.clear_pending_action()
                self.pending_intent = None
                resolved = pending_act.resolve_action(clean_text)
                if resolved.get("cancelled"):
                    cancel_msg = resolved.get("message", "Action cancelled, Sir.")
                    self.response_manager.conversation(cancel_msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(cancel_msg)
                    return
                # Execute resolved action directly
                self._execute_intent(resolved, confirm=True, speak=True, utterance_id=utterance_id)
                self._update_status("STANDBY", utterance_id)
                return
            else:
                # User did not answer the pending clarification (e.g. topic change)
                logger.info(f"[UTTERANCE {utterance_id}][PENDING_SUPERSEDED] Follow-up '{clean_text}' does not answer pending clarification '{pending_act.clarification_question}'. Discarding pending action and executing new request.")
                self.conversation_manager.clear_pending_action()
                self.pending_intent = None

        # 0.9. GUI Draft-and-Confirm Safety Gate handler
        if getattr(self, "_pending_confirmation", None):
            pending_conf = self._pending_confirmation
            pending_time = pending_conf.get("timestamp", 0)
            if pending_time and (time.time() - pending_time > 60.0):
                logger.info(f"[UTTERANCE {utterance_id}] Pending GUI draft-and-confirm timed out after 60s.")
                self._pending_confirmation = None
            else:
                from modules.system import gui_interactor
                yes_phrases = ["yes", "confirm", "sure", "ok", "go ahead", "do it", "send", "send it", "press enter", "submit", "submit it", "yes send it"]
                no_phrases = ["no", "cancel", "don't send", "dont send", "do not send", "abort", "discard", "stop"]
                if any(p in clean_text for p in yes_phrases) and not any(n in clean_text for n in ["no", "don't", "dont", "cancel"]):
                    ok = gui_interactor.confirm_pending_gui_action(self)
                    msg = "Confirmed and sent, Sir." if ok else "Action submitted."
                    self.response_manager.success(msg, spoken_text=msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return {"success": True, "action": "confirm_gui_action", "message": msg}
                elif any(p in clean_text for p in no_phrases):
                    ok = gui_interactor.cancel_pending_gui_action(self)
                    msg = "Action cancelled and draft discarded, Sir."
                    self.response_manager.conversation(msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return {"success": True, "action": "cancel_gui_action", "message": msg}

        # 1. Safety & Workspace confirmation handler
        if self.pending_intent:
            # Check timeout (60 seconds)
            pending_time = self.pending_intent.get("timestamp", 0)
            if pending_time and (time.time() - pending_time > 60.0):
                logger.info(f"[UTTERANCE {utterance_id}] Pending confirmation timed out after 60s. Discarding pending intent.")
                self.pending_intent = None

        if self.pending_intent:
            intent_kind = self.pending_intent.get("intent")
            if intent_kind == "workspace_optional_confirmation":
                ws_id = self.pending_intent.get("workspace_id") or self.pending_intent.get("target")
                opt_id = self.pending_intent.get("optional_id")
                from core.os.workspace_manager import workspace_manager

                # Handle cancellation
                if clean_text in ["cancel", "stop", "abort", "nevermind"] or clean_text.startswith("cancel ") or clean_text.startswith("abort "):
                    self.pending_intent = None
                    msg = "Workspace launch cancelled, Sir."
                    self.response_manager.conversation(msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                # Handle always preference
                if any(p in clean_text for p in ["always", "always open", "always launch", "always do"]):
                    self.pending_intent = None
                    res = workspace_manager.execute_workspace(ws_id, always_optional_ids=[opt_id])
                    msg = res.get("message", "Workspace launched.")
                    if res.get("success"):
                        self.response_manager.success(msg, spoken_text=msg, speak=True)
                    else:
                        self.response_manager.failure(msg, spoken_text=msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                # Handle never preference
                if any(p in clean_text for p in ["never", "never open", "never launch", "never do"]):
                    self.pending_intent = None
                    res = workspace_manager.execute_workspace(ws_id, never_optional_ids=[opt_id])
                    msg = res.get("message", "Workspace launched.")
                    if res.get("success"):
                        self.response_manager.success(msg, spoken_text=msg, speak=True)
                    else:
                        self.response_manager.failure(msg, spoken_text=msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                # Handle yes
                yes_match = (
                    any(clean_text == p or clean_text.startswith(p + " ") or f" {p} " in f" {clean_text} " for p in ["yes", "confirm", "sure", "ok", "go ahead", "do it", "yeah", "yep", "please", "open it", "open discord"]) and
                    not any(p in clean_text for p in ["no", "don't", "dont", "skip", "never", "leave it", "without"])
                )
                if yes_match:
                    self.pending_intent = None
                    res = workspace_manager.execute_workspace(ws_id, confirmed_optional_ids=[opt_id])
                    msg = res.get("message", "Workspace launched.")
                    if res.get("success"):
                        self.response_manager.success(msg, spoken_text=msg, speak=True)
                    else:
                        self.response_manager.failure(msg, spoken_text=msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                # Handle no
                no_match = any(clean_text == p or clean_text.startswith(p + " ") or f" {p} " in f" {clean_text} " for p in ["no", "don't", "dont", "skip", "negative", "leave it", "without", "nope", "nah"])
                if no_match:
                    self.pending_intent = None
                    res = workspace_manager.execute_workspace(ws_id, declined_optional_ids=[opt_id])
                    msg = res.get("message", "Workspace launched.")
                    if res.get("success"):
                        self.response_manager.success(msg, spoken_text=msg, speak=True)
                    else:
                        self.response_manager.failure(msg, spoken_text=msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                # Ambiguous reply
                msg = "Please reply with yes, no, always, or never to decide if Discord should open, or say cancel."
                self.response_manager.conversation(msg, speak=True)
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text(msg)
                return

            if intent_kind == "desktop_interaction.clarify_target":
                from core.interaction import text_entry_service
                text_to_enter = self.pending_intent.get("text", "")
                action_kind = self.pending_intent.get("action", "enter_text")
                candidates = self.pending_intent.get("candidates", [])

                if any(p in clean_text for p in ["cancel", "stop", "nevermind", "abort"]):
                    self.pending_intent = None
                    msg = "Text entry cancelled, Sir."
                    self.response_manager.conversation(msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                chosen_dest = clean_text
                for cand in candidates:
                    cand_name = cand.get("name", "").lower()
                    cand_type = cand.get("control_type", "").lower()
                    if cand_name and (cand_name in clean_text or clean_text in cand_name):
                        chosen_dest = cand.get("name")
                        break
                    if cand_type and cand_type in clean_text:
                        chosen_dest = cand.get("name") or cand_type
                        break

                self.pending_intent = None
                res = text_entry_service.enter_text(
                    text=text_to_enter,
                    action=action_kind,
                    explicit_destination=chosen_dest
                )
                msg = res.get("message", "Text inserted.")
                if res.get("success"):
                    self.response_manager.success(msg, spoken_text=msg, speak=True)
                else:
                    self.response_manager.failure(msg, spoken_text=msg, speak=True)
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text(msg)
                return

            if intent_kind == "desktop_interaction.await_focus":
                from core.interaction import text_entry_service, desktop_context_service
                text_to_enter = self.pending_intent.get("text", "")
                action_kind = self.pending_intent.get("action", "enter_text")

                if any(p in clean_text for p in ["cancel", "stop", "nevermind", "abort"]):
                    self.pending_intent = None
                    msg = "Text entry cancelled, Sir."
                    self.response_manager.conversation(msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

                if any(p in clean_text for p in ["ready", "done", "ok", "yes", "i clicked", "focused", "go ahead", "now", "here"]):
                    self.pending_intent = None
                    ctx = desktop_context_service.get_current_context()
                    target = ctx.focused_element
                    if target:
                        res = text_entry_service.context_service.adapter.insert_text(
                            target=target,
                            text=text_to_enter,
                            mode="insert",
                            expected_hwnd=ctx.window_hwnd,
                            expected_title=ctx.window_title
                        )
                        msg = f"The draft is inserted into {target.name}. I haven't sent it." if res.get("success") else res.get("message", "Failed to insert.")
                        if res.get("success"):
                            self.response_manager.success(msg, spoken_text=msg, speak=True)
                        else:
                            self.response_manager.failure(msg, spoken_text=msg, speak=True)
                    else:
                        msg = "I still cannot detect a focused text field. Please ensure your cursor is in the field, or say cancel."
                        self.pending_intent = {
                            "intent": "desktop_interaction.await_focus",
                            "text": text_to_enter,
                            "action": action_kind
                        }
                        self.response_manager.conversation(msg, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(msg)
                    return

            if intent_kind == "desktop_interaction.send_confirm":
                from core.interaction import text_entry_service
                self.pending_intent = None
                yes_phrases = ["yes", "confirm", "sure", "ok", "go ahead", "do it", "send", "send it"]
                if any(p in clean_text for p in yes_phrases) and not any(n in clean_text for n in ["no", "don't", "dont", "cancel"]):
                    res = text_entry_service.execute_send_message(confirm=True)
                    msg = res.get("message", "Message sent.")
                    self.response_manager.success(msg, spoken_text=msg, speak=True)
                else:
                    msg = "Message sending cancelled. The draft remains in place, Sir."
                    self.response_manager.conversation(msg, speak=True)
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text(msg)
                return

            yes_phrases = ["yes", "confirm", "sure", "ok", "go ahead", "do it"]
            task_id = self.pending_intent.get("task_id")
            if any(p in clean_text for p in yes_phrases):
                logger.info(f"[UTTERANCE {utterance_id}] Safety confirmation accepted.")
                if task_id:
                    from core.agent.task_models import TaskStatus
                    self.pending_intent = None
                    res_task = self.multi_step_planner.continue_task(confirm=True)
                    summary = res_task.execution_summary or "Resumed task completed."
                    if res_task.status == TaskStatus.COMPLETED:
                        self.response_manager.success(summary, spoken_text=summary, speak=True)
                    else:
                        self.response_manager.failure(summary, spoken_text=summary, speak=True)
                    self._update_status("STANDBY", utterance_id)
                    self._update_speech_text(summary)
                else:
                    pending = self.pending_intent
                    self.pending_intent = None
                    self._execute_intent(pending, confirm=True, utterance_id=utterance_id)
            else:
                logger.info(f"[UTTERANCE {utterance_id}] Safety confirmation rejected.")
                if task_id:
                    self.multi_step_planner.cancel_active_task()
                self.pending_intent = None
                self.response_manager.cancellation()
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text("Action canceled. Standby.")
            return

        # 2. Duplicate request check
        norm_res = self.normalizer.normalize(text)
        normalized = norm_res["normalized"]
        if self._is_duplicate_request(normalized, utterance_id=utterance_id):
            logger.info(f"[UTTERANCE {utterance_id}][DEDUP] Suppressing duplicate rapid request execution: '{normalized}'")
            self._update_status("STANDBY", utterance_id)
            return

        # 3. Multi-command clause splitting & Agentic multi-step planning
        chained_commands = self.normalizer.split_chained_commands(text)
        if len(chained_commands) > 1:
            logger.info(f"[UTTERANCE {utterance_id}][MULTI_COMMAND] Planning and executing {len(chained_commands)} sub-commands via MultiStepPlanner: {chained_commands}")
            task = self.multi_step_planner.plan(text)
            if task and task.steps:
                from core.agent.task_models import TaskStatus
                exec_task = self.multi_step_planner.execute_task(
                    task,
                    on_step_start=lambda s: self._notify_pipeline_stage(text, normalized, f"step_{s.step_index+1}:{s.tool_name}", "MultiStepPlanner", s.description, "Executing"),
                    on_step_complete=lambda s, r: self._notify_pipeline_stage(text, normalized, f"step_{s.step_index+1}:{s.tool_name}", "MultiStepPlanner", r.get("message", ""), "Running")
                )
                summary_text = exec_task.execution_summary or self.multi_step_planner._generate_truthful_summary(exec_task)

                if exec_task.status == TaskStatus.AWAITING_CONFIRMATION:
                    curr_step = exec_task.steps[exec_task.current_step_index]
                    self.pending_intent = {
                        "task_id": exec_task.task_id,
                        "intent": "agent_task_step",
                        "action": curr_step.tool_name,
                        "message": f"Action requires confirmation: {curr_step.description}. Proceed?"
                    }
                    self.response_manager.warning(self.pending_intent["message"], speak=True)
                    self._update_speech_text(f"Safety Warning: {self.pending_intent['message']}")
                    if self.on_permission_dialog_cb:
                        self._trigger_cb(self.on_permission_dialog_cb, curr_step.tool_name, self.pending_intent["message"])
                    return

                if exec_task.status == TaskStatus.COMPLETED:
                    self.response_manager.success(summary_text, spoken_text=summary_text, speak=True)
                    try:
                        from core.learning import procedure_learner
                        procedure_learner.learn_procedure(
                            name=task.parsed_goal or f"proc_{int(time.time())}",
                            intent="multi_step_workflow",
                            user_request=text,
                            steps=[{"tool": s.tool_name, "parameters": s.parameters, "description": s.description} for s in task.steps],
                            source="multi_step_planner"
                        )
                    except Exception as le:
                        logger.debug(f"Failed to auto-learn multi-step procedure: {le}")
                else:
                    self.response_manager.failure(summary_text, spoken_text=summary_text, speak=True)

                self._notify_pipeline_stage(text, normalized, "multi_step_task", "MultiStepPlanner", summary_text, "Speaking")
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text(summary_text)

                t_total_ms = (time.time() - t0_start) * 1000
                logger.info(f"[PERFORMANCE][{utterance_id}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms multi_exec={t_total_ms:.0f}ms total={t_total_ms:.0f}ms")
                return

        self._process_single_command(text, raw_full_text=text, speak=True, utterance_id=utterance_id, t0_start=t0_start, whisper_ms=whisper_ms, audio_dur_s=audio_dur_s, normalized=normalized)
        if self._active_utterance_id == utterance_id:
            self._active_utterance_id = None

    def _process_single_command(
        self,
        text: str,
        raw_full_text: str = None,
        speak: bool = True,
        utterance_id: Optional[str] = None,
        t0_start: Optional[float] = None,
        whisper_ms: float = 0.0,
        audio_dur_s: float = 0.0,
        normalized: Optional[str] = None
    ) -> dict:
        uid = utterance_id or uuid.uuid4().hex[:6].upper()
        t0_proc = time.time()
        raw_full_text = raw_full_text or text
        trace = tracer.get_current_trace()

        def _check_cancelled():
            if self.current_status == "SLEEPING":
                return True
            if self._sleep_cancel_event.is_set():
                return True
            with self._cancelled_lock:
                if uid in self._cancelled_utterance_ids:
                    return True
            return False

        self._update_status("ROUTING", uid)
        # Route via 3-Layer Intelligence Router
        t0_route = time.time()
        req = intelligence_router.route(text, session_context=self.conversation_manager.get_context(), normalized=normalized, ai_mode=self.ai_mode)
        routing_ms = (time.time() - t0_route) * 1000
        normalized_text = req.normalized_text
        if req.intent != "CORRECTION":
            self._last_raw_transcript = raw_full_text or text
            self._last_normalized_transcript = normalized_text or text
        logger.info(f"[UTTERANCE {uid}][ROUTER] Mode='{req.mode}' | Layer={req.layer} | Intent='{req.intent}' | Target='{req.target}' ({routing_ms:.1f}ms)")

        # Case 0A: Instant Reflex for Stop Talking
        if req.intent == "STOP_TALKING":
            t0_stop = time.time()
            self.tts_manager.interrupt(force=True)
            self._tts_speaking_lock = False
            self.listener.set_speaking_active(False)
            self.conversation_manager.mark_interrupted()
            msg = "Speech paused."
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            stop_ms = (time.time() - t0_stop) * 1000
            logger.info(f"[STOP_TALKING][{uid}] Audio stopped in {stop_ms:.2f}ms. Standing by.")
            return {"success": True, "action": "stop_speech", "message": msg}

        # Case 0B: User Correction
        if req.intent == "CORRECTION":
            corrected_query = self.conversation_manager.apply_correction(text)
            logger.info(f"[UTTERANCE {uid}][CORRECTION] Corrected query from '{text}' -> '{corrected_query}'")
            if evolution_collector:
                try:
                    evolution_collector.record_correction(
                        failed_transcript=self._last_raw_transcript or text,
                        corrected_transcript=corrected_query
                    )
                except Exception as ce:
                    logger.debug(f"Correction recording error: {ce}")
            return self._process_single_command(
                corrected_query,
                raw_full_text=raw_full_text,
                speak=speak,
                utterance_id=uid,
                t0_start=t0_start,
                whisper_ms=whisper_ms,
                audio_dur_s=audio_dur_s
            )

        # Case 0C: Cancellation and Negation Safety Protection
        if req.intent in ["CANCELLATION", "NEGATION"]:
            if self.pending_intent:
                self.pending_intent = None
            if hasattr(self, "multi_step_planner") and self.multi_step_planner:
                self.multi_step_planner.cancel_active_task()
            if req.intent == "CANCELLATION":
                msg = "Action canceled. Standing by."
                self.response_manager.cancellation(msg, speak=speak)
            else:
                msg = "Understood. I will not perform that action."
                self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"intent:{req.intent.lower()}", "LOCAL EXECUTION", msg, "Speaking")
            return {"success": True, "action": req.action or "cancellation", "message": msg}

        # Case 1: Clarification Needed
        if req.intent == "CLARIFICATION_REQUIRED":
            clarification_msg = req.clarification_prompt or f"Could you please clarify what you mean by '{req.target}'?"
            from core.conversation_manager import PendingActionContext
            pending_ctx = PendingActionContext(
                original_request=raw_full_text,
                intent=req.action or "clarification",
                action=req.action,
                target=req.target,
                clarification_question=clarification_msg,
                clarification_type=req.entities.get("ambiguous_type", "generic") if req.entities else "generic",
                valid_options=["yes", "no", "cancel"]
            )
            self.conversation_manager.set_pending_action(pending_ctx)
            self.response_manager.conversation(clarification_msg, speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "clarify:request", "LOCAL EXECUTION", clarification_msg, "Speaking")
            return {"success": True, "action": "clarification", "message": clarification_msg}

        # Case 1B: Task Follow-up & Lifecycle Controls (Track C)
        if req.intent == "TASK_FOLLOWUP":
            action = req.action
            from core.agent.task_models import TaskStatus
            if action == "cancel":
                self.conversation_manager.clear_interrupted_state()
                res = self.multi_step_planner.cancel_active_task()
                msg = res.get("message", "Task cancelled.")
                self.pending_intent = None
                self.response_manager.cancellation(msg, speak=speak)
            elif action == "retry":
                res_task = self.multi_step_planner.retry_last_task()
                msg = res_task.execution_summary or "Retrying last task."
                if res_task.status == TaskStatus.COMPLETED:
                    self.response_manager.success(msg, spoken_text=msg, speak=speak)
                else:
                    self.response_manager.failure(msg, spoken_text=msg, speak=speak)
            elif action == "skip_step":
                res_task = self.multi_step_planner.skip_current_step()
                msg = res_task.execution_summary or "Skipped step and continued."
                self.response_manager.conversation(msg, speak=speak)
            elif action == "continue":
                if self.conversation_manager.has_interrupted_explanation():
                    msg, remaining = self.conversation_manager.resume_explanation()
                    logger.info(f"[EXPLANATION_RESUMED][{uid}] Resuming {len(remaining)} sentences: '{msg}'")
                    if speak and hasattr(self.tts_manager, "speak_sentences") and len(remaining) > 1:
                        self.tts_manager.speak_sentences(remaining, interrupt=True, job_id=uid)
                        self.response_manager.conversation(msg, speak=False)
                    else:
                        self.response_manager.conversation(msg, speak=speak)
                else:
                    res_task = self.multi_step_planner.continue_task(confirm=True)
                    msg = res_task.execution_summary or "Task resumed."
                    if res_task.status == TaskStatus.COMPLETED:
                        self.response_manager.success(msg, spoken_text=msg, speak=speak)
                    else:
                        self.response_manager.failure(msg, spoken_text=msg, speak=speak)
            elif action == "status":
                res = self.multi_step_planner.get_active_task_status()
                msg = res.get("message", "No active tasks.")
                self.response_manager.conversation(msg, speak=speak)
            elif action == "explain_failure":
                msg = self.multi_step_planner.explain_last_failure()
                self.response_manager.conversation(msg, speak=speak)
            elif action == "open_result":
                idx = (req.entities or {}).get("index", 0)
                res = self.multi_step_planner.open_search_result_followup(idx)
                msg = res.get("message", "Opened search result.")
                self.response_manager.conversation(msg, speak=speak)
            elif action == "switch_provider":
                res = self.multi_step_planner.switch_search_provider_followup(req.target)
                msg = res.get("message", f"Searched on {req.target.title()}.")
                self.response_manager.conversation(msg, speak=speak)
            elif action == "reopen_tab":
                res = self.multi_step_planner.reopen_last_tab_followup()
                msg = res.get("message", "Reopened recent tab.")
                self.response_manager.conversation(msg, speak=speak)
            else:
                msg = "Task follow-up completed."
                self.response_manager.conversation(msg, speak=speak)

            self._notify_pipeline_stage(raw_full_text, normalized_text, f"task:{action}", "MultiStepPlanner", msg, "Speaking")
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            return {"success": True, "action": f"task_followup_{action}", "message": msg}

        # Case 1C: Check Verified Learned Procedures First (Phases 3 & 5: Reuse verified procedures, skip unnecessary AI/Nemotron calls)
        from core.learning import procedure_learner
        learned_proc = procedure_learner.match_procedure(text, req.intent)
        if learned_proc:
            logger.info(f"[UTTERANCE {uid}][PROCEDURE_MATCH] Reusing verified procedure '{learned_proc['name']}' (confidence={learned_proc.get('confidence', 1.0):.2f})")
            proc_res = procedure_learner.execute_procedure(learned_proc, self.executor)
            summary = proc_res.get("message", "Procedure executed successfully.")
            if proc_res.get("success"):
                self.response_manager.success(summary, spoken_text=summary, speak=speak)
            else:
                self.response_manager.failure(summary, spoken_text=summary, speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"proc:{learned_proc['name']}", "ProcedureLearner", summary, "Speaking")
            self._update_status("STANDBY", uid)
            self._update_speech_text(summary)
            return {"success": proc_res.get("success", False), "action": f"learned_proc_{learned_proc['name']}", "message": summary}

        # Case 1D: Stage 4 Verified ALEE Skills (< 1ms Fast Trigger Matching)
        try:
            from core.evolution.skill_developer import skill_developer
            matched_skill = skill_developer.match_trigger(text)
            if matched_skill:
                logger.info(f"[UTTERANCE {uid}][SKILL_MATCH] Matched verified skill '{matched_skill['name']}'")
                skill_res = skill_developer.execute_skill(matched_skill, runtime=self, speak=speak)
                summary = skill_res.get("message", "Skill executed successfully.")
                if skill_res.get("success"):
                    self.response_manager.success(summary, spoken_text=summary, speak=speak)
                else:
                    self.response_manager.failure(summary, spoken_text=summary, speak=speak)
                self._notify_pipeline_stage(raw_full_text, normalized_text, f"skill:{matched_skill['name']}", "SkillDeveloper", summary, "Speaking")
                self._update_status("STANDBY", uid)
                self._update_speech_text(summary)
                return {"success": skill_res.get("success", False), "action": f"skill_{matched_skill['name']}", "message": summary}
        except Exception as se:
            logger.debug(f"[EVOLUTION] Skill trigger match notice: {se}")

        # Case 2: Layer 3 - Complex Reasoning / Agentic Multi-Step Task / Universal Research
        if req.layer == 3 or req.mode == MODE_REASONING:
            self._update_status("THINKING", uid)
            logger.info(f"[UTTERANCE {uid}][AGENTIC_REASONING] Processing Layer 3 request for: '{text}'")

            # Check if this is a Universal Research inquiry
            if req.intent == "UNIVERSAL_RESEARCH" or req.action in [
                "SHOPPING_RESEARCH", "PRODUCT_COMPARISON", "TECHNOLOGY_RESEARCH",
                "GAMING_RESEARCH", "PROGRAMMING_RESEARCH", "NEWS_RESEARCH",
                "DOCUMENT_RESEARCH", "LIVE_RESEARCH", "RESEARCH_FOLLOW_UP"
            ]:
                self._update_status("RESEARCH_PLANNING", uid)
                self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", "SANTRA Research Engine", "Formulating research plan...", "Planning", turn_id=uid)
                from core.research import research_manager

                def _on_stage(stage: str, desc: str):
                    self._update_status(stage, uid)
                    # Telemetry status update only - do NOT pass stage descriptions as the final conversational answer!
                    self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", f"RESEARCH [{stage}]", "", stage.title(), turn_id=uid)

                spoken_sentences = []
                stream_id = uid
                def _on_research_sentence_chunk(sentence: str):
                    if not speak or not sentence.strip():
                        return
                    clean_chunk = sanitize_speech_text(sentence)
                    if not clean_chunk:
                        return
                    spoken_sentences.append(clean_chunk)
                    if len(spoken_sentences) == 1:
                        self._update_status("STREAMING_RESPONSE", uid)
                    elif self.current_status not in ["SPEAKING", "STREAMING_RESPONSE"]:
                        self._update_status("SYNTHESIZING", uid)
                    self._update_speech_text(clean_chunk)
                    is_first = (len(spoken_sentences) == 1)
                    idx = len(spoken_sentences) - 1
                    if is_first:
                        self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", "NVIDIA NEMOTRON — SYNTHESIZING", clean_chunk, "Synthesizing", turn_id=uid)
                    self.tts_manager.enqueue_stream_sentence(
                        clean_chunk,
                        stream_job_id=stream_id,
                        sentence_index=idx,
                        interrupt=is_first
                    )

                res_res = research_manager.execute_research(
                    text,
                    on_stage_change=_on_stage,
                    on_sentence_chunk=_on_research_sentence_chunk if speak else None,
                    is_cancelled=_check_cancelled
                )
                if _check_cancelled() or res_res.get("status") == "CANCELLED":
                    logger.info(f"[UTTERANCE {uid}][RESEARCH] Research cancelled. Suppressing speech and memory save.")
                    self.tts_manager.interrupt(force=True)
                    self._update_status("STANDBY", uid)
                    return {"success": False, "action": "universal_research", "message": "Research cancelled.", "cancelled": True}
                answer = res_res.get("answer", "")
                if not answer or not answer.strip():
                    answer = "I completed research on your query, but could not extract sufficient verified findings to provide a complete answer."

                self.memory.add_interaction(text, answer)
                # Stage 2: ALEE Automatic Research Knowledge Capture
                try:
                    from core.evolution.knowledge_explorer import knowledge_explorer
                    knowledge_explorer.ingest_research_knowledge(
                        query=text,
                        answer=answer,
                        source_urls=[res_res.get("research_id", "")],
                        category="research"
                    )
                except Exception as rke:
                    logger.debug(f"[EVOLUTION] Research knowledge capture error: {rke}")

                # CRITICAL: Deliver the synthesized research answer to the UI conversation turn!
                self._notify_pipeline_stage(raw_full_text, normalized_text, f"research:{req.action}", "SANTRA Research Engine", answer, "Completed", turn_id=uid)
                self.response_manager.conversation(answer, speak=speak)
                self._update_status("COMPLETED", uid)
                self._update_speech_text(answer)
                time.sleep(0.1)
                self._update_status("STANDBY", uid)
                return {"success": True, "action": "universal_research", "message": answer, "research_id": res_res.get("research_id")}

            # Check if this is an explicit reasoning / coding prompt rather than desktop OS automation
            is_pure_reasoning = req.intent == "NEMOTRON_REASONING" or any(text.lower().startswith(p) for p in ["nvidia:", "nemotron:"])

            # First attempt structured multi-step plan for compound OS workflows if not pure reasoning
            task = None
            if not is_pure_reasoning:
                task = self.multi_step_planner.plan(text)
                # Only treat as multi-step desktop plan if there are actually executable desktop tool steps
                if task and task.steps and any(s.tool_name in ["open_app", "open_browser", "web_search", "youtube_search", "write_to_notepad", "open_search_result", "verify_page_loaded"] for s in task.steps):
                    pass
                else:
                    task = None

            if task and task.steps:
                from core.agent.task_models import TaskStatus
                logger.info(f"[UTTERANCE {uid}][MULTI_STEP_PLANNER] Executing planned task '{task.parsed_goal}' with {len(task.steps)} steps")
                exec_task = self.multi_step_planner.execute_task(
                    task,
                    on_step_start=lambda s: self._notify_pipeline_stage(raw_full_text, normalized_text, f"step_{s.step_index+1}:{s.tool_name}", "MultiStepPlanner", s.description, "Executing"),
                    on_step_complete=lambda s, r: self._notify_pipeline_stage(raw_full_text, normalized_text, f"step_{s.step_index+1}:{s.tool_name}", "MultiStepPlanner", r.get("message", ""), "Running")
                )
                summary = exec_task.execution_summary or self.multi_step_planner._generate_truthful_summary(exec_task)

                if exec_task.status == TaskStatus.AWAITING_CONFIRMATION:
                    curr_step = exec_task.steps[exec_task.current_step_index]
                    self.pending_intent = {
                        "task_id": exec_task.task_id,
                        "intent": "agent_task_step",
                        "action": curr_step.tool_name,
                        "message": f"Action requires confirmation: {curr_step.description}. Proceed?"
                    }
                    self.response_manager.warning(self.pending_intent["message"], speak=speak)
                    self._update_speech_text(f"Safety Warning: {self.pending_intent['message']}")
                    if self.on_permission_dialog_cb:
                        self._trigger_cb(self.on_permission_dialog_cb, curr_step.tool_name, self.pending_intent["message"])
                    return {"success": True, "action": "awaiting_confirmation", "message": self.pending_intent["message"]}

                self.memory.add_interaction(text, summary)
                if exec_task.status == TaskStatus.COMPLETED:
                    self.response_manager.success(summary, spoken_text=summary, speak=speak)
                    try:
                        from core.learning import procedure_learner
                        procedure_learner.learn_procedure(
                            name=task.parsed_goal or f"proc_{int(time.time())}",
                            intent=req.intent or "multi_step_workflow",
                            user_request=text,
                            steps=[{"tool": s.tool_name, "parameters": s.parameters, "description": s.description} for s in task.steps],
                            source="multi_step_planner"
                        )
                    except Exception as le:
                        logger.debug(f"Failed to auto-learn multi-step procedure: {le}")
                else:
                    self.response_manager.failure(summary, spoken_text=summary, speak=speak)

                self._notify_pipeline_stage(raw_full_text, normalized_text, f"agent:{task.parsed_goal}", "MultiStepPlanner", summary, "Speaking")
                self._update_status("STANDBY", uid)
                self._update_speech_text(summary)
                return {"success": exec_task.status == TaskStatus.COMPLETED, "action": "multi_step_task", "message": summary}

            # Fallback to AgentBrain ReAct loop
            t0_agent = time.time()
            agent_res = self.conversation_manager.agent.reason_and_execute(text, conversation_history=self.conversation_manager.history, is_cancelled=_check_cancelled)
            agent_ms = (time.time() - t0_agent) * 1000
            response_text = agent_res.get("text")
            if not response_text or not response_text.strip():
                response_text = "I was unable to retrieve a response because the AI provider returned an empty answer, sir."

            self.memory.add_interaction(text, response_text)
            self.response_manager.conversation(response_text, speak=speak)
            source_lbl = agent_res.get("source", "Santra ReAct Agent")
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"agent:{req.action}", f"AgentBrain ({source_lbl})", response_text, "Speaking")

            self._update_status("STANDBY", uid)
            self._update_speech_text(response_text)
            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms agent={agent_ms:.0f}ms total={total_ms:.0f}ms")
            return {"success": True, "action": "reasoning_agent", "message": response_text, "source": source_lbl}

        # Case 3: Conversational Greetings, Acknowledgments, Social Intelligence & Etiquette
        intent_lower = req.intent.lower()
        if intent_lower in [
            "greeting", "greeting_reflex", "social_greeting", "session_start", "thank_you", "goodbye", "help", "identity", 
            "social_humor", "social_personality", "social_chat", "about",
            "repeat_response", "acknowledgement", "affirmation", "negation", "how_are_you", "status_check"
        ]:
            from core.social_engine import social_engine
            if intent_lower in ["greeting", "greeting_reflex", "social_greeting"]:
                resp_text = get_greeting_reflex_response(normalized_text or raw_full_text)
                res = self.response_manager.conversation(resp_text, speak=speak)
                self._update_status("STANDBY", uid)
                self._update_speech_text(resp_text)
                self._notify_pipeline_stage(raw_full_text, normalized_text, "chat:greeting", "Reflex", resp_text, "Speaking", turn_id=uid)
                return {"success": True, "action": "greeting_reflex", "message": resp_text}
            elif intent_lower == "session_start":
                resp_text = "Ready and standing by, Sir. All systems are operational. What would you like to work on?"
                res = self.response_manager.conversation(resp_text, speak=speak)
                self.conversation_manager.update_context(action="session_start", target="session")
            elif intent_lower == "identity":
                sub_type = (req.entities or {}).get("sub_type") or req.target or "general"
                if sub_type == "creator_other_work":
                    from config import config
                    creator = getattr(config, "creator_name", "").strip()
                    if creator:
                        resp_text = f"I do not have access to an external portfolio for my developer, {creator}, beyond my own codebase, Sir."
                    else:
                        resp_text = "My developer information has not been configured in system settings, Sir, so I have no record of other projects."
                else:
                    resp_text = social_engine.get_identity_response(sub_type)
                res = self.response_manager.conversation(resp_text, speak=speak)
                self.conversation_manager.update_context(action="identity", target=sub_type)
            elif intent_lower == "social_humor":
                action = req.action or (req.entities or {}).get("action", "")
                cat = (req.entities or {}).get("category")
                target = (req.entities or {}).get("target") or req.target
                if action == "tell_joke":
                    resp_text = social_engine.get_joke(cat)
                elif action == "roast":
                    resp_text = social_engine.get_roast(target or "user")
                elif action == "fun_fact":
                    resp_text = social_engine.get_fun_fact(cat)
                elif action == "dramatic_intro":
                    resp_text = social_engine.get_dramatic_intro()
                elif action == "followup":
                    resp_text = social_engine.handle_followup(normalized_text) or social_engine.get_joke()
                else:
                    resp_text = social_engine.get_joke()
                res = self.response_manager.conversation(resp_text, speak=speak)
                self.conversation_manager.update_context(action="social_humor", target="humor")
            elif intent_lower == "social_personality":
                action = req.action or (req.entities or {}).get("action", "")
                if action == "set_tone":
                    tone = (req.entities or {}).get("tone") or req.target or "normal"
                    resp_text = social_engine.update_tone(tone)
                elif action == "set_length":
                    length = (req.entities or {}).get("length") or req.target or "normal"
                    resp_text = social_engine.update_response_length(length)
                elif action == "toggle_humor":
                    humor_flag = (req.entities or {}).get("humor", True)
                    resp_text = social_engine.toggle_humor(humor_flag)
                else:
                    resp_text = "Personality configuration updated, Sir."
                res = self.response_manager.conversation(resp_text, speak=speak)
                self.conversation_manager.update_context(action="social_personality", target="personality")
            elif intent_lower == "social_chat":
                sub_type = req.action or req.target or "general"
                resp_text = social_engine.get_casual_reply(sub_type)
                res = self.response_manager.conversation(resp_text, speak=speak)
                self.conversation_manager.update_context(action="social_chat", target=sub_type)
            elif intent_lower == "help":
                from core.capability_service import capability_service
                scope = (req.entities or {}).get("scope") or req.target or "overview"
                if req.action == "explain_capability":
                    resp_text = capability_service.explain_capability(normalized_text)
                    if scope == "youtube" or "youtube" in normalized_text:
                        self.conversation_manager.update_context(action="help", target="youtube")
                elif scope == "all" or req.action == "show_all_commands":
                    resp_text = capability_service.get_all_commands_reference()
                elif scope in ["browser", "filesystem", "applications", "system", "search", "developer", "content", "media", "custom", "social", "personality", "offline", "unavailable"]:
                    resp_text = capability_service.get_scoped_commands(scope)
                else:
                    resp_text = capability_service.get_help_overview()
                res = self.response_manager.conversation(resp_text, speak=speak)
            elif intent_lower == "repeat_response":
                res = self.response_manager.repeat_last_response(speak=speak)
                resp_text = res.get("text", "")
            else:
                resp_text = self.response_manager.local_engine.format_intent_response({"intent": intent_lower, "raw": normalized_text})
                res = self.response_manager.conversation(resp_text, speak=speak)

            self._notify_pipeline_stage(raw_full_text, normalized_text, f"{intent_lower}:respond", "LOCAL EXECUTION", resp_text, "Speaking")
            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms exec=0ms total={total_ms:.0f}ms")
            return {"success": True, "action": intent_lower, "message": resp_text}

        # Case 4: Layer 1 Fast Local & Layer 2 Deterministic Actions
        os_intents = [
            "open_app", "application.launch", "close_app", "minimize_app", "maximize_app", "window_control", "file_access",
            "screenshot", "system_control", "status_request", "system_action",
            "open_website", "history_query", "terminal_execute", "system_telemetry",
            "open_new_chrome_tab", "open_new_chrome_window",
            "project_control", "filesystem_control", "web_search",
            "time_query", "date_query", "math_calculation", "media_control", "spotify_control",
            "test_speech", "test_microphone",
            "browser_control", "browser_tab_control", "browser_action", "youtube_control", "content_generation",
            "local_search", "developer_workflow", "follow_up",
            "explain_tool_execution", "memory_control", "privacy_control",
            "command_management", "custom_command",
            "turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot",
            "workspace.launch", "workspace_control", "launch_workspace", "power_control", "power.scheme", "battery_info",
            "screen_analysis", "gui_type_text", "confirm_action", "cancel_action",
            "show_panel", "hide_panel",
            "fs_create_folder", "fs_create_file", "fs_list_directory", "fs_trash_item", "fs_read_file", "fs_modify_file",
            "open_in_ide", "open_with",
            "panel_visibility", "unsupported_capability", "invalid_command"
        ]

        if (intent_lower in os_intents or
            intent_lower.startswith("fs_") or
            intent_lower.startswith("application.") or
            intent_lower.startswith("desktop.") or
            intent_lower.startswith("desktop_interaction.") or
            intent_lower.startswith("screen.") or
            intent_lower.startswith("screen_understanding.") or
            intent_lower.startswith("files.") or
            intent_lower.startswith("file_management.") or
            intent_lower.startswith("ai.") or
            intent_lower.startswith("ai_management.") or
            intent_lower.startswith("virtual_lab.")):
            intent_node = dict(req.entities) if req.entities else {}
            intent_node.update({
                "intent": intent_lower,
                "action": req.action,
                "target": req.target,
                "confidence": req.confidence,
                "entities": req.entities,
                "raw": raw_full_text
            })
            t0_exec = time.time()
            exec_res = self._execute_intent(intent_node, confirm=False, speak=speak, utterance_id=uid)
            exec_ms = (time.time() - t0_exec) * 1000
            if exec_res.get("success"):
                self.conversation_manager.update_context(req.action, req.target)

            msg = exec_res.get("message", "Executed.")
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"{intent_lower}:{req.action}", "LOCAL EXECUTION", msg, "Speaking", turn_id=uid)

            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms exec={exec_ms:.0f}ms total={total_ms:.0f}ms")
            return exec_res
        else:
            # Case 5: Informational Questions & Conversation
            logger.info(f"[UTTERANCE {uid}] Query routed to ConversationManager.")
            self._update_status("WAITING_FOR_NVIDIA", uid)
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{req.action}", "NVIDIA NEMOTRON — REQUESTING", "Querying NVIDIA Nemotron...", "Processing", turn_id=uid)
            t0_conv = time.time()

            spoken_sentences = []
            stream_id = uid
            def _on_sentence_chunk(sentence: str):
                if not speak or not sentence.strip():
                    return
                clean_chunk = sanitize_speech_text(sentence)
                if not clean_chunk:
                    return
                spoken_sentences.append(clean_chunk)
                if len(spoken_sentences) == 1:
                    self._update_status("STREAMING_RESPONSE", uid)
                elif self.current_status not in ["SPEAKING", "STREAMING_RESPONSE"]:
                    self._update_status("SYNTHESIZING", uid)
                self._update_speech_text(clean_chunk)
                is_first = (len(spoken_sentences) == 1)
                idx = len(spoken_sentences) - 1
                if is_first:
                    self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{req.action}", "NVIDIA NEMOTRON — PROCESSING", clean_chunk, "Synthesizing", turn_id=uid)
                self.tts_manager.enqueue_stream_sentence(
                    clean_chunk,
                    stream_job_id=stream_id,
                    sentence_index=idx,
                    interrupt=is_first
                )

            try:
                if speak:
                    conv_res = self.conversation_manager.process_query(
                        text,
                        on_sentence=_on_sentence_chunk,
                        is_cancelled=_check_cancelled
                    )
                else:
                    conv_res = self.conversation_manager.process_query(text)
                conv_ms = (time.time() - t0_conv) * 1000

                # Check if cancelled during or after request
                if _check_cancelled() or (isinstance(conv_res, dict) and conv_res.get("cancelled")):
                    logger.info(f"[REQUEST_CANCELLED][{uid}] Utterance cancelled or superseded.")
                    self._update_status("CANCELLED", uid)
                    self._update_speech_text("Request cancelled.")
                    time.sleep(0.1)
                    self._update_status("STANDBY", uid)
                    return {"success": False, "action": "conversation", "message": "Request cancelled.", "source": "Cancelled"}

                response_text = conv_res.get("text", "") if isinstance(conv_res, dict) else ""
                err_code = getattr(self.conversation_manager.provider_manager, "get_last_error_code", lambda: None)()

                # Check if timed out
                if not response_text and err_code == "AI_PROVIDER_TIMEOUT":
                    timeout_msg = "The AI request timed out before receiving a response, Sir. Please try asking again."
                    logger.warning(f"[REQUEST_TIMED_OUT][{uid}] Nemotron request timed out after {conv_ms:.1f}ms.")
                    self._update_status("TIMED_OUT", uid)
                    self._update_speech_text(timeout_msg)
                    self.response_manager.conversation(timeout_msg, speak=speak)
                    self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{req.action}", "NVIDIA NEMOTRON — TIMED OUT", timeout_msg, "Timed Out", turn_id=uid)
                    time.sleep(0.3)
                    self._update_status("STANDBY", uid)
                    return {"success": False, "action": "conversation", "message": timeout_msg, "source": "Timed Out"}

                # Check general empty or failed response
                if not response_text:
                    if err_code == "CREDENTIALS_INVALID":
                        fail_msg = "Unable to authenticate with the AI provider, Sir. Please verify your NVIDIA API key."
                    elif err_code == "RATE_LIMITED":
                        fail_msg = "The AI provider is currently rate-limited, Sir. Please try again in a moment."
                    elif err_code == "NETWORK_ERROR":
                        fail_msg = "Unable to reach the NVIDIA NIM endpoint, Sir. Please check your internet connection."
                    else:
                        fail_msg = "I was unable to retrieve a response from the AI provider, Sir."
                    logger.warning(f"[REQUEST_FAILED][{uid}] Provider failed: {err_code}")
                    self._update_status("STANDBY", uid)
                    self._update_speech_text(fail_msg)
                    self.response_manager.conversation(fail_msg, speak=speak)
                    self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{req.action}", "NVIDIA NEMOTRON — FAILED", fail_msg, "Failed", turn_id=uid)
                    return {"success": False, "action": "conversation", "message": fail_msg, "source": "Failed"}

                self.memory.add_interaction(text, response_text)

                # Store structured explanation if response has multiple sentences and no parent explanation is paused
                has_parent = self.conversation_manager.has_interrupted_explanation()
                if not has_parent and response_text and ("." in response_text or "!" in response_text or "?" in response_text):
                    self.conversation_manager.set_active_explanation(
                        topic=req.target or text,
                        goal=text,
                        text=response_text
                    )

                # Deliver speech if not already streamed as sentence chunks
                if not spoken_sentences:
                    if not has_parent and speak and self.conversation_manager.explanation_state and len(self.conversation_manager.explanation_state.sentences) > 1:
                        self.tts_manager.speak_sentences(self.conversation_manager.explanation_state.sentences, interrupt=True)
                    else:
                        self.response_manager.conversation(response_text, speak=speak)

                stage_source = conv_res.get("source", "Conversation") if isinstance(conv_res, dict) else "Conversation"
                pipeline_status = "NVIDIA NEMOTRON — RESPONSE RECEIVED"
                self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{req.action}", pipeline_status, response_text, "Speaking", turn_id=uid)

                self._update_status("COMPLETED", uid)
                self._update_speech_text(response_text)
                time.sleep(0.05)
                self._update_status("STANDBY", uid)

                total_ms = (time.time() - (t0_start or t0_proc)) * 1000
                logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms conv={conv_ms:.0f}ms total={total_ms:.0f}ms")
                return {"success": True, "action": "conversation", "message": response_text, "source": stage_source}

            except Exception as e:
                logger.error(f"[CONVERSATION_EXCEPTION][{uid}] Error processing conversation turn: {e}", exc_info=True)
                err_msg = "An error occurred while processing the conversation request, Sir."
                self._update_status("STANDBY", uid)
                self._update_speech_text(err_msg)
                return {"success": False, "action": "conversation", "message": err_msg, "source": "Error"}

            finally:
                # Ensure runtime NEVER remains stuck in WAITING_FOR_NVIDIA
                with self._state_lock:
                    if self.current_status in ["WAITING_FOR_NVIDIA", "ROUTING", "VALIDATING_INPUT", "GENERATING_RESPONSE"]:
                        self.current_status = "STANDBY"
                        if self.on_status_change_cb:
                            self._trigger_cb(self.on_status_change_cb, "STANDBY")

    def _execute_intent(self, intent_node: dict, confirm: bool = False, speak: bool = True, utterance_id: Optional[str] = None) -> dict:
        global evolution_collector
        uid = utterance_id or uuid.uuid4().hex[:6].upper()
        self._update_status("EXECUTING", uid)
        intent = intent_node.get("intent", "").lower()
        action = intent_node.get("action") or intent

        # Handle Instant Fast-Path Greetings Directly in Runtime
        if intent in ["greeting", "greeting_reflex", "greet"] or action in ["greeting", "greeting_reflex", "greet"]:
            resp_text = get_greeting_reflex_response(intent_node.get("raw") or intent_node.get("target") or "")
            self.response_manager.conversation(resp_text, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(resp_text)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, "greeting_reflex", True, resp_text)
            self._notify_pipeline_stage("", "", "chat:greeting", "Reflex", resp_text, "Speaking")
            return {"success": True, "action": "greeting_reflex", "message": resp_text}

        # Handle Camera Subsystem Actions Directly
        if intent in ["turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot"]:
            if intent == "turn_on_camera":
                ok = self.camera_manager.acquire(reason="voice_cmd")
                msg = "Camera activated and vision perception online, Sir." if ok else "Camera hardware unavailable."
            elif intent == "turn_off_camera":
                self.camera_manager.force_stop()
                ok = True
                msg = "Camera deactivated and hardware released, Sir."
            elif intent == "start_hand_tracking":
                ok = self.camera_manager.acquire(reason="hand_tracking")
                msg = "Hand tracking and gesture recognition active, Sir." if ok else "Camera unavailable."
            elif intent == "stop_hand_tracking":
                self.camera_manager.release(reason="hand_tracking")
                ok = True
                msg = "Hand tracking deactivated, Sir."
            elif intent == "camera_snapshot":
                ok, path = self.camera_manager.capture_snapshot()
                msg = f"Photo captured to {path}, Sir." if ok else "Failed to capture photo."

            res = {"success": ok, "action": intent, "target": "camera", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, intent, ok, msg)
            self._notify_pipeline_stage("", "", f"camera:{intent}", "CameraManager", msg, "Speaking")
            return res

        # Handle Holographic HUD Panel Visibility Actions
        if intent in ["show_panel", "hide_panel", "panel_visibility"]:
            act = "show" if (intent == "show_panel" or action == "show_panel") else "hide"
            if self.panel_visibility_cb:
                self._trigger_cb(self.panel_visibility_cb, act)
            msg = "Holographic HUD online, Sir." if act == "show" else "Switching to stealth background mode, Sir."
            res = {"success": True, "action": intent, "target": "hud_panel", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, intent, True, msg)
            self._notify_pipeline_stage("", "", f"hud:{act}", "HUDController", msg, "Speaking")
            return res

        # Handle Screen Perception Actions Directly in Runtime
        if intent in ["screen_analysis", "screen.analyze", "screen_understanding.analyze"]:
            hud_was_active = False
            if hasattr(self, "panel_visibility_cb") and self.panel_visibility_cb:
                try:
                    self.panel_visibility_cb("hide")
                    hud_was_active = True
                    time.sleep(0.06)
                except Exception as hide_err:
                    logger.debug(f"[RUNTIME] Screen analysis HUD hide notice: {hide_err}")

            from modules.system.screen_perception import capture_screen_context
            ctx = capture_screen_context()

            if hud_was_active and hasattr(self, "panel_visibility_cb") and self.panel_visibility_cb:
                try:
                    self.panel_visibility_cb("show")
                except Exception:
                    pass

            active_win = ctx.get("active_window", "your active window")
            readable = ctx.get("readable_texts", [])
            clean_texts = []
            for it in readable:
                txt = (it.get("name") or "").strip()
                if txt and len(txt) > 1 and txt not in clean_texts:
                    clean_texts.append(txt)
            summary = "; ".join(clean_texts[:5]) if clean_texts else ctx.get("description", "No readable text detected.")
            spoken = f"Active window is {active_win}. Visible elements/text: {summary}."

            res = {"success": ctx.get("success", True), "action": "screen_analysis", "target": active_win, "message": spoken, "spoken": spoken, "context": ctx}
            self.response_manager.conversation(spoken, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(spoken)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, "screen_analysis", True, spoken)
            self._notify_pipeline_stage("", "", "screen:analyze", "ScreenPerception", spoken, "Speaking")
            try:
                from core.evolution.collector import evolution_collector
                if evolution_collector:
                    evolution_collector.record_experience(
                        user_request=intent_node.get("raw") or "analyze screen",
                        intent="SCREEN_ANALYSIS",
                        action="capture_screen_context",
                        parameters={"active_window": active_win},
                        success=True,
                        message=spoken
                    )
            except Exception:
                pass
            return res

        # Handle GUI Typing & Draft-and-Confirm Safety Gate Directly in Runtime
        if intent in ["gui_type_text", "desktop.enter_text", "desktop_interaction.type_text"]:
            from modules.system.gui_interactor import type_into_input_box
            text_val = intent_node.get("text") or intent_node.get("target") or intent_node.get("query") or ""
            submit_val = intent_node.get("submit", False)
            type_res = type_into_input_box(text=text_val, auto_locate=True, submit=submit_val, runtime=self)
            msg = type_res.get("message", "Text typed into input field.")
            is_ok = bool(type_res.get("success", False))
            res = {"success": is_ok, "action": "gui_type_text", "target": type_res.get("target_window"), "message": msg, "data": type_res}
            if is_ok:
                self.response_manager.conversation(msg, speak=speak)
            else:
                self.response_manager.failure(msg, spoken_text=msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, "gui_type_text", is_ok, msg)
            self._notify_pipeline_stage("", "", "gui:type_text", "GuiInteractor", msg, "Speaking")
            try:
                from core.evolution.collector import evolution_collector
                if evolution_collector:
                    evolution_collector.record_experience(
                        user_request=intent_node.get("raw") or f"type {text_val}",
                        intent="GUI_TYPE_TEXT",
                        action="type_into_input_box",
                        parameters={"text": text_val, "submit": submit_val},
                        success=is_ok,
                        message=msg
                    )
            except Exception:
                pass
            return res

        # Handle Confirmation and Cancellation of GUI Actions Directly in Runtime
        if intent in ["confirm_action", "gui_confirm_submit"]:
            from modules.system.gui_interactor import confirm_pending_gui_action
            ok = confirm_pending_gui_action(self)
            msg = "Confirmed and sent, Sir." if ok else "No pending action to confirm, Sir."
            res = {"success": ok, "action": "confirm_action", "target": "pending_action", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, "confirm_action", ok, msg)
            self._notify_pipeline_stage("", "", "gui:confirm", "GuiInteractor", msg, "Speaking")
            return res

        if intent in ["cancel_action", "gui_cancel_submit"]:
            from modules.system.gui_interactor import cancel_pending_gui_action
            ok = cancel_pending_gui_action(self)
            msg = "Action cancelled and draft discarded, Sir." if ok else "No pending action to cancel, Sir."
            res = {"success": ok, "action": "cancel_action", "target": "pending_action", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, "cancel_action", ok, msg)
            self._notify_pipeline_stage("", "", "gui:cancel", "GuiInteractor", msg, "Speaking")
            return res

        # Handle Filesystem CRUD Operations Directly in Runtime
        if intent.startswith("fs_"):
            from modules.system import filesystem_crud
            target_path = intent_node.get("path") or intent_node.get("target") or ""
            if intent == "fs_create_folder":
                fs_res = filesystem_crud.create_folder(target_path)
                if fs_res.get("success") and fs_res.get("path"):
                    self._last_filesystem_target = Path(fs_res["path"])
                    filesystem_crud.set_last_filesystem_target(self._last_filesystem_target)
            elif intent == "fs_create_file":
                content = intent_node.get("content", "")
                fs_res = filesystem_crud.create_file(target_path, content=content)
                if fs_res.get("success") and fs_res.get("path"):
                    self._last_filesystem_target = Path(fs_res["path"])
                    filesystem_crud.set_last_filesystem_target(self._last_filesystem_target)
            elif intent == "fs_list_directory":
                fs_res = filesystem_crud.list_directory(target_path if target_path != "current" else None)
            elif intent == "fs_trash_item":
                fs_res = filesystem_crud.trash_item(target_path, runtime=self)
                if fs_res.get("success"):
                    if self._last_filesystem_target and (
                        str(self._last_filesystem_target) == fs_res.get("path") or
                        str(target_path).lower() in ("it", "this", "that", "the folder", "the file")
                    ):
                        self._last_filesystem_target = None
                        filesystem_crud.set_last_filesystem_target(None)
            elif intent == "fs_read_file":
                fs_res = filesystem_crud.read_file(target_path)
            elif intent == "fs_modify_file":
                content = intent_node.get("content", "")
                mode = intent_node.get("mode", "append")
                fs_res = filesystem_crud.modify_file(target_path, content=content, mode=mode)
            else:
                fs_res = {"success": False, "message": f"Unknown filesystem operation '{intent}'."}

            msg = fs_res.get("message", "Filesystem operation completed.")
            res = {"success": fs_res.get("success", False), "action": intent, "target": target_path, "message": msg, "data": fs_res}
            if fs_res.get("success"):
                self.response_manager.success(msg, spoken_text=msg, speak=speak)
            else:
                self.response_manager.failure(msg, spoken_text=msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, intent, fs_res.get("success", False), msg)
            self._notify_pipeline_stage("", "", f"fs:{intent}", "FilesystemCrud", msg, "Speaking")
            try:
                from core.evolution.collector import evolution_collector
                if evolution_collector:
                    evolution_collector.record_experience(
                        user_request=intent_node.get("raw") or f"{intent} {target_path}",
                        intent=intent.upper(),
                        action=intent,
                        parameters={"path": target_path},
                        success=fs_res.get("success", False),
                        message=msg
                    )
            except Exception:
                pass
            return res

        # Handle Open in IDE (VSCode / Antigravity) with Entity Context Memory
        if intent in ["open_in_ide", "open_with"]:
            from modules.system import filesystem_crud
            ide = (intent_node.get("ide") or "vscode").lower().strip()
            ide_display = "VS Code" if ide in ["vscode", "code"] else ("Antigravity" if ide == "antigravity" else ide.title())
            target_str = intent_node.get("target")

            target_path = None
            if not target_str or target_str.lower() in ("it", "this", "that", "the folder", "the file", "the project", "vscode", "antigravity"):
                target_path = getattr(self, "_last_filesystem_target", None) or filesystem_crud.get_last_filesystem_target()
            else:
                target_path = filesystem_crud.find_or_resolve_target(target_str, runtime=self)

            if not target_path or not Path(target_path).exists():
                msg = f"I could not locate the target item to open in {ide_display}."
                res = {"success": False, "action": intent, "target": str(target_path) if target_path else "", "message": msg}
                self.response_manager.failure(msg, spoken_text=msg, speak=speak)
            else:
                import subprocess

                ide_bin = find_ide_executable(ide, fallback_to_active=False)
                # If requested IDE not found and it was generic vscode/code, check if Antigravity is active
                if not ide_bin and ide in ["vscode", "code"]:
                    alt_bin = find_ide_executable("antigravity", fallback_to_active=False)
                    if alt_bin:
                        ide_bin = alt_bin
                        ide_display = "Antigravity"

                if not ide_bin:
                    msg = f"Could not locate the executable for {ide_display} on your system PATH."
                    res = {"success": False, "action": intent, "target": str(target_path), "message": msg}
                    self.response_manager.failure(msg, spoken_text=msg, speak=speak)
                else:
                    target_abs = str(Path(target_path).resolve())
                    raw_name = Path(target_path).name
                    clean_name = re.sub(r"^(?:name|named|called)\s+", "", raw_name, flags=re.IGNORECASE).strip()
                    clean_name = re.sub(r"\s+(?:folder|directory|file)$", "", clean_name, flags=re.IGNORECASE).strip()
                    target_display = clean_name or raw_name or "project"

                    DETACHED_FLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                    try:
                        # Non-blocking detached process launch
                        subprocess.Popen([ide_bin, target_abs], creationflags=DETACHED_FLAGS, close_fds=True)
                        msg = f"Opened {target_display} in {ide_display}."
                        res = {"success": True, "action": intent, "target": target_abs, "message": msg}
                        self.response_manager.success(msg, spoken_text=msg, speak=speak)
                    except Exception as launch_err:
                        msg = f"Failed to open in {ide_display}: {launch_err}"
                        res = {"success": False, "action": intent, "target": target_abs, "message": msg}
                        self.response_manager.failure(msg, spoken_text=msg, speak=speak)

            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, intent, res.get("success", False), msg)
            self._notify_pipeline_stage("", "", f"ide:{intent}", "IDEBridge", msg, "Speaking")
            try:
                from core.evolution.collector import evolution_collector
                if evolution_collector:
                    evolution_collector.record_experience(
                        user_request=intent_node.get("raw") or f"open in {ide}",
                        intent="OPEN_IN_IDE",
                        action=intent,
                        parameters={"ide": ide, "target": str(target_path)},
                        success=res.get("success", False),
                        message=msg
                    )
            except Exception:
                pass
            return res

        # Handle Standby, Sleep & Listening Lifecycle Actions Directly in Runtime
        if action in ["enable_ai_mode", "disable_ai_mode"]:
            enabled = (action == "enable_ai_mode")
            msg = self.set_ai_mode(enabled)
            res = {"success": True, "action": action, "target": "ai_mode", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, True, msg)
            self._notify_pipeline_stage("", "", f"ai_mode:{action}", "LOCAL EXECUTION", msg, "Speaking")
            return res

        if action == "wake_acknowledgment":
            msg = "I'm listening, Sir. How can I help?"
            res = {"success": True, "action": "wake_acknowledgment", "target": "runtime", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, True, msg)
            self._notify_pipeline_stage("", "", f"runtime:{action}", "JarvisRuntime", msg, "Speaking")
            return res

        if action in ["enter_standby", "disable_listening", "enable_listening", "sleep_assistant", "enter_sleep", "sleep_mode"]:
            if action in ["sleep_assistant", "enter_sleep", "sleep_mode"]:
                self.enter_sleep_mode(reason="voice_command", speak=speak)
                msg = "Entering sleep mode, Sir. Say 'Santra' to wake me."
                res = {"success": True, "action": action, "target": "runtime", "message": msg}
                if self.on_action_complete_cb:
                    self._trigger_cb(self.on_action_complete_cb, action, True, msg)
                self._notify_pipeline_stage("", "", f"runtime:{action}", "JarvisRuntime", msg, "Speaking")
                return res
            elif action == "enter_standby":
                self.enter_standby(speak=speak)
                msg = "Entering standby mode, Sir. Say 'Hey Santra' or press Talk to activate me."
            elif action == "disable_listening":
                self.set_mute_state(True)
                msg = "Microphone muted. Hands-free listening disabled. Use the talk button to resume."
            elif action == "enable_listening":
                self.set_mute_state(False)
                msg = "Microphone active. Hands-free listening resumed."

            res = {"success": True, "action": action, "target": "runtime", "message": msg}
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, True, msg)
            self._notify_pipeline_stage("", "", f"runtime:{action}", "JarvisRuntime", msg, "Speaking")
            return res

        # Handle Virtual Testing Room / Capability Lab Launch
        if action == "open_virtual_lab" or intent == "virtual_lab.open":
            msg = "Opening the Santra Virtual Testing Room and Capability Evaluation Lab."
            res = {"success": True, "action": "open_virtual_lab", "target": "virtual_lab", "message": msg}
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, "open_virtual_lab", True, msg)
            if hasattr(self, "open_virtual_lab_cb") and self.open_virtual_lab_cb:
                self.open_virtual_lab_cb()
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            return res

        # 1. Missing argument check
        if intent_node.get("missing_arg"):
            missing_msg = self.response_registry.get_missing_arg_prompt(intent_node) or "What would you like me to do, Sir?"
            logger.info(f"[MISSING_ARG] Prompting: '{missing_msg}'")
            self.response_manager.missing_argument(missing_msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(missing_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, missing_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                "action": action,
                "message": missing_msg
            }

        # 2. Unsupported capability
        if intent == "unsupported_capability":
            unsupported_msg = self.response_registry.get_outcome_response(CommandOutcome.UNSUPPORTED_CAPABILITY)
            logger.info(f"[UNSUPPORTED] '{unsupported_msg}'")
            self.response_manager.unsupported_capability(unsupported_msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(unsupported_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, unsupported_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.UNSUPPORTED_CAPABILITY.value,
                "action": action,
                "message": unsupported_msg
            }

        # 3. Invalid command
        if intent == "invalid_command":
            invalid_msg = self.response_registry.get_outcome_response(CommandOutcome.INVALID_COMMAND)
            logger.info(f"[INVALID_COMMAND] '{invalid_msg}'")
            self.response_manager.invalid_command(invalid_msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(invalid_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, invalid_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.INVALID_COMMAND.value,
                "action": action,
                "message": invalid_msg
            }

        # 4. Acknowledgment only before long-running / multi-step operations
        # For immediate local operations (<150ms), produce one final response to prevent speech collisions
        if intent in ["content_generation", "multi_step_workflow"] or intent_node.get("is_long_running"):
            ack_msg = self.response_registry.get_acknowledgment(intent_node)
            if ack_msg and speak:
                logger.info(f"[ACKNOWLEDGMENT] Speaking: '{ack_msg}'")
                self.response_manager.acknowledge_command(ack_msg, speak=speak)

        trace = tracer.get_current_trace()
        t_tool_start = time.time()
        if trace:
            trace.record_timestamp("tool_start", t_tool_start)

        self._update_status("EXECUTING", uid)
        logger.info(f"[COMMAND_EXEC_START] uid={uid}, intent='{intent}', action='{action}'")
        result = self.executor.execute(intent_node, confirm=confirm)
        t_tool_end = time.time()
        logger.info(f"[COMMAND_EXEC_COMPLETE] uid={uid}, action='{action}', success={result.get('success', False)}, msg='{result.get('message', '')}'")

        if trace:
            trace.record_timestamp("tool_end", t_tool_end)
            category = "[EXTERNAL_API]" if intent in ["open_website", "web_search"] else "[OS]"
            trace.record_tool_execution(
                name=action,
                category=category,
                operation=action,
                duration_ms=(t_tool_end - t_tool_start) * 1000,
                success=result.get("success", False),
                error=result.get("message") if not result.get("success") else None
            )

        if result.get("requires_clarification") or result.get("requires_focus"):
            self.pending_intent = result.get("pending_intent")
            if self.pending_intent:
                self.pending_intent["timestamp"] = time.time()
                from core.conversation_manager import PendingActionContext
                pending_ctx = PendingActionContext(
                    original_request=self.pending_intent.get("original_request") or intent_node.get("raw", ""),
                    intent=self.pending_intent.get("intent", intent),
                    action=self.pending_intent.get("action", action),
                    target=self.pending_intent.get("target", intent_node.get("target", "")),
                    target_url=self.pending_intent.get("target_url") or intent_node.get("url"),
                    target_domain=self.pending_intent.get("target_domain") or intent_node.get("domain"),
                    browser=self.pending_intent.get("browser") or intent_node.get("browser", "chrome"),
                    search_query=self.pending_intent.get("search_query") or intent_node.get("query", ""),
                    clarification_question=result.get("message", ""),
                    clarification_type=self.pending_intent.get("clarification_type", "generic"),
                    valid_options=self.pending_intent.get("valid_options", [])
                )
                self.conversation_manager.set_pending_action(pending_ctx)
            self.response_manager.conversation(result["message"], speak=speak)
            self._update_speech_text(result["message"])
            self._update_status("STANDBY")
            self._active_utterance_id = None
            return result

        if result.get("pending_confirmation"):
            if result.get("is_conversational_confirmation") or result.get("intent") == "workspace_optional_confirmation":
                # Conversational confirmation (e.g. optional workspace app)
                # Store confirmation metadata with timestamp and association
                self.pending_intent = dict(result)
                self.pending_intent["timestamp"] = time.time()
                # Do NOT trigger security dialog modal, do NOT prefix with "Safety Warning:"
                self.response_manager.conversation(result["message"], speak=speak)
                self._update_speech_text(result["message"])
                self._update_status("STANDBY")
                self._active_utterance_id = None
                return result

            # Genuine Security Authorization Required (e.g. high-risk actions, deletion, shutdown, custom cmd)
            self.pending_intent = intent_node
            self.pending_intent["timestamp"] = time.time()
            self.response_manager.warning(result["message"], speak=speak)
            self._update_speech_text(f"Safety Warning: {result['message']}")
            if self.on_permission_dialog_cb:
                self._trigger_cb(self.on_permission_dialog_cb, result["action"], result["message"])
            return result

        self.pending_intent = None
        success = result.get("success", False)
        action = result.get("action", intent)
        message = result.get("message", "")
        raw_outcome = result.get("outcome")
        if raw_outcome:
            try:
                outcome = CommandOutcome(raw_outcome)
            except ValueError:
                outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED
        else:
            outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

        logger.info(f"[UTTERANCE {uid}][EXECUTOR_RESULT] Success={success} | Outcome={outcome.value} | Action='{action}' | Message='{message}'")

        if success:
            spoken = self.response_registry.get_success_response(intent_node, result)
            self.response_manager.success(message, spoken_text=spoken, speak=speak)
        else:
            spoken = self.response_registry.get_failure_response(intent_node, outcome, message)
            self.response_manager.failure(message, spoken_text=spoken, speak=speak)

        # Phase 2 & 3: Verification Engine & Experience Persistence
        try:
            from core.learning import verification_engine
            from memory.persistent_memory import persistent_memory

            verification = verification_engine.verify_action_outcome(action, intent_node, result)
            outcome_level_str = verification.get("outcome")
            if hasattr(outcome_level_str, "value"):
                outcome_level_str = outcome_level_str.value
            elif not outcome_level_str:
                outcome_level_str = "completed" if success else "failed"

            persistent_memory.record_execution_experience(
                user_request=intent_node.get("raw") or action,
                normalized_intent=intent,
                tool_or_procedure=action,
                execution_parameters=intent_node,
                execution_outcome=outcome_level_str,
                verification_evidence=verification.get("evidence"),
                observed_failure=verification.get("failure_reason") if not success else None,
                confidence=float(intent_node.get("confidence", 1.0))
            )
        except Exception as ve:
            logger.debug(f"Failed to verify/record execution experience: {ve}")

        # ALEE Stage 1: Async Non-Blocking Experience Ingestion
        if evolution_collector:
            try:
                exec_latency = (t_tool_end - t_tool_start) * 1000 if 't_tool_start' in locals() and 't_tool_end' in locals() else 0.0
                evolution_collector.record_experience(
                    user_request=intent_node.get("raw") or action,
                    intent=intent,
                    action=action,
                    parameters=intent_node,
                    success=success,
                    message=message,
                    latency_ms=exec_latency,
                    raw_transcript=getattr(self, "_last_raw_transcript", None) or intent_node.get("raw") or action
                )
            except Exception as ee:
                logger.debug(f"[EVOLUTION] Collector recording error: {ee}")

        self._update_status("STANDBY", uid)
        self._update_speech_text(spoken)

        if trace:
            trace.record_timestamp("response_ready", time.time())

        if self.on_action_complete_cb:
            self._trigger_cb(self.on_action_complete_cb, action, success, spoken)
        if self.on_history_update_cb:
            self._trigger_cb(self.on_history_update_cb, self.history_tracker.get_history())

        return {"success": success, "outcome": outcome.value, "action": action, "message": spoken}

    def _notify_pipeline_stage(self, raw, norm, intent_str, exec_str, resp_str, state, turn_id=None):
        if self.on_pipeline_stage_cb:
            self._trigger_cb(self.on_pipeline_stage_cb, raw, norm, intent_str, exec_str, resp_str, state, turn_id)

    # ==========================================
    # DUPLEX AUDIO & SPEAKER STATUS
    # ==========================================
    def _on_speaker_synthesizing(self):
        self._tts_speaking_lock = True
        self.listener.set_speaking_active(True)
        self._update_status("SYNTHESIZING")

    def _on_speaker_started(self):
        if self.current_status in ["SLEEPING", "STOPPED"]:
            logger.info(f"[TTS_LIFECYCLE] Suppressing speaker started status transition while in {self.current_status}.")
            return
        self._tts_speaking_lock = True
        self.listener.set_speaking_active(True)
        self._update_status("SPEAKING")
        logger.info("[TTS_LIFECYCLE] Speaking started. Listener VAD suppressed.")

    def _on_speaker_stopped(self):
        if self.current_status in ["SLEEPING", "STOPPED"]:
            return
        if not self.tts_manager.is_speaking():
            self._tts_speaking_lock = False
            self.listener.set_speaking_active(False)
            self._update_status("STANDBY")
            self._update_speech_text("Standby. Say 'Santra' or speak into microphone.")
            logger.info("[TTS_LIFECYCLE] Speaking finished. Listener VAD unsuppressed (cooldown=0.35s). Voice Core on Standby.")

    def toggle_mute(self):
        """Toggles the microphone mute state."""
        self.set_mute_state(not self.muted)

    def set_mute_state(self, muted: bool):
        self.muted = muted
        if muted:
            logger.info("Microphone muted. Halting listener and wakeword detector.")
            if hasattr(self, "wakeword_detector") and self.wakeword_detector:
                try:
                    self.wakeword_detector.stop()
                except Exception as we:
                    logger.debug(f"Error stopping wakeword detector on mute: {we}")
            self.listener.stop()
            self._update_status("STANDBY")
            self._update_speech_text("Microphone Muted (Privacy Mode Active)")
            self.tts_manager.speak("Systems muted. Privacy mode active.", interrupt=True)
        else:
            logger.info("Microphone active. Starting listener and wakeword detector.")
            self.listener.start(self._on_speech_start, self._on_speech_end)
            if hasattr(self, "wakeword_detector") and self.wakeword_detector:
                try:
                    self.wakeword_detector.start(self._on_wakeword)
                except Exception as we:
                    logger.debug(f"Error starting wakeword detector on unmute: {we}")
            self._update_status("STANDBY")
            self._update_speech_text("Standby. Say 'Santra' or speak into microphone.")
            self.tts_manager.speak("Systems active. Standing by.", interrupt=True)

    def enter_standby(self, speak: bool = True):
        """Returns Jarvis cleanly to standby mode, silencing TTS and resetting capture state."""
        logger.info("[STANDBY] Returning to standby mode.")
        if self._tts_speaking_lock or self.tts_manager.is_speaking():
            self.tts_manager.interrupt(force=True)
            self._tts_speaking_lock = False
            self.listener.set_speaking_active(False)
        self.pending_intent = None
        self._update_status("STANDBY")
        try:
            from core.system_resource_manager import system_resource_manager
            system_resource_manager.set_profile("STANDBY")
        except Exception:
            pass
        msg = "Standing by, Sir."
        self._update_speech_text(msg)
        if speak and not self.muted:
            self.tts_manager.speak(msg)

    def enter_sleep_mode(self, reason: str = "user_request", speak: bool = True) -> bool:
        """Enters low-resource Sleep Mode:
        - Halts ongoing TTS and clears pending operations safely.
        - Disables background VAD and full speech transcription.
        - Unloads heavy Whisper model from memory if configured to save RAM/VRAM.
        - Keeps single microphone stream alive feeding strictly the local wake-word detector.
        - Reduces telemetry sampling frequency to conserve battery and CPU.
        - Transitions authoritative state to SLEEPING and updates UI.
        """
        with self._state_lock:
            if self.current_status == "SLEEPING":
                logger.info("[SLEEP_MODE] Already in SLEEPING mode.")
                return True

        logger.info(f"[SLEEP_MODE] Entering Sleep Mode (reason='{reason}')...")

        # 1. Mark cancellation event and invalidate active utterances
        with self._cancelled_lock:
            self._sleep_cancel_event.set()
            if self._active_utterance_id:
                self._cancelled_utterance_ids.add(self._active_utterance_id)
                logger.info(f"[SLEEP_MODE] Active utterance {self._active_utterance_id} marked CANCELLED.")

        # 2. Put TTS manager into sleep mode (halts audio and invalidates queued generations)
        self.tts_manager.set_sleep_mode(True)
        self._tts_speaking_lock = False

        # 3. Cancel non-critical pending intents / tasks
        self.pending_intent = None
        if hasattr(self, "multi_step_planner"):
            try:
                self.multi_step_planner.cancel_active_task()
            except Exception as pe:
                logger.debug(f"Error cancelling active task on sleep: {pe}")

        # 4. Audio confirmation before going silent if speech enabled
        confirm_msg = "Entering sleep mode, Sir. Say 'Santra' to wake me."
        if speak and not self.muted:
            try:
                self.tts_manager.speak(confirm_msg, interrupt=True, job_id="sleep_confirm")
            except Exception as se:
                logger.debug(f"Error speaking sleep confirmation: {se}")

        # 4. Silence listener VAD and transcription pipeline
        self.listener.set_speaking_active(False)
        self.listener.set_sleep_mode(True)

        # 5. Sleep profile and idle model memory release
        try:
            from core.system_resource_manager import system_resource_manager
            system_resource_manager.set_profile("SLEEPING")
        except Exception:
            pass

        if getattr(config, "model_idle_timeout_sec", 600.0) > 0:
            try:
                self.transcriber.unload_model()
            except Exception as ue:
                logger.debug(f"Error unloading model on sleep: {ue}")

        # 6. Transition state to SLEEPING
        self._update_status("SLEEPING")
        self._update_speech_text("Sleep mode active. Say 'Santra' or click Wake to resume.")
        logger.info("[SLEEP_MODE] SANTRA is now SLEEPING. Listening strictly for wake phrase 'Santra'.")
        return True

    def wake_up(self, source: str = "voice", force: bool = False) -> bool:
        """Transitions JARVIS from SLEEPING to WAKING then ACTIVE/STANDBY/LISTENING.
        - Validates wake event (applies debounce).
        - Re-enables full listening and transcription pipeline.
        - Asynchronously pre-warms transcriber model in background.
        - Switches resource manager to ACTIVE profile.
        - Plays wake earcon chime or acknowledgment.
        - Preserves trailing command audio via listener pre-roll.
        """
        now = time.time()
        if not force and (now - getattr(self, "_last_wake_time", 0.0)) < 0.8:
            logger.debug("[WAKE_UP_DEBOUNCED] Ignoring rapid duplicate wake event (<0.8s).")
            return True
        self._last_wake_time = now

        logger.info(f"[WAKE_UP] Waking up JARVIS (source='{source}')...")

        # 1. Transition to WAKING
        self._update_status("WAKING")
        self._update_speech_text("Waking up...")

        with self._cancelled_lock:
            self._sleep_cancel_event.clear()
        self.tts_manager.set_sleep_mode(False)

        # 2. Restore normal listener pipeline
        self.listener.set_sleep_mode(False)

        # 3. Pre-warm transcriber model in background
        try:
            self.transcriber.preload_in_background()
        except Exception as pe:
            logger.debug(f"Transcriber prewarm on wake: {pe}")

        try:
            from core.system_resource_manager import system_resource_manager
            system_resource_manager.set_profile("ACTIVE")
        except Exception:
            pass

        # 4. Play instantaneous acoustic earcon chime with feedback suppression
        if hasattr(self.listener, "suppress_chime_feedback"):
            self.listener.suppress_chime_feedback(0.22)
        self.tts_manager.play_wake_chime()

        # 5. Transition to ACTIVE / LISTENING or STANDBY
        if source in ("voice", "wakeword", "voice_command"):
            utterance_id = uuid.uuid4().hex[:6].upper()
            self._active_utterance_id = utterance_id
            self._update_status("LISTENING", utterance_id)
            self._update_speech_text("Listening...")
            # Trigger capture preserving pre-roll so trailing command ("open Chrome") is captured!
            self.listener.trigger_manual_recording(manual=True)
        else:
            self._update_status("STANDBY")
            self._update_speech_text("Standby. Ready for commands, Sir.")

        logger.info(f"[WAKE_UP_COMPLETE] JARVIS is now awake and ready (source='{source}').")
        return True

    @property
    def is_hands_free_operational(self) -> bool:
        """Truthful diagnostic property indicating whether hands-free wake word detection
        is genuinely operational (not using mock, not disabled, and engine/mic available).
        """
        if self.muted:
            return False
        if not hasattr(self, "wakeword_detector") or self.wakeword_detector is None:
            return False
        from core.wakeword import MockWakeWordDetector
        if isinstance(self.wakeword_detector, MockWakeWordDetector):
            return False
        return self.wakeword_detector.is_available() and self.wakeword_detector.is_listening()

    def get_wake_word_diagnostics(self) -> dict:
        """Returns truthful diagnostics about the wake word and microphone subsystems."""
        from core.wakeword import MockWakeWordDetector
        engine_type = getattr(config, "wakeword_engine", "openwakeword")
        is_mock = isinstance(self.wakeword_detector, MockWakeWordDetector)
        det_available = self.wakeword_detector.is_available() if self.wakeword_detector else False
        det_listening = self.wakeword_detector.is_listening() if self.wakeword_detector else False
        operational = self.is_hands_free_operational

        diag_msg = self.wakeword_detector.get_diagnostic() if self.wakeword_detector else "Wake word detector not configured."
        if is_mock:
            diag_msg = "Mock wake-word detector active. Real hands-free activation is not operational (manual talk button or test triggers only)."

        return {
            "configured_engine": engine_type,
            "actual_detector_class": self.wakeword_detector.__class__.__name__ if self.wakeword_detector else "None",
            "is_mock": is_mock,
            "engine_available": det_available,
            "is_listening": det_listening,
            "hands_free_operational": operational,
            "is_muted": self.muted,
            "active_microphone": getattr(self.listener, "active_input_device_name", "Unknown"),
            "status_message": diag_msg
        }

    def get_audio_system_diagnostics(self) -> dict:
        """Comprehensive truthful diagnostic report for microphone, wake-word, STT, and TTS subsystems."""
        from core.wakeword import MockWakeWordDetector

        # 1. Microphone & Stream
        mic_listening = self.listener.is_listening() if hasattr(self, "listener") and self.listener else False
        mic_recording = self.listener.is_recording() if hasattr(self, "listener") and self.listener else False
        mic_device = getattr(self.listener, "active_input_device_name", "Unknown Microphone")
        mic_index = getattr(self.listener, "active_input_device_index", None)
        sample_rate = getattr(self.listener, "sample_rate", 16000)

        # 2. Wake-word Engine
        ww_engine = getattr(config, "wakeword_engine", "openwakeword")
        ww_class = self.wakeword_detector.__class__.__name__ if self.wakeword_detector else "None"
        ww_available = self.wakeword_detector.is_available() if self.wakeword_detector else False
        ww_listening = self.wakeword_detector.is_listening() if self.wakeword_detector else False
        raw_phrases = getattr(self.wakeword_detector, "wake_words", None)
        default_phrases = getattr(config, "wake_words", ["santra", "hey santra", "jarvis", "hey jarvis"])
        ww_phrases = list(raw_phrases) if isinstance(raw_phrases, (list, tuple)) else list(default_phrases)
        ww_thresh = getattr(self.wakeword_detector, "sensitivity", 0.45)
        is_mock_ww = isinstance(self.wakeword_detector, MockWakeWordDetector)

        # 3. Stream Sharing / Audio Consumer
        consumers_count = len(getattr(self.listener, "_audio_consumers", []))

        # 4. Speech-to-Text (STT)
        stt_status = getattr(self.transcriber, "status", "UNKNOWN")
        stt_model = getattr(self.transcriber, "model_size", "base.en")
        stt_device = getattr(self.transcriber, "device", "cpu")

        # 5. Text-to-Speech (TTS)
        tts_provider = self.tts_manager.primary_provider.get_name() if hasattr(self.tts_manager, "primary_provider") and self.tts_manager.primary_provider else "edge"
        tts_speaking = self.tts_manager.is_speaking()
        tts_queue_size = self.tts_manager.get_queue_size()

        # 6. Manual Talk readiness
        manual_talk_ready = mic_listening and not self.muted

        # Diagnostics summary message
        if self.muted:
            summary = "Microphone muted (Privacy Mode active). Voice activation disabled."
        elif not mic_listening:
            summary = f"Microphone stream inactive on [{mic_index}] '{mic_device}'."
        elif is_mock_ww:
            summary = "Mock wake-word active (Manual Talk ready, hands-free simulated)."
        elif not ww_available:
            summary = f"Wake-word engine unavailable ({self.wakeword_detector.get_diagnostic() if self.wakeword_detector else 'N/A'}). Manual Talk active."
        else:
            summary = f"Audio pipeline fully operational on [{mic_index}] '{mic_device}'. Primary wake phrase: 'Santra' (Threshold: {ww_thresh})."

        return {
            "summary": summary,
            "microphone": {
                "device_name": mic_device,
                "device_index": mic_index,
                "is_listening": mic_listening,
                "is_recording": mic_recording,
                "sample_rate_hz": sample_rate,
                "channels": 1,
                "blocksize": 2048,
                "is_muted": self.muted
            },
            "wakeword": {
                "engine_configured": ww_engine,
                "detector_class": ww_class,
                "is_mock": is_mock_ww,
                "is_available": ww_available,
                "is_listening": ww_listening,
                "supported_phrases": ww_phrases,
                "detection_threshold": ww_thresh,
                "shared_consumer_registered": consumers_count > 0,
                "hands_free_operational": self.is_hands_free_operational
            },
            "manual_talk": {
                "ready": manual_talk_ready,
                "active_status": self.current_status,
                "toggle_stop_supported": True
            },
            "stt": {
                "backend": "faster-whisper",
                "status": stt_status,
                "model_size": stt_model,
                "device": stt_device
            },
            "tts": {
                "active_provider": tts_provider,
                "is_speaking": tts_speaking,
                "queue_size": tts_queue_size
            }
        }

