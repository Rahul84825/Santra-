"""
SANTRA — Categorized Command Palette & Capability Hub
Authoritative, searchable capability launcher with structured command lifecycle,
real-time status feedback, and zero-crash exception isolation.
"""

import time
import uuid
import logging
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QWidget, QFrame, QGridLayout,
    QProgressBar, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor

from core.tool_registry import tool_registry, ToolDefinition

logger = logging.getLogger("Santra.CommandPalette")


class CommandLifecycleState(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class CommandExecutionRecord:
    command_id: str
    command_name: str
    status: CommandLifecycleState = CommandLifecycleState.IDLE
    start_time: Optional[float] = None
    completion_time: Optional[float] = None
    result_summary: str = ""
    error_details: str = ""
    verification_status: str = "PENDING"
    cancellation_state: bool = False


class CommandCard(QFrame):
    """Modern UI card representing a registered capability with execution state."""

    execute_requested = pyqtSignal(str, str)  # (action_key, command_phrase)

    def __init__(self, key: str, title: str, category: str, description: str,
                 shortcut: str = "", risk: str = "LOW", is_hub: bool = False, parent=None):
        super().__init__(parent)
        self.key = key
        self.title = title
        self.category = category
        self.description = description
        self.shortcut = shortcut
        self.risk = risk
        self.is_hub = is_hub
        self._record: Optional[CommandExecutionRecord] = None

        self.setObjectName("commandCard")
        self.setStyleSheet("""
            QFrame#commandCard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QFrame#commandCard:hover {
                background-color: #243248;
                border: 1px solid #0ea5e9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Top row: Title + Badges
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("color: #f8fafc; font-size: 13px; font-weight: 600;")
        top_row.addWidget(self.lbl_title)

        if shortcut:
            lbl_sc = QLabel(shortcut)
            lbl_sc.setStyleSheet("""
                color: #38bdf8;
                background-color: rgba(14, 165, 233, 0.12);
                border: 1px solid rgba(14, 165, 233, 0.3);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 600;
            """)
            top_row.addWidget(lbl_sc)

        top_row.addStretch()

        # Category pill
        lbl_cat = QLabel(category.upper())
        lbl_cat.setStyleSheet("""
            color: #94a3b8;
            background-color: #0f172a;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.05em;
        """)
        top_row.addWidget(lbl_cat)

        # Risk badge
        if risk != "LOW":
            lbl_risk = QLabel(f"⚠️ {risk}")
            lbl_risk.setStyleSheet("""
                color: #fbbf24;
                background-color: rgba(245, 158, 11, 0.12);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9px;
                font-weight: 700;
            """)
            top_row.addWidget(lbl_risk)

        layout.addLayout(top_row)

        # Description
        self.lbl_desc = QLabel(description)
        self.lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)

        # Bottom row: Status & Action
        bot_row = QHBoxLayout()
        bot_row.setSpacing(8)

        self.lbl_status = QLabel("● READY")
        self.lbl_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600;")
        bot_row.addWidget(self.lbl_status)

        bot_row.addStretch()

        self.btn_run = QPushButton("LAUNCH HUB" if is_hub else "RUN ➜")
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                border: none;
                border-radius: 5px;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0284c7;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #64748b;
            }
        """)
        self.btn_run.clicked.connect(self._on_click)
        bot_row.addWidget(self.btn_run)

        layout.addLayout(bot_row)

    def _on_click(self):
        self.execute_requested.emit(self.key, self.title)

    def set_lifecycle_state(self, state: CommandLifecycleState, message: str = ""):
        color_map = {
            CommandLifecycleState.IDLE: ("#10b981", "● READY"),
            CommandLifecycleState.READY: ("#10b981", "● READY"),
            CommandLifecycleState.VALIDATING: ("#38bdf8", "⏳ VALIDATING"),
            CommandLifecycleState.QUEUED: ("#38bdf8", "⏱️ QUEUED"),
            CommandLifecycleState.RUNNING: ("#f59e0b", "⚡ RUNNING..."),
            CommandLifecycleState.VERIFYING: ("#38bdf8", "🔍 VERIFYING"),
            CommandLifecycleState.SUCCEEDED: ("#10b981", "✓ SUCCEEDED"),
            CommandLifecycleState.FAILED: ("#ef4444", "✕ FAILED"),
            CommandLifecycleState.BLOCKED: ("#f59e0b", "⛔ BLOCKED"),
            CommandLifecycleState.CANCELLED: ("#94a3b8", "⊘ CANCELLED"),
            CommandLifecycleState.UNVERIFIED: ("#94a3b8", "○ UNVERIFIED"),
        }
        col, txt = color_map.get(state, ("#94a3b8", str(state.value)))
        if message:
            txt = f"{txt}: {message[:40]}"
        self.lbl_status.setText(txt)
        self.lbl_status.setStyleSheet(f"color: {col}; font-size: 11px; font-weight: 600;")

        if state in (CommandLifecycleState.RUNNING, CommandLifecycleState.QUEUED):
            self.btn_run.setEnabled(False)
        else:
            self.btn_run.setEnabled(True)


class CommandPaletteDialog(QDialog):
    """Categorized Modern Command Palette & Capability Hub for SANTRA."""

    sig_command_dispatched = pyqtSignal(str)

    TOOL_DISPATCH_PHRASES = {
        "research": "open research hub",
        "code": "open project intelligence",
        "lab": "open virtual lab",
        "ai": "open ai settings",
        "screen": "open screen intelligence",
        "accent": "open accent settings",
        "spotify": "open spotify panel",
        "test_speakers": "test audio speakers",
        "hianime": "open hianime",
        "chatgpt": "open chatgpt",
        "wake": "trigger wake word",
        "open_app": "open notepad",
        "application.launch": "launch notepad",
        "close_app": "close notepad",
        "switch_window": "list open windows",
        "application.properties": "check application properties",
        "application.install_dir": "open application install directory",
        "application.settings": "open application settings",
        "application.metadata": "application metadata",
        "application.status": "application status",
        "application.list_installed": "list installed applications",
        "application.refresh": "refresh applications",
        "desktop.get_context": "get screen context",
        "desktop.enter_text": "type text into search bar",
        "desktop.search_in_app": "search in this application",
        "desktop.replace_selection": "replace text",
        "desktop.send_message": "send message",
        "open_browser": "open chrome",
        "open_website": "open google.com",
        "browser_tab_control": "switch tab",
        "browser_action": "browser refresh",
        "web_search": "search python documentation",
        "youtube_search": "search youtube",
        "site_search": "search google",
        "local_search": "find files",
        "open_search_result": "open first search result",
        "verify_page_loaded": "check page loaded",
        "write_to_notepad": "open notepad",
        "media_control": "check volume",
        "youtube_control": "youtube play",
        "spotify_control": "spotify status",
    }

    def __init__(self, parent=None, callbacks: dict = None, on_command_submit: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.callbacks = callbacks or {}
        self.on_command_submit = on_command_submit
        self.setWindowTitle("SANTRA — Command Palette & Capability Hub")
        self.resize(860, 640)
        self.setMinimumSize(740, 520)
        self.setModal(True)

        self.cards: List[CommandCard] = []
        self._execution_history: Dict[str, CommandExecutionRecord] = {}
        self._active_category = "ALL"

        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QLineEdit#paletteSearch {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 13px;
                padding: 10px 14px;
            }
            QLineEdit#paletteSearch:focus {
                border: 1px solid #0ea5e9;
                background-color: #0d1526;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QWidget#scrollContent {
                background: transparent;
            }
            QPushButton.filterBtn {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 14px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
            }
            QPushButton.filterBtn:hover {
                background-color: #243248;
                color: #f8fafc;
            }
            QPushButton.filterBtn:checked {
                background-color: #0ea5e9;
                border: 1px solid #0284c7;
                color: #ffffff;
            }
        """)

        self._init_ui()
        self._load_registered_commands()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(12)

        # Header bar
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("SANTRA COMMAND PALETTE")
        title_lbl.setStyleSheet("color: #f8fafc; font-size: 16px; font-weight: 700; letter-spacing: 0.05em;")
        title_box.addWidget(title_lbl)

        sub_lbl = QLabel("AUTONOMOUS CAPABILITY LAUNCHER // REAL REGISTERED ACTIONS")
        sub_lbl.setStyleSheet("color: #0ea5e9; font-size: 10px; font-weight: 600; letter-spacing: 0.1em;")
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        btn_close = QPushButton("✕ CLOSE")
        btn_close.setStyleSheet("""
            background: #1e293b;
            border: 1px solid #334155;
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
            padding: 6px 14px;
            border-radius: 6px;
        """)
        btn_close.clicked.connect(self.close)
        header_layout.addWidget(btn_close)
        main_layout.addLayout(header_layout)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setObjectName("paletteSearch")
        self.search_input.setPlaceholderText("🔍 Search commands, capabilities, tools, or shortcuts...")
        self.search_input.textChanged.connect(self._filter_cards)
        main_layout.addWidget(self.search_input)

        # Category Filter Pills
        self.cat_layout = QHBoxLayout()
        self.cat_layout.setSpacing(8)
        self.cat_buttons = {}

        categories = [
            ("ALL", "All"),
            ("HUBS", "System Hubs"),
            ("SYSTEM", "System"),
            ("BROWSER", "Browser"),
            ("AUDIO", "Voice & Audio"),
            ("DEV", "Dev & Code"),
            ("MEDIA", "Media"),
            ("AI", "AI & Vision")
        ]

        for cat_key, cat_label in categories:
            btn = QPushButton(cat_label)
            btn.setProperty("class", "filterBtn")
            btn.setCheckable(True)
            if cat_key == "ALL":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, k=cat_key: self._on_category_selected(k))
            self.cat_layout.addWidget(btn)
            self.cat_buttons[cat_key] = btn

        self.cat_layout.addStretch()
        main_layout.addLayout(self.cat_layout)

        # Scroll area for command cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("scrollContent")
        self.cards_layout = QGridLayout(self.content_widget)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(2, 4, 10, 4)

        scroll.setWidget(self.content_widget)
        main_layout.addWidget(scroll, stretch=1)

        # Status & Activity Footer
        footer = QHBoxLayout()
        self.lbl_footer_status = QLabel("Ready. Select or search any registered command.")
        self.lbl_footer_status.setStyleSheet("color: #64748b; font-size: 11px;")
        footer.addWidget(self.lbl_footer_status)
        footer.addStretch()

        self.lbl_count = QLabel("0 capabilities available")
        self.lbl_count.setStyleSheet("color: #64748b; font-size: 11px;")
        footer.addWidget(self.lbl_count)
        main_layout.addLayout(footer)

    def _load_registered_commands(self):
        """Builds command cards from authoritative tools and specialized hubs."""
        self.cards.clear()

        # 1. Specialized System Hubs (Mapped from UI Callbacks)
        hubs = [
            ("research", "✦ Universal Research Hub", "HUBS", "Open Universal Research & Live Knowledge Engine", "Ctrl+Shift+R", "LOW", True),
            ("code", "💻 Project Intelligence", "HUBS", "Open Project Architecture & Codebase Explorer", "Ctrl+Shift+C", "LOW", True),
            ("lab", "🧪 Virtual Testing Lab", "HUBS", "Open Santra Virtual Testing Room & Scenario Lab", "Ctrl+Shift+L", "LOW", True),
            ("ai", "⚙️ AI Provider Settings", "HUBS", "Configure Nemotron, local Ollama, keys, and priority", "Ctrl+Shift+A", "LOW", True),
            ("screen", "🔍 Visual Screen Intelligence", "HUBS", "Analyze visible desktop screen and OCR content", "Ctrl+Shift+S", "LOW", True),
            ("accent", "🗣️ Accent & Pronunciation", "HUBS", "Configure Indian Accent & Wake-Word Intelligence", "Ctrl+Shift+P", "LOW", True),
            ("spotify", "🎵 Spotify Control Suite", "HUBS", "Open Spotify Playback & Playlist Manager", "Ctrl+Shift+M", "LOW", True),
            ("test_speakers", "🔊 Test Output Audio", "AUDIO", "Run diagnostic test tone on current speaker/headphones", "", "LOW", False),
            ("hianime", "🌐 HiAnime in Brave", "BROWSER", "Navigate to HiAnime streaming via Brave Browser", "", "LOW", False),
            ("chatgpt", "💬 Chrome ChatGPT", "BROWSER", "Open ChatGPT browser session in Google Chrome", "", "LOW", False),
            ("wake", "⚡ Trigger Wake Word", "AUDIO", "Trigger SANTRA voice listener immediately", "Space", "LOW", False),
        ]

        for key, title, cat, desc, sc, risk, is_hub in hubs:
            card = CommandCard(key=key, title=title, category=cat, description=desc, shortcut=sc, risk=risk, is_hub=is_hub)
            if key in self.callbacks or self.on_command_submit:
                card.set_lifecycle_state(CommandLifecycleState.READY)
            else:
                card.set_lifecycle_state(CommandLifecycleState.BLOCKED, "No handler")
            card.execute_requested.connect(self._handle_command_execution)
            self.cards.append(card)

        # 2. Add Authoritative Capabilities from tool_registry
        for tool in tool_registry.list_all_tools()[:30]:  # Top representative tools
            cat_tag = "SYSTEM"
            c_low = tool.category.lower()
            if "browser" in c_low or "search" in c_low:
                cat_tag = "BROWSER"
            elif "audio" in c_low or "tts" in c_low:
                cat_tag = "AUDIO"
            elif "dev" in c_low or "file" in c_low or "project" in c_low:
                cat_tag = "DEV"
            elif "media" in c_low:
                cat_tag = "MEDIA"
            elif "ai" in c_low or "vision" in c_low:
                cat_tag = "AI"

            card = CommandCard(
                key=f"tool:{tool.name}",
                title=tool.name,
                category=cat_tag,
                description=tool.description,
                risk=tool.risk_level,
                is_hub=False
            )
            tool_def = tool_registry.get_tool(tool.name)
            if not tool_def or not tool_def.implemented:
                card.set_lifecycle_state(CommandLifecycleState.BLOCKED, "Unimplemented")
            elif not self.on_command_submit and f"tool:{tool.name}" not in self.callbacks:
                card.set_lifecycle_state(CommandLifecycleState.BLOCKED, "No handler")
            elif tool.name in ["spotify_control", "desktop.send_message"]:
                card.set_lifecycle_state(CommandLifecycleState.UNVERIFIED, "Prerequisites/Auth")
            else:
                card.set_lifecycle_state(CommandLifecycleState.READY)
            card.execute_requested.connect(self._handle_command_execution)
            self.cards.append(card)

        self._relayout_cards()

    def _on_category_selected(self, selected_cat: str):
        self._active_category = selected_cat
        for cat_k, btn in self.cat_buttons.items():
            btn.setChecked(cat_k == selected_cat)
        self._filter_cards()

    def _filter_cards(self):
        query = self.search_input.text().lower().strip()
        visible_count = 0

        for card in self.cards:
            cat_match = (self._active_category == "ALL") or (card.category == self._active_category)
            text_match = (
                not query or
                query in card.title.lower() or
                query in card.description.lower() or
                query in card.category.lower() or
                query in card.shortcut.lower()
            )
            is_visible = cat_match and text_match
            card.setVisible(is_visible)
            if is_visible:
                visible_count += 1

        self.lbl_count.setText(f"{visible_count} of {len(self.cards)} capabilities shown")

    def _relayout_cards(self):
        # Clear grid
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)

        # 2 columns responsive layout
        row, col = 0, 0
        for card in self.cards:
            self.cards_layout.addWidget(card, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        self._filter_cards()

    def _handle_command_execution(self, action_key: str, command_title: str):
        """Executes a command through the structured command lifecycle without closing the app."""
        cmd_id = uuid.uuid4().hex[:8]
        record = CommandExecutionRecord(
            command_id=cmd_id,
            command_name=command_title,
            status=CommandLifecycleState.VALIDATING,
            start_time=time.time()
        )
        self._execution_history[cmd_id] = record

        # Locate card
        matching_card = next((c for c in self.cards if c.key == action_key), None)
        if matching_card:
            matching_card.set_lifecycle_state(CommandLifecycleState.VALIDATING)

        self.lbl_footer_status.setText(f"Validating '{command_title}'...")

        try:
            # 1. Validation Stage
            if action_key.startswith("tool:"):
                tool_name = action_key.replace("tool:", "")
                tool_def = tool_registry.get_tool(tool_name)
                if not tool_def or not tool_def.implemented:
                    record.status = CommandLifecycleState.BLOCKED
                    record.error_details = "Tool is unimplemented or unavailable"
                    if matching_card:
                        matching_card.set_lifecycle_state(CommandLifecycleState.BLOCKED, "Unimplemented")
                    self.lbl_footer_status.setText(f"⛔ Action blocked: Tool '{tool_name}' not available.")
                    return

            # 2. Queued & Running Stage
            record.status = CommandLifecycleState.RUNNING
            if matching_card:
                matching_card.set_lifecycle_state(CommandLifecycleState.RUNNING)
            self.lbl_footer_status.setText(f"Executing '{command_title}'...")

            # 3. Execution Dispatch
            cb = self.callbacks.get(action_key)
            if cb and callable(cb):
                cb()
                record.status = CommandLifecycleState.SUCCEEDED
                record.completion_time = time.time()
                record.result_summary = "Hub opened or action executed successfully"
                if matching_card:
                    matching_card.set_lifecycle_state(CommandLifecycleState.SUCCEEDED)
                self.lbl_footer_status.setText(f"✓ '{command_title}' executed successfully.")
            elif self.on_command_submit:
                tool_bare = action_key.replace("tool:", "")
                phrase = self.TOOL_DISPATCH_PHRASES.get(tool_bare, self.TOOL_DISPATCH_PHRASES.get(action_key, command_title))

                self.on_command_submit(phrase)
                record.status = CommandLifecycleState.SUCCEEDED
                record.completion_time = time.time()
                record.result_summary = f"Dispatched phrase: {phrase}"
                if matching_card:
                    matching_card.set_lifecycle_state(CommandLifecycleState.SUCCEEDED, "Dispatched")
                self.lbl_footer_status.setText(f"✓ Dispatched command: '{phrase}'")
            else:
                record.status = CommandLifecycleState.FAILED
                record.error_details = "No execution handler wired for action"
                if matching_card:
                    matching_card.set_lifecycle_state(CommandLifecycleState.FAILED, "No handler")
                self.lbl_footer_status.setText(f"✕ Execution failed: No handler for '{action_key}'.")

        except Exception as e:
            logger.error(f"[COMMAND_PALETTE_ERROR] Exception in action '{action_key}': {e}", exc_info=True)
            record.status = CommandLifecycleState.FAILED
            record.error_details = str(e)
            record.completion_time = time.time()
            if matching_card:
                matching_card.set_lifecycle_state(CommandLifecycleState.FAILED, str(e))
            self.lbl_footer_status.setText(f"✕ Error executing '{command_title}': {e}")
