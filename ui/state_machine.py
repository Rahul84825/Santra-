"""
Jarvis UI Visual State Machine.
Defines UI visual states, theme mappings, and reactive visual parameters.
"""

from enum import Enum
from dataclasses import dataclass
from PyQt6.QtGui import QColor
from ui.theme import HUDColors

class SantraRuntimeState(str, Enum):
    """Authoritative Runtime States for SANTRA."""
    INITIALIZING = "INITIALIZING"
    STANDBY = "STANDBY"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    VALIDATING_INPUT = "VALIDATING_INPUT"
    ROUTING = "ROUTING"
    WAITING_FOR_NVIDIA = "WAITING_FOR_NVIDIA"
    GENERATING_RESPONSE = "GENERATING_RESPONSE"
    STREAMING_RESPONSE = "STREAMING_RESPONSE"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    SLEEPING = "SLEEPING"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"
    SHUTTING_DOWN = "SHUTTING_DOWN"

class JarvisUIState(str, Enum):
    OFFLINE = "OFFLINE"
    BOOT = "BOOT"
    INITIALIZING = "INITIALIZING"
    STANDBY = "STANDBY"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    VALIDATING_INPUT = "VALIDATING_INPUT"
    ROUTING = "ROUTING"
    WAITING_FOR_NVIDIA = "WAITING_FOR_NVIDIA"
    GENERATING_RESPONSE = "GENERATING_RESPONSE"
    STREAMING_RESPONSE = "STREAMING_RESPONSE"
    UNDERSTANDING = "UNDERSTANDING"
    PROCESSING = "PROCESSING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    SLEEPING = "SLEEPING"
    WAKING = "WAKING"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"
    SHUTTING_DOWN = "SHUTTING_DOWN"

@dataclass
class StateVisualConfig:
    title: str
    subtext: str
    primary_color: QColor
    glow_color: QColor
    rotation_speed: float  # Degrees per frame
    pulse_freq: float      # Core breathing rate
    particle_speed: float  # Particle velocity multiplier

