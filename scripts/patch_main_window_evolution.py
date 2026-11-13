"""
Patch ui/main_window.py with ALEE Evolution Status card and sig_evolution_updated signal
"""

def patch():
    with open('ui/main_window.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add sig_evolution_updated signal
    target1 = '    sig_ai_mode_changed = pyqtSignal(bool)\n'
    repl1 = '    sig_ai_mode_changed = pyqtSignal(bool)\n    sig_evolution_updated = pyqtSignal(dict)\n'
    assert target1 in content, 'target1 not found'
    content = content.replace(target1, repl1, 1)

    # 2. Add card_evolution in _init_ui
    target2 = '''        self.lbl_side_active_tool = QLabel("IDLE")
        self.lbl_side_active_tool.setStyleSheet("color: #e2e8f0; font-size: 11px; font-weight: 600;")
        card_task_layout.addWidget(self.lbl_side_active_tool)
        info_layout.addWidget(card_task)

        info_layout.addStretch(1)'''

    repl2 = '''        self.lbl_side_active_tool = QLabel("IDLE")
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

        info_layout.addWidget(card_evolution)

        info_layout.addStretch(1)'''
    assert target2 in content, 'target2 not found'
    content = content.replace(target2, repl2, 1)

    # 3. Wire signal in _wire_signals
    target3 = '        self.sig_ai_mode_changed.connect(self._on_ai_mode_changed)\n'
    repl3 = '        self.sig_ai_mode_changed.connect(self._on_ai_mode_changed)\n        self.sig_evolution_updated.connect(self._on_evolution_updated)\n'
    assert target3 in content, 'target3 not found'
    content = content.replace(target3, repl3, 1)

    # 4. Add _on_evolution_updated handler method
    target4 = '''    def _update_typing_badge(self, state: str, details: dict):'''
    repl4 = '''    def _on_evolution_updated(self, data: dict):
        """Thread-safe update of ALEE telemetry badge."""
        if not data:
            return
        active_aliases = data.get("active_aliases_count", 0)
        total_knowledge = (data.get("database_stats") or {}).get("total_knowledge_items", 0)
        benchmarks = data.get("benchmarks") or {}
        score = benchmarks.get("score", 100.0)
        sys_res = data.get("system_resources") or {}
        can_run = sys_res.get("can_run", True)
        game = sys_res.get("game_detected")

        if hasattr(self, "lbl_evo_aliases"):
            self.lbl_evo_aliases.setText(f"Aliases: {active_aliases}")
        if hasattr(self, "lbl_evo_knowledge"):
            self.lbl_evo_knowledge.setText(f"Docs: {total_knowledge}")
        if hasattr(self, "lbl_evo_score"):
            self.lbl_evo_score.setText(f"Score: {int(score)}% PASS" if score >= 90 else f"Score: {int(score)}%")
        if hasattr(self, "lbl_evo_guard"):
            if game:
                self.lbl_evo_guard.setText("PAUSED (GAME)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            elif not can_run:
                self.lbl_evo_guard.setText("PAUSED (RES)")
                self.lbl_evo_guard.setStyleSheet("color: #f59e0b; font-size: 9px; font-weight: 600;")
            else:
                self.lbl_evo_guard.setText("LEARNING IDLE")
                self.lbl_evo_guard.setStyleSheet("color: #10b981; font-size: 9px; font-weight: 600;")

    def _update_typing_badge(self, state: str, details: dict):'''
    assert target4 in content, 'target4 not found'
    content = content.replace(target4, repl4, 1)

    with open('ui/main_window.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Successfully patched ui/main_window.py with Evolution Telemetry Card")

if __name__ == '__main__':
    patch()
