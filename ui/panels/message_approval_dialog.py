"""Futuristic HUD Dialog for The Ask-Before-Send Gated Approval Workflow."""

import logging
from typing import Optional, Dict, Any, Callable
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QWidget
)

from ui.theme import HUDColors, get_hud_stylesheet

logger = logging.getLogger("Jarvis.MessageApprovalDialog")


class MessageApprovalDialog(QDialog):
    """Explicit confirmation dialog requiring user approval before external message dispatch."""

    sig_approved = pyqtSignal(str)   # Emits edited or confirmed text
    sig_rejected = pyqtSignal()      # Emits cancellation

    def __init__(
        self,
        target_app: str,
        target_control: str,
        draft_text: str,
        parent: Optional[QWidget] = None,
        on_confirm_cb: Optional[Callable[[bool, str], None]] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("SANTRA // OUTBOUND MESSAGE APPROVAL")
        self.resize(560, 360)
        self.setStyleSheet(get_hud_stylesheet())
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.target_app = target_app
        self.target_control = target_control
        self.draft_text = draft_text
        self.on_confirm_cb = on_confirm_cb

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title
        lbl_title = QLabel("OUTBOUND MESSAGE APPROVAL REQUIRED")
        lbl_title.setStyleSheet("""
            color: #00e5ff;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.15em;
        """)
        layout.addWidget(lbl_title)

        # Target Information Badge
        lbl_info = QLabel(f"TARGET APP: <b>{self.target_app}</b>  |  FIELD: <i>{self.target_control}</i>")
        lbl_info.setStyleSheet("""
            color: #a0ecff;
            font-size: 11px;
            letter-spacing: 0.05em;
            background: rgba(0, 229, 255, 0.08);
            padding: 6px 10px;
            border: 1px solid rgba(0, 229, 255, 0.25);
            border-radius: 2px;
        """)
        layout.addWidget(lbl_info)

        lbl_desc = QLabel("I've drafted this message for you. Please review before sending:")
        lbl_desc.setStyleSheet("color: #d1f4ff; font-size: 11px;")
        layout.addWidget(lbl_desc)

        # Editable Draft Text Box
        self.txt_draft = QTextEdit()
        self.txt_draft.setPlainText(self.draft_text)
        self.txt_draft.setStyleSheet("""
            QTextEdit {
                background: rgba(5, 18, 24, 0.95);
                color: #ffffff;
                border: 1px solid rgba(0, 229, 255, 0.5);
                border-radius: 3px;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 13px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.txt_draft, stretch=1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setProperty("class", "cyberButton")
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_draft_only = QPushButton("KEEP AS DRAFT ONLY")
        self.btn_draft_only.setProperty("class", "cyberButton")
        self.btn_draft_only.clicked.connect(self._on_keep_draft)
        btn_layout.addWidget(self.btn_draft_only)

        self.btn_send = QPushButton("SEND NOW ➜")
        self.btn_send.setProperty("class", "cyberButton")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: rgba(0, 229, 255, 0.25);
                border: 1px solid #00e5ff;
                color: #ffffff;
                font-weight: 700;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.45);
            }
        """)
        self.btn_send.clicked.connect(self._on_send)
        btn_layout.addWidget(self.btn_send)

        layout.addLayout(btn_layout)

    def _on_send(self):
        text = self.txt_draft.toPlainText().strip()
        logger.info(f"[APPROVAL_DIALOG] User granted send permission for '{self.target_app}'.")
        if self.on_confirm_cb:
            self.on_confirm_cb(True, text)
        self.sig_approved.emit(text)
        self.accept()

    def _on_keep_draft(self):
        logger.info("[APPROVAL_DIALOG] User chose to keep message as draft only.")
        if self.on_confirm_cb:
            self.on_confirm_cb(False, self.txt_draft.toPlainText().strip())
        self.sig_rejected.emit()
        self.reject()

    def _on_cancel(self):
        logger.info("[APPROVAL_DIALOG] User cancelled message workflow.")
        if self.on_confirm_cb:
            self.on_confirm_cb(False, "")
        self.sig_rejected.emit()
        self.reject()

