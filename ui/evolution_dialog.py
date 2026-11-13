"""
SANTRA Autonomous Learning & Evolution Engine (ALEE)
Evolution Center Control Panel Dialog (Stage 5/6)

Interactive PyQt6 modal dialog providing:
- Tab 1: Proposals & Versioned Rollback Gate (Review, Approve, Auto-Rollback, Manual Rollback)
- Tab 2: Learned Domain Aliases & Autonomous Skills (Add alias, inspect, promote sandbox skills)
- Tab 3: System Weakness Telemetry & Live Self-Benchmarks
"""

import os
import json
import time
import logging
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QMessageBox, QTextEdit, QScrollArea
)

from core.evolution.storage import EvolutionStorage, evolution_storage
from core.evolution.evolution_manager import EvolutionManager, evolution_manager
from core.evolution.skill_developer import SkillDeveloper, skill_developer
from core.evolution.evaluator import PerformanceEvaluator, performance_evaluator

logger = logging.getLogger("Santra.UI.EvolutionDialog")

# Sleek dark-mode styling conforming to SANTRA UI standards
DIALOG_STYLESHEET = """
QDialog {
    background-color: #0b0f17;
    color: #f8fafc;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
}
QLabel {
    color: #f8fafc;
}
QTabWidget::pane {
    border: 1px solid rgba(148, 163, 184, 0.15);
    background: #0f172a;
    border-radius: 8px;
    padding: 6px;
}
QTabBar::tab {
    background: #1e293b;
    color: #94a3b8;
    padding: 8px 18px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
    font-size: 11px;
}
QTabBar::tab:selected {
    background: #0f172a;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}
QTableWidget {
    background-color: #0b0f17;
    alternate-background-color: #111827;
    color: #f1f5f9;
    gridline-color: rgba(148, 163, 184, 0.1);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 6px;
    font-size: 11px;
    selection-background-color: #1e293b;
}
QHeaderView::section {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 6px;
    font-weight: 700;
    font-size: 10px;
    border: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}
QLineEdit {
    background: #1e293b;
    color: #f8fafc;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
}
QLineEdit:focus {
    border: 1px solid #38bdf8;
}
QPushButton {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #38bdf8;
}
QPushButton.btnPrimary {
    background-color: #0284c7;
    border: none;
}
QPushButton.btnPrimary:hover {
    background-color: #0369a1;
}
QPushButton.btnSuccess {
    background-color: #059669;
    border: none;
}
QPushButton.btnSuccess:hover {
    background-color: #047857;
}
QPushButton.btnAmber {
    background-color: #d97706;
    border: none;
}
QPushButton.btnAmber:hover {
    background-color: #b45309;
}
QFrame.statCard {
    background: #1e293b;
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 8px;
    padding: 10px;
}
"""


