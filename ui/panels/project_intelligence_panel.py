"""Project Intelligence, Code Exploration, and Safe File Engineering HUD Panel."""

import os
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QListWidget, QListWidgetItem, QTextEdit, QFileDialog
)

from ui.widgets.hud_frame import HUDFrame
from core.project_intelligence.context_engine import project_context_engine, ProjectContextEngine
from core.project_intelligence.models import ProjectOverview

logger = logging.getLogger("Jarvis.ProjectIntelligencePanel")


class ProjectScanWorker(QThread):
    """Background worker that scans and indexes a project directory asynchronously."""
    scan_completed = pyqtSignal(object)  # ProjectOverview
    scan_failed = pyqtSignal(str)

    def __init__(self, project_path: str, engine: Optional[ProjectContextEngine] = None):
        super().__init__()
        self.project_path = project_path
        self.engine = engine or project_context_engine

    def run(self):
        try:
            overview = self.engine.index_project(self.project_path)
            self.scan_completed.emit(overview)
        except Exception as e:
            logger.error(f"[PROJECT_SCAN] Scan failed: {e}", exc_info=True)
            self.scan_failed.emit(str(e))


class CodeSearchWorker(QThread):
    """Background worker for FTS5 code search."""
    search_completed = pyqtSignal(list)
    search_failed = pyqtSignal(str)

    def __init__(self, query: str, project_name: Optional[str] = None, engine: Optional[ProjectContextEngine] = None):
        super().__init__()
        self.query = query
        self.project_name = project_name
        self.engine = engine or project_context_engine

    def run(self):
        try:
            results = self.engine.search_code(self.query, project_name=self.project_name)
            self.search_completed.emit(results)
        except Exception as e:
            logger.error(f"[CODE_SEARCH] Search error: {e}")
            self.search_failed.emit(str(e))


