"""Dashboard tab - worker status monitoring."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QGridLayout, QFrame,
)
from PySide6.QtCore import Qt

from cluster_core import load_config, WorkerCheckThread


class WorkerCard(QFrame):
    def __init__(self, worker: dict):
        super().__init__()
        self.worker = worker
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setStyleSheet("""
            WorkerCard {
                background: #2a2a2a; border: 1px solid #444;
                border-radius: 8px; padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #888; font-size: 18px;")
        name_label = QLabel(worker["name"])
        name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #eee;")
        header.addWidget(self.status_dot)
        header.addWidget(name_label)
        header.addStretch()
        layout.addLayout(header)

        # Details
        details = [
            ("호스트", worker.get("host", "-")),
            ("사용자", worker.get("user", "-")),
            ("모델", worker.get("model", "-").upper()),
            ("역할", worker.get("role", "-")),
        ]
        for label, value in details:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet("color: #888; min-width: 50px;")
            val = QLabel(value)
            val.setStyleSheet("color: #ccc;")
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            layout.addLayout(row)

        self.status_label = QLabel("확인 중...")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)

    def set_online(self, online: bool):
        if online:
            self.status_dot.setStyleSheet("color: #4caf50; font-size: 18px;")
            self.status_label.setText("온라인")
            self.status_label.setStyleSheet("color: #4caf50;")
            self.setStyleSheet("""
                WorkerCard {
                    background: #2a2a2a; border: 1px solid #4caf50;
                    border-radius: 8px; padding: 12px;
                }
            """)
        else:
            self.status_dot.setStyleSheet("color: #f44336; font-size: 18px;")
            self.status_label.setText("오프라인")
            self.status_label.setStyleSheet("color: #f44336;")
            self.setStyleSheet("""
                WorkerCard {
                    background: #2a2a2a; border: 1px solid #f44336;
                    border-radius: 8px; padding: 12px;
                }
            """)


class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        self._check_thread = None
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title bar
        title_bar = QHBoxLayout()
        title = QLabel("클러스터 대시보드")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #eee;")
        title_bar.addWidget(title)
        title_bar.addStretch()

        self.refresh_btn = QPushButton("상태 확인")
        self.refresh_btn.setObjectName("primary")
        self.refresh_btn.clicked.connect(self.refresh)
        title_bar.addWidget(self.refresh_btn)
        layout.addLayout(title_bar)

        # Local node
        local_group = QGroupBox("오케스트레이터 (이 PC)")
        local_layout = QHBoxLayout(local_group)
        local_layout.addWidget(QLabel("● 로컬 Claude"))
        local_layout.addWidget(QLabel("역할: 태스크 분할 / 결과 통합 / 리서치"))
        local_layout.addStretch()
        self.local_status = QLabel("온라인")
        self.local_status.setStyleSheet("color: #4caf50; font-weight: bold;")
        local_layout.addWidget(self.local_status)
        layout.addWidget(local_group)

        # Worker cards
        self.cards_layout = QHBoxLayout()
        self.cards_layout.setSpacing(12)
        self.worker_cards: dict[str, WorkerCard] = {}
        layout.addLayout(self.cards_layout)

        layout.addStretch()

        # Summary
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(self.summary_label)

        self.refresh()

    def refresh(self):
        config = load_config()
        workers = config.get("workers", [])

        # Clear old cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.worker_cards.clear()

        # Create cards
        for w in workers:
            card = WorkerCard(w)
            self.worker_cards[w["name"]] = card
            self.cards_layout.addWidget(card)

        if not workers:
            lbl = QLabel("등록된 워커가 없습니다. 설정 탭에서 추가하세요.")
            lbl.setStyleSheet("color: #888; padding: 40px;")
            lbl.setAlignment(Qt.AlignCenter)
            self.cards_layout.addWidget(lbl)
            return

        # Start check
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("확인 중...")
        self.summary_label.setText("워커 상태 확인 중...")
        self._online_count = 0
        self._total_count = len(workers)

        self._check_thread = WorkerCheckThread(workers)
        self._check_thread.result.connect(self._on_worker_result)
        self._check_thread.finished_all.connect(self._on_check_done)
        self._check_thread.start()

    def _on_worker_result(self, name: str, online: bool):
        if name in self.worker_cards:
            self.worker_cards[name].set_online(online)
        if online:
            self._online_count += 1

    def _on_check_done(self):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("상태 확인")
        self.summary_label.setText(
            f"온라인: {self._online_count}/{self._total_count} 워커"
        )
