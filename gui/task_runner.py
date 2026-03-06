"""Task runner tab - prompt input, execution, results."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPlainTextEdit,
    QPushButton, QComboBox, QGroupBox, QSplitter, QTabWidget, QFrame,
)
from PySide6.QtCore import Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QFont, QColor

from cluster_core import TaskRunThread


class WorkerStatusWidget(QFrame):
    """Individual worker status row."""

    PHASE_COLORS = {
        "waiting": "#666",
        "running": "#2196f3",
        "ok": "#4caf50",
        "error": "#f44336",
        "timeout": "#ff9800",
    }
    PHASE_ICONS = {
        "waiting": "\u23f3",   # hourglass
        "running": "\u25b6",   # play
        "ok": "\u2714",        # check
        "error": "\u2718",     # cross
        "timeout": "\u231b",   # hourglass done
    }

    def __init__(self, name: str, model: str, task_snippet: str):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.worker_name = name
        self._phase = "running"
        self._elapsed = QElapsedTimer()
        self._elapsed.start()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.icon_label = QLabel(self.PHASE_ICONS["running"])
        self.icon_label.setFixedWidth(20)
        layout.addWidget(self.icon_label)

        self.name_label = QLabel(f"<b>{name}</b>")
        self.name_label.setFixedWidth(130)
        layout.addWidget(self.name_label)

        self.model_label = QLabel(model or "?")
        self.model_label.setFixedWidth(60)
        self.model_label.setStyleSheet("color: #aaa;")
        layout.addWidget(self.model_label)

        self.task_label = QLabel(task_snippet)
        self.task_label.setStyleSheet("color: #999;")
        layout.addWidget(self.task_label, 1)

        self.time_label = QLabel("0s")
        self.time_label.setFixedWidth(50)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.time_label)

        self.status_label = QLabel("실행 중...")
        self.status_label.setFixedWidth(80)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.status_label)

        self._update_style()

    def _update_style(self):
        color = self.PHASE_COLORS.get(self._phase, "#666")
        self.icon_label.setText(self.PHASE_ICONS.get(self._phase, "?"))
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        border = color if self._phase == "running" else "#333"
        self.setStyleSheet(f"WorkerStatusWidget {{ border: 1px solid {border}; border-radius: 4px; }}")

    def tick(self):
        if self._phase == "running":
            secs = self._elapsed.elapsed() // 1000
            self.time_label.setText(f"{secs}s")

    def set_complete(self, status: str):
        self._phase = status
        secs = self._elapsed.elapsed() // 1000
        self.time_label.setText(f"{secs}s")
        labels = {"ok": "완료", "error": "오류", "timeout": "타임아웃"}
        self.status_label.setText(labels.get(status, status))
        self._update_style()


class TaskRunnerTab(QWidget):
    def __init__(self):
        super().__init__()
        self._task_thread = None
        self._worker_widgets: dict[str, WorkerStatusWidget] = {}
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(500)
        self._tick_timer.timeout.connect(self._tick_workers)
        self._global_timer = QElapsedTimer()

        layout = QVBoxLayout(self)

        # Input section
        input_group = QGroupBox("태스크 입력")
        input_layout = QVBoxLayout(input_group)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("실행할 태스크를 입력하세요...")
        self.prompt_edit.setMaximumHeight(120)
        input_layout.addWidget(self.prompt_edit)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("모델:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["자동 분배", "claude", "gemini"])
        controls.addWidget(self.model_combo)
        controls.addStretch()

        self.run_btn = QPushButton("실행")
        self.run_btn.setObjectName("primary")
        self.run_btn.setMinimumWidth(120)
        self.run_btn.clicked.connect(self._run_task)
        controls.addWidget(self.run_btn)
        input_layout.addLayout(controls)
        layout.addWidget(input_group)

        # Status bar
        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; padding: 4px;")
        status_row.addWidget(self.status_label)
        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet("color: #888; padding: 4px;")
        self.elapsed_label.setAlignment(Qt.AlignRight)
        status_row.addWidget(self.elapsed_label)
        layout.addLayout(status_row)

        # Results section
        splitter = QSplitter(Qt.Vertical)

        # Worker progress panel
        self.progress_group = QGroupBox("워커 진행 상황")
        self.progress_layout = QVBoxLayout(self.progress_group)
        self.progress_layout.setSpacing(4)
        self._no_worker_label = QLabel("태스크 실행 시 워커 상태가 여기에 표시됩니다")
        self._no_worker_label.setStyleSheet("color: #666; padding: 12px;")
        self._no_worker_label.setAlignment(Qt.AlignCenter)
        self.progress_layout.addWidget(self._no_worker_label)
        self.progress_layout.addStretch()
        splitter.addWidget(self.progress_group)

        # Result tabs
        result_group = QGroupBox("실행 결과")
        result_layout = QVBoxLayout(result_group)

        self.result_tabs = QTabWidget()
        self.merged_result = QPlainTextEdit()
        self.merged_result.setReadOnly(True)
        self.merged_result.setFont(QFont("monospace", 10))
        self.result_tabs.addTab(self.merged_result, "통합 결과")

        self.individual_results = QPlainTextEdit()
        self.individual_results.setReadOnly(True)
        self.individual_results.setFont(QFont("monospace", 10))
        self.result_tabs.addTab(self.individual_results, "개별 결과")

        result_layout.addWidget(self.result_tabs)

        # Copy button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("결과 복사")
        copy_btn.clicked.connect(self._copy_result)
        btn_row.addWidget(copy_btn)
        result_layout.addLayout(btn_row)

        splitter.addWidget(result_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

    def _run_task(self):
        task = self.prompt_edit.toPlainText().strip()
        if not task:
            self.status_label.setText("태스크를 입력하세요.")
            self.status_label.setStyleSheet("color: #f44336;")
            return

        model = self.model_combo.currentText()
        if model == "자동 분배":
            model = None

        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.merged_result.clear()
        self.individual_results.clear()
        self.elapsed_label.setText("")
        self.status_label.setStyleSheet("color: #888;")
        self._clear_workers()

        self._global_timer.start()
        self._tick_timer.start()

        self._task_thread = TaskRunThread(task, model)
        self._task_thread.status_update.connect(self._on_status)
        self._task_thread.subtasks_ready.connect(self._on_subtasks)
        self._task_thread.worker_started.connect(self._on_worker_started)
        self._task_thread.worker_result.connect(self._on_worker_result)
        self._task_thread.task_complete.connect(self._on_complete)
        self._task_thread.start()

    def _clear_workers(self):
        for w in self._worker_widgets.values():
            self.progress_layout.removeWidget(w)
            w.deleteLater()
        self._worker_widgets.clear()
        self._no_worker_label.show()

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_subtasks(self, subtasks: list):
        pass  # workers will appear via worker_started

    def _on_worker_started(self, name: str, task_snippet: str):
        self._no_worker_label.hide()
        if name not in self._worker_widgets:
            model = ""
            if "claude" in name.lower() or name == "local(claude)":
                model = "claude"
            elif "gemini" in name.lower():
                model = "gemini"
            widget = WorkerStatusWidget(name, model, task_snippet)
            self._worker_widgets[name] = widget
            # Insert before the stretch
            self.progress_layout.insertWidget(self.progress_layout.count() - 1, widget)

    def _on_worker_result(self, result: dict):
        name = result["worker"]
        if name in self._worker_widgets:
            self._worker_widgets[name].set_complete(result["status"])

        icon = "\u2714" if result["status"] == "ok" else "\u2718"
        text = f"{icon} {result['worker']} ({result.get('model', '?')})\n"
        text += result.get("result", "")[:500] + "\n\n"
        self.individual_results.appendPlainText(text)

        # Update status with completion count
        done = sum(1 for w in self._worker_widgets.values() if w._phase != "running")
        total = len(self._worker_widgets)
        if total > 0:
            self.status_label.setText(f"병렬 실행 중... ({done}/{total} 완료)")

    def _on_complete(self, merged: str, filepath: str):
        self._tick_timer.stop()
        self.merged_result.setPlainText(merged)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("실행")
        total_secs = self._global_timer.elapsed() // 1000
        status = f"완료 ({total_secs}초)"
        if filepath:
            status += f" | 저장: {filepath}"
        self.status_label.setText(status)
        self.status_label.setStyleSheet("color: #4caf50;")
        self.elapsed_label.setText(f"총 {total_secs}초")

    def _tick_workers(self):
        for w in self._worker_widgets.values():
            w.tick()
        secs = self._global_timer.elapsed() // 1000
        self.elapsed_label.setText(f"{secs}s")

    def _copy_result(self):
        from PySide6.QtWidgets import QApplication
        text = self.merged_result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("클립보드에 복사됨")

    def refresh(self):
        pass
