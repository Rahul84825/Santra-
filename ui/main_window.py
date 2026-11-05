"""
SANTRA Master Desktop Interface MainWindow.
Implements the 5-Zone Modern Desktop Architecture:
1. Top Header Bar (Brand, subtitle, status badge pill, active audio device, quick controls)
2. Left Navigation Sidebar (Conversation, Commands, Projects, Vision, Testing Lab, Spotify, Pronunciation, Settings)
3. Main Workspace (Scrollable high-contrast conversation history with syntax-highlighted code blocks, copy controls)
4. Right Telemetry & Status Sidebar (Embedded Arc Reactor, System resources, Audio hardware, Active pipeline)
5. Bottom Command Composer (High-contrast input bar, EXECUTE, PALETTE, SLEEP, TALK)

Performance Optimized:
- Eliminated 60 FPS full-window repaints and scanline loops.
- Incremental message rendering (O(1) turn addition vs O(N) widget teardown).
- Automatic telemetry pausing when minimized or hidden.
"""

import time
import math
import logging
from typing import Optional, List, Dict

try:
    import psutil
except ImportError:
    psutil = None

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF, QRectF, QSize
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
from ui.reactor.arc_reactor import ArcReactorWidget
from ui.widgets.boot_overlay import BootOverlayWidget

logger = logging.getLogger("Jarvis.UI")


