"""Central Holographic Arc Reactor HUD Widget for SANTRA.

Implements high-fidelity, hardware-accelerated vector graphics via PyQt6 QPainter:
- Concentric rotating segmented rings and tick reticles
- Audio-reactive pulsing plasma core (0.0 to 1.0 amplitude tracking)
- Multi-state visual transitions:
    STANDBY: Gentle slow cyan pulsation (0.5 Hz)
    LISTENING: Expanding responsive ripple rings
    THINKING / ROUTING: Rapid counter-rotating segmented dials & particle shimmer
    SPEAKING: Vibrant synchronized waveform waves radiating outwards
    PAUSED_GAMING / PAUSED_HIGH_LOAD: Soft solar amber halo
- Smooth 60 FPS animation powered by a single non-blocking QTimer (0 MB VRAM)
"""

import math
import random
from typing import List, Optional
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QRadialGradient, QLinearGradient
)
from PyQt6.QtWidgets import QWidget

from ui.state_machine import JarvisUIState, STATE_CONFIGS, StateVisualConfig


class Particle:
    """Floating energy particle radiating around the reactor."""
    __slots__ = ("x", "y", "angle", "dist", "speed", "size", "alpha", "max_dist")

    def __init__(self, base_radius: float):
        self.angle = random.uniform(0, math.tau)
        self.dist = random.uniform(base_radius * 0.4, base_radius * 1.1)
        self.max_dist = base_radius * 1.25
        self.speed = random.uniform(0.3, 1.2)
        self.size = random.uniform(1.2, 2.6)
        self.alpha = random.uniform(40, 200)
        self.x = 0.0
        self.y = 0.0

    def update(self, cx: float, cy: float, speed_mult: float):
        self.dist += self.speed * speed_mult
        if self.dist > self.max_dist:
            self.dist = random.uniform(self.max_dist * 0.35, self.max_dist * 0.6)
            self.alpha = random.uniform(60, 220)
        self.angle = (self.angle + 0.01 * speed_mult) % math.tau
        self.x = cx + self.dist * math.cos(self.angle)
        self.y = cy + self.dist * math.sin(self.angle)


