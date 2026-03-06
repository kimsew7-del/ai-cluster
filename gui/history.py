"""History tab - browse past results."""

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QPlainTextEdit, QSplitter,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from cluster_core import load_results


class HistoryTab(QWidget):
    def __init__(self):
        super().__init__()
        self._results = []
        layout = QVBoxLayout(self)

        title_bar = QHBoxLayout()
        title = QLabel("실행 히스토리")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #eee;")
        title_bar.addWidget(title)
        title_bar.addStretch()

        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.refresh)
        title_bar.addWidget(refresh_btn)
        layout.addLayout(title_bar)

        splitter = QSplitter(Qt.Vertical)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["시간", "태스크", "서브태스크", "소요(초)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.currentCellChanged.connect(self._on_select)
        splitter.addWidget(self.table)

        # Detail view
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        btn_row = QHBoxLayout()
        self.rerun_btn = QPushButton("이 태스크 재실행")
        self.rerun_btn.setEnabled(False)
        btn_row.addStretch()
        btn_row.addWidget(self.rerun_btn)
        detail_layout.addLayout(btn_row)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setFont(QFont("monospace", 10))
        self.detail_view.setPlaceholderText("항목을 선택하면 상세 결과가 표시됩니다")
        detail_layout.addWidget(self.detail_view)
        splitter.addWidget(detail_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

    def refresh(self):
        self._results = load_results()
        self.table.setRowCount(len(self._results))
        for i, r in enumerate(self._results):
            ts = r.get("timestamp", r.get("_file", ""))
            if "T" in ts:
                ts = ts.replace("T", " ")[:19]
            task = r.get("task", "")[:80]
            sub_count = str(len(r.get("subtasks", [])))
            elapsed = str(r.get("elapsed_sec", "?"))

            self.table.setItem(i, 0, QTableWidgetItem(ts))
            self.table.setItem(i, 1, QTableWidgetItem(task))
            self.table.setItem(i, 2, QTableWidgetItem(sub_count))
            self.table.setItem(i, 3, QTableWidgetItem(elapsed))

    def _on_select(self, row, col, prev_row, prev_col):
        if 0 <= row < len(self._results):
            r = self._results[row]
            self.rerun_btn.setEnabled(True)

            lines = []
            lines.append(f"태스크: {r.get('task', '')}")
            lines.append(f"시간: {r.get('timestamp', '')}")
            lines.append(f"소요: {r.get('elapsed_sec', '?')}초")
            lines.append("")

            subtasks = r.get("subtasks", [])
            if subtasks:
                lines.append("--- 서브태스크 ---")
                for i, st in enumerate(subtasks):
                    lines.append(f"  [{i+1}] [{st.get('role', '?')}] {st.get('task', '')}")
                lines.append("")

            results = r.get("results", [])
            if results:
                lines.append("--- 개별 결과 ---")
                for res in results:
                    icon = "[OK]" if res.get("status") == "ok" else "[ERR]"
                    lines.append(f"\n{icon} {res.get('worker', '?')} ({res.get('model', '?')})")
                    lines.append(res.get("result", "")[:1000])
                lines.append("")

            merged = r.get("merged", "")
            if merged:
                lines.append("--- 통합 결과 ---")
                lines.append(merged)

            self.detail_view.setPlainText("\n".join(lines))