class ProjectIntelligencePanel(HUDFrame):
    """Holographic HUD Panel for full codebase understanding and symbol navigation."""

    def __init__(self, parent=None, engine: Optional[ProjectContextEngine] = None):
        super().__init__(parent)
        self.engine = engine or project_context_engine
        self.current_project_name: Optional[str] = None
        self.scan_worker: Optional[ProjectScanWorker] = None
        self.search_worker: Optional[CodeSearchWorker] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header Title
        lbl_title = QLabel("PROJECT INTELLIGENCE // CODEBASE ARCHITECTURE")
        lbl_title.setStyleSheet("""
            color: #00e5ff;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.15em;
        """)
        layout.addWidget(lbl_title)

        # Path Selector & Scan Bar
        path_layout = QHBoxLayout()
        path_layout.setSpacing(8)

        self.input_path = QLineEdit()
        self.input_path.setProperty("class", "cyberInput")
        self.input_path.setPlaceholderText("Select or enter project root folder path...")
        self.input_path.setText(str(Path.cwd()))
        path_layout.addWidget(self.input_path, stretch=1)

        self.btn_browse = QPushButton("📁 BROWSE")
        self.btn_browse.setProperty("class", "cyberButton")
        self.btn_browse.clicked.connect(self._on_browse)
        path_layout.addWidget(self.btn_browse)

        self.btn_scan = QPushButton("⚡ INDEX / SCAN")
        self.btn_scan.setProperty("class", "cyberButton")
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background: rgba(0, 229, 255, 0.2);
                border: 1px solid #00e5ff;
                color: #ffffff;
                font-weight: 700;
            }
        """)
        self.btn_scan.clicked.connect(self._on_scan)
        path_layout.addWidget(self.btn_scan)

        layout.addLayout(path_layout)

        # Status Banner
        self.lbl_status = QLabel("Ready to scan project repository.")
        self.lbl_status.setStyleSheet("color: rgba(0, 229, 255, 0.7); font-size: 10px;")
        layout.addWidget(self.lbl_status)

        # Tab Widget for Architecture, Code Search, Symbols, and Dependencies
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(0, 229, 255, 0.3);
                background: rgba(3, 12, 16, 0.9);
            }
            QTabBar::tab {
                background: rgba(0, 229, 255, 0.08);
                color: #8be9fd;
                border: 1px solid rgba(0, 229, 255, 0.2);
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: rgba(0, 229, 255, 0.25);
                color: #ffffff;
                border: 1px solid #00e5ff;
            }
        """)

        # Tab 1: Overview
        tab_overview = QWidget()
        overview_layout = QVBoxLayout(tab_overview)
        self.txt_overview = QTextEdit()
        self.txt_overview.setReadOnly(True)
        self.txt_overview.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: #e0f7fa;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
            }
        """)
        overview_layout.addWidget(self.txt_overview)
        self.tabs.addTab(tab_overview, "OVERVIEW")

        # Tab 2: Full-Text Code Search (FTS5)
        tab_search = QWidget()
        search_layout = QVBoxLayout(tab_search)
        search_bar = QHBoxLayout()
        self.input_search = QLineEdit()
        self.input_search.setProperty("class", "cyberInput")
        self.input_search.setPlaceholderText("Search code across project using SQLite FTS5 (e.g. 'def calculate', 'math.sqrt')...")
        self.input_search.returnPressed.connect(self._on_search)
        search_bar.addWidget(self.input_search, stretch=1)

        self.btn_search = QPushButton("SEARCH ➜")
        self.btn_search.setProperty("class", "cyberButton")
        self.btn_search.clicked.connect(self._on_search)
        search_bar.addWidget(self.btn_search)
        search_layout.addLayout(search_bar)

        self.list_search_results = QListWidget()
        self.list_search_results.setStyleSheet("""
            QListWidget {
                background: rgba(2, 8, 12, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.25);
                color: #e0f7fa;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(0, 229, 255, 0.1);
            }
            QListWidget::item:selected {
                background: rgba(0, 229, 255, 0.2);
            }
        """)
        search_layout.addWidget(self.list_search_results)
        self.tabs.addTab(tab_search, "CODE SEARCH (FTS5)")

        # Tab 3: Symbols (AST)
        tab_symbols = QWidget()
        sym_layout = QVBoxLayout(tab_symbols)
        sym_bar = QHBoxLayout()
        self.input_sym = QLineEdit()
        self.input_sym.setProperty("class", "cyberInput")
        self.input_sym.setPlaceholderText("Search symbols (classes, functions, methods)...")
        self.input_sym.returnPressed.connect(self._on_search_symbols)
        sym_bar.addWidget(self.input_sym, stretch=1)

        self.btn_sym = QPushButton("FIND ➜")
        self.btn_sym.setProperty("class", "cyberButton")
        self.btn_sym.clicked.connect(self._on_search_symbols)
        sym_bar.addWidget(self.btn_sym)
        sym_layout.addLayout(sym_bar)

        self.list_symbols = QListWidget()
        self.list_symbols.setStyleSheet("""
            QListWidget {
                background: rgba(2, 8, 12, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.25);
                color: #e0f7fa;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(0, 229, 255, 0.1);
            }
        """)
        sym_layout.addWidget(self.list_symbols)
        self.tabs.addTab(tab_symbols, "SYMBOLS (AST)")

        layout.addWidget(self.tabs, stretch=1)

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Root Folder", self.input_path.text())
        if folder:
            self.input_path.setText(folder)

    def _on_scan(self):
        target = self.input_path.text().strip()
        if not target or not Path(target).exists():
            self.lbl_status.setText("Error: Path does not exist.")
            return

        self.lbl_status.setText(f"Scanning and indexing '{Path(target).name}'...")
        self.btn_scan.setEnabled(False)

        self.scan_worker = ProjectScanWorker(target, self.engine)
        self.scan_worker.scan_completed.connect(self._on_scan_finished)
        self.scan_worker.scan_failed.connect(self._on_scan_failed)
        self.scan_worker.start()

    def _on_scan_finished(self, overview: ProjectOverview):
        self.btn_scan.setEnabled(True)
        self.current_project_name = overview.project_name
        self.lbl_status.setText(f"Successfully indexed '{overview.project_name}' ({overview.total_files} files, {overview.total_lines} lines).")

        # Format overview
        lines = [
            f"PROJECT: {overview.project_name}",
            f"ROOT PATH: {overview.root_path}",
            f"TOTAL SOURCE FILES: {overview.total_files}",
            f"TOTAL LINES OF CODE: {overview.total_lines:,}",
            f"DETECTED FRAMEWORKS: {', '.join(overview.frameworks) if overview.frameworks else 'None'}",
            f"TEST FILES: {overview.test_files_count}",
            f"DOCUMENTATION: {len(overview.documentation_files)} files",
            "\nLANGUAGES DETECTED:"
        ]
        for lang, count in sorted(overview.languages.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {lang.title()}: {count} files")

        self.txt_overview.setPlainText("\n".join(lines))

    def _on_scan_failed(self, error: str):
        self.btn_scan.setEnabled(True)
        self.lbl_status.setText(f"Scan failed: {error}")

    def _on_search(self):
        query = self.input_search.text().strip()
        if not query:
            return

        self.list_search_results.clear()
        self.lbl_status.setText(f"Searching code for '{query}'...")

        self.search_worker = CodeSearchWorker(query, self.current_project_name, self.engine)
        self.search_worker.search_completed.connect(self._on_search_finished)
        self.search_worker.search_failed.connect(lambda e: self.lbl_status.setText(f"Search failed: {e}"))
        self.search_worker.start()

    def _on_search_finished(self, results: List[Dict[str, Any]]):
        self.list_search_results.clear()
        self.lbl_status.setText(f"Found {len(results)} match(es).")
        for r in results:
            item = QListWidgetItem(f"[{r['relative_path']}]\n  {r['snippet']}")
            self.list_search_results.addItem(item)

    def _on_search_symbols(self):
        sym_query = self.input_sym.text().strip()
        if not sym_query:
            return

        self.list_symbols.clear()
        results = self.engine.find_symbol(sym_query, self.current_project_name)
        self.lbl_status.setText(f"Found {len(results)} symbol match(es).")
        for s in results:
            doc = f" - {s['docstring']}" if s.get("docstring") else ""
            item = QListWidgetItem(f"{s['symbol_type'].upper()}: {s['name']} (Line {s['line_number']} in {s['relative_path']}){doc}")
            self.list_symbols.addItem(item)

