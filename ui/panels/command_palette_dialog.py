"""
SANTRA — Categorized Command Palette & Capability Hub
Provides an organized, cyber-styled command drawer and launcher dialog for SANTRA's
desktop tools, specialized intelligence panels, audio controls, and workspace actions.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from ui.theme import HUDColors


class CommandPaletteDialog(QDialog):
    """Categorized Cyber Command Palette for SANTRA."""

    def __init__(self, parent=None, callbacks: dict = None):
        super().__init__(parent)
        self.callbacks = callbacks or {}
        self.setWindowTitle("SANTRA — Command Palette & Capability Hub")
        self.resize(780, 520)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #020b14;
                border: 1px solid rgba(0, 229, 255, 0.4);
                border-radius: 6px;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QWidget#scrollContent {{
                background: transparent;
            }}
            QLabel.categoryTitle {{
                color: #00e5ff;
                font-family: 'Chakra Petch', sans-serif;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.15em;
                padding-top: 10px;
                padding-bottom: 4px;
            }}
            QPushButton.paletteBtn {{
                background: rgba(0, 229, 255, 0.06);
                border: 1px solid rgba(0, 229, 255, 0.25);
                border-radius: 4px;
                color: #eaf9ff;
                font-family: 'Chakra Petch', sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 10px 14px;
                text-align: left;
            }}
            QPushButton.paletteBtn:hover {{
                background: rgba(0, 229, 255, 0.18);
                border: 1px solid #00e5ff;
                color: #ffffff;
            }}
            QPushButton.paletteBtn:pressed {{
                background: rgba(0, 229, 255, 0.35);
            }}
        """)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        title_lbl = QLabel("COMMAND PALETTE & SYSTEM HUBS")
        title_lbl.setStyleSheet("""
            color: #00e5ff;
            font-family: 'Chakra Petch', sans-serif;
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.2em;
        """)
        header_layout.addWidget(title_lbl)

        btn_close = QPushButton("✕ CLOSE")
        btn_close.setStyleSheet("""
            background: rgba(255, 51, 85, 0.15);
            border: 1px solid rgba(255, 51, 85, 0.5);
            color: #ff3355;
            font-family: 'Chakra Petch', sans-serif;
            font-size: 11px;
            font-weight: 700;
            padding: 5px 12px;
            border-radius: 3px;
        """)
        btn_close.clicked.connect(self.accept)
        header_layout.addStretch()
        header_layout.addWidget(btn_close)
        main_layout.addLayout(header_layout)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(0, 229, 255, 0.2);")
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)

        # Scroll Area for categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_widget.setObjectName("scrollContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(14)
        content_layout.setContentsMargins(4, 4, 10, 4)

        # Category 1: Developer & Intelligence Hubs
        self._add_category_header(content_layout, "DEVELOPER & REASONING HUBS")
        grid_dev = QGridLayout()
        grid_dev.setSpacing(10)
        self._add_palette_action(grid_dev, 0, 0, "💻 Project Intelligence", "Ctrl+Shift+C", "Open Project Intelligence & Codebase Explorer", "code")
        self._add_palette_action(grid_dev, 0, 1, "🧪 Virtual Testing Lab", "Ctrl+Shift+L", "Open Santra Virtual Testing Room & Scenario Lab", "lab")
        self._add_palette_action(grid_dev, 1, 0, "⚙️ AI Provider Settings", "Ctrl+Shift+A", "Manage Nemotron, models, API keys, and priority", "ai")
        self._add_palette_action(grid_dev, 1, 1, "🔍 Visual Screen Intelligence", "Ctrl+Shift+S", "Analyze visible desktop screen and OCR content", "screen")
        content_layout.addLayout(grid_dev)

        # Category 2: Voice, Accent & Audio Subsystems
        self._add_category_header(content_layout, "VOICE, ACCENT & AUDIO SUBSYSTEMS")
        grid_audio = QGridLayout()
        grid_audio.setSpacing(10)
        self._add_palette_action(grid_audio, 0, 0, "🗣️ Accent & Pronunciation", "Ctrl+Shift+P", "Configure Indian Accent & Wake-Word Intelligence", "accent")
        self._add_palette_action(grid_audio, 0, 1, "🔊 Test Output Audio", "", "Run diagnostic test tone on current speaker/headphones", "test_speakers")
        content_layout.addLayout(grid_audio)

        # Category 3: Media, Browser & Web Automation
        self._add_category_header(content_layout, "MEDIA, BROWSER & AUTOMATION")
        grid_media = QGridLayout()
        grid_media.setSpacing(10)
        self._add_palette_action(grid_media, 0, 0, "🎵 Spotify Control Suite", "Ctrl+Shift+M", "Open Spotify Integration, Playback & Playlist Manager", "spotify")
        self._add_palette_action(grid_media, 0, 1, "🌐 HiAnime in Brave", "", "Navigate to HiAnime streaming via Brave Browser", "hianime")
        self._add_palette_action(grid_media, 1, 0, "💬 Chrome ChatGPT", "", "Open ChatGPT browser session in Google Chrome", "chatgpt")
        self._add_palette_action(grid_media, 1, 1, "⚡ Trigger Wake Word", "Space", "Trigger SANTRA voice listener immediately", "wake")
        content_layout.addLayout(grid_media)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _add_category_header(self, layout: QVBoxLayout, title: str):
        lbl = QLabel(f"// {title}")
        lbl.setProperty("class", "categoryTitle")
        layout.addWidget(lbl)

    def _add_palette_action(self, grid: QGridLayout, row: int, col: int, text: str, shortcut: str, tooltip: str, action_key: str):
        display_text = f"{text}  [{shortcut}]" if shortcut else text
        btn = QPushButton(display_text)
        btn.setProperty("class", "paletteBtn")
        btn.setToolTip(tooltip)
        btn.clicked.connect(lambda: self._handle_action(action_key))
        grid.addWidget(btn, row, col)

    def _handle_action(self, action_key: str):
        self.accept()
        cb = self.callbacks.get(action_key)
        if cb and callable(cb):
            cb()

