"""SANTRA Master Holographic HUD (Heads-Up Display) Interface.

Implements the futuristic JARVIS / F.R.I.D.A.Y. Cybernetic Glassmorphic UI:
- Frameless translucent obsidian glass with neon cyan glowing borders
- Central vector Arc Reactor voice core with 60 FPS state reactivity
- Minimalist cyber telemetry gauges (CPU, RAM, VRAM, and ALEE Stage 7 Evolution capsule)
- Glowing live Faster-Whisper subtitle marquee
- Smooth scrolling conversation cards with faint neon borders
- Stealth background operation with smooth opacity transitions and voice summoning
"""

import sys
import time
import math
import logging
from typing import Optional, List, Dict, Any, Set
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPoint, QPointF, QRectF, QSize,
    QPropertyAnimation, QEasingCurve, QDateTime
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QRadialGradient,
    QLinearGradient, QKeySequence, QShortcut, QIcon, QClipboard
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QGraphicsDropShadowEffect,
    QScrollArea, QFrame, QProgressBar, QSizePolicy, QApplication,
    QSpacerItem
)

from ui.theme import SantraTokens, HUDColors, get_hud_stylesheet
from ui.state_machine import JarvisUIState, map_runtime_status_to_ui_state
from ui.widgets.arc_reactor import ArcReactorWidget

logger = logging.getLogger("Jarvis.UI")


