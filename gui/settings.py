"""Settings tab - worker management, orchestrator config."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSpinBox, QMessageBox, QComboBox,
)
from PySide6.QtCore import Qt

from cluster_core import load_config, save_config


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("설정")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #eee;")
        layout.addWidget(title)

        # Worker management
        worker_group = QGroupBox("워커 관리")
        worker_layout = QVBoxLayout(worker_group)

        self.worker_table = QTableWidget()
        self.worker_table.setColumnCount(5)
        self.worker_table.setHorizontalHeaderLabels(["이름", "호스트 (IP)", "사용자", "모델", "역할"])
        self.worker_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.worker_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.worker_table.setSelectionMode(QAbstractItemView.SingleSelection)
        worker_layout.addWidget(self.worker_table)

        worker_btns = QHBoxLayout()
        add_btn = QPushButton("워커 추가")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_worker)
        worker_btns.addWidget(add_btn)

        remove_btn = QPushButton("선택 삭제")
        remove_btn.clicked.connect(self._remove_worker)
        worker_btns.addWidget(remove_btn)

        worker_btns.addStretch()

        save_btn = QPushButton("설정 저장")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_settings)
        worker_btns.addWidget(save_btn)
        worker_layout.addLayout(worker_btns)
        layout.addWidget(worker_group)

        # Orchestrator settings
        orch_group = QGroupBox("오케스트레이터 설정")
        orch_layout = QVBoxLayout(orch_group)

        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel("타임아웃 (초):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 1800)
        self.timeout_spin.setValue(300)
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addStretch()
        orch_layout.addLayout(timeout_row)

        retry_row = QHBoxLayout()
        retry_row.addWidget(QLabel("최대 재시도:"))
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(2)
        retry_row.addWidget(self.retry_spin)
        retry_row.addStretch()
        orch_layout.addLayout(retry_row)

        layout.addWidget(orch_group)

        # Role mapping
        role_group = QGroupBox("역할 매핑")
        role_layout = QVBoxLayout(role_group)

        for role_name in ["coding", "research", "summary"]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{role_name}:"))
            combo = QComboBox()
            combo.setObjectName(f"role_{role_name}")
            combo.addItems(["local", "round-robin"])
            row.addWidget(combo)
            row.addStretch()
            role_layout.addLayout(row)

        layout.addWidget(role_group)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        config = load_config()
        workers = config.get("workers", [])

        self.worker_table.setRowCount(len(workers))
        for i, w in enumerate(workers):
            self.worker_table.setItem(i, 0, QTableWidgetItem(w.get("name", "")))
            self.worker_table.setItem(i, 1, QTableWidgetItem(w.get("host", "")))
            self.worker_table.setItem(i, 2, QTableWidgetItem(w.get("user", "")))
            self.worker_table.setItem(i, 3, QTableWidgetItem(w.get("model", "")))
            self.worker_table.setItem(i, 4, QTableWidgetItem(w.get("role", "")))

        orch = config.get("orchestrator", {})
        self.timeout_spin.setValue(orch.get("timeout", 300))
        self.retry_spin.setValue(orch.get("max_retries", 2))

        # Update role combos with worker names
        roles = config.get("roles", {})
        for role_name in ["coding", "research", "summary"]:
            combo = self.findChild(QComboBox, f"role_{role_name}")
            if combo:
                combo.clear()
                combo.addItems(["local", "round-robin"] + [w.get("name", "") for w in workers])
                current = roles.get(role_name, "local")
                idx = combo.findText(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _add_worker(self):
        row = self.worker_table.rowCount()
        self.worker_table.setRowCount(row + 1)
        self.worker_table.setItem(row, 0, QTableWidgetItem("new-worker"))
        self.worker_table.setItem(row, 1, QTableWidgetItem("100.x.x.x"))
        self.worker_table.setItem(row, 2, QTableWidgetItem("user"))
        self.worker_table.setItem(row, 3, QTableWidgetItem("claude"))
        self.worker_table.setItem(row, 4, QTableWidgetItem("coding"))

    def _remove_worker(self):
        row = self.worker_table.currentRow()
        if row >= 0:
            self.worker_table.removeRow(row)

    def _save_settings(self):
        config = load_config()

        # Workers
        workers = []
        for i in range(self.worker_table.rowCount()):
            w = {}
            for j, key in enumerate(["name", "host", "user", "model", "role"]):
                item = self.worker_table.item(i, j)
                w[key] = item.text() if item else ""
            workers.append(w)
        config["workers"] = workers

        # Orchestrator
        config["orchestrator"] = {
            "timeout": self.timeout_spin.value(),
            "max_retries": self.retry_spin.value(),
            "results_dir": "~/.claude-cluster/results",
        }

        # Roles
        roles = {}
        for role_name in ["coding", "research", "summary"]:
            combo = self.findChild(QComboBox, f"role_{role_name}")
            if combo:
                roles[role_name] = combo.currentText()
        roles["default"] = "round-robin"
        config["roles"] = roles

        save_config(config)
        QMessageBox.information(self, "저장", "설정이 저장되었습니다.")