class ArcReactorWidget(QWidget):
    """Futuristic JARVIS / F.R.I.D.A.Y. Holographic Arc Reactor Core."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)

        self._state_str = "STANDBY"
        self._state = JarvisUIState.STANDBY
        self._config = STATE_CONFIGS.get(self._state, STATE_CONFIGS[JarvisUIState.STANDBY])

        # Animation state variables
        self._angle_outer = 0.0
        self._angle_inner = 0.0
        self._angle_ticks = 0.0
        self._pulse_phase = 0.0
        self._core_scale = 1.0
        self._target_core_scale = 1.0
        self._audio_amplitude = 0.0

        # Ripple rings for LISTENING / SPEAKING
        self._ripple_radius_1 = 0.0
        self._ripple_radius_2 = 0.0
        self._ripple_radius_3 = 0.0

        # Energy particles
        self._particles: List[Particle] = [Particle(base_radius=90.0) for _ in range(36)]

        # 60 FPS Render Timer (~16.6ms)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_frame)
        self._timer.start(16)

    def set_state(self, state):
        """Sets the active UI state (accepts JarvisUIState or string)."""
        if isinstance(state, str):
            st_upper = state.upper()
            self._state_str = st_upper
            if "PAUSED" in st_upper:
                self._state = JarvisUIState.STANDBY
            elif "LISTEN" in st_upper:
                self._state = JarvisUIState.LISTENING
            elif "THINK" in st_upper or "ROUT" in st_upper or "PROCESS" in st_upper:
                self._state = JarvisUIState.THINKING
            elif "SPEAK" in st_upper or "SYNTH" in st_upper:
                self._state = JarvisUIState.SPEAKING
            elif "SLEEP" in st_upper:
                self._state = JarvisUIState.SLEEPING
            else:
                self._state = JarvisUIState.STANDBY
        elif isinstance(state, JarvisUIState):
            self._state = state
            self._state_str = state.name
        else:
            self._state = JarvisUIState.STANDBY
            self._state_str = "STANDBY"

        self._config = STATE_CONFIGS.get(self._state, STATE_CONFIGS[JarvisUIState.STANDBY])
        self.update()

    def set_audio_amplitude(self, amp: float):
        """Modulates core scale and ripples based on live voice audio chunk amplitude (0.0 to 1.0)."""
        clamped = max(0.0, min(1.0, float(amp)))
        self._audio_amplitude = clamped
        self._target_core_scale = 1.0 + clamped * 0.45

    def get_primary_color(self) -> QColor:
        """Returns the primary holographic QColor for the current state."""
        if "PAUSED" in self._state_str:
            return QColor(255, 170, 0)
        elif self._state == JarvisUIState.LISTENING:
            return QColor(0, 240, 255)
        elif self._state == JarvisUIState.SPEAKING:
            return QColor(0, 229, 255)
        elif self._state == JarvisUIState.THINKING:
            return QColor(245, 158, 11)
        elif self._state == JarvisUIState.SLEEPING:
            return QColor(139, 92, 246)
        else:
            return QColor(0, 229, 255)

    def trigger_gesture_pulse(self, gesture_name: str = "PULSE"):
        """Triggers a transient reactive flare when a gesture is recognized."""
        g = (gesture_name or "PULSE").upper()
        if "PINCH" in g:
            self._target_core_scale = 1.40
        elif "POINT" in g:
            self._angle_outer = (self._angle_outer + 35.0) % 360.0
            self._target_core_scale = 1.25
        elif "OPEN_PALM" in g:
            self._target_core_scale = 1.35
        else:
            self._target_core_scale = 1.35
        self.update()

    def _animate_frame(self):
        """Advances rotation angles, particle coordinates, and breathing scales at 60 FPS."""
        speed = self._config.rotation_speed
        is_paused = "PAUSED" in self._state_str

        # Speed overrides based on state
        if is_paused:
            rot_mult = 0.25
        elif self._state == JarvisUIState.THINKING:
            rot_mult = 3.2
        elif self._state == JarvisUIState.SPEAKING:
            rot_mult = 1.6
        elif self._state == JarvisUIState.LISTENING:
            rot_mult = 1.2
        else:
            rot_mult = 1.0

        self._angle_outer = (self._angle_outer + 0.65 * speed * rot_mult) % 360.0
        self._angle_inner = (self._angle_inner - 1.10 * speed * rot_mult) % 360.0
        self._angle_ticks = (self._angle_ticks + 0.40 * speed * rot_mult) % 360.0

        # Pulse breathing
        pulse_freq = 0.035 if is_paused else self._config.pulse_freq
        self._pulse_phase = (self._pulse_phase + pulse_freq) % math.tau

        # Smooth core scale dampening
        self._core_scale += (self._target_core_scale - self._core_scale) * 0.18
        if self._target_core_scale > 1.0:
            self._target_core_scale = max(1.0, self._target_core_scale - 0.02)

        # Ripple waves animation
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        max_r = min(cx, cy) - 10.0

        self._ripple_radius_1 = (self._ripple_radius_1 + 1.2) % max_r
        self._ripple_radius_2 = (self._ripple_radius_2 + 1.2) % max_r
        self._ripple_radius_3 = (self._ripple_radius_3 + 1.2) % max_r

        # Particle updates
        p_speed = 0.2 if is_paused else (self._config.particle_speed * rot_mult)
        for p in self._particles:
            p.update(cx, cy, p_speed)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        max_r = min(cx, cy) - 10.0

        if max_r < 25:
            return

        is_paused = "PAUSED" in self._state_str

        # Primary Hologram Colors
        if is_paused:
            # Solar Amber Halo (#ffaa00)
            primary_col = QColor(255, 170, 0)
        elif self._state == JarvisUIState.LISTENING:
            # Cyber Cyan Active
            primary_col = QColor(0, 240, 255)
        elif self._state == JarvisUIState.SPEAKING:
            # Radiant Emerald / Hologram Blue Wave
            primary_col = QColor(0, 229, 255)
        elif self._state == JarvisUIState.THINKING:
            # Solar Amber / Violet Thought
            primary_col = QColor(255, 185, 30)
        elif self._state == JarvisUIState.SLEEPING:
            primary_col = QColor(139, 92, 246)
        else:
            # Standby / Default Cyber Cyan (#00f0ff)
            primary_col = QColor(0, 240, 255)

        pr = primary_col.red()
        pg = primary_col.green()
        pb = primary_col.blue()

        # -------------------------------------------------------------
        # 1. PARTICLES (Shimmering Starfield)
        # -------------------------------------------------------------
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self._particles:
            alpha = int(p.alpha * (0.4 if is_paused else 0.8))
            painter.setBrush(QColor(pr, pg, pb, alpha))
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

        # -------------------------------------------------------------
        # 2. OUTER AMBIENT GLOW
        # -------------------------------------------------------------
        glow_grad = QRadialGradient(cx, cy, max_r)
        glow_grad.setColorAt(0.0, QColor(pr, pg, pb, 45))
        glow_grad.setColorAt(0.55, QColor(pr, pg, pb, 15))
        glow_grad.setColorAt(1.0, QColor(pr, pg, pb, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.drawEllipse(QPointF(cx, cy), max_r, max_r)

        # -------------------------------------------------------------
        # 3. EXPANDING RIPPLE RINGS (Voice Reactivity)
        # -------------------------------------------------------------
        if self._state in [JarvisUIState.LISTENING, JarvisUIState.SPEAKING]:
            for r_rip in [self._ripple_radius_1, self._ripple_radius_2]:
                if r_rip > max_r * 0.35:
                    rip_alpha = int(180 * (1.0 - (r_rip / max_r)))
                    painter.setPen(QPen(QColor(pr, pg, pb, max(0, rip_alpha)), 1.2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(cx, cy), r_rip, r_rip)

        # -------------------------------------------------------------
        # 4. OUTER SEGMENTED ROTATING ARCS
        # -------------------------------------------------------------
        r_outer = max_r * 0.92
        pen_outer = QPen(QColor(pr, pg, pb, 110), 1.2)
        painter.setPen(pen_outer)
        painter.drawEllipse(QPointF(cx, cy), r_outer, r_outer)

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_outer)
        pen_arc = QPen(QColor(pr, pg, pb, 230), 2.8)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)

        arc_rect = QRectF(-r_outer, -r_outer, r_outer * 2, r_outer * 2)
        # 3 Prominent 50-degree segmented arcs (120 deg apart)
        for i in range(3):
            painter.drawArc(arc_rect, int((i * 120) * 16), int(50 * 16))
        painter.restore()

        # -------------------------------------------------------------
        # 5. CONCENTRIC TICK RETICLES (Rotating counter-clockwise)
        # -------------------------------------------------------------
        r_ticks = max_r * 0.77
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_ticks)

        num_ticks = 40
        for i in range(num_ticks):
            angle_rad = (i * (360.0 / num_ticks)) * (math.pi / 180.0)
            is_cardinal = (i % 10 == 0)
            is_major = (i % 5 == 0)
            t_len = 8.0 if is_cardinal else (5.5 if is_major else 3.0)

            tick_col = QColor(pr, pg, pb, 220 if is_cardinal else (140 if is_major else 60))
            painter.setPen(QPen(tick_col, 1.4 if is_cardinal else 1.0))

            x1 = (r_ticks - t_len) * math.cos(angle_rad)
            y1 = (r_ticks - t_len) * math.sin(angle_rad)
            x2 = r_ticks * math.cos(angle_rad)
            y2 = r_ticks * math.sin(angle_rad)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        painter.restore()

        # -------------------------------------------------------------
        # 6. INTERMEDIATE SEGMENT RING (Inner Orbit)
        # -------------------------------------------------------------
        r_mid = max_r * 0.60
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle_inner)

        pen_mid = QPen(QColor(pr, pg, pb, 130), 1.0)
        painter.setPen(pen_mid)
        painter.drawEllipse(QPointF(0, 0), r_mid, r_mid)

        # 4 Segmented heavy dials (90 deg apart)
        pen_block = QPen(QColor(pr, pg, pb, 240), 3.2)
        pen_block.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_block)
        mid_rect = QRectF(-r_mid, -r_mid, r_mid * 2, r_mid * 2)
        for i in range(4):
            painter.drawArc(mid_rect, int((i * 90 + 15) * 16), int(35 * 16))
        painter.restore()

        # -------------------------------------------------------------
        # 7. INNER PULSING PLASMA CORE (Audio-Reactive)
        # -------------------------------------------------------------
        pulse_factor = 0.5 + 0.5 * math.sin(self._pulse_phase)
        r_core_base = max_r * 0.36
        r_core = r_core_base * (0.90 + 0.20 * pulse_factor) * self._core_scale

        core_grad = QRadialGradient(cx, cy, r_core)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        core_grad.setColorAt(0.25, QColor(pr, pg, pb, 240))
        core_grad.setColorAt(0.70, QColor(pr, pg, pb, 100))
        core_grad.setColorAt(1.0, QColor(pr, pg, pb, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), r_core, r_core)

        # Central Crosshair & Inner Reticle
        pen_core_ring = QPen(QColor(255, 255, 255, 200), 1.5)
        painter.setPen(pen_core_ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r_core * 0.45, r_core * 0.45)

        # Crosshairs
        pen_cross = QPen(QColor(pr, pg, pb, 170), 1.0)
        painter.setPen(pen_cross)
        c_len = r_core * 0.85
        painter.drawLine(QPointF(cx - c_len, cy), QPointF(cx - r_core * 0.2, cy))
        painter.drawLine(QPointF(cx + r_core * 0.2, cy), QPointF(cx + c_len, cy))
        painter.drawLine(QPointF(cx, cy - c_len), QPointF(cx, cy - r_core * 0.2))
        painter.drawLine(QPointF(cx, cy + r_core * 0.2), QPointF(cx, cy + c_len))