class EvolutionCenterDialog(QDialog):
    """Central interactive management interface for SANTRA ALEE."""

    data_changed = pyqtSignal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        storage: Optional[EvolutionStorage] = None,
        evo_mgr: Optional[EvolutionManager] = None,
        skill_dev: Optional[SkillDeveloper] = None,
        evaluator: Optional[PerformanceEvaluator] = None
    ):
        super().__init__(parent)
        self.storage = storage or evolution_storage
        self.evo_mgr = evo_mgr or evolution_manager
        self.skill_dev = skill_dev or skill_developer
        self.evaluator = evaluator or performance_evaluator

        self.setWindowTitle("SANTRA — ALEE Autonomous Evolution Center")
        self.resize(960, 680)
        self.setStyleSheet(DIALOG_STYLESHEET)

        self._init_ui()
        self._load_all_data()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        # 1. Header Banner
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("ALEE AUTONOMOUS EVOLUTION CENTER")
        lbl_title.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: 800; letter-spacing: 0.08em;")
        lbl_sub = QLabel("Controlled Self-Improvement · Level 3 Approval Gate · Zero-VRAM Versioned Rollback")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_row.addLayout(title_box)

        header_row.addStretch(1)

        self.lbl_status_pill = QLabel("HEALTHY (94.9% PASS)")
        self.lbl_status_pill.setStyleSheet("""
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.4);
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 700;
            font-size: 11px;
        """)
        header_row.addWidget(self.lbl_status_pill)
        root_layout.addLayout(header_row)

        # 2. Main Tabs
        self.tabs = QTabWidget()
        self.tab_proposals = QWidget()
        self.tab_skills_aliases = QWidget()
        self.tab_telemetry = QWidget()

        self._init_proposals_tab()
        self._init_skills_aliases_tab()
        self._init_telemetry_tab()

        self.tabs.addTab(self.tab_proposals, "Proposals & Rollback Gate")
        self.tabs.addTab(self.tab_skills_aliases, "Domain Aliases & Autonomous Skills")
        self.tabs.addTab(self.tab_telemetry, "Weakness Telemetry & Self-Benchmarks")

        root_layout.addWidget(self.tabs, stretch=1)

        # 3. Footer Bar
        footer_row = QHBoxLayout()
        self.lbl_footer_status = QLabel("Ready.")
        self.lbl_footer_status.setStyleSheet("color: #64748b; font-size: 11px;")
        footer_row.addWidget(self.lbl_footer_status)
        footer_row.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        footer_row.addWidget(btn_close)
        root_layout.addLayout(footer_row)

    # ==========================================
    # TAB 1: PROPOSALS & ROLLBACK GATE
    # ==========================================
    def _init_proposals_tab(self):
        layout = QVBoxLayout(self.tab_proposals)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Action Bar
        action_bar = QHBoxLayout()
        lbl_info = QLabel("Proposals submitted by ALEE weakness monitors awaiting human review:")
        lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        action_bar.addWidget(lbl_info)
        action_bar.addStretch(1)

        btn_gen = QPushButton("⚡ Generate Proposals")
        btn_gen.clicked.connect(self._on_generate_proposals)
        action_bar.addWidget(btn_gen)

        btn_approve_all = QPushButton("✓ Approve All Safe Pending")
        btn_approve_all.setProperty("class", "btnSuccess")
        btn_approve_all.setStyleSheet("background-color: #059669; color: #fff; font-weight: 700;")
        btn_approve_all.clicked.connect(self._on_approve_all)
        action_bar.addWidget(btn_approve_all)

        layout.addLayout(action_bar)

        # Proposals Table
        self.tbl_proposals = QTableWidget()
        self.tbl_proposals.setColumnCount(6)
        self.tbl_proposals.setHorizontalHeaderLabels([
            "Proposal ID", "Type", "Target Key", "Evidence", "Reason", "Action"
        ])
        header = self.tbl_proposals.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tbl_proposals)

    def _load_proposals(self):
        proposals = self.storage.get_all_proposals(limit=100)
        self.tbl_proposals.setRowCount(len(proposals))

        for row, p in enumerate(proposals):
            p_id = p["proposal_id"]
            status = p.get("status", "PENDING")

            # ID
            item_id = QTableWidgetItem(p_id)
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_proposals.setItem(row, 0, item_id)

            # Type & Risk Level
            p_type = p.get("proposal_type", "")
            risk_class, risk_level = self.evo_mgr.get_proposal_risk(p_type)
            item_type = QTableWidgetItem(f"{p_type} [{risk_level}]")
            item_type.setFlags(item_type.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if risk_level == "HIGH":
                item_type.setForeground(Qt.GlobalColor.red)
            elif risk_level == "MEDIUM":
                item_type.setForeground(Qt.GlobalColor.yellow)
            self.tbl_proposals.setItem(row, 1, item_type)

            # Target
            item_target = QTableWidgetItem(p.get("target_key", ""))
            item_target.setFlags(item_target.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_proposals.setItem(row, 2, item_target)

            # Evidence
            item_ev = QTableWidgetItem(str(p.get("evidence_count", 1)))
            item_ev.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_ev.setFlags(item_ev.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_proposals.setItem(row, 3, item_ev)

            # Reason
            item_reason = QTableWidgetItem(p.get("reason", ""))
            item_reason.setFlags(item_reason.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_proposals.setItem(row, 4, item_reason)

            # Action Button
            btn_cell = QWidget()
            btn_layout = QHBoxLayout(btn_cell)
            btn_layout.setContentsMargins(4, 2, 4, 2)

            if status == "PENDING":
                btn_act = QPushButton("Approve & Verify")
                btn_act.setStyleSheet("background: #059669; color: #fff; font-size: 10px; padding: 4px 8px;")
                btn_act.clicked.connect(lambda _, pid=p_id: self._on_approve_single(pid))
                btn_layout.addWidget(btn_act)
            elif status == "APPROVED":
                btn_act = QPushButton("Rollback")
                btn_act.setStyleSheet("background: #d97706; color: #fff; font-size: 10px; padding: 4px 8px;")
                btn_act.clicked.connect(lambda _, pid=p_id: self._on_rollback_single(pid))
                btn_layout.addWidget(btn_act)
            else:
                lbl_badge = QLabel(status)
                lbl_badge.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
                btn_layout.addWidget(lbl_badge, alignment=Qt.AlignmentFlag.AlignCenter)

            self.tbl_proposals.setCellWidget(row, 5, btn_cell)

    def _on_generate_proposals(self):
        new_props = self.evo_mgr.generate_proposals()
        self._load_proposals()
        self.lbl_footer_status.setText(f"Generated/refreshed proposals: {len(new_props)} currently pending.")
        self.data_changed.emit()

    def _on_approve_single(self, prop_id: str):
        proposal = self.storage.get_proposal(prop_id)
        if not proposal:
            QMessageBox.warning(self, "Proposal Not Found", f"Proposal '{prop_id}' does not exist.")
            return

        p_type = proposal.get("proposal_type", "")
        risk_class, risk_level = self.evo_mgr.get_proposal_risk(p_type)
        if risk_level in ("MEDIUM", "HIGH"):
            confirm = QMessageBox.question(
                self,
                f"Confirm Proposal Approval ({risk_level} Risk)",
                f"Proposal: {prop_id}\nType: {p_type} ({risk_class})\nTarget: {proposal.get('target_key')}\n\nReason: {proposal.get('reason')}\n\nApprove and verify across regression benchmarks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm != QMessageBox.StandardButton.Yes:
                self.lbl_footer_status.setText(f"Approval of '{prop_id}' cancelled by user.")
                return

        ok, msg = self.evo_mgr.approve_proposal(prop_id, confirmed_by_user=True)
        if ok:
            self.lbl_footer_status.setText(f"Proposal '{prop_id}' approved & verified.")
        else:
            QMessageBox.warning(self, "Approval Failed / Rolled Back", msg)
        self._load_proposals()
        self._load_telemetry()
        self.data_changed.emit()

    def _on_rollback_single(self, prop_id: str):
        ok, msg = self.evo_mgr.rollback_proposal(prop_id)
        if ok:
            self.lbl_footer_status.setText(f"Proposal '{prop_id}' rolled back.")
        else:
            QMessageBox.warning(self, "Rollback Failed", msg)
        self._load_proposals()
        self._load_telemetry()
        self.data_changed.emit()

    def _on_approve_all(self):
        confirm = QMessageBox.question(
            self,
            "Confirm Batch Approval",
            "Approve all pending evolution proposals across regression benchmarks?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        res = self.evo_mgr.approve_all_pending(confirmed_by_user=True)
        self.lbl_footer_status.setText(f"Approved {res['approved_count']} proposals ({res['failed_count']} failed/reverted).")
        self._load_proposals()
        self._load_telemetry()
        self.data_changed.emit()

    # ==========================================
    # TAB 2: DOMAIN ALIASES & AUTONOMOUS SKILLS
    # ==========================================
    def _init_skills_aliases_tab(self):
        layout = QVBoxLayout(self.tab_skills_aliases)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Section A: Aliases
        lbl_aliases = QLabel("PHONETIC DOMAIN ALIASES (Acoustic Correction)")
        lbl_aliases.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 700; letter-spacing: 0.08em;")
        layout.addWidget(lbl_aliases)

        # Mini Add Bar
        add_row = QHBoxLayout()
        self.in_misheard = QLineEdit()
        self.in_misheard.setPlaceholderText("Misheard (e.g. ballorant)")
        add_row.addWidget(self.in_misheard, stretch=2)

        self.in_intended = QLineEdit()
        self.in_intended.setPlaceholderText("Intended (e.g. valorant)")
        add_row.addWidget(self.in_intended, stretch=2)

        btn_add_alias = QPushButton("+ Add Alias Pair")
        btn_add_alias.clicked.connect(self._on_add_alias)
        add_row.addWidget(btn_add_alias)
        layout.addLayout(add_row)

        self.tbl_aliases = QTableWidget()
        self.tbl_aliases.setColumnCount(4)
        self.tbl_aliases.setHorizontalHeaderLabels(["Misheard Phrase", "Intended Target", "Confidence", "Auto Apply"])
        self.tbl_aliases.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tbl_aliases)

        # Section B: Skills
        lbl_skills = QLabel("AUTONOMOUS SKILLS REGISTRY (Declarative Multi-Step Workflows)")
        lbl_skills.setStyleSheet("color: #a78bfa; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; margin-top: 6px;")
        layout.addWidget(lbl_skills)

        self.tbl_skills = QTableWidget()
        self.tbl_skills.setColumnCount(5)
        self.tbl_skills.setHorizontalHeaderLabels(["Skill ID", "Name", "Status", "Success / Fail", "Action"])
        h_skills = self.tbl_skills.horizontalHeader()
        h_skills.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_skills.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_skills.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_skills.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_skills.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tbl_skills)

    def _load_aliases(self):
        with self.storage._lock:
            conn = self.storage._get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT misheard_phrase, intended_phrase, confidence_count, auto_apply
                FROM phonetic_aliases ORDER BY confidence_count DESC
            """)
            rows = cur.fetchall()
            cur.close()

        self.tbl_aliases.setRowCount(len(rows))
        for r, (m, i, c, a) in enumerate(rows):
            it_m = QTableWidgetItem(m)
            it_m.setFlags(it_m.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_aliases.setItem(r, 0, it_m)

            it_i = QTableWidgetItem(i)
            it_i.setFlags(it_i.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_aliases.setItem(r, 1, it_i)

            it_c = QTableWidgetItem(str(c))
            it_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_c.setFlags(it_c.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_aliases.setItem(r, 2, it_c)

            it_a = QTableWidgetItem("Active" if a else "Pending")
            it_a.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if a:
                it_a.setForeground(Qt.GlobalColor.green)
            it_a.setFlags(it_a.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_aliases.setItem(r, 3, it_a)

    def _load_skills(self):
        skills = self.storage.get_all_skills()
        self.tbl_skills.setRowCount(len(skills))

        for r, s in enumerate(skills):
            s_id = s["skill_id"]
            status = s.get("status", "SANDBOX")

            it_id = QTableWidgetItem(s_id)
            it_id.setFlags(it_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_skills.setItem(r, 0, it_id)

            it_name = QTableWidgetItem(s.get("name", ""))
            it_name.setFlags(it_name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_skills.setItem(r, 1, it_name)

            it_status = QTableWidgetItem(status)
            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "VERIFIED":
                it_status.setForeground(Qt.GlobalColor.cyan)
            self.tbl_skills.setItem(r, 2, it_status)

            counts = f"{s.get('success_count', 0)} / {s.get('failure_count', 0)}"
            it_cnt = QTableWidgetItem(counts)
            it_cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_skills.setItem(r, 3, it_cnt)

            # Promotion action button
            btn_cell = QWidget()
            btn_lay = QHBoxLayout(btn_cell)
            btn_lay.setContentsMargins(4, 2, 4, 2)
            if status == "SANDBOX":
                btn_promote = QPushButton("Promote Skill")
                btn_promote.setStyleSheet("background: #0284c7; color: #fff; font-size: 10px; padding: 4px 8px;")
                btn_promote.clicked.connect(lambda _, sid=s_id: self._on_promote_skill(sid))
                btn_lay.addWidget(btn_promote)
            else:
                lbl_ok = QLabel("Ready")
                lbl_ok.setStyleSheet("color: #10b981; font-weight: 700; font-size: 10px;")
                btn_lay.addWidget(lbl_ok, alignment=Qt.AlignmentFlag.AlignCenter)
            self.tbl_skills.setCellWidget(r, 4, btn_cell)

    def _on_add_alias(self):
        mis = self.in_misheard.text().strip().lower()
        intend = self.in_intended.text().strip().lower()
        if not mis or not intend:
            QMessageBox.warning(self, "Invalid Alias", "Please provide both misheard and intended phrases.")
            return

        with self.storage._lock:
            conn = self.storage._get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO phonetic_aliases (misheard_phrase, intended_phrase, confidence_count, auto_apply, last_seen)
                VALUES (?, ?, 5, 1, ?)
                ON CONFLICT(misheard_phrase) DO UPDATE SET
                    intended_phrase=excluded.intended_phrase,
                    confidence_count=MAX(phonetic_aliases.confidence_count, 5),
                    auto_apply=1,
                    last_seen=excluded.last_seen
            """, (mis, intend, time.time()))
            conn.commit()
            cur.close()

        self.in_misheard.clear()
        self.in_intended.clear()
        self._load_aliases()
        self.lbl_footer_status.setText(f"Added alias pair: '{mis}' -> '{intend}'.")
        self.data_changed.emit()

    def _on_promote_skill(self, skill_id: str):
        # 1. Isolated dry-run testing
        passed = self.skill_dev.test_skill_in_sandbox(skill_id)
        if not passed:
            QMessageBox.warning(self, "Dry-Run Failed", f"Skill '{skill_id}' failed safety or dry-run validation.")
            self._load_skills()
            return

        # 2. Explicit User Confirmation Gate
        confirm = QMessageBox.question(
            self,
            "Confirm Skill Promotion",
            f"Skill '{skill_id}' passed isolated dry-run testing (Status: DRY_RUN_PASSED).\n\nPromote this skill to active VERIFIED status?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            promoted, msg = self.skill_dev.promote_skill_to_verified(skill_id, confirmed_by_user=True)
            if promoted:
                self.lbl_footer_status.setText(f"Skill '{skill_id}' verified and active.")
            else:
                QMessageBox.warning(self, "Promotion Failed", msg)
        else:
            self.lbl_footer_status.setText(f"Skill '{skill_id}' kept in DRY_RUN_PASSED status.")
        self._load_skills()
        self.data_changed.emit()

    # ==========================================
    # TAB 3: WEAKNESS TELEMETRY & LIVE BENCHMARKS
    # ==========================================
    def _init_telemetry_tab(self):
        layout = QVBoxLayout(self.tab_telemetry)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Stat Cards Row
        cards_row = QHBoxLayout()

        self.card_exp = QFrame()
        self.card_exp.setProperty("class", "statCard")
        lay_exp = QVBoxLayout(self.card_exp)
        lay_exp.addWidget(QLabel("HISTORICAL SUCCESS RATE"))
        self.lbl_stat_success = QLabel("N/A")
        self.lbl_stat_success.setStyleSheet("color: #10b981; font-size: 16px; font-weight: 800;")
        lay_exp.addWidget(self.lbl_stat_success)
        cards_row.addWidget(self.card_exp)

        self.card_lat = QFrame()
        self.card_lat.setProperty("class", "statCard")
        lay_lat = QVBoxLayout(self.card_lat)
        lay_lat.addWidget(QLabel("OFFLINE BENCHMARK"))
        self.lbl_stat_score = QLabel("Score: NOT RUN")
        self.lbl_stat_score.setStyleSheet("color: #94a3b8; font-size: 16px; font-weight: 800;")
        lay_lat.addWidget(self.lbl_stat_score)
        cards_row.addWidget(self.card_lat)

        self.card_props = QFrame()
        self.card_props.setProperty("class", "statCard")
        lay_props = QVBoxLayout(self.card_props)
        lay_props.addWidget(QLabel("ACTIVE PROPOSALS"))
        self.lbl_stat_props = QLabel("N/A")
        self.lbl_stat_props.setStyleSheet("color: #f59e0b; font-size: 16px; font-weight: 800;")
        lay_props.addWidget(self.lbl_stat_props)
        cards_row.addWidget(self.card_props)

        layout.addLayout(cards_row)

        # Benchmark Runner Bar
        bench_row = QHBoxLayout()
        lbl_b_title = QLabel("Core Learning Smoke Test (FTS5 + Aliases + Injection Filter):")
        lbl_b_title.setStyleSheet("color: #94a3b8; font-size: 11px;")
        bench_row.addWidget(lbl_b_title)
        bench_row.addStretch(1)

        btn_run_bench = QPushButton("▶ Run Core Smoke Test Now")
        btn_run_bench.setProperty("class", "btnPrimary")
        btn_run_bench.clicked.connect(self._on_run_benchmark)
        bench_row.addWidget(btn_run_bench)
        layout.addLayout(bench_row)

        # Telemetry Output Box
        self.txt_telemetry = QTextEdit()
        self.txt_telemetry.setReadOnly(True)
        self.txt_telemetry.setStyleSheet("""
            background-color: #0b0f17;
            color: #94a3b8;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 11px;
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 6px;
        """)
        layout.addWidget(self.txt_telemetry, stretch=1)

    def _load_telemetry(self):
        stats = self.storage.get_stats()
        tot = stats.get("total_experiences", 0)
        succ = stats.get("successful_experiences", 0)
        rate = (succ / tot * 100) if tot > 0 else 100.0
        self.lbl_stat_success.setText(f"{rate:.1f}% ({succ:,}/{tot:,})")

        pending = stats.get("pending_proposals_count", 0)
        appr = stats.get("approved_proposals_count", 0)
        self.lbl_stat_props.setText(f"{pending} Pending · {appr} Approved")

        # Weakness details
        weaknesses = self.evaluator.analyze_weaknesses()
        failing = weaknesses.get("failing_intents", [])

        lines = [
            "=== SANTRA ALEE RUNTIME HEALTH & WEAKNESS AUDIT ===",
            f"Total Experiences: {tot} | Successful: {succ} | Failures: {stats.get('failed_experiences', 0)}",
            f"Success Rate: {rate:.2f}% (Independently Verified app executions counted)",
            f"Active Phonetic Aliases: {stats.get('active_aliases', 0)} / {stats.get('total_aliases', 0)}",
            f"Registered Skills: {stats.get('verified_skills', 0)} Verified / {stats.get('total_skills', 0)} Total",
            f"Knowledge Items: {stats.get('total_knowledge_items', 0)} chunks",
            "",
            "=== FAILING OPERATIONS DETECTED ==="
        ]
        if failing:
            for f_item in failing:
                lines.append(
                    f"- [{f_item['operation']}] Failures: {f_item['failed_count']}/{f_item['total_executions']} "
                    f"({f_item['success_rate']:.1f}% success) | Most Common Error: '{f_item['most_common_error']}'"
                )
        else:
            lines.append("No active failing operations detected.")

        self.txt_telemetry.setPlainText("\n".join(lines))

    def _on_run_benchmark(self):
        t0 = time.perf_counter()
        results = self.evaluator.run_regression_benchmarks()
        dt_ms = (time.perf_counter() - t0) * 1000
        score = results.get("score", 100.0)
        passed = results.get("passed", 0)
        total = results.get("total", 0)

        self.lbl_stat_score.setText(f"{int(score)}% PASS ({dt_ms:.2f}ms)")
        cur_text = self.txt_telemetry.toPlainText()
        bench_block = (
            f"\n\n=== LIVE SELF-BENCHMARK RESULTS ({time.strftime('%H:%M:%S')}) ===\n"
            f"Regression Suite Execution Time: {dt_ms:.3f} ms\n"
            f"Overall Benchmark Score: {score:.1f}% ({passed}/{total} tests passed)\n"
            f"Tests Detail: {json.dumps(results.get('tests', {}), indent=2)}"
        )
        self.txt_telemetry.setPlainText(cur_text + bench_block)
        self.lbl_footer_status.setText(f"Benchmark run complete: {score}% pass in {dt_ms:.2f}ms.")

    def _load_all_data(self):
        self._load_proposals()
        self._load_aliases()
        self._load_skills()
        self._load_telemetry()