class MainWindow(QMainWindow):
    """SANTRA Modern Autonomous Desktop Assistant Interface."""

    sig_status_changed = pyqtSignal(str)
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
        self.setWindowTitle("SANTRA — Autonomous Desktop Intelligence")
        self.resize(1240, 820)
        self.setMinimumSize(1000, 680)
        self.global_hotkey_manager = None

        self._current_state = JarvisUIState.STANDBY
        self._status_text = "STANDBY"
        self._camera_state_str = "OFF"

        self._mic_muted = False
        self._signal_level = 0.85
        self._target_signal_level = 0.85
        self._active_tool = ""
        self._caption_text = ""
        self._error_text = ""
        self._active_audio_device = "Built-in Realtek Microphone"

        # Conversation history turns: [{"role": "user"|"jarvis", "text": "..."}]
        self._turns: List[Dict[str, str]] = []
        self._turn_widgets: Dict[str, Any] = {}
        self._finalized_turn_ids: Set[str] = set()

        # Apply Global Stylesheet
        self.setStyleSheet(get_hud_stylesheet())

        self._init_ui()
        self._wire_signals()
        self._setup_shortcuts()

        # Low-overhead background telemetry timer (1.5s interval)
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._update_telemetry)
        self._telemetry_timer.start(1500)

        # UI State interpolation timer (30 FPS, lightweight)
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._on_hud_tick)
        self._hud_timer.start(33)

        self.trigger_wakeword_cb = None
        self.toggle_mute_cb = None
        self.toggle_sleep_cb = None
        self.speak_cb = None

        logger.info("SANTRA Autonomous Desktop UI initialized.")

    def _init_ui(self):
        # Master Canvas Widget
        self.canvas = QWidget(self)
        self.setCentralWidget(self.canvas)

        root_layout = QVBoxLayout(self.canvas)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # =========================================================================
        # ZONE 1: TOP HEADER BAR
        # =========================================================================
        self.header_bar = QFrame(self.canvas)
        self.header_bar.setObjectName("headerBar")
        self.header_bar.setFixedHeight(58)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(18, 8, 18, 8)
        header_layout.setSpacing(14)

        # Brand & Subtitle
        brand_container = QWidget()
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(1)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(6)

        self.lbl_brand = QLabel("SANTRA")
        self.lbl_brand.setStyleSheet("""
            color: #f8fafc;
            font-size: 16px;
            font-weight: 800;
            letter-spacing: 0.18em;
        """)
        brand_row.addWidget(self.lbl_brand)

        lbl_dot = QLabel("•")
        lbl_dot.setStyleSheet("color: #0ea5e9; font-size: 16px; font-weight: bold;")
        brand_row.addWidget(lbl_dot)
        brand_row.addStretch()
        brand_layout.addLayout(brand_row)

        self.lbl_subtitle = QLabel("AUTONOMOUS DESKTOP INTELLIGENCE")
        self.lbl_subtitle.setStyleSheet("""
            color: #94a3b8;
            font-size: 8px;
            font-weight: 600;
            letter-spacing: 0.22em;
        """)
        brand_layout.addWidget(self.lbl_subtitle)
        header_layout.addWidget(brand_container)

        header_layout.addStretch(1)

        # Status Pill Badge
        self.lbl_status_pill = QLabel("● STANDBY")
        self.lbl_status_pill.setProperty("class", "statusPill")
        self.lbl_status_pill.setStyleSheet("""
            color: #38bdf8;
            background-color: rgba(14, 165, 233, 0.15);
            border: 1px solid rgba(14, 165, 233, 0.45);
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.08em;
        """)
        header_layout.addWidget(self.lbl_status_pill)

        # Explicit AI Mode Badge
        self.lbl_ai_mode_badge = QLabel("● NORMAL MODE")
        self.lbl_ai_mode_badge.setStyleSheet("""
            color: #64748b;
            background-color: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
        """)
        header_layout.addWidget(self.lbl_ai_mode_badge)

        # Active Audio Device Badge
        self.lbl_audio_device = QLabel(f"🎙 {self._active_audio_device}")
        self.lbl_audio_device.setStyleSheet("""
            color: #94a3b8;
            background-color: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 500;
        """)
        header_layout.addWidget(self.lbl_audio_device)

        header_layout.addStretch(1)

        # Quick Action Controls
        self.btn_quick_talk = QPushButton("🎙️ TALK")
        self.btn_quick_talk.setProperty("class", "santraButton")
        self.btn_quick_talk.clicked.connect(self._on_wake_clicked)
        header_layout.addWidget(self.btn_quick_talk)

        self.btn_quick_palette = QPushButton("▤ COMMANDS")
        self.btn_quick_palette.setProperty("class", "santraButton")
        self.btn_quick_palette.clicked.connect(self._open_command_palette)
        header_layout.addWidget(self.btn_quick_palette)

        self.btn_quick_sleep = QPushButton("🌙 SLEEP")
        self.btn_quick_sleep.setProperty("class", "santraButton")
        self.btn_quick_sleep.clicked.connect(self._on_sleep_clicked)
        header_layout.addWidget(self.btn_quick_sleep)

        root_layout.addWidget(self.header_bar)

        # =========================================================================
        # ZONES 2, 3, 4: BODY CONTAINER (Horizontal Split)
        # =========================================================================
        self.body_frame = QFrame(self.canvas)
        self.body_frame.setObjectName("bodyFrame")
        body_layout = QHBoxLayout(self.body_frame)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # -------------------------------------------------------------------------
        # ZONE 2: LEFT NAVIGATION SIDEBAR
        # -------------------------------------------------------------------------
        self.nav_sidebar = QFrame(self.body_frame)
        self.nav_sidebar.setObjectName("navSidebar")
        self.nav_sidebar.setFixedWidth(210)
        nav_layout = QVBoxLayout(self.nav_sidebar)
        nav_layout.setContentsMargins(10, 14, 10, 14)
        nav_layout.setSpacing(5)

        lbl_nav_title = QLabel("CAPABILITIES & HUBS")
        lbl_nav_title.setStyleSheet("""
            color: #64748b;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.16em;
            padding-left: 6px;
            margin-bottom: 6px;
        """)
        nav_layout.addWidget(lbl_nav_title)

        # Navigation Hub Buttons
        self.btn_nav_conversation = QPushButton("💬  Conversation")
        self.btn_nav_conversation.setProperty("class", "navButton active")
        nav_layout.addWidget(self.btn_nav_conversation)

        self.btn_nav_commands = QPushButton("▤  Commands (Ctrl+K)")
        self.btn_nav_commands.setProperty("class", "navButton")
        self.btn_nav_commands.clicked.connect(self._open_command_palette)
        nav_layout.addWidget(self.btn_nav_commands)

        self.btn_nav_projects = QPushButton("📁  Projects & Code")
        self.btn_nav_projects.setProperty("class", "navButton")
        self.btn_nav_projects.clicked.connect(self._open_project_intelligence)
        nav_layout.addWidget(self.btn_nav_projects)

        self.btn_nav_vision = QPushButton("👁️  Visual Screen")
        self.btn_nav_vision.setProperty("class", "navButton")
        self.btn_nav_vision.clicked.connect(self._open_screen_intelligence)
        nav_layout.addWidget(self.btn_nav_vision)

        self.btn_nav_lab = QPushButton("🔬  Virtual Testing Lab")
        self.btn_nav_lab.setProperty("class", "navButton")
        self.btn_nav_lab.clicked.connect(self._open_virtual_lab)
        nav_layout.addWidget(self.btn_nav_lab)

        self.btn_nav_spotify = QPushButton("🎵  Spotify Suite")
        self.btn_nav_spotify.setProperty("class", "navButton")
        self.btn_nav_spotify.clicked.connect(self._open_spotify_panel)
        nav_layout.addWidget(self.btn_nav_spotify)

        self.btn_nav_voice = QPushButton("🎙️  Voice & Pronounce")
        self.btn_nav_voice.setProperty("class", "navButton")
        self.btn_nav_voice.clicked.connect(self._open_pronunciation_settings)
        nav_layout.addWidget(self.btn_nav_voice)

        self.btn_nav_ai = QPushButton("⚙️  AI Engine Settings")
        self.btn_nav_ai.setProperty("class", "navButton")
        self.btn_nav_ai.clicked.connect(self._open_ai_settings)
        nav_layout.addWidget(self.btn_nav_ai)

        nav_layout.addStretch(1)

        # System info note at bottom of sidebar
        lbl_build_info = QLabel("SANTRA v2.0\nWindows 11 Native\nNVIDIA RTX 3050")
        lbl_build_info.setStyleSheet("""
            color: #475569;
            font-size: 10px;
            font-weight: 500;
            line-height: 1.4;
            padding-left: 6px;
        """)
        nav_layout.addWidget(lbl_build_info)

        body_layout.addWidget(self.nav_sidebar)

        # -------------------------------------------------------------------------
        # ZONE 3: MAIN WORKSPACE (Conversation & Command Composer)
        # -------------------------------------------------------------------------
        self.workspace_frame = QFrame(self.body_frame)
        self.workspace_frame.setObjectName("workspaceFrame")
        workspace_layout = QVBoxLayout(self.workspace_frame)
        workspace_layout.setContentsMargins(14, 12, 14, 12)
        workspace_layout.setSpacing(10)

        # Top workspace status row (Typing badge, tool kicker)
        top_status_row = QHBoxLayout()
        top_status_row.setContentsMargins(0, 0, 0, 0)
        top_status_row.setSpacing(8)

        # Floating Active Tool Chip
        self.tool_badge_frame = QWidget()
        self.tool_badge_frame.setStyleSheet("""
            QWidget {
                background: #1e293b;
                border: 1px solid #0ea5e9;
                border-radius: 6px;
            }
        """)
        tool_layout = QHBoxLayout(self.tool_badge_frame)
        tool_layout.setContentsMargins(10, 4, 12, 4)
        tool_layout.setSpacing(8)

        self.lbl_tool_kicker = QLabel("ACCESSING")
        self.lbl_tool_kicker.setStyleSheet("color: #38bdf8; font-size: 10px; font-weight: 700;")
        tool_layout.addWidget(self.lbl_tool_kicker)

        self.lbl_tool_name = QLabel("")
        self.lbl_tool_name.setStyleSheet("color: #f8fafc; font-size: 11px; font-weight: 600;")
        tool_layout.addWidget(self.lbl_tool_name)
        self.tool_badge_frame.hide()
        top_status_row.addWidget(self.tool_badge_frame)

        top_status_row.addStretch(1)

        # Typing Indicator Badge
        self.typing_badge = QLabel()
        self.typing_badge.setStyleSheet("""
            color: #00ffaa;
            background: rgba(0, 255, 170, 0.12);
            border: 1px solid rgba(0, 255, 170, 0.45);
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
        """)
        self.typing_badge.setText("⌨️ TYPING: INACTIVE")
        self.typing_badge.hide()
        top_status_row.addWidget(self.typing_badge)

        workspace_layout.addLayout(top_status_row)

        # Conversation History Scroll Area
        self.log_scroll = QScrollArea(self.workspace_frame)
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.log_scroll.setStyleSheet("""
            QScrollArea {
                background: #0d1117;
                border: 1px solid #21262d;
                border-radius: 8px;
            }
        """)

        self.log_widget = QWidget()
        self.log_widget.setStyleSheet("background: transparent;")
        self.log_layout = QVBoxLayout(self.log_widget)
        self.log_layout.setContentsMargins(12, 12, 12, 12)
        self.log_layout.setSpacing(10)
        self.log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.log_scroll.setWidget(self.log_widget)
        workspace_layout.addWidget(self.log_scroll, stretch=1)

        # Live Caption Label (Real-time Whisper STT feedback)
        self.lbl_caption = QLabel()
        self.lbl_caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_caption.setStyleSheet("""
            color: #38bdf8;
            font-size: 13px;
            font-weight: 500;
            background: rgba(14, 165, 233, 0.08);
            border: 1px solid rgba(14, 165, 233, 0.25);
            border-radius: 4px;
            padding: 6px 12px;
        """)
        self.lbl_caption.hide()
        workspace_layout.addWidget(self.lbl_caption)

        # -------------------------------------------------------------------------
        # ZONE 5: BOTTOM COMMAND COMPOSER
        # -------------------------------------------------------------------------
        # self.input_container preserves exactly 5 widgets in layout for verification tests!
        self.input_container = QWidget(self.workspace_frame)
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.cmd_input = QLineEdit()
        self.cmd_input.setProperty("class", "santraInput cyberInput")
        self.cmd_input.setPlaceholderText("Command SANTRA (e.g. 'Open Chrome', 'Explain binary search', 'Search files')...")
        self.cmd_input.returnPressed.connect(self._on_submit_command)
        input_layout.addWidget(self.cmd_input, stretch=1)

        self.btn_execute = QPushButton("EXECUTE ➜")
        self.btn_execute.setProperty("class", "primaryButton cyberButton")
        self.btn_execute.clicked.connect(self._on_submit_command)
        input_layout.addWidget(self.btn_execute)

        self.btn_palette = QPushButton("COMMANDS ▤")
        self.btn_palette.setProperty("class", "santraButton cyberButton")
        self.btn_palette.setToolTip("Open Categorized Command Palette & Capability Hub (Ctrl+K)")
        self.btn_palette.clicked.connect(self._open_command_palette)
        input_layout.addWidget(self.btn_palette)

        self.btn_sleep = QPushButton("🌙 SLEEP")
        self.btn_sleep.setProperty("class", "santraButton cyberButton")
        self.btn_sleep.setToolTip("Toggle low-resource Sleep Mode (wake with 'Santra' or Wake button)")
        self.btn_sleep.clicked.connect(self._on_sleep_clicked)
        input_layout.addWidget(self.btn_sleep)

        self.btn_mic = QPushButton("🎙️ TALK")
        self.btn_mic.setProperty("class", "santraButton cyberButton")
        self.btn_mic.clicked.connect(self._on_wake_clicked)
        input_layout.addWidget(self.btn_mic)

        workspace_layout.addWidget(self.input_container)
        body_layout.addWidget(self.workspace_frame, stretch=1)

        # -------------------------------------------------------------------------
        # ZONE 4: RIGHT TELEMETRY & STATUS SIDEBAR
        # -------------------------------------------------------------------------
        self.info_sidebar = QFrame(self.body_frame)
        self.info_sidebar.setObjectName("infoSidebar")
        self.info_sidebar.setFixedWidth(240)
        info_layout = QVBoxLayout(self.info_sidebar)
        info_layout.setContentsMargins(12, 14, 12, 14)
        info_layout.setSpacing(12)

        # Mini Arc Reactor Widget Centered
        reactor_container = QFrame()
        reactor_container.setProperty("class", "santraCard")
        reactor_layout = QVBoxLayout(reactor_container)
        reactor_layout.setContentsMargins(4, 4, 4, 4)
        reactor_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.arc_reactor = ArcReactorWidget(reactor_container)
        self.arc_reactor.setMinimumSize(140, 140)
        self.arc_reactor.setFixedSize(148, 148)
        reactor_layout.addWidget(self.arc_reactor)
        info_layout.addWidget(reactor_container)

        # System State Card
        card_state = QFrame()
        card_state.setProperty("class", "santraCard")
        card_state_layout = QVBoxLayout(card_state)
        card_state_layout.setContentsMargins(10, 8, 10, 8)
        card_state_layout.setSpacing(4)

        lbl_state_title = QLabel("SYSTEM STATE")
        lbl_state_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.12em;")
        card_state_layout.addWidget(lbl_state_title)

        self.lbl_side_state = QLabel("STANDBY")
        self.lbl_side_state.setStyleSheet("color: #38bdf8; font-size: 13px; font-weight: 700; letter-spacing: 0.05em;")
        card_state_layout.addWidget(self.lbl_side_state)

        lbl_engine_info = QLabel("Intent Router + LLM Brain")
        lbl_engine_info.setStyleSheet("color: #94a3b8; font-size: 10px;")
        card_state_layout.addWidget(lbl_engine_info)
        info_layout.addWidget(card_state)

        # Resource Monitor Card (CPU & RAM)
        card_res = QFrame()
        card_res.setProperty("class", "santraCard")
        card_res_layout = QVBoxLayout(card_res)
        card_res_layout.setContentsMargins(10, 8, 10, 8)
        card_res_layout.setSpacing(5)

        lbl_res_title = QLabel("RESOURCE MONITOR")
        lbl_res_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.12em;")
        card_res_layout.addWidget(lbl_res_title)

        # CPU Row
        cpu_row = QHBoxLayout()
        self.lbl_cpu = QLabel("CPU")
        self.lbl_cpu.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        cpu_row.addWidget(self.lbl_cpu)
        self.lbl_cpu_val = QLabel("0%")
        self.lbl_cpu_val.setStyleSheet("color: #f8fafc; font-size: 10px; font-weight: 700;")
        cpu_row.addWidget(self.lbl_cpu_val, alignment=Qt.AlignmentFlag.AlignRight)
        card_res_layout.addLayout(cpu_row)

        self.bar_cpu = QProgressBar()
        self.bar_cpu.setRange(0, 100)
        self.bar_cpu.setValue(10)
        self.bar_cpu.setFixedHeight(5)
        card_res_layout.addWidget(self.bar_cpu)

        # RAM Row
        ram_row = QHBoxLayout()
        self.lbl_ram = QLabel("RAM")
        self.lbl_ram.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
        ram_row.addWidget(self.lbl_ram)
        self.lbl_ram_val = QLabel("0%")
        self.lbl_ram_val.setStyleSheet("color: #f8fafc; font-size: 10px; font-weight: 700;")
        ram_row.addWidget(self.lbl_ram_val, alignment=Qt.AlignmentFlag.AlignRight)
        card_res_layout.addLayout(ram_row)

        self.bar_ram = QProgressBar()
        self.bar_ram.setRange(0, 100)
        self.bar_ram.setValue(45)
        self.bar_ram.setFixedHeight(5)
        card_res_layout.addWidget(self.bar_ram)

        info_layout.addWidget(card_res)

        # Audio & Microphone Telemetry Card
        card_audio = QFrame()
        card_audio.setProperty("class", "santraCard")
        card_audio_layout = QVBoxLayout(card_audio)
        card_audio_layout.setContentsMargins(10, 8, 10, 8)
        card_audio_layout.setSpacing(4)

        lbl_audio_title = QLabel("AUDIO HARDWARE")
        lbl_audio_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.12em;")
        card_audio_layout.addWidget(lbl_audio_title)

        self.lbl_side_audio_dev = QLabel("Realtek Mic / Noise Buds")
        self.lbl_side_audio_dev.setStyleSheet("color: #f8fafc; font-size: 10px; font-weight: 500;")
        card_audio_layout.addWidget(self.lbl_side_audio_dev)

        self.bar_audio_level = QProgressBar()
        self.bar_audio_level.setRange(0, 100)
        self.bar_audio_level.setValue(35)
        self.bar_audio_level.setFixedHeight(5)
        card_audio_layout.addWidget(self.bar_audio_level)

        lbl_audio_watcher = QLabel("● Hot-Swap Recovery: ACTIVE")
        lbl_audio_watcher.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 600;")
        card_audio_layout.addWidget(lbl_audio_watcher)

        info_layout.addWidget(card_audio)

        # Active Task Card
        card_task = QFrame()
        card_task.setProperty("class", "santraCard")
        card_task_layout = QVBoxLayout(card_task)
        card_task_layout.setContentsMargins(10, 8, 10, 8)
        card_task_layout.setSpacing(3)

        lbl_task_title = QLabel("ACTIVE PIPELINE")
        lbl_task_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.12em;")
        card_task_layout.addWidget(lbl_task_title)

        self.lbl_side_active_tool = QLabel("IDLE")
        self.lbl_side_active_tool.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: 600;")
        card_task_layout.addWidget(self.lbl_side_active_tool)
        info_layout.addWidget(card_task)

        # ALEE Autonomous Evolution Status Card
        card_evolution = QFrame()
        card_evolution.setProperty("class", "santraCard")
        card_evo_layout = QVBoxLayout(card_evolution)
        card_evo_layout.setContentsMargins(10, 8, 10, 8)
        card_evo_layout.setSpacing(4)

        lbl_evo_title = QLabel("ALEE EVOLUTION STATUS")
        lbl_evo_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.12em;")
        card_evo_layout.addWidget(lbl_evo_title)

        evo_stats_row = QHBoxLayout()
        self.lbl_evo_aliases = QLabel("Aliases: 11")
        self.lbl_evo_aliases.setStyleSheet("color: #38bdf8; font-size: 10px; font-weight: 600;")
        evo_stats_row.addWidget(self.lbl_evo_aliases)
        self.lbl_evo_knowledge = QLabel("Docs: 1")
        self.lbl_evo_knowledge.setStyleSheet("color: #a78bfa; font-size: 10px; font-weight: 600;")
        evo_stats_row.addWidget(self.lbl_evo_knowledge, alignment=Qt.AlignmentFlag.AlignRight)
        card_evo_layout.addLayout(evo_stats_row)

        evo_score_row = QHBoxLayout()
        self.lbl_evo_score = QLabel("Score: 100% PASS")
        self.lbl_evo_score.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 700;")
        evo_score_row.addWidget(self.lbl_evo_score)
        self.lbl_evo_guard = QLabel("LEARNING IDLE")
        self.lbl_evo_guard.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 600;")
        evo_score_row.addWidget(self.lbl_evo_guard, alignment=Qt.AlignmentFlag.AlignRight)
        card_evo_layout.addLayout(evo_score_row)

        evo_props_row = QHBoxLayout()
        self.lbl_evo_proposals = QLabel("Proposals: 0 Pending")
        self.lbl_evo_proposals.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")
        evo_props_row.addWidget(self.lbl_evo_proposals)
        card_evo_layout.addLayout(evo_props_row)

        btn_open_evo = QPushButton("⚡ OPEN EVOLUTION CENTER")
        btn_open_evo.setStyleSheet("""
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 4px;
            font-size: 9px;
            font-weight: 700;
            padding: 4px 6px;
            margin-top: 4px;
        """)
        btn_open_evo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_evo.clicked.connect(self._open_evolution_dialog)
        card_evo_layout.addWidget(btn_open_evo)

        info_layout.addWidget(card_evolution)

        info_layout.addStretch(1)
        body_layout.addWidget(self.info_sidebar)

        root_layout.addWidget(self.body_frame, stretch=1)

        # -------------------------------------------------------------------------
        # Cinematic Boot Sequence Overlay
        # -------------------------------------------------------------------------
        self.boot_overlay = BootOverlayWidget(self, on_finish_cb=self._on_boot_finished)
        self.boot_overlay.resize(self.size())
        self.boot_overlay.raise_()

    def _setup_shortcuts(self):
        # Spacebar activates voice wake when input is not focused
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(self._on_space_pressed)

        # Screen Intelligence shortcut
        self.shortcut_screen = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.shortcut_screen.activated.connect(self._open_screen_intelligence)

        # AI Settings shortcut
        self.shortcut_ai = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self.shortcut_ai.activated.connect(self._open_ai_settings)

        # Virtual Testing Room shortcut
        self.shortcut_lab = QShortcut(QKeySequence("Ctrl+Shift+L"), self)
        self.shortcut_lab.activated.connect(self._open_virtual_lab)

        # Command Palette shortcut (Ctrl+K)
        self.shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_palette.activated.connect(self._open_command_palette)

        # Pronunciation & Accent Intelligence shortcut
        self.shortcut_pronunciation = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.shortcut_pronunciation.activated.connect(self._open_pronunciation_settings)

        # Spotify Suite shortcut
        self.shortcut_spotify = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self.shortcut_spotify.activated.connect(self._open_spotify_panel)

        # Project Intelligence shortcut
        self.shortcut_code = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.shortcut_code.activated.connect(self._open_project_intelligence)

        # Universal Research shortcut (Ctrl+Shift+R)
        self.shortcut_research = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.shortcut_research.activated.connect(self._open_research_panel)

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
            logger.error(f"Failed to open Research Panel: {e}", exc_info=True)

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
            logger.error(f"Failed to open Project Intelligence Panel: {e}", exc_info=True)

    def _open_spotify_panel(self):
        try:
            from ui.panels.spotify_panel import SpotifyDialog
            dialog = SpotifyDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Spotify Dialog: {e}", exc_info=True)

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
                "test_speakers": self._test_audio_speakers,
                "hianime": lambda: self.sig_command_submitted.emit("open hianime"),
                "chatgpt": lambda: self.sig_command_submitted.emit("open chatgpt"),
                "wake": self._on_wake_clicked,
            }
            dialog = CommandPaletteDialog(self, callbacks=callbacks, on_command_submit=lambda phrase: self.sig_command_submitted.emit(phrase))
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Command Palette: {e}", exc_info=True)

    def _open_evolution_dialog(self):
        try:
            from ui.evolution_dialog import EvolutionCenterDialog
            dialog = EvolutionCenterDialog(self)
            dialog.data_changed.connect(self._refresh_evolution_telemetry)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Evolution Center: {e}", exc_info=True)

    def _refresh_evolution_telemetry(self):
        try:
            from core.evolution.scheduler import evolution_scheduler
            report = evolution_scheduler.run_maintenance_now()
            self._on_evolution_updated(report)
        except Exception as e:
            logger.debug(f"Evolution telemetry refresh error: {e}")

    def _test_audio_speakers(self):
        self.sig_command_submitted.emit("test audio speakers")

    def _open_screen_intelligence(self):
        try:
            from ui.panels.screen_intelligence_panel import ScreenIntelligencePanel
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dialog = QDialog(self)
            dialog.setWindowTitle("SANTRA — Visual Screen Intelligence")
            dialog.resize(760, 560)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(10, 10, 10, 10)
            from core.ai.provider_manager import ProviderManager
            prov_mgr = getattr(self, "provider_manager", None) or ProviderManager()
            panel = ScreenIntelligencePanel(dialog, on_speech_output_cb=getattr(self, "speak_cb", None), provider_manager=prov_mgr)
            layout.addWidget(panel)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Screen Intelligence: {e}")

    def _open_ai_settings(self):
        try:
            from ui.panels.ai_settings_dialog import AISettingsDialog
            dialog = AISettingsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open AI Settings: {e}")

    def _open_pronunciation_settings(self):
        try:
            from ui.panels.pronunciation_settings_dialog import PronunciationSettingsDialog
            dialog = PronunciationSettingsDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Pronunciation Settings: {e}", exc_info=True)

    def _open_virtual_lab(self):
        try:
            from ui.panels.virtual_lab_panel import VirtualLabDialog
            dialog = VirtualLabDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Virtual Lab: {e}", exc_info=True)

    def _on_space_pressed(self):
        if not self.cmd_input.hasFocus():
            self._on_wake_clicked()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "boot_overlay") and self.boot_overlay.isVisible():
            self.boot_overlay.resize(self.size())

    def _update_telemetry(self):
        """Low-frequency system metrics update without blocking GUI thread."""
        if not self.isVisible() or self.isMinimized():
            return

        if psutil:
            try:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                self.bar_cpu.setValue(int(cpu))
                self.lbl_cpu_val.setText(f"{int(cpu)}%")
                self.bar_ram.setValue(int(ram))
                self.lbl_ram_val.setText(f"{int(ram)}%")
            except Exception:
                pass

    def _on_hud_tick(self):
        """Smooth signal level interpolation."""
        diff = self._target_signal_level - self._signal_level
        if abs(diff) > 0.01:
            self._signal_level += diff * 0.15
            if hasattr(self, "bar_audio_level"):
                self.bar_audio_level.setValue(int(self._signal_level * 100))

    def paintEvent(self, event):
        """High-performance paint: background handled by stylesheet; no expensive scanline loops."""
        super().paintEvent(event)

    def _on_boot_finished(self):
        """Called when startup boot sequence finishes."""
        if hasattr(self, "boot_overlay"):
            self.boot_overlay.hide()
        self._on_status_changed("STANDBY")

    def _wire_signals(self):
        self.sig_status_changed.connect(self._on_status_changed)
        self.sig_mic_state_changed.connect(self._on_mic_state_changed)
        self.sig_sys_stats_updated.connect(self._on_sys_stats_updated)
        self.sig_speech_text_updated.connect(self._on_speech_text_updated)
        self.sig_last_action_updated.connect(self._on_last_action_updated)
        self.sig_pipeline_stage_updated.connect(self._on_pipeline_stage_updated)
        self.sig_history_updated.connect(self._on_history_updated)
        self.sig_show_permission_dialog.connect(self._on_show_permission_dialog)
        self.sig_speech_debug_updated.connect(self._on_speech_debug_updated)
        self.sig_audio_amplitude_updated.connect(self.arc_reactor.set_audio_amplitude)
        self.sig_camera_state_updated.connect(self._on_camera_state_updated)
        self.sig_gesture_detected.connect(self._on_gesture_detected)
        self.sig_typing_state_changed.connect(self._update_typing_badge)
        self.sig_show_message_approval.connect(self._show_message_approval_dialog)
        self.sig_ai_mode_changed.connect(self._on_ai_mode_changed)
        self.sig_evolution_updated.connect(self._on_evolution_updated)

        # Wire typing coordinator callback
        try:
            from core.typing.typing_coordinator import typing_coordinator
            typing_coordinator.register_state_callback(
                lambda state, details: self.sig_typing_state_changed.emit(state.value, details)
            )
        except Exception as e:
            logger.debug(f"Typing coordinator callback registration: {e}")

    def _on_evolution_updated(self, data: dict):
        """Thread-safe update of ALEE telemetry badge."""
        if not data:
            return
        active_aliases = data.get("active_aliases_count", 0)
        db_stats = data.get("database_stats") or {}
        total_knowledge = db_stats.get("total_knowledge_items", 0)
        verified_skills = db_stats.get("verified_skills", 0)
        benchmarks = data.get("benchmarks") or {}
        score = benchmarks.get("score", 100.0)
        status = data.get("status", "HEALTHY")

        if hasattr(self, "lbl_evo_aliases"):
            self.lbl_evo_aliases.setText(f"Aliases: {active_aliases}")
        if hasattr(self, "lbl_evo_knowledge"):
            if "verified_skills" in db_stats:
                self.lbl_evo_knowledge.setText(f"Docs: {total_knowledge} · Skills: {verified_skills}")
            else:
                self.lbl_evo_knowledge.setText(f"Docs: {total_knowledge}")
        if hasattr(self, "lbl_evo_score"):
            self.lbl_evo_score.setText(f"Score: {int(score)}% PASS" if score >= 90 else f"Score: {int(score)}%")
        if hasattr(self, "lbl_evo_guard"):
            if status == "PAUSED_VOICE":
                self.lbl_evo_guard.setText("PAUSED (VOICE)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            elif status == "PAUSED_GAMING":
                self.lbl_evo_guard.setText("PAUSED (GAME)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            elif status == "PAUSED_BATTERY":
                self.lbl_evo_guard.setText("PAUSED (BATT)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            elif status == "PAUSED_HIGH_LOAD":
                self.lbl_evo_guard.setText("PAUSED (LOAD)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            elif status == "PAUSED_CONSTRAINTS":
                self.lbl_evo_guard.setText("PAUSED (RES)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            elif status == "DEGRADED":
                self.lbl_evo_guard.setText("DEGRADED")
                self.lbl_evo_guard.setStyleSheet("color: #ef4444; font-size: 9px; font-weight: 600;")
            else:
                self.lbl_evo_guard.setText("LEARNING IDLE")
                self.lbl_evo_guard.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 600;")

        pending_props = data.get("pending_proposals_count", db_stats.get("pending_proposals_count", 0))
        if hasattr(self, "lbl_evo_proposals"):
            self.lbl_evo_proposals.setText(f"Proposals: {pending_props} Pending")
            if pending_props > 0:
                self.lbl_evo_proposals.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            else:
                self.lbl_evo_proposals.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 600;")

    def _update_typing_badge(self, state: str, details: dict):
        if state in ["listening", "active", "transcribing", "text_ready", "inserting"]:
            app = details.get("app", "Active Window")
            mode = details.get("mode", "continuous")
            self.typing_badge.setText(f"⌨️ TYPING: {app.upper()} [{mode.upper()}]")
            self.typing_badge.setStyleSheet("""
                color: #00ffaa;
                background: rgba(0, 255, 170, 0.15);
                border: 1px solid rgba(0, 255, 170, 0.6);
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
            """)
            self.typing_badge.show()
        elif state == "paused":
            self.typing_badge.setText("⌨️ TYPING: PAUSED")
            self.typing_badge.setStyleSheet("""
                color: #ffaa00;
                background: rgba(255, 170, 0, 0.15);
                border: 1px solid rgba(255, 170, 0, 0.6);
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
            """)
            self.typing_badge.show()
        else:
            self.typing_badge.hide()

    def _show_message_approval_dialog(self, target_app: str, target_control: str, draft_text: str, on_confirm_cb):
        try:
            from ui.panels.message_approval_dialog import MessageApprovalDialog
            dialog = MessageApprovalDialog(
                target_app=target_app,
                target_control=target_control,
                draft_text=draft_text,
                parent=self,
                on_confirm_cb=on_confirm_cb
            )
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to open Message Approval Dialog: {e}", exc_info=True)

    def _on_camera_state_updated(self, event):
        """Updates UI with real camera telemetry and state."""
        if hasattr(event, "state"):
            state_val = event.state.value if hasattr(event.state, "value") else str(event.state)
            self._camera_state_str = state_val
            is_active = (state_val == "ACTIVE")
            self.arc_reactor.set_camera_active(is_active)
            if is_active and hasattr(event, "fps_capture"):
                self.lbl_tool_kicker.setText("PERCEPTION")
                self.lbl_tool_name.setText(f"CAMERA ACTIVE ({int(event.fps_capture)} FPS)")
                self.tool_badge_frame.show()
                QTimer.singleShot(2500, self.tool_badge_frame.hide)

    def _on_gesture_detected(self, event):
        """Triggers subtle Arc Reactor pulse on confirmed gesture."""
        if hasattr(event, "gesture"):
            g_name = event.gesture.value if hasattr(event.gesture, "value") else str(event.gesture)
            self.arc_reactor.trigger_gesture_pulse(g_name)
            self.lbl_tool_kicker.setText("GESTURE")
            self.lbl_tool_name.setText(f"{g_name} ({getattr(event, 'hand', 'Hand')})")
            self.tool_badge_frame.show()
            QTimer.singleShot(1800, self.tool_badge_frame.hide)

    def _on_wake_clicked(self):
        if self.trigger_wakeword_cb:
            self.trigger_wakeword_cb()

    def _on_sleep_clicked(self):
        if self._current_state == JarvisUIState.SLEEPING:
            self._on_wake_clicked()
        elif self.toggle_sleep_cb:
            self.toggle_sleep_cb()
        else:
            self.sig_command_submitted.emit("enter sleep mode")

    def _on_submit_command(self):
        cmd = self.cmd_input.text().strip()
        if cmd:
            self.cmd_input.clear()
            self._add_turn("user", cmd)
            if cmd.lower() in ["open virtual lab", "open virtual testing room", "virtual lab", "virtual testing room", "test lab"]:
                self._open_virtual_lab()
                return
            self.sig_command_submitted.emit(cmd)

    def _add_or_update_turn(self, role: str, text: str, turn_id: Optional[str] = None, is_final: bool = False):
        """Idempotent conversation turn addition and in-place streaming card update."""
        if not text or not text.strip():
            return

        # Do not render transient query notifications as permanent chat cards
        if text.strip() in ["Querying NVIDIA Nemotron...", "Thinking...", "Processing..."]:
            return

        now_str = time.strftime("%H:%M:%S")

        # 1. In-place update for ongoing streaming or finalized turns
        if turn_id:
            if turn_id in self._finalized_turn_ids and not is_final:
                logger.debug(f"[DUPLICATE_EVENT_IGNORED] Turn {turn_id} already finalized. Ignoring duplicate event.")
                return

            if turn_id in self._turn_widgets:
                turn, card = self._turn_widgets[turn_id]
                turn["text"] = text
                if is_final:
                    self._finalized_turn_ids.add(turn_id)
                self._update_card_body(card, text)
                return

        # 2. Check for duplicate identical turn within 1.0s window for unkeyed turns
        if not turn_id and self._turns and self._turns[-1]["role"] == role and self._turns[-1]["text"] == text:
            logger.debug(f"[DUPLICATE_EVENT_IGNORED] Unkeyed duplicate message suppressed.")
            return

        # 3. Append new turn
        turn = {"role": role, "text": text, "timestamp": now_str, "turn_id": turn_id}
        self._turns.append(turn)
        if len(self._turns) > 60:
            self._turns = self._turns[-60:]

        card = self._append_turn_widget(turn)
        if turn_id:
            self._turn_widgets[turn_id] = (turn, card)
            if is_final:
                self._finalized_turn_ids.add(turn_id)

        # Maintain bounded widget count
        while self.log_layout.count() > 60:
            item = self.log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_card_body(self, card: QFrame, new_text: str):
        """Updates text content inside an existing turn card in-place."""
        card_layout = card.layout()
        if not card_layout:
            return
        # Find existing body label if present
        for i in range(card_layout.count()):
            item = card_layout.itemAt(i)
            if item and item.widget() and getattr(item.widget(), "_is_body_label", False):
                item.widget().setText(new_text)
                return
        # Fallback: remove old body items and append new label
        while card_layout.count() > 1:
            item = card_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        lbl_body = QLabel(new_text)
        lbl_body._is_body_label = True
        lbl_body.setWordWrap(True)
        lbl_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_body.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 500; line-height: 1.4;")
        card_layout.addWidget(lbl_body)

    def _add_turn(self, role: str, text: str):
        """Backwards compatible alias for _add_or_update_turn."""
        self._add_or_update_turn(role, text)

    def _rebuild_log_view(self):
        """Rebuilds complete view if requested (e.g. on full history load)."""
        while self.log_layout.count():
            item = self.log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for turn in self._turns:
            self._append_turn_widget(turn)

    def _append_turn_widget(self, turn: dict):
        """Creates and appends a single high-contrast message card."""
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
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                }
            """)
            header_text = f"[{ts}] YOU  ➜"
            header_color = "#38bdf8"
        else:
            card.setStyleSheet("""
                QFrame {
                    background-color: #0f172a;
                    border: 1px solid #0284c7;
                    border-radius: 8px;
                }
            """)
            header_text = f"[{ts}] SANTRA (Autonomous)  ➜"
            header_color = "#0ea5e9"

        # Header Row (Title + Copy Button)
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        lbl_hdr = QLabel(header_text)
        lbl_hdr.setStyleSheet(f"color: {header_color}; font-size: 11px; font-weight: 700; letter-spacing: 0.05em;")
        hdr_row.addWidget(lbl_hdr)
        hdr_row.addStretch(1)

        btn_copy = QPushButton("📋 Copy")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 10px;
                padding: 2px 6px;
            }
            QPushButton:hover {
                color: #f8fafc;
                background: #334155;
                border-radius: 3px;
            }
        """)
        btn_copy.clicked.connect(lambda checked=False, t=text: QApplication.clipboard().setText(t))
        hdr_row.addWidget(btn_copy)
        card_layout.addLayout(hdr_row)

        # Message Body (Handles Markdown code blocks gracefully)
        if "```" in text:
            parts = text.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    # Code block
                    code_lines = part.strip().splitlines()
                    lang = ""
                    if code_lines and code_lines[0].lower() in ["python", "py", "json", "bash", "powershell", "cpp", "c", "html", "css", "javascript", "js"]:
                        lang = code_lines[0]
                        clean_code = "\n".join(code_lines[1:])
                    else:
                        clean_code = part.strip()

                    code_container = QFrame()
                    code_container.setStyleSheet("""
                        background-color: #020617;
                        border: 1px solid #1e293b;
                        border-radius: 6px;
                    """)
                    cc_layout = QVBoxLayout(code_container)
                    cc_layout.setContentsMargins(8, 6, 8, 6)
                    cc_layout.setSpacing(4)

                    if lang:
                        lbl_lang = QLabel(lang.upper())
                        lbl_lang.setStyleSheet("color: #0ea5e9; font-size: 9px; font-weight: 700;")
                        cc_layout.addWidget(lbl_lang)

                    lbl_code = QLabel(clean_code)
                    lbl_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    lbl_code.setStyleSheet("""
                        color: #7dd3fc;
                        font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace;
                        font-size: 12px;
                        line-height: 1.4;
                    """)
                    cc_layout.addWidget(lbl_code)
                    card_layout.addWidget(code_container)
                else:
                    stripped = part.strip()
                    if stripped:
                        lbl_txt = QLabel(stripped)
                        lbl_txt.setWordWrap(True)
                        lbl_txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                        lbl_txt.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 500; line-height: 1.4;")
                        card_layout.addWidget(lbl_txt)
        else:
            lbl_body = QLabel(text)
            lbl_body._is_body_label = True
            lbl_body.setWordWrap(True)
            lbl_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_body.setStyleSheet("""
                color: #f1f5f9;
                font-size: 13px;
                font-weight: 500;
                line-height: 1.4;
            """)
            card_layout.addWidget(lbl_body)

        self.log_layout.addWidget(card)

        # Smooth autoscroll to bottom
        QTimer.singleShot(20, lambda: self.log_scroll.verticalScrollBar().setValue(
            self.log_scroll.verticalScrollBar().maximum()
        ))
        return card

    def _on_status_changed(self, status: str):
        self._status_text = status.upper()
        self._current_state = map_runtime_status_to_ui_state(status)
        self.arc_reactor.set_state(self._current_state)

        # Update Header Status Pill
        pill_color = "#38bdf8"
        pill_bg = "rgba(14, 165, 233, 0.15)"
        pill_border = "rgba(14, 165, 233, 0.45)"

        if self._current_state == JarvisUIState.SLEEPING:
            pill_color = "#a78bfa"
            pill_bg = "rgba(139, 92, 246, 0.15)"
            pill_border = "rgba(139, 92, 246, 0.45)"
            self.btn_mic.setText("⚡ WAKE")
            self.btn_sleep.setText("⚡ WAKE")
            self.btn_quick_sleep.setText("⚡ WAKE")
            self._target_signal_level = 0.10
            self.lbl_caption.hide()
        elif self._current_state in [JarvisUIState.LISTENING, JarvisUIState.TRANSCRIBING]:
            pill_color = "#06b6d4"
            pill_bg = "rgba(6, 182, 212, 0.2)"
            pill_border = "rgba(6, 182, 212, 0.6)"
            self.btn_mic.setText("🎙️ TALK")
            self.btn_sleep.setText("🌙 SLEEP")
            self.btn_quick_sleep.setText("🌙 SLEEP")
            self._target_signal_level = 0.95
            self.lbl_caption.show()
        elif self._current_state in [JarvisUIState.THINKING, JarvisUIState.PROCESSING, JarvisUIState.UNDERSTANDING, JarvisUIState.EXECUTING]:
            pill_color = "#f59e0b"
            pill_bg = "rgba(245, 158, 11, 0.15)"
            pill_border = "rgba(245, 158, 11, 0.5)"
            self._target_signal_level = 0.75
        elif self._current_state == JarvisUIState.SPEAKING:
            pill_color = "#10b981"
            pill_bg = "rgba(16, 185, 129, 0.2)"
            pill_border = "rgba(16, 185, 129, 0.5)"
            self._target_signal_level = 0.90
        elif self._current_state == JarvisUIState.WAITING_FOR_NVIDIA:
            pill_color = "#c084fc"
            pill_bg = "rgba(192, 132, 252, 0.2)"
            pill_border = "rgba(192, 132, 252, 0.6)"
            self._target_signal_level = 0.85
        elif self._current_state == JarvisUIState.STREAMING_RESPONSE:
            pill_color = "#38bdf8"
            pill_bg = "rgba(56, 189, 248, 0.25)"
            pill_border = "rgba(56, 189, 248, 0.65)"
            self._target_signal_level = 0.95
        elif self._current_state in [JarvisUIState.ROUTING, JarvisUIState.VALIDATING_INPUT]:
            pill_color = "#38bdf8"
            pill_bg = "rgba(14, 165, 233, 0.15)"
            pill_border = "rgba(14, 165, 233, 0.45)"
            self._target_signal_level = 0.70
        elif self._current_state in [JarvisUIState.TIMED_OUT, JarvisUIState.CANCELLED]:
            pill_color = "#f97316"
            pill_bg = "rgba(249, 115, 22, 0.18)"
            pill_border = "rgba(249, 115, 22, 0.55)"
            self._target_signal_level = 0.40
        elif self._current_state == JarvisUIState.COMPLETED:
            pill_color = "#10b981"
            pill_bg = "rgba(16, 185, 129, 0.2)"
            pill_border = "rgba(16, 185, 129, 0.5)"
            self._target_signal_level = 0.50
        elif self._current_state == JarvisUIState.ERROR:
            pill_color = "#ef4444"
            pill_bg = "rgba(239, 68, 68, 0.15)"
            pill_border = "rgba(239, 68, 68, 0.5)"
        else:
            self.btn_mic.setText("🎙️ TALK")
            self.btn_sleep.setText("🌙 SLEEP")
            self.btn_quick_sleep.setText("🌙 SLEEP")
            self._target_signal_level = 0.35
            self.lbl_caption.hide()

        self.lbl_status_pill.setText(f"● {self._status_text}")
        self.lbl_status_pill.setStyleSheet(f"""
            color: {pill_color};
            background-color: {pill_bg};
            border: 1px solid {pill_border};
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.08em;
        """)

        if hasattr(self, "lbl_side_state"):
            self.lbl_side_state.setText(self._status_text)
            self.lbl_side_state.setStyleSheet(f"color: {pill_color}; font-size: 13px; font-weight: 700;")

    def _on_mic_state_changed(self, is_active: bool):
        if is_active:
            self._on_status_changed("LISTENING")
        else:
            self._on_status_changed("STANDBY")

    def _on_sys_stats_updated(self, cpu: float, ram: float):
        if hasattr(self, "bar_cpu"):
            self.bar_cpu.setValue(int(cpu))
            self.lbl_cpu_val.setText(f"{int(cpu)}%")
        if hasattr(self, "bar_ram"):
            self.bar_ram.setValue(int(ram))
            self.lbl_ram_val.setText(f"{int(ram)}%")

    def _on_speech_text_updated(self, text: str):
        self._caption_text = text
        if text:
            curr_st = getattr(self, "_current_status", "")
            if curr_st in ["SPEAKING", "SYNTHESIZING"]:
                self.lbl_caption.setText(f"Speaking: \"{text}\"")
            else:
                self.lbl_caption.setText(f"{text}")
            self.lbl_caption.show()
        else:
            self.lbl_caption.hide()

    def _on_ai_mode_changed(self, enabled: bool):
        if not hasattr(self, "lbl_ai_mode_badge"):
            return
        if enabled:
            self.lbl_ai_mode_badge.setText("✦ AI MODE")
            self.lbl_ai_mode_badge.setStyleSheet("""
                color: #c084fc;
                background-color: rgba(168, 85, 247, 0.15);
                border: 1px solid rgba(168, 85, 247, 0.5);
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.08em;
            """)
        else:
            self.lbl_ai_mode_badge.setText("● NORMAL MODE")
            self.lbl_ai_mode_badge.setStyleSheet("""
                color: #64748b;
                background-color: rgba(30, 41, 59, 0.7);
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.08em;
            """)

    def _on_pipeline_stage_updated(self, raw: str, norm: str, intent: str, exec_str: str, resp: str, state: str, turn_id: str = ""):
        if raw and not any(t["text"] == raw for t in self._turns if t["role"] == "user"):
            self._add_or_update_turn("user", raw, turn_id=f"user_{turn_id}" if turn_id else None, is_final=True)
        if resp and resp.strip() not in ["Querying NVIDIA Nemotron...", "Thinking...", "Processing..."]:
            # Suppress internal stage progress strings from overwriting chat card
            if resp.strip() in [
                "Research completed.", "Formulating research plan...", "Executing searches...",
                "Extracting evidence...", "Synthesizing research answer with NVIDIA Nemotron...",
                "Streaming cited research answer..."
            ]:
                return
            is_final = (state.lower() in ["speaking", "completed", "done", "standby"])
            self._add_or_update_turn("jarvis", resp, turn_id=turn_id if turn_id else None, is_final=is_final)

        if exec_str:
            self._active_tool = exec_str
            self.lbl_tool_name.setText(exec_str.upper())
            self.tool_badge_frame.show()
            if hasattr(self, "lbl_side_active_tool"):
                self.lbl_side_active_tool.setText(exec_str.upper())
            QTimer.singleShot(3500, self.tool_badge_frame.hide)

    def _on_last_action_updated(self, action: str, success: bool, msg: str):
        if action:
            self._active_tool = action
            self.lbl_tool_name.setText(action.upper())
            self.tool_badge_frame.show()
            if hasattr(self, "lbl_side_active_tool"):
                self.lbl_side_active_tool.setText(action.upper())
            QTimer.singleShot(3500, self.tool_badge_frame.hide)

    def _on_history_updated(self, history: list):
        pass

    def _on_show_permission_dialog(self, action: str, message: str):
        reply = QMessageBox.question(
            self,
            "Security Authorization Required",
            f"SANTRA is requesting confirmation to execute:\n\nAction: {action}\nDetails: {message}\n\nDo you authorize this operation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        self.sig_permission_resolved.emit(reply == QMessageBox.StandardButton.Yes)

    def _on_speech_debug_updated(self, text: str, conf: float, lang: str, dur: float):
        if text and text.strip():
            self._caption_text = text.strip()
            self.lbl_caption.setText(f"Transcribing: \"{text.strip()}\"")
            self.lbl_caption.show()

    def changeEvent(self, event):
        """Throttle timers when window is minimized."""
        super().changeEvent(event)
        if self.isMinimized():
            if hasattr(self, "_telemetry_timer"):
                self._telemetry_timer.stop()
            if hasattr(self, "_hud_timer"):
                self._hud_timer.stop()
        else:
            if hasattr(self, "_telemetry_timer") and not self._telemetry_timer.isActive():
                self._telemetry_timer.start(1500)
            if hasattr(self, "_hud_timer") and not self._hud_timer.isActive():
                self._hud_timer.start(33)

    def hideEvent(self, event):
        """Throttle timers when window is hidden."""
        super().hideEvent(event)
        if hasattr(self, "_telemetry_timer"):
            self._telemetry_timer.stop()
        if hasattr(self, "_hud_timer"):
            self._hud_timer.stop()

    def showEvent(self, event):
        """Resume timers when window is restored."""
        super().showEvent(event)
        if hasattr(self, "_telemetry_timer") and not self._telemetry_timer.isActive():
            self._telemetry_timer.start(1500)
        if hasattr(self, "_hud_timer") and not self._hud_timer.isActive():
            self._hud_timer.start(33)

    def closeEvent(self, event):
        # Hide window to system tray instead of destroying application
        event.ignore()
        self.hide()
        self.sig_closed.emit()
