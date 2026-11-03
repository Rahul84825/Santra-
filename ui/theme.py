"""
SANTRA Modern Desktop Design System & Theme.
Provides design tokens, palette definitions, gradients, fonts, and stylesheets
for the high-contrast, modern SANTRA desktop assistant.
"""

from PyQt6.QtGui import QColor

class SantraTokens:
    # 1. Backgrounds & Surfaces (Deep graphite & subtle dark-slate)
    BG_BASE = QColor(13, 17, 23)             # #0d1117 Main window background
    BG_SURFACE = QColor(22, 27, 34)          # #161b22 Side rails & elevated panels
    BG_CARD = QColor(30, 41, 59)             # #1e293b Slate cards & message containers
    BG_CARD_HOVER = QColor(51, 65, 85)       # #334155 Hovered card
    BG_INPUT = QColor(15, 23, 42)            # #0f172a Active input composer
    BG_USER_BUBBLE = QColor(24, 34, 53)      # #182235 Distinct user query card
    BG_SANTRA_BUBBLE = QColor(19, 31, 49)    # #131f31 Santra response card

    # 2. Accents (Controlled Cyan, Sky, Teal - Professional, not neon)
    ACCENT_CYAN = QColor(14, 165, 233)       # #0ea5e9 Sky Cyan primary
    ACCENT_TEAL = QColor(20, 184, 166)       # #14b8a6 Muted Teal secondary
    ACCENT_GLOW = QColor(14, 165, 233, 45)   # Subtle focus glow
    ACCENT_HOVER = QColor(56, 189, 248)      # #38bdf8

    # 3. Typography & Hierarchy (High Contrast)
    TEXT_PRIMARY = QColor(248, 250, 252)     # #f8fafc Crisp pure white
    TEXT_SECONDARY = QColor(148, 163, 184)   # #94a3b8 Readable muted grey
    TEXT_MUTED = QColor(100, 116, 139)       # #64748b Timestamps & hints
    TEXT_ACCENT = QColor(56, 189, 248)       # #38bdf8 Accent highlights

    # 4. Status Indicators
    STATUS_STANDBY = QColor(14, 165, 233)    # Blue/Cyan
    STATUS_LISTENING = QColor(6, 182, 212)   # Cyan
    STATUS_PROCESSING = QColor(245, 158, 11) # Amber / Gold
    STATUS_SPEAKING = QColor(16, 185, 129)   # Emerald Green
    STATUS_SLEEPING = QColor(139, 92, 246)   # Purple / Indigo
    STATUS_ERROR = QColor(239, 68, 68)       # Red / Coral

    # 5. Borders & Dividers
    BORDER_SUBTLE = QColor(51, 65, 85)       # #334155 Clean thin border
    BORDER_LIGHT = QColor(71, 85, 105)       # #475569
    BORDER_FOCUS = QColor(14, 165, 233)      # #0ea5e9 Controlled focus border


class HUDColors(SantraTokens):
    """Backward compatibility layer for legacy HUDColors references."""
    INTERFACE = SantraTokens.ACCENT_CYAN
    BG = SantraTokens.BG_BASE
    BG_TOOL = QColor(22, 27, 34, 230)
    BG_INPUT = SantraTokens.BG_INPUT
    BG_VOID = SantraTokens.BG_BASE
    BG_PANEL = SantraTokens.BG_SURFACE
    BG_CARD = SantraTokens.BG_CARD

    ACCENT_CYAN_DIM = QColor(14, 165, 233, 110)
    ACCENT_CYAN_GLOW = SantraTokens.ACCENT_GLOW

    STANDBY_CYAN = SantraTokens.STATUS_STANDBY
    LISTENING_CYAN = SantraTokens.STATUS_LISTENING
    THINKING_GOLD = SantraTokens.STATUS_PROCESSING
    SPEAKING_TEAL = SantraTokens.STATUS_SPEAKING
    ERROR_CORAL = SantraTokens.STATUS_ERROR

    CYAN_PRIMARY = SantraTokens.ACCENT_CYAN
    CYAN_GLOW = SantraTokens.ACCENT_GLOW
    CYAN_DIM = QColor(14, 165, 233, 110)
    AMBER_STANDBY = SantraTokens.STATUS_PROCESSING
    AMBER_GLOW = QColor(245, 158, 11, 75)
    VIOLET_THINKING = SantraTokens.STATUS_SLEEPING
    VIOLET_GLOW = QColor(139, 92, 246, 75)
    TEAL_SPEAKING = SantraTokens.STATUS_SPEAKING
    TEAL_GLOW = QColor(16, 185, 129, 75)
    CRIMSON_ERROR = SantraTokens.STATUS_ERROR
    CRIMSON_GLOW = QColor(239, 68, 68, 75)

    TEXT_BRIGHT = SantraTokens.TEXT_PRIMARY
    TEXT_JARVIS = SantraTokens.TEXT_PRIMARY
    TEXT_USER = SantraTokens.TEXT_SECONDARY
    TEXT_DIM = SantraTokens.TEXT_MUTED
    TEXT_MUTED = SantraTokens.TEXT_MUTED

    BORDER_CYAN = SantraTokens.BORDER_SUBTLE
    BORDER_DIM = QColor(51, 65, 85, 120)
    BORDER_GLOW = SantraTokens.ACCENT_CYAN
    BORDER_MUTED = SantraTokens.BORDER_SUBTLE


