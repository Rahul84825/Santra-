"""SANTRA Universal Research & Live Intelligence Panel.
Interactive PyQt6 panel displaying real-time research stages, source citations,
extracted evidence, conflict statuses, and persistent knowledge retrieval.
"""

import time
import logging
from typing import Optional, Callable
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QProgressBar, QFrame, QScrollArea
)
from PyQt6.QtGui import QFont, QColor

from core.research.research_manager import research_manager
from core.research.research_models import ResearchStatus
from core.research.research_memory import research_memory

logger = logging.getLogger("Jarvis.ResearchPanel")

class ResearchWorker(QThread):
    """Background worker for non-blocking research operations."""
    sig_stage_changed = pyqtSignal(str, str)
    sig_sentence_chunk = pyqtSignal(str)
    sig_completed = pyqtSignal(dict)
    sig_failed = pyqtSignal(str)

    def __init__(self, query: str):
        super().__init__()
        self.query = query
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            res = research_manager.execute_research(
                query=self.query,
                on_stage_change=lambda stage, desc: self.sig_stage_changed.emit(stage, desc),
                on_sentence_chunk=lambda chunk: self.sig_sentence_chunk.emit(chunk),
                is_cancelled=lambda: self._is_cancelled
            )
            self.sig_completed.emit(res)
        except Exception as e:
            logger.error(f"[ResearchWorker] Error executing research: {e}")
            self.sig_failed.emit(str(e))


class ResearchPanel(QWidget):
    """PyQt6 Research Panel displaying live research stages and evidence."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.worker: Optional[ResearchWorker] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        title_lbl = QLabel("✦ UNIVERSAL RESEARCH & LIVE INTELLIGENCE")
        title_lbl.setStyleSheet("color: #00F0FF; font-size: 14pt; font-weight: bold; letter-spacing: 1px;")
        header_layout.addWidget(title_lbl)

        market_badge = QLabel("MARKET: INDIA (₹ INR)")
        market_badge.setStyleSheet("color: #FFB703; background: #1B263B; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 9pt;")
        header_layout.addWidget(market_badge)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Query Input Bar
        input_layout = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter research query (e.g. 'Best budget controller under 2000 in India', 'Compare React and Next.js')...")
        self.query_input.setStyleSheet("""
            QLineEdit {
                background: #0D1B2A;
                color: #FFFFFF;
                border: 1px solid #1B4965;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border: 1px solid #00F0FF;
            }
        """)
        self.query_input.returnPressed.connect(self._start_research)
        input_layout.addWidget(self.query_input)

        self.btn_search = QPushButton("START RESEARCH")
        self.btn_search.setStyleSheet("""
            QPushButton {
                background: #00F0FF;
                color: #050B14;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: #38B6FF;
            }
        """)
        self.btn_search.clicked.connect(self._start_research)
        input_layout.addWidget(self.btn_search)

        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #E63946;
                color: #FFFFFF;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 10pt;
            }
            QPushButton:disabled {
                background: #333333;
                color: #666666;
            }
        """)
        self.btn_cancel.clicked.connect(self._cancel_research)
        input_layout.addWidget(self.btn_cancel)

        layout.addLayout(input_layout)

        # Stage Progress Bar & Status Label
        stage_layout = QHBoxLayout()
        self.stage_lbl = QLabel("STANDBY: Awaiting research query.")
        self.stage_lbl.setStyleSheet("color: #8D99AE; font-size: 10pt;")
        stage_layout.addWidget(self.stage_lbl)
        stage_layout.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #0D1B2A;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #00F0FF;
                border-radius: 4px;
            }
        """)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        stage_layout.addWidget(self.progress_bar)

        layout.addLayout(stage_layout)

        # Splitter: Left = Results, Right = Sources & Citations
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #1B4965;
            }
        """)

        # Left Pane: Synthesized Citing Answer
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        ans_title = QLabel("REASONED ANSWER & RECOMMENDATIONS")
        ans_title.setStyleSheet("color: #38B6FF; font-weight: bold; font-size: 10pt;")
        left_layout.addWidget(ans_title)

        self.answer_view = QTextEdit()
        self.answer_view.setReadOnly(True)
        self.answer_view.setStyleSheet("""
            QTextEdit {
                background: #080E18;
                color: #E0E1DD;
                border: 1px solid #1B263B;
                border-radius: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 10pt;
                line-height: 1.4;
                padding: 10px;
            }
        """)
        left_layout.addWidget(self.answer_view)
        splitter.addWidget(left_widget)

        # Right Pane: Sources & Evidence Table
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        src_title = QLabel("DISCOVERED SOURCES & EVIDENCE PROVENANCE")
        src_title.setStyleSheet("color: #38B6FF; font-weight: bold; font-size: 10pt;")
        right_layout.addWidget(src_title)

        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(3)
        self.sources_table.setHorizontalHeaderLabels(["Domain", "Authority", "Source Title"])
        self.sources_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sources_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sources_table.setStyleSheet("""
            QTableWidget {
                background: #080E18;
                color: #E0E1DD;
                border: 1px solid #1B263B;
                gridline-color: #1B263B;
                font-size: 9pt;
            }
            QHeaderView::section {
                background: #0D1B2A;
                color: #8D99AE;
                padding: 4px;
                border: 1px solid #1B263B;
                font-weight: bold;
            }
        """)
        right_layout.addWidget(self.sources_table)
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 380])
        layout.addWidget(splitter)

    def _start_research(self):
        query = self.query_input.text().strip()
        if not query:
            return

        self.btn_search.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.answer_view.clear()
        self.sources_table.setRowCount(0)
        self.stage_lbl.setText("INITIALIZING: Starting research...")

        self.worker = ResearchWorker(query)
        self.worker.sig_stage_changed.connect(self._on_stage_changed)
        self.worker.sig_sentence_chunk.connect(self._on_chunk)
        self.worker.sig_completed.connect(self._on_completed)
        self.worker.sig_failed.connect(self._on_failed)
        self.worker.start()

    def _cancel_research(self):
        if self.worker:
            self.worker.cancel()
            self.stage_lbl.setText("CANCELLING: Terminating research workers...")
            self.btn_cancel.setEnabled(False)

    def _on_stage_changed(self, stage: str, desc: str):
        self.stage_lbl.setText(f"[{stage}] {desc}")

    def _on_chunk(self, chunk: str):
        self.answer_view.insertPlainText(chunk)

    def _on_completed(self, result: dict):
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.stage_lbl.setText(f"COMPLETED in {result.get('latency_ms', 0):.0f}ms ({result.get('sources_count', 0)} sources)")
        
        # Populate final formatted answer if not already filled via stream
        if not self.answer_view.toPlainText().strip():
            self.answer_view.setPlainText(result.get("answer", ""))

        # Populate sources table
        citations = result.get("citations", [])
        self.sources_table.setRowCount(len(citations))
        for row, c in enumerate(citations):
            dom_item = QTableWidgetItem(c.get("domain", ""))
            auth_item = QTableWidgetItem(c.get("source_type", ""))
            title_item = QTableWidgetItem(c.get("title", ""))
            self.sources_table.setItem(row, 0, dom_item)
            self.sources_table.setItem(row, 1, auth_item)
            self.sources_table.setItem(row, 2, title_item)

    def _on_failed(self, error: str):
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.stage_lbl.setText(f"FAILED: {error}")
        self.answer_view.setPlainText(f"Research operation failed: {error}")