STATE_CONFIGS = {
    JarvisUIState.OFFLINE: StateVisualConfig(
        title="SYSTEM OFFLINE",
        subtext="DISCONNECTED",
        primary_color=HUDColors.TEXT_MUTED,
        glow_color=HUDColors.BORDER_MUTED,
        rotation_speed=0.2,
        pulse_freq=0.02,
        particle_speed=0.3
    ),
    JarvisUIState.BOOT: StateVisualConfig(
        title="INITIALIZING SYSTEM",
        subtext="VERIFYING SUBSYSTEMS",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=1.8,
        pulse_freq=0.08,
        particle_speed=1.5
    ),
    JarvisUIState.STANDBY: StateVisualConfig(
        title="STANDBY",
        subtext="READY - SAY 'SANTRA' TO ACTIVATE",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=0.5,
        pulse_freq=0.03,
        particle_speed=0.6
    ),
    JarvisUIState.LISTENING: StateVisualConfig(
        title="LISTENING",
        subtext="CAPTURING VOICE STREAM",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=QColor(0, 240, 255, 120),
        rotation_speed=1.4,
        pulse_freq=0.09,
        particle_speed=1.8
    ),
    JarvisUIState.TRANSCRIBING: StateVisualConfig(
        title="TRANSCRIBING",
        subtext="PROCESSING NEURAL SPEECH",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=2.0,
        pulse_freq=0.10,
        particle_speed=2.0
    ),
    JarvisUIState.VALIDATING_INPUT: StateVisualConfig(
        title="VALIDATING INPUT",
        subtext="CHECKING SPEECH INTEGRITY",
        primary_color=HUDColors.AMBER_STANDBY,
        glow_color=HUDColors.AMBER_GLOW,
        rotation_speed=2.1,
        pulse_freq=0.11,
        particle_speed=2.1
    ),
    JarvisUIState.ROUTING: StateVisualConfig(
        title="ROUTING",
        subtext="INTELLIGENCE LAYER SELECTION",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=2.3,
        pulse_freq=0.12,
        particle_speed=2.2
    ),
    JarvisUIState.WAITING_FOR_NVIDIA: StateVisualConfig(
        title="WAITING FOR NVIDIA",
        subtext="AWAITING NEMOTRON FIRST TOKEN",
        primary_color=HUDColors.VIOLET_THINKING,
        glow_color=HUDColors.VIOLET_GLOW,
        rotation_speed=2.6,
        pulse_freq=0.13,
        particle_speed=2.4
    ),
    JarvisUIState.GENERATING_RESPONSE: StateVisualConfig(
        title="GENERATING RESPONSE",
        subtext="NVIDIA NEMOTRON REASONING",
        primary_color=HUDColors.VIOLET_THINKING,
        glow_color=HUDColors.VIOLET_GLOW,
        rotation_speed=2.8,
        pulse_freq=0.14,
        particle_speed=2.5
    ),
    JarvisUIState.STREAMING_RESPONSE: StateVisualConfig(
        title="STREAMING RESPONSE",
        subtext="STREAMING NEURAL RESPONSE",
        primary_color=HUDColors.TEAL_SPEAKING,
        glow_color=HUDColors.TEAL_GLOW,
        rotation_speed=2.5,
        pulse_freq=0.13,
        particle_speed=2.3
    ),
    JarvisUIState.UNDERSTANDING: StateVisualConfig(
        title="UNDERSTANDING",
        subtext="RESOLVING INTENT",
        primary_color=HUDColors.AMBER_STANDBY,
        glow_color=HUDColors.AMBER_GLOW,
        rotation_speed=2.2,
        pulse_freq=0.12,
        particle_speed=2.2
    ),
    JarvisUIState.PROCESSING: StateVisualConfig(
        title="PROCESSING",
        subtext="RESOLVING REQUEST",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=2.4,
        pulse_freq=0.12,
        particle_speed=2.2
    ),
    JarvisUIState.THINKING: StateVisualConfig(
        title="REASONING",
        subtext="AGENTIC COGNITION ONLINE",
        primary_color=HUDColors.VIOLET_THINKING,
        glow_color=HUDColors.VIOLET_GLOW,
        rotation_speed=2.8,
        pulse_freq=0.14,
        particle_speed=2.5
    ),
    JarvisUIState.EXECUTING: StateVisualConfig(
        title="EXECUTING",
        subtext="DISPATCHING TOOL ACTION",
        primary_color=HUDColors.AMBER_STANDBY,
        glow_color=HUDColors.AMBER_GLOW,
        rotation_speed=3.2,
        pulse_freq=0.15,
        particle_speed=3.0
    ),
    JarvisUIState.SPEAKING: StateVisualConfig(
        title="RESPONDING",
        subtext="NEURAL VOICE SYNTHESIS",
        primary_color=HUDColors.TEAL_SPEAKING,
        glow_color=HUDColors.TEAL_GLOW,
        rotation_speed=1.6,
        pulse_freq=0.12,
        particle_speed=1.6
    ),
    JarvisUIState.COMPLETED: StateVisualConfig(
        title="COMPLETED",
        subtext="ACTION COMPLETED",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=0.8,
        pulse_freq=0.04,
        particle_speed=0.8
    ),
    JarvisUIState.CANCELLED: StateVisualConfig(
        title="CANCELLED",
        subtext="OPERATION CANCELLED",
        primary_color=HUDColors.AMBER_STANDBY,
        glow_color=HUDColors.AMBER_GLOW,
        rotation_speed=0.4,
        pulse_freq=0.03,
        particle_speed=0.4
    ),
    JarvisUIState.TIMED_OUT: StateVisualConfig(
        title="TIMED OUT",
        subtext="PROVIDER DEADLINE EXPIRED",
        primary_color=HUDColors.CRIMSON_ERROR,
        glow_color=HUDColors.CRIMSON_GLOW,
        rotation_speed=0.5,
        pulse_freq=0.05,
        particle_speed=0.5
    ),
    JarvisUIState.SLEEPING: StateVisualConfig(
        title="SYSTEM SLEEPING",
        subtext="LOW-POWER IDLE - SAY 'SANTRA' OR CLICK WAKE",
        primary_color=QColor(70, 120, 210),
        glow_color=QColor(30, 70, 160, 90),
        rotation_speed=0.15,
        pulse_freq=0.015,
        particle_speed=0.2
    ),
    JarvisUIState.WAKING: StateVisualConfig(
        title="WAKING UP",
        subtext="RESTORING VOICE PIPELINE",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=2.2,
        pulse_freq=0.12,
        particle_speed=2.0
    ),
    JarvisUIState.RECOVERING: StateVisualConfig(
        title="RECOVERING",
        subtext="RESTORING AUDIO PIPELINE",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=2.2,
        pulse_freq=0.12,
        particle_speed=2.0
    ),
    JarvisUIState.INITIALIZING: StateVisualConfig(
        title="INITIALIZING SYSTEM",
        subtext="VERIFYING SUBSYSTEMS",
        primary_color=HUDColors.CYAN_PRIMARY,
        glow_color=HUDColors.CYAN_GLOW,
        rotation_speed=1.8,
        pulse_freq=0.08,
        particle_speed=1.5
    ),
    JarvisUIState.SHUTTING_DOWN: StateVisualConfig(
        title="SHUTTING DOWN",
        subtext="TERMINATING SUBSYSTEMS",
        primary_color=HUDColors.TEXT_MUTED,
        glow_color=HUDColors.BORDER_MUTED,
        rotation_speed=0.2,
        pulse_freq=0.02,
        particle_speed=0.3
    ),
    JarvisUIState.ERROR: StateVisualConfig(
        title="SYSTEM ALERT",
        subtext="ACTION FAILED / RECOVERING",
        primary_color=HUDColors.CRIMSON_ERROR,
        glow_color=HUDColors.CRIMSON_GLOW,
        rotation_speed=0.6,
        pulse_freq=0.06,
        particle_speed=0.5
    ),
}