def get_hud_stylesheet() -> str:
    """Master stylesheet for the modern SANTRA Desktop Assistant."""
    return """
    QMainWindow {
        background-color: #0d1117;
    }
    QWidget {
        color: #f8fafc;
        font-family: 'Segoe UI Variable', 'Segoe UI', 'Inter', system-ui, sans-serif;
    }
    
    /* Top Header Bar */
    QFrame#headerBar {
        background-color: #161b22;
        border-bottom: 1px solid #21262d;
    }
    
    /* Left Navigation Sidebar */
    QFrame#navSidebar {
        background-color: #161b22;
        border-right: 1px solid #21262d;
    }
    
    /* Sidebar Navigation Button */
    QPushButton.navButton {
        background-color: transparent;
        border: none;
        border-radius: 6px;
        color: #94a3b8;
        font-size: 13px;
        font-weight: 500;
        padding: 9px 14px;
        text-align: left;
    }
    QPushButton.navButton:hover {
        background-color: #1e293b;
        color: #f8fafc;
    }
    QPushButton.navButton:checked, QPushButton.navButton.active {
        background-color: rgba(14, 165, 233, 0.15);
        border-left: 3px solid #0ea5e9;
        color: #38bdf8;
        font-weight: 600;
    }

    /* Right Telemetry / Info Sidebar */
    QFrame#infoSidebar {
        background-color: #161b22;
        border-left: 1px solid #21262d;
    }

    /* Modern Card Widget */
    QFrame.santraCard {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
    }
    
    /* Command Input Line */
    QLineEdit.cyberInput, QLineEdit.santraInput {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 6px;
        color: #f8fafc;
        font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
        font-size: 13px;
        padding: 10px 16px;
    }
    QLineEdit.cyberInput:focus, QLineEdit.santraInput:focus {
        border: 1px solid #0ea5e9;
        background-color: #0d1526;
        color: #ffffff;
    }
    QLineEdit.cyberInput::placeholder, QLineEdit.santraInput::placeholder {
        color: #64748b;
    }
    
    /* Action & Cyber Buttons */
    QPushButton.cyberButton, QPushButton.santraButton {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 6px;
        color: #f8fafc;
        padding: 9px 18px;
        font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
        font-weight: 600;
        font-size: 12px;
    }
    QPushButton.cyberButton:hover, QPushButton.santraButton:hover {
        background-color: #334155;
        border: 1px solid #0ea5e9;
        color: #38bdf8;
    }
    QPushButton.cyberButton:pressed, QPushButton.santraButton:pressed {
        background-color: #0ea5e9;
        color: #ffffff;
    }

    /* Primary Accent Button */
    QPushButton.primaryButton {
        background-color: #0ea5e9;
        border: 1px solid #0284c7;
        border-radius: 6px;
        color: #ffffff;
        padding: 9px 18px;
        font-weight: 600;
        font-size: 12px;
    }
    QPushButton.primaryButton:hover {
        background-color: #38bdf8;
    }
    QPushButton.primaryButton:pressed {
        background-color: #0369a1;
    }

    /* Danger / Cancel Button */
    QPushButton.dangerButton {
        background-color: rgba(239, 68, 68, 0.15);
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-radius: 6px;
        color: #f87171;
        padding: 9px 16px;
        font-weight: 600;
        font-size: 12px;
    }
    QPushButton.dangerButton:hover {
        background-color: #ef4444;
        color: #ffffff;
    }

    /* Status Pills / Badges */
    QLabel.statusPill {
        border-radius: 12px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }
    
    /* Scrollbars */
    QScrollBar:vertical {
        background: #0d1117;
        width: 6px;
        margin: 0px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical {
        background: #334155;
        min-height: 25px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #0ea5e9;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* Progress Bars */
    QProgressBar {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 3px;
        text-align: center;
        color: transparent;
    }
    QProgressBar::chunk {
        background-color: #0ea5e9;
        border-radius: 2px;
    }
    """