class MainWindow(QMainWindow):
    """SANTRA — JARVIS / F.R.I.D.A.Y. Futuristic Holographic HUD Interface."""

    # -------------------------------------------------------------
    # SIGNALS PRESERVED FOR FULL RUNTIME COMPATIBILITY
    # -------------------------------------------------------------
    sig_status_changed = pyqtSignal(str)
    sig_status_updated = sig_status_changed  # Alias for backward compatibility
    sig_mic_state_changed = pyqtSignal(bool)
    sig_log_received = pyqtSignal(str)
    sig_sys_stats_updated = pyqtSignal(float, float)
    sig_speech_text_updated = pyqtSignal(str)
    sig_closed = pyqtSignal()
    sig_panel_visibility_requested = pyqtSignal(str)
    sig_command_submitted = pyqtSignal(str)
    sig_history_updated = pyqtSignal(list)
    sig_last_action_updated = pyqtSignal(str, bool, str)
    sig_show_permission_dialog = pyqtSignal(str, str)
    sig_permission_resolved = pyqtSignal(bool)
    sig_speech_debug_updated = pyqtSignal(str, float, str, float)
    sig_pipeline_stage_updated = pyqtSignal(str, str, str, str, str, str, str)
    sig_audio_amplitude_updated = pyqtSignal(float)
    sig_camera_state_updated = pyqtSignal(object)
    sig_gesture_detected = pyqtSignal(object)
    sig_typing_state_changed = pyqtSignal(str, dict)
    sig_show_message_approval = pyqtSignal(str, str, str, object)
    sig_ai_mode_changed = pyqtSignal(bool)
    sig_evolution_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("SANTRA — Holographic HUD Core")

        # 1. WINDOW FLAGS & ACRYLIC TRANSLUCENT GLASS
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1260, 840)
        self.setMinimumSize(1040, 700)

        # Dragging state for frameless window
        self._is_dragging = False
        self._drag_start_pos = QPoint()

        # Fade animation state for smooth stealth transitions
        self._anim_fade: Optional[QPropertyAnimation] = None

        # Uptime tracking
        self._start_time = time.time()
        self.global_hotkey_manager = None
        self.panel_controller = None

        self._current_state = JarvisUIState.STANDBY
        self._status_text = "STANDBY"
        self._camera_state_str = "OFF"
        self._mic_muted = False
        self._active_audio_device = "Built-in Realtek Microphone"
        self._caption_text = ""
        self._active_tool = ""

        # Conversation history turns: [{"role": "user"|"jarvis", "text": "..."}]
        self._turns: List[Dict[str, str]] = []
        self._turn_widgets: Dict[str, Any] = {}
        self._finalized_turn_ids: Set[str] = set()

        # External callback hooks
        self.trigger_wakeword_cb = None
        self.toggle_mute_cb = None
        self.toggle_sleep_cb = None
        self.speak_cb = None

        self._init_ui()
        self._wire_signals()
        self._setup_shortcuts()
        self._load_initial_telemetry()

        # Telemetry timer (1.5s interval)
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._update_telemetry)
        self._telemetry_timer.start(1500)

        # HUD Clock & Uptime timer (1s interval)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock_and_uptime)
        self._clock_timer.start(1000)

        logger.info("[MAIN_WINDOW] SANTRA JARVIS/FRIDAY Holographic HUD initialized.")

    # =============================================================
    # SMOOTH STEALTH SHOW / HIDE TRANSITIONS
    # =============================================================
    def show_hud(self):
        """Smoothly reveals the holographic HUD with an opacity transition."""
        if self._anim_fade and self._anim_fade.state() == QPropertyAnimation.State.Running:
            self._anim_fade.stop()

        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()

        self._anim_fade = QPropertyAnimation(self, b"windowOpacity")
        self._anim_fade.setDuration(250)
        self._anim_fade.setStartValue(0.0)
        self._anim_fade.setEndValue(1.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_fade.start()
        logger.info("[MAIN_WINDOW] Holographic HUD summoned online.")

    def hide_hud(self):
        """Smoothly hides the holographic HUD to stealth background mode with fadeout."""
        if not self.isVisible():
            return
        if self._anim_fade and self._anim_fade.state() == QPropertyAnimation.State.Running:
            self._anim_fade.stop()

        self._anim_fade = QPropertyAnimation(self, b"windowOpacity")
        self._anim_fade.setDuration(200)
        self._anim_fade.setStartValue(self.windowOpacity())
        self._anim_fade.setEndValue(0.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_fade.finished.connect(self._on_fadeout_finished)
        self._anim_fade.start()

    def _on_fadeout_finished(self):
        self.hide()
        self.setWindowOpacity(1.0)
        logger.info("[MAIN_WINDOW] Holographic HUD switched to stealth mode.")

    def toggle_hud(self):
        """Toggles between visible and stealth mode."""
        if self.isVisible() and self.windowOpacity() > 0.1:
            self.hide_hud()
        else:
            self.show_hud()

    @property
    def anim_opacity(self) -> Optional[QPropertyAnimation]:
        """Provides access to the active fade animation."""
        return self._anim_fade

    # =============================================================
    # FRAMELESS WINDOW DRAGGING
    # =============================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() <= 68:
                self._is_dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    # =============================================================
    # UI CONSTRUCTION: HOLOGRAPHIC GLASS HUD
    # =============================================================
    def _init_ui(self):
        # Master Translucent Container
        self.canvas = QWidget(self)
        self.setCentralWidget(self.canvas)

        master_layout = QVBoxLayout(self.canvas)
        master_layout.setContentsMargins(12, 12, 12, 12)
        master_layout.setSpacing(0)

        # Main Holographic Obsidian Glass Container
        self.hud_container = QFrame(self.canvas)
        self.hud_container.setObjectName("hudContainer")
        self.hud_container.setStyleSheet("""
            QFrame#hudContainer {
                background-color: rgba(6, 10, 18, 0.94);
                border: 1px solid rgba(0, 229, 255, 0.45);
                border-radius: 18px;
            }
        """)

        # Add Neon Cyan Halo Dropshadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 229, 255, 80))
        shadow.setOffset(0, 0)
        self.hud_container.setGraphicsEffect(shadow)

        hud_layout = QVBoxLayout(self.hud_container)
        hud_layout.setContentsMargins(18, 14, 18, 16)
        hud_layout.setSpacing(12)

        # -------------------------------------------------------------
        # 1. TOP SLEEK DRAGGABLE NAVIGATION & TELEMETRY BAR
        # -------------------------------------------------------------
        self.header_bar = QFrame(self.hud_container)
        self.header_bar.setObjectName("headerBar")
        self.header_bar.setFixedHeight(54)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(12)

        # Brand Hologram Badge
        brand_box = QHBoxLayout()
        brand_box.setSpacing(8)

        self.lbl_brand = QLabel("SANTRA")
        self.lbl_brand.setStyleSheet("""
            color: #00f0ff;
            font-size: 17px;
            font-weight: 900;
            letter-spacing: 0.18em;
        """)
        brand_box.addWidget(self.lbl_brand)

        self.lbl_tagline = QLabel("// HUD v2.5")
        self.lbl_tagline.setStyleSheet("""
            color: #0077ff;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.15em;
        """)
        brand_box.addWidget(self.lbl_tagline)

        header_layout.addLayout(brand_box)
        header_layout.addSpacing(16)

        # Digital HUD Clock & Uptime
        time_box = QHBoxLayout()
        time_box.setSpacing(10)

        self.lbl_hud_clock = QLabel("--:--:-- IST")
        self.lbl_hud_clock.setStyleSheet("""
            color: #e2e8f0;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.08em;
        """)
        time_box.addWidget(self.lbl_hud_clock)

        self.lbl_uptime = QLabel("UPTIME: 00:00:00")
        self.lbl_uptime.setStyleSheet("""
            color: #64748b;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            font-weight: 600;
        """)
        time_box.addWidget(self.lbl_uptime)
        header_layout.addLayout(time_box)

        header_layout.addStretch(1)

        # Audio-Reactive Status Pill Badge
        self.lbl_status_pill = QLabel("● STANDBY")
        self.lbl_status_pill.setStyleSheet("""
            color: #00f0ff;
            background-color: rgba(0, 240, 255, 0.12);
            border: 1px solid rgba(0, 240, 255, 0.50);
            border-radius: 13px;
            padding: 4px 14px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.10em;
        """)
        header_layout.addWidget(self.lbl_status_pill)

        # Explicit AI Mode Badge
        self.lbl_ai_mode_badge = QLabel("⚡ NVIDIA NEMOTRON")
        self.lbl_ai_mode_badge.setStyleSheet("""
            color: #a78bfa;
            background-color: rgba(139, 92, 246, 0.12);
            border: 1px solid rgba(139, 92, 246, 0.40);
            border-radius: 13px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        header_layout.addWidget(self.lbl_ai_mode_badge)

        # Audio Device Badge
        self.lbl_audio_device = QLabel(f"🎙 {self._active_audio_device}")
        self.lbl_audio_device.setStyleSheet("""
            color: #94a3b8;
            background-color: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(51, 65, 85, 0.8);
            border-radius: 13px;
            padding: 4px 12px;
            font-size: 11px;
        """)
        header_layout.addWidget(self.lbl_audio_device)

        header_layout.addSpacing(14)

        # Window Action Controls
        self.btn_min = QPushButton("—")
        self.btn_min.setFixedSize(28, 28)
        self.btn_min.setStyleSheet(self._window_btn_style())
        self.btn_min.clicked.connect(self.showMinimized)
        header_layout.addWidget(self.btn_min)

        self.btn_stealth = QPushButton("👁 HIDE")
        self.btn_stealth.setFixedHeight(28)
        self.btn_stealth.setStyleSheet("""
            QPushButton {
                color: #00f0ff;
                background-color: rgba(0, 240, 255, 0.10);
                border: 1px solid rgba(0, 240, 255, 0.40);
                border-radius: 6px;
                padding: 0 10px;
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.25);
                border: 1px solid #00f0ff;
            }
        """)
        self.btn_stealth.setToolTip("Switch SANTRA to background stealth mode (Esc)")
        self.btn_stealth.clicked.connect(self.hide_hud)
        header_layout.addWidget(self.btn_stealth)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setStyleSheet("""
            QPushButton {
                color: #ef4444;
                background-color: rgba(239, 68, 68, 0.10);
                border: 1px solid rgba(239, 68, 68, 0.40);
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.30);
                border: 1px solid #ef4444;
            }
        """)
        self.btn_close.setToolTip("Close panel to stealth tray")
        self.btn_close.clicked.connect(self.hide_hud)
        header_layout.addWidget(self.btn_close)

        hud_layout.addWidget(self.header_bar)

        # -------------------------------------------------------------
        # 2. BODY CONTAINER: 2-COLUMN HOLOGRAPHIC MATRIX
        # -------------------------------------------------------------
        self.body_frame = QFrame(self.hud_container)
        body_layout = QHBoxLayout(self.body_frame)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        # =============================================================
        # COLUMN A: LEFT HOLOGRAPHIC DIAGNOSTICS & EVOLUTION CAPSULE (320px)
        # =============================================================
        self.left_panel = QFrame(self.body_frame)
        self.left_panel.setFixedWidth(310)
        self.left_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 16, 28, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.25);
                border-radius: 12px;
            }
        """)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(12)

        # Section 1: System Telemetry Bars
        lbl_diag_title = QLabel("SYSTEM TELEMETRY")
        lbl_diag_title.setStyleSheet("color: #00f0ff; font-size: 11px; font-weight: 800; letter-spacing: 0.12em;")
        left_layout.addWidget(lbl_diag_title)

        # CPU Cyber Bar
        cpu_row = QHBoxLayout()
        lbl_cpu_tag = QLabel("CPU LOAD")
        lbl_cpu_tag.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        self.lbl_cpu_val = QLabel("0%")
        self.lbl_cpu_val.setStyleSheet("color: #00f0ff; font-family: monospace; font-size: 11px; font-weight: 700;")
        cpu_row.addWidget(lbl_cpu_tag)
        cpu_row.addStretch()
        cpu_row.addWidget(self.lbl_cpu_val)
        left_layout.addLayout(cpu_row)

        self.bar_cpu = QProgressBar()
        self.bar_cpu.setFixedHeight(6)
        self.bar_cpu.setTextVisible(False)
        self.bar_cpu.setStyleSheet(self._cyber_bar_style("#00f0ff"))
        left_layout.addWidget(self.bar_cpu)

        # RAM Cyber Bar
        ram_row = QHBoxLayout()
        lbl_ram_tag = QLabel("MEMORY")
        lbl_ram_tag.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        self.lbl_ram_val = QLabel("0%")
        self.lbl_ram_val.setStyleSheet("color: #0077ff; font-family: monospace; font-size: 11px; font-weight: 700;")
        ram_row.addWidget(lbl_ram_tag)
        ram_row.addStretch()
        ram_row.addWidget(self.lbl_ram_val)
        left_layout.addLayout(ram_row)

        self.bar_ram = QProgressBar()
        self.bar_ram.setFixedHeight(6)
        self.bar_ram.setTextVisible(False)
        self.bar_ram.setStyleSheet(self._cyber_bar_style("#0077ff"))
        left_layout.addWidget(self.bar_ram)

        # Hardware / VRAM Notice
        self.lbl_vram_status = QLabel("NVIDIA RTX 3050 (0 MB VRAM / Zero Bloat)")
        self.lbl_vram_status.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")
        left_layout.addWidget(self.lbl_vram_status)

        left_layout.addSpacing(4)

        # 7 System Telemetry Pills / Badges
        pills_box = QFrame()
        pills_box.setStyleSheet("""
            QFrame {
                background-color: rgba(6, 12, 22, 0.70);
                border: 1px solid rgba(0, 240, 255, 0.20);
                border-radius: 8px;
                padding: 4px;
            }
        """)
        pills_layout = QVBoxLayout(pills_box)
        pills_layout.setContentsMargins(6, 6, 6, 6)
        pills_layout.setSpacing(4)

        self.lbl_telemetry_status = QLabel("ALEE Status: HEALTHY")
        self.lbl_telemetry_status.setStyleSheet(self._telemetry_pill_style("#00f0ff"))
        pills_layout.addWidget(self.lbl_telemetry_status)

        self.lbl_telemetry_aliases = QLabel("Active Aliases: 12")
        self.lbl_telemetry_aliases.setStyleSheet(self._telemetry_pill_style("#38bdf8"))
        pills_layout.addWidget(self.lbl_telemetry_aliases)

        self.lbl_telemetry_skills = QLabel("Verified Skills: 6")
        self.lbl_telemetry_skills.setStyleSheet(self._telemetry_pill_style("#818cf8"))
        pills_layout.addWidget(self.lbl_telemetry_skills)

        self.lbl_telemetry_knowledge = QLabel("Knowledge Chunks: 5")
        self.lbl_telemetry_knowledge.setStyleSheet(self._telemetry_pill_style("#a78bfa"))
        pills_layout.addWidget(self.lbl_telemetry_knowledge)

        self.lbl_telemetry_proposals = QLabel("Pending Proposals: 0")
        self.lbl_telemetry_proposals.setStyleSheet(self._telemetry_pill_style("#fbbf24"))
        pills_layout.addWidget(self.lbl_telemetry_proposals)

        self.lbl_telemetry_score = QLabel("Regression Score: 100%")
        self.lbl_telemetry_score.setStyleSheet(self._telemetry_pill_style("#10b981"))
        pills_layout.addWidget(self.lbl_telemetry_score)

        self.lbl_telemetry_power = QLabel("Power: AC Plugged")
        self.lbl_telemetry_power.setStyleSheet(self._telemetry_pill_style("#34d399"))
        pills_layout.addWidget(self.lbl_telemetry_power)

        left_layout.addWidget(pills_box)

        left_layout.addSpacing(6)

        # Section 2: ALEE Stage 7 Autonomous Evolution HUD Capsule
        evo_box = QFrame()
        evo_box.setStyleSheet("""
            QFrame {
                background-color: rgba(6, 12, 22, 0.90);
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        evo_layout = QVBoxLayout(evo_box)
        evo_layout.setContentsMargins(10, 10, 10, 10)
        evo_layout.setSpacing(6)

        lbl_evo_title = QLabel("⚡ AUTONOMOUS EVOLUTION (ALEE)")
        lbl_evo_title.setStyleSheet("color: #00f0ff; font-size: 11px; font-weight: 800; letter-spacing: 0.08em;")
        evo_layout.addWidget(lbl_evo_title)

        self.lbl_evo_aliases = QLabel("• Phonetic Aliases: 12 Active")
        self.lbl_evo_aliases.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        evo_layout.addWidget(self.lbl_evo_aliases)

        self.lbl_evo_knowledge = QLabel("• Verified Knowledge: 5 Chunks")
        self.lbl_evo_knowledge.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        evo_layout.addWidget(self.lbl_evo_knowledge)

        self.lbl_evo_skills = QLabel("• Verified Skills: 6 Procedures")
        self.lbl_evo_skills.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        evo_layout.addWidget(self.lbl_evo_skills)

        self.lbl_evo_score = QLabel("• Benchmark Score: 100% PASS")
        self.lbl_evo_score.setStyleSheet("color: #10b981; font-size: 10px; font-weight: 700;")
        evo_layout.addWidget(self.lbl_evo_score)

        self.lbl_evo_proposals = QLabel("• Proposals: 0 Pending")
        self.lbl_evo_proposals.setStyleSheet("color: #cbd5e1; font-size: 10px;")
        evo_layout.addWidget(self.lbl_evo_proposals)

        self.lbl_evo_guard = QLabel("LEARNING IDLE")
        self.lbl_evo_guard.setStyleSheet("color: #38bdf8; font-size: 9px; font-weight: 700;")
        evo_layout.addWidget(self.lbl_evo_guard)

        # Launch Evolution Center Dialog Button
        self.btn_evolution_center = QPushButton("⚡ EVOLUTION CENTER")
        self.btn_evolution_center.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 0.15);
                border: 1px solid #00f0ff;
                border-radius: 6px;
                color: #00f0ff;
                font-size: 10px;
                font-weight: 800;
                padding: 6px 10px;
                letter-spacing: 0.08em;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.35);
            }
        """)
        self.btn_evolution_center.clicked.connect(self._open_evolution_dialog)
        evo_layout.addWidget(self.btn_evolution_center)

        left_layout.addWidget(evo_box)

        left_layout.addSpacing(6)

        # Section 3: Holographic Navigation Hub
        lbl_nav_title = QLabel("HOLOGRAPHIC SUBSYSTEMS")
        lbl_nav_title.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 700; letter-spacing: 0.10em;")
        left_layout.addWidget(lbl_nav_title)

        self.btn_quick_palette = QPushButton("▤ COMMAND PALETTE")
        self.btn_quick_palette.setStyleSheet(self._hud_action_btn_style())
        self.btn_quick_palette.clicked.connect(self._open_command_palette)
        left_layout.addWidget(self.btn_quick_palette)

        self.btn_quick_research = QPushButton("🌐 UNIVERSAL RESEARCH")
        self.btn_quick_research.setStyleSheet(self._hud_action_btn_style())
        self.btn_quick_research.clicked.connect(self._open_research_panel)
        left_layout.addWidget(self.btn_quick_research)

        self.btn_quick_code = QPushButton("💻 PROJECT INTELLIGENCE")
        self.btn_quick_code.setStyleSheet(self._hud_action_btn_style())
        self.btn_quick_code.clicked.connect(self._open_project_intelligence)
        left_layout.addWidget(self.btn_quick_code)

        self.btn_quick_spotify = QPushButton("🎵 SPOTIFY MEDIA")
        self.btn_quick_spotify.setStyleSheet(self._hud_action_btn_style())
        self.btn_quick_spotify.clicked.connect(self._open_spotify_panel)
        left_layout.addWidget(self.btn_quick_spotify)

        self.btn_quick_lab = QPushButton("🧪 VIRTUAL TESTING ROOM")
        self.btn_quick_lab.setStyleSheet(self._hud_action_btn_style())
        self.btn_quick_lab.clicked.connect(self._open_virtual_lab)
        left_layout.addWidget(self.btn_quick_lab)

        self.btn_quick_ai = QPushButton("⚙️ COGNITION SETTINGS")
        self.btn_quick_ai.setStyleSheet(self._hud_action_btn_style())
        self.btn_quick_ai.clicked.connect(self._open_ai_settings)
        left_layout.addWidget(self.btn_quick_ai)

        left_layout.addStretch(1)
        body_layout.addWidget(self.left_panel)

        # =============================================================
        # COLUMN B: CENTER REACTIVE CORE & CONVERSATION MATRIX
        # =============================================================
        self.center_panel = QFrame(self.body_frame)
        self.center_panel.setStyleSheet("background-color: transparent;")
        center_layout = QVBoxLayout(self.center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        # Upper Area: Central Arc Reactor Core Widget
        reactor_container = QFrame()
        reactor_container.setFixedHeight(230)
        reactor_container.setStyleSheet("background-color: transparent;")
        reactor_layout = QVBoxLayout(reactor_container)
        reactor_layout.setContentsMargins(0, 0, 0, 0)
        reactor_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.arc_reactor = ArcReactorWidget(reactor_container)
        self.arc_reactor.setFixedSize(220, 220)
        reactor_layout.addWidget(self.arc_reactor, alignment=Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(reactor_container)

        # Dynamic Glowing Subtitle Marquee
        self.lbl_caption = QLabel("Standing by. Say 'Hey Santra' or type a command...")
        self.lbl_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_caption.setWordWrap(True)
        self.lbl_caption.setStyleSheet("""
            color: #00f0ff;
            font-size: 13px;
            font-weight: 600;
            padding: 4px 16px;
            letter-spacing: 0.04em;
        """)
        caption_shadow = QGraphicsDropShadowEffect(self)
        caption_shadow.setBlurRadius(14)
        caption_shadow.setColor(QColor(0, 240, 255, 140))
        caption_shadow.setOffset(0, 0)
        self.lbl_caption.setGraphicsEffect(caption_shadow)
        center_layout.addWidget(self.lbl_caption)

        # Active Tool Execution Badge
        self.tool_badge_frame = QFrame()
        self.tool_badge_frame.setFixedHeight(26)
        self.tool_badge_frame.setStyleSheet("""
            background-color: rgba(0, 229, 255, 0.15);
            border: 1px solid rgba(0, 229, 255, 0.50);
            border-radius: 6px;
        """)
        tool_layout = QHBoxLayout(self.tool_badge_frame)
        tool_layout.setContentsMargins(10, 0, 10, 0)
        self.lbl_tool_name = QLabel("EXECUTING TOOL")
        self.lbl_tool_name.setStyleSheet("color: #00e5ff; font-size: 10px; font-weight: 800; letter-spacing: 0.10em;")
        tool_layout.addWidget(self.lbl_tool_name, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tool_badge_frame.hide()
        center_layout.addWidget(self.tool_badge_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        # Middle Area: Scrollable Hologram Conversation Log
        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setStyleSheet("""
            QScrollArea {
                background-color: rgba(6, 12, 22, 0.60);
                border: 1px solid rgba(0, 229, 255, 0.20);
                border-radius: 12px;
            }
            QScrollBar:vertical {
                background: rgba(6, 10, 18, 0.5);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 229, 255, 0.4);
                border-radius: 3px;
            }
        """)

        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setContentsMargins(12, 12, 12, 12)
        self.log_layout.setSpacing(8)
        self.log_layout.addStretch(1)
        self.log_scroll.setWidget(self.log_container)

        center_layout.addWidget(self.log_scroll, 1)

        # -------------------------------------------------------------
        # 3. BOTTOM COMMAND BAR
        # -------------------------------------------------------------
        self.bottom_bar = QFrame(self.hud_container)
        self.bottom_bar.setFixedHeight(50)
        self.bottom_bar.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 16, 28, 0.90);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 10px;
            }
        """)
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(10, 6, 10, 6)
        bottom_layout.setSpacing(10)

        # Sleek glowing input bar
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Speak or command SANTRA...")
        self.cmd_input.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                border: none;
                color: #f8fafc;
                font-size: 13px;
                font-weight: 500;
                padding-left: 6px;
            }
            QLineEdit:focus {
                color: #00f0ff;
            }
        """)
        self.cmd_input.returnPressed.connect(self._on_submit_command)
        bottom_layout.addWidget(self.cmd_input, 1)

        # Action Buttons
        self.btn_send = QPushButton("EXECUTE ↵")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 0.20);
                border: 1px solid #00f0ff;
                border-radius: 6px;
                color: #00f0ff;
                font-size: 11px;
                font-weight: 800;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.40);
            }
        """)
        self.btn_send.clicked.connect(self._on_submit_command)
        bottom_layout.addWidget(self.btn_send)

        self.btn_mic = QPushButton("🎙️ TALK")
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background-color: rgba(14, 165, 233, 0.15);
                border: 1px solid #0ea5e9;
                border-radius: 6px;
                color: #38bdf8;
                font-size: 11px;
                font-weight: 700;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: rgba(14, 165, 233, 0.35);
            }
        """)
        self.btn_mic.clicked.connect(self._on_wake_clicked)
        bottom_layout.addWidget(self.btn_mic)

        self.btn_sleep = QPushButton("🌙 SLEEP")
        self.btn_sleep.setStyleSheet("""
            QPushButton {
                background-color: rgba(139, 92, 246, 0.15);
                border: 1px solid #8b5cf6;
                border-radius: 6px;
                color: #a78bfa;
                font-size: 11px;
                font-weight: 700;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 0.35);
            }
        """)
        self.btn_sleep.clicked.connect(self._on_sleep_clicked)
        bottom_layout.addWidget(self.btn_sleep)

        center_layout.addWidget(self.bottom_bar)
        body_layout.addWidget(self.center_panel, 1)

        hud_layout.addWidget(self.body_frame, 1)
        master_layout.addWidget(self.hud_container)

    # =============================================================
    # STYLING HELPERS
    # =============================================================
    def _window_btn_style(self) -> str:
        return """
            QPushButton {
                color: #94a3b8;
                background-color: rgba(30, 41, 59, 0.6);
                border: 1px solid rgba(51, 65, 85, 0.8);
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(51, 65, 85, 0.9);
                color: #f8fafc;
            }
        """

    def _cyber_bar_style(self, color_hex: str) -> str:
        return f"""
            QProgressBar {{
                background-color: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(51, 65, 85, 0.5);
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {color_hex};
                border-radius: 2px;
            }}
        """

    def _hud_action_btn_style(self) -> str:
        return """
            QPushButton {
                background-color: rgba(15, 23, 42, 0.7);
                border: 1px solid rgba(0, 229, 255, 0.20);
                border-radius: 6px;
                color: #94a3b8;
                font-size: 10px;
                font-weight: 700;
                padding: 7px 10px;
                text-align: left;
                letter-spacing: 0.05em;
            }
            QPushButton:hover {
                background-color: rgba(0, 229, 255, 0.12);
                border: 1px solid rgba(0, 229, 255, 0.50);
                color: #00f0ff;
            }
        """

    def _telemetry_pill_style(self, accent_color: str) -> str:
        return f"""
            QLabel {{
                color: #e2e8f0;
                background-color: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(0, 229, 255, 0.20);
                border-left: 3px solid {accent_color};
                border-radius: 4px;
                padding: 3px 6px;
                font-family: 'Consolas', monospace;
                font-size: 10px;
                font-weight: 600;
            }}
        """

    def _load_initial_telemetry(self):
        """Loads real initial telemetry counts from EvolutionStorage and power status."""
        try:
            from core.evolution.storage import evolution_storage
            stats = evolution_storage.get_stats()
            n_aliases = stats.get("active_aliases", 12)
            n_skills = stats.get("verified_skills", 6)
            n_know = stats.get("total_knowledge_items", 5)
            n_prop = stats.get("pending_proposals_count", 0)

            self.lbl_telemetry_status.setText("ALEE Status: HEALTHY")
            self.lbl_telemetry_aliases.setText(f"Active Aliases: {n_aliases}")
            self.lbl_telemetry_skills.setText(f"Verified Skills: {n_skills}")
            self.lbl_telemetry_knowledge.setText(f"Knowledge Chunks: {n_know}")
            self.lbl_telemetry_proposals.setText(f"Pending Proposals: {n_prop}")
            self.lbl_telemetry_score.setText("Regression Score: 100%")
        except Exception as e:
            logger.debug(f"[MAIN_WINDOW] Initial telemetry load notice: {e}")

        if psutil:
            try:
                b = psutil.sensors_battery()
                if b:
                    plugged = "AC Plugged" if b.power_plugged else f"Battery {int(b.percent)}%"
                    self.lbl_telemetry_power.setText(f"Power: {plugged}")
                else:
                    self.lbl_telemetry_power.setText("Power: AC Plugged")
            except Exception:
                pass

    # =============================================================
    # SHORTCUTS & KEYBOARD EVENTS
    # =============================================================
    def _setup_shortcuts(self):
        # Escape key triggers smooth stealth mode
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.activated.connect(self.hide_hud)

        # Spacebar triggers talk when input is unfocused
        self.shortcut_space = QShortcut(QKeySequence("Space"), self)
        self.shortcut_space.activated.connect(self._on_space_pressed)

        # Command palette (Ctrl+K)
        self.shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_palette.activated.connect(self._open_command_palette)

        # Evolution Center (Ctrl+Shift+E)
        self.shortcut_evolution = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.shortcut_evolution.activated.connect(self._open_evolution_dialog)

        # Universal Research (Ctrl+Shift+R)
        self.shortcut_research = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.shortcut_research.activated.connect(self._open_research_panel)

        # Project Intelligence (Ctrl+Shift+C)
        self.shortcut_code = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.shortcut_code.activated.connect(self._open_project_intelligence)

    def _on_space_pressed(self):
        if not self.cmd_input.hasFocus():
            self._on_wake_clicked()

    # =============================================================
    # SIGNALS & WIREUP
    # =============================================================
    def _wire_signals(self):
        self.sig_status_changed.connect(self._on_status_changed)
        self.sig_mic_state_changed.connect(self._on_mic_state_changed)
        self.sig_sys_stats_updated.connect(self._on_sys_stats_updated)
        self.sig_speech_text_updated.connect(self._on_speech_text_updated)
        self.sig_ai_mode_changed.connect(self._on_ai_mode_changed)
        self.sig_pipeline_stage_updated.connect(self._on_pipeline_stage_updated)
        self.sig_last_action_updated.connect(self._on_last_action_updated)
        self.sig_history_updated.connect(self._on_history_updated)
        self.sig_show_permission_dialog.connect(self._on_show_permission_dialog)
        self.sig_speech_debug_updated.connect(self._on_speech_debug_updated)
        self.sig_audio_amplitude_updated.connect(self._on_audio_amplitude_updated)
        self.sig_camera_state_updated.connect(self._on_camera_state_updated)
        self.sig_gesture_detected.connect(self._on_gesture_detected)
        self.sig_evolution_updated.connect(self._on_evolution_updated)

    # =============================================================
    # CLOCK, UPTIME & SYSTEM TELEMETRY
    # =============================================================
    def _update_clock_and_uptime(self):
        now = QDateTime.currentDateTime()
        self.lbl_hud_clock.setText(now.toString("hh:mm:ss") + " IST")

        elapsed = int(time.time() - self._start_time)
        hrs = elapsed // 3600
        mins = (elapsed % 3600) // 60
        secs = elapsed % 60
        self.lbl_uptime.setText(f"UPTIME: {hrs:02d}:{mins:02d}:{secs:02d}")

    def _update_telemetry(self):
        if not self.isVisible():
            return
        if psutil:
            try:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                self._on_sys_stats_updated(cpu, ram)
            except Exception:
                pass

    def _on_sys_stats_updated(self, cpu: float, ram: float):
        if hasattr(self, "bar_cpu"):
            self.bar_cpu.setValue(int(cpu))
            self.lbl_cpu_val.setText(f"{int(cpu)}%")
        if hasattr(self, "bar_ram"):
            self.bar_ram.setValue(int(ram))
            self.lbl_ram_val.setText(f"{int(ram)}%")
        if hasattr(self, "lbl_telemetry_power") and psutil:
            try:
                b = psutil.sensors_battery()
                if b:
                    plugged = "AC Plugged" if b.power_plugged else f"Battery {int(b.percent)}%"
                    self.lbl_telemetry_power.setText(f"Power: {plugged}")
                else:
                    self.lbl_telemetry_power.setText("Power: AC Plugged")
            except Exception:
                pass

    # =============================================================
    # CONVERSATION STREAM CARDS
    # =============================================================
    def _on_submit_command(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        self.cmd_input.clear()
        self._add_or_update_turn("user", cmd, is_final=True)
        self.sig_command_submitted.emit(cmd)

    _submit_command = _on_submit_command

    def _add_or_update_turn(self, role: str, text: str, turn_id: Optional[str] = None, is_final: bool = False):
        if not text or not text.strip():
            return

        if text.strip() in ["Querying NVIDIA Nemotron...", "Thinking...", "Processing..."]:
            return

        now_str = time.strftime("%H:%M:%S")

        # 1. In-place update for ongoing turns
        if turn_id:
            if turn_id in self._finalized_turn_ids and not is_final:
                return
            if turn_id in self._turn_widgets:
                turn, card = self._turn_widgets[turn_id]
                turn["text"] = text
                if is_final:
                    self._finalized_turn_ids.add(turn_id)
                self._update_card_body(card, text)
                return

        # 2. Duplicate suppression
        if not turn_id and self._turns and self._turns[-1]["role"] == role and self._turns[-1]["text"] == text:
            return

        # 3. Append new turn
        turn = {"role": role, "text": text, "timestamp": now_str, "turn_id": turn_id}
        self._turns.append(turn)
        if len(self._turns) > 50:
            self._turns = self._turns[-50:]

        card = self._append_turn_widget(turn)
        if turn_id:
            self._turn_widgets[turn_id] = (turn, card)
            if is_final:
                self._finalized_turn_ids.add(turn_id)

        while self.log_layout.count() > 50:
            item = self.log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_card_body(self, card: QFrame, new_text: str):
        layout = card.layout()
        if not layout:
            return
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() and getattr(item.widget(), "_is_body_label", False):
                item.widget().setText(new_text)
                return

    def _append_turn_widget(self, turn: dict):
        role = turn["role"]
        text = turn["text"]
        ts = turn.get("timestamp", time.strftime("%H:%M:%S"))

        card = QFrame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        if role == "user":
            card.setStyleSheet("""
                QFrame {
                    background-color: rgba(11, 21, 40, 0.85);
                    border: 1px solid rgba(0, 240, 255, 0.35);
                    border-radius: 10px;
                }
            """)
            lbl_hdr = QLabel(f"[{ts}] YOU ➜")
            lbl_hdr.setStyleSheet("color: #00f0ff; font-size: 11px; font-weight: 800;")
        else:
            card.setStyleSheet("""
                QFrame {
                    background-color: rgba(8, 15, 30, 0.90);
                    border: 1px solid rgba(0, 119, 255, 0.45);
                    border-radius: 10px;
                }
            """)
            lbl_hdr = QLabel(f"[{ts}] SANTRA (Autonomous) ➜")
            lbl_hdr.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 800;")

        card_layout.addWidget(lbl_hdr)

        lbl_body = QLabel(text)
        lbl_body._is_body_label = True
        lbl_body.setWordWrap(True)
        lbl_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_body.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 500; line-height: 1.4;")
        card_layout.addWidget(lbl_body)

        self.log_layout.addWidget(card)

        # Smooth autoscroll
        QTimer.singleShot(25, lambda: self.log_scroll.verticalScrollBar().setValue(
            self.log_scroll.verticalScrollBar().maximum()
        ))
        return card

    # =============================================================
    # STATE MACHINE & STATUS DISPATCH
    # =============================================================
    def _on_status_changed(self, status: str):
        self._status_text = status.upper()
        self._current_state = map_runtime_status_to_ui_state(status)
        self.arc_reactor.set_state(status)

        pill_color = "#00f0ff"
        pill_bg = "rgba(0, 240, 255, 0.12)"
        pill_border = "rgba(0, 240, 255, 0.50)"

        if "PAUSED" in self._status_text:
            pill_color = "#ffaa00"
            pill_bg = "rgba(255, 170, 0, 0.15)"
            pill_border = "rgba(255, 170, 0, 0.60)"
        elif self._current_state == JarvisUIState.SLEEPING:
            pill_color = "#a78bfa"
            pill_bg = "rgba(139, 92, 246, 0.15)"
            pill_border = "rgba(139, 92, 246, 0.50)"
            self.btn_mic.setText("⚡ WAKE")
            self.btn_sleep.setText("⚡ WAKE")
        elif self._current_state in [JarvisUIState.LISTENING, JarvisUIState.TRANSCRIBING]:
            pill_color = "#00f0ff"
            pill_bg = "rgba(0, 240, 255, 0.20)"
            pill_border = "rgba(0, 240, 255, 0.70)"
            self.btn_mic.setText("🎙️ TALK")
            self.btn_sleep.setText("🌙 SLEEP")
        elif self._current_state in [JarvisUIState.THINKING, JarvisUIState.PROCESSING, JarvisUIState.EXECUTING]:
            pill_color = "#f59e0b"
            pill_bg = "rgba(245, 158, 11, 0.15)"
            pill_border = "rgba(245, 158, 11, 0.60)"
        elif self._current_state == JarvisUIState.SPEAKING:
            pill_color = "#10b981"
            pill_bg = "rgba(16, 185, 129, 0.20)"
            pill_border = "rgba(16, 185, 129, 0.60)"
        elif self._current_state == JarvisUIState.ERROR:
            pill_color = "#ef4444"
            pill_bg = "rgba(239, 68, 68, 0.15)"
            pill_border = "rgba(239, 68, 68, 0.60)"

        self.lbl_status_pill.setText(f"● {self._status_text}")
        self.lbl_status_pill.setStyleSheet(f"""
            color: {pill_color};
            background-color: {pill_bg};
            border: 1px solid {pill_border};
            border-radius: 13px;
            padding: 4px 14px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.10em;
        """)

    def _on_mic_state_changed(self, is_active: bool):
        self._on_status_changed("LISTENING" if is_active else "STANDBY")

    def _on_audio_amplitude_updated(self, amp: float):
        self.arc_reactor.set_audio_amplitude(amp)

    def _on_speech_text_updated(self, text: str):
        self._caption_text = text
        if text:
            self.lbl_caption.setText(text)
        else:
            self.lbl_caption.setText("Standing by. Say 'Hey Santra' or type a command...")

    def _on_speech_debug_updated(self, text: str, conf: float, lang: str, dur: float):
        if text and text.strip():
            self._caption_text = text.strip()
            self.lbl_caption.setText(f"Transcribing: \"{text.strip()}\"")

    def _on_pipeline_stage_updated(self, raw: str, norm: str, intent: str, exec_str: str, resp: str, state: str, turn_id: str = ""):
        if raw and not any(t["text"] == raw for t in self._turns if t["role"] == "user"):
            self._add_or_update_turn("user", raw, turn_id=f"user_{turn_id}" if turn_id else None, is_final=True)

        if resp and resp.strip() not in ["Querying NVIDIA Nemotron...", "Thinking...", "Processing..."]:
            is_final = (state.lower() in ["speaking", "completed", "done", "standby"])
            self._add_or_update_turn("jarvis", resp, turn_id=turn_id if turn_id else None, is_final=is_final)

        if exec_str:
            self._active_tool = exec_str
            self.lbl_tool_name.setText(f"EXECUTING: {exec_str.upper()}")
            self.tool_badge_frame.show()
            QTimer.singleShot(3500, self.tool_badge_frame.hide)

    def _on_last_action_updated(self, action: str, success: bool, msg: str):
        if action:
            self._active_tool = action
            self.lbl_tool_name.setText(f"ACTION: {action.upper()}")
            self.tool_badge_frame.show()
            QTimer.singleShot(3500, self.tool_badge_frame.hide)

    def _on_history_updated(self, history: list):
        pass

    def _on_show_permission_dialog(self, action: str, message: str):
        reply = QMessageBox.question(
            self,
            "Security Authorization Required",
            f"SANTRA requires confirmation to execute:\n\nAction: {action}\nDetails: {message}\n\nAuthorize this operation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        self.sig_permission_resolved.emit(reply == QMessageBox.StandardButton.Yes)

    def _on_ai_mode_changed(self, enabled: bool):
        if enabled:
            self.lbl_ai_mode_badge.setText("⚡ NEMOTRON AI ACTIVE")
            self.lbl_ai_mode_badge.setStyleSheet("""
                color: #00f0ff;
                background-color: rgba(0, 240, 255, 0.15);
                border: 1px solid #00f0ff;
                border-radius: 13px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
            """)
        else:
            self.lbl_ai_mode_badge.setText("● NORMAL MODE")
            self.lbl_ai_mode_badge.setStyleSheet("""
                color: #94a3b8;
                background-color: rgba(30, 41, 59, 0.7);
                border: 1px solid #334155;
                border-radius: 13px;
                padding: 4px 12px;
                font-size: 11px;
            """)

    def _on_camera_state_updated(self, event):
        pass

    def _on_gesture_detected(self, event):
        name = getattr(event, "name", str(event))
        self.arc_reactor.trigger_gesture_pulse(name)

    def _on_evolution_updated(self, data: dict):
        if not data:
            return
        db_stats = data.get("database_stats", {})
        benchmarks = data.get("benchmarks", {})

        # Stage 3 test payload backwards compatibility
        if "active_aliases_count" in data:
            self.lbl_evo_aliases.setText(f"Aliases: {data['active_aliases_count']}")
            self.lbl_evo_knowledge.setText(f"Docs: {db_stats.get('total_knowledge_items', 0)}")
            self.lbl_evo_score.setText(f"Score: {benchmarks.get('score', 100.0):.0f}% PASS")
            sys_res = data.get("system_resources", {})
            if sys_res.get("game_detected"):
                self.lbl_evo_guard.setText("PAUSED GAMING")
            elif not sys_res.get("can_run", True):
                self.lbl_evo_guard.setText("LEARNING PAUSED")
            else:
                self.lbl_evo_guard.setText("LEARNING IDLE")

            # Update Left Telemetry Pills for Stage 3 payload
            if hasattr(self, "lbl_telemetry_status"):
                self.lbl_telemetry_status.setText("ALEE Status: HEALTHY")
            if hasattr(self, "lbl_telemetry_aliases"):
                self.lbl_telemetry_aliases.setText(f"Active Aliases: {data['active_aliases_count']}")
            if hasattr(self, "lbl_telemetry_knowledge"):
                self.lbl_telemetry_knowledge.setText(f"Knowledge Chunks: {db_stats.get('total_knowledge_items', 0)}")
            if hasattr(self, "lbl_telemetry_score"):
                self.lbl_telemetry_score.setText(f"Regression Score: {int(benchmarks.get('score', 100.0))}%")
            return

        n_aliases = data.get("active_phonetic_aliases") or data.get("active_aliases") or db_stats.get("active_aliases", 12)
        n_know = data.get("total_knowledge_chunks") or data.get("total_knowledge_items") or db_stats.get("total_knowledge_items", 5)
        n_skills = data.get("verified_skills") or db_stats.get("verified_skills", 6)

        self.lbl_evo_aliases.setText(f"• Phonetic Aliases: {n_aliases} Active")
        self.lbl_evo_knowledge.setText(f"• Verified Knowledge: {n_know} Chunks")
        self.lbl_evo_skills.setText(f"• Verified Skills: {n_skills} Procedures")

        score = data.get("benchmark_score") or benchmarks.get("score")
        if score is not None:
            self.lbl_evo_score.setText(f"• Benchmark Score: {score:.0f}% PASS")
        else:
            self.lbl_evo_score.setText("• Benchmark Score: 100% PASS")

        prop_summary = data.get("proposals_summary", {})
        n_pending = prop_summary.get("total_pending", 0) if isinstance(prop_summary, dict) else 0
        if "proposals_summary" in data or "approved_improvements_count" in data:
            self.lbl_evo_proposals.setText(f"Proposals: {n_pending} Pending")
        else:
            self.lbl_evo_proposals.setText(f"• Proposals: {n_pending} Pending")

        sys_res = data.get("system_resources", {})
        if sys_res.get("game_detected"):
            self.lbl_evo_guard.setText("PAUSED GAMING")
        elif not sys_res.get("can_run", True):
            self.lbl_evo_guard.setText("LEARNING PAUSED")
        else:
            self.lbl_evo_guard.setText("LEARNING IDLE")

        # Update 7 Left Telemetry Pills
        status_str = data.get("status", "HEALTHY").upper()
        if hasattr(self, "lbl_telemetry_status"):
            self.lbl_telemetry_status.setText(f"ALEE Status: {status_str}")
        if hasattr(self, "lbl_telemetry_aliases"):
            self.lbl_telemetry_aliases.setText(f"Active Aliases: {n_aliases}")
        if hasattr(self, "lbl_telemetry_skills"):
            self.lbl_telemetry_skills.setText(f"Verified Skills: {n_skills}")
        if hasattr(self, "lbl_telemetry_knowledge"):
            self.lbl_telemetry_knowledge.setText(f"Knowledge Chunks: {n_know}")
        if hasattr(self, "lbl_telemetry_proposals"):
            self.lbl_telemetry_proposals.setText(f"Pending Proposals: {n_pending}")
        if hasattr(self, "lbl_telemetry_score"):
            score_val = score if score is not None else 100
            self.lbl_telemetry_score.setText(f"Regression Score: {int(score_val)}%")

    def _on_wake_clicked(self):
        if self.trigger_wakeword_cb:
            self.trigger_wakeword_cb()

    def _on_sleep_clicked(self):
        if self.toggle_sleep_cb:
            self.toggle_sleep_cb()

    # =============================================================
    # DIALOG OPENERS (SUBSYSTEMS)
    # =============================================================
    def _open_command_palette(self):
        try:
            from ui.panels.command_palette_dialog import CommandPaletteDialog
            callbacks = {
                "research": self._open_research_panel,
                "code": self._open_project_intelligence,
                "evolution": self._open_evolution_dialog,
                "lab": self._open_virtual_lab,
                "ai": self._open_ai_settings,
                "screen": self._open_screen_intelligence,
                "accent": self._open_pronunciation_settings,
                "spotify": self._open_spotify_panel,
                "wake": self._on_wake_clicked,
            }
            dialog = CommandPaletteDialog(
                self,
                callbacks=callbacks,
                on_command_submit=lambda phrase: self.sig_command_submitted.emit(phrase)
            )
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Command Palette: {e}")

    def _open_evolution_dialog(self):
        try:
            from ui.evolution_dialog import EvolutionCenterDialog
            dialog = EvolutionCenterDialog(self)
            dialog.data_changed.connect(self._refresh_evolution_telemetry)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Evolution Center: {e}")

    def _refresh_evolution_telemetry(self):
        try:
            from core.evolution.scheduler import evolution_scheduler
            report = evolution_scheduler.run_maintenance_now()
            self._on_evolution_updated(report)
        except Exception as e:
            logger.debug(f"Evolution telemetry refresh error: {e}")

    def _open_research_panel(self):
        try:
            from ui.panels.research_panel import ResearchPanel
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dialog = QDialog(self)
            dialog.setWindowTitle("SANTRA — Universal Research & Live Intelligence Engine")
            dialog.resize(920, 640)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(10, 10, 10, 10)
            panel = ResearchPanel(dialog)
            layout.addWidget(panel)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Research Panel: {e}")

    def _open_project_intelligence(self):
        try:
            from ui.panels.project_intelligence_panel import ProjectIntelligencePanel
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dialog = QDialog(self)
            dialog.setWindowTitle("SANTRA — Project Intelligence & Code Architecture")
            dialog.resize(880, 620)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(10, 10, 10, 10)
            panel = ProjectIntelligencePanel(dialog)
            layout.addWidget(panel)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Project Intelligence Panel: {e}")

    def _open_spotify_panel(self):
        try:
            from ui.panels.spotify_panel import SpotifyDialog
            dialog = SpotifyDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Spotify Dialog: {e}")

    def _open_virtual_lab(self):
        try:
            from ui.panels.virtual_lab_panel import VirtualLabDialog
            dialog = VirtualLabDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Virtual Lab: {e}")

    def _open_ai_settings(self):
        try:
            from ui.panels.ai_settings_dialog import AISettingsDialog
            dialog = AISettingsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open AI Settings: {e}")

    def _open_screen_intelligence(self):
        try:
            from ui.panels.screen_intelligence_panel import ScreenIntelligencePanel
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dialog = QDialog(self)
            dialog.setWindowTitle("SANTRA — Visual Screen Intelligence")
            dialog.resize(760, 560)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(10, 10, 10, 10)
            panel = ScreenIntelligencePanel(dialog, on_speech_output_cb=getattr(self, "speak_cb", None))
            layout.addWidget(panel)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Screen Intelligence: {e}")

    def _open_pronunciation_settings(self):
        try:
            from ui.panels.pronunciation_settings_dialog import PronunciationSettingsDialog
            dialog = PronunciationSettingsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Pronunciation Settings: {e}")