def map_runtime_status_to_ui_state(status: str) -> JarvisUIState:
    """Maps runtime status strings from core to authoritative JarvisUIState."""
    s = (status or "").upper().strip()
    if "SLEEP" in s:
        return JarvisUIState.SLEEPING
    if "RECOVER" in s:
        return JarvisUIState.RECOVERING
    if "WAK" in s:
        return JarvisUIState.WAKING
    if "LISTEN" in s:
        return JarvisUIState.LISTENING
    if "TRANSCRIB" in s:
        return JarvisUIState.TRANSCRIBING
    if "VALIDAT" in s:
        return JarvisUIState.VALIDATING_INPUT
    if "ROUT" in s:
        return JarvisUIState.ROUTING
    if "WAIT" in s and ("NVIDIA" in s or "NEMOTRON" in s or "PROVIDER" in s):
        return JarvisUIState.WAITING_FOR_NVIDIA
    if "STREAM" in s:
        return JarvisUIState.STREAMING_RESPONSE
    if "GENERAT" in s:
        return JarvisUIState.GENERATING_RESPONSE
    if "TIMED" in s or "TIMEOUT" in s:
        return JarvisUIState.TIMED_OUT
    if "CANCEL" in s:
        return JarvisUIState.CANCELLED
    if "COMPLETE" in s:
        return JarvisUIState.COMPLETED
    if "THINK" in s or "REASON" in s or "SYNTH" in s:
        return JarvisUIState.THINKING
    if "PROCESS" in s:
        return JarvisUIState.PROCESSING
    if "EXEC" in s or "TOOL" in s or "ACTION" in s:
        return JarvisUIState.EXECUTING
    if "SPEAK" in s or "VOICE" in s:
        return JarvisUIState.SPEAKING
    if "ERR" in s or "FAIL" in s:
        return JarvisUIState.ERROR
    if "INIT" in s or "BOOT" in s:
        return JarvisUIState.INITIALIZING
    if "SHUT" in s or "STOP" in s or "OFFLINE" in s:
        return JarvisUIState.SHUTTING_DOWN
    return JarvisUIState.STANDBY
