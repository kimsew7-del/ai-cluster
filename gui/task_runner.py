"""Task runner tab - prompt input, execution, results."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPlainTextEdit,
    QPushButton, QComboBox, QGroupBox, QSplitter, QTabWidget, QFrame,
    QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QFont, QColor

from cluster_core import TaskRunThread, get_project_dir, get_avg_elapsed


class WorkerStatusWidget(QFrame):
    """Individual worker status row with live output preview."""

    PHASE_COLORS = {
        "waiting": "#666",
        "running": "#2196f3",
        "ok": "#4caf50",
        "error": "#f44336",
        "timeout": "#ff9800",
    }

    def __init__(self, name: str, model: str, task_snippet: str):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.worker_name = name
        self._phase = "running"
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._output_chars = 0
        self._output_lines = 0
        self._last_line = ""
        self._spinner_idx = 0
        self._spinner_frames = ["\u28f7", "\u28ef", "\u28df", "\u287f", "\u28bf", "\u28fb", "\u28fd", "\u28fe"]

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(4)

        # Top row: icon, name, model, time, status
        top = QHBoxLayout()
        top.setSpacing(8)

        self.icon_label = QLabel(self._spinner_frames[0])
        self.icon_label.setFixedWidth(16)
        self.icon_label.setStyleSheet("font-size: 14px;")
        top.addWidget(self.icon_label)

        self.name_label = QLabel(f"<b>{name}</b>")
        self.name_label.setFixedWidth(130)
        top.addWidget(self.name_label)

        self.model_label = QLabel(model or "?")
        self.model_label.setFixedWidth(60)
        self.model_label.setStyleSheet("color: #aaa;")
        top.addWidget(self.model_label)

        self.task_label = QLabel(task_snippet)
        self.task_label.setStyleSheet("color: #888; font-size: 11px;")
        top.addWidget(self.task_label, 1)

        self.chars_label = QLabel("")
        self.chars_label.setFixedWidth(70)
        self.chars_label.setStyleSheet("color: #666; font-size: 11px;")
        self.chars_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.chars_label)

        self.time_label = QLabel("0s")
        self.time_label.setFixedWidth(45)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.time_label.setStyleSheet("font-weight: bold;")
        top.addWidget(self.time_label)

        self.status_label = QLabel("실행 중")
        self.status_label.setFixedWidth(65)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.status_label)

        main_layout.addLayout(top)

        # Bottom row: live output preview
        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet(
            "color: #7aa2f7; font-family: monospace; font-size: 11px; "
            "padding: 2px 4px 2px 24px;"
        )
        self.preview_label.setWordWrap(True)
        self.preview_label.setMaximumHeight(36)
        main_layout.addWidget(self.preview_label)

        self._update_style()

    def _update_style(self):
        color = self.PHASE_COLORS.get(self._phase, "#666")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        if self._phase == "running":
            self.setStyleSheet(
                f"WorkerStatusWidget {{ border: 1px solid {color}; border-radius: 4px; "
                f"background: rgba(33, 150, 243, 15); }}"
            )
        elif self._phase == "ok":
            self.setStyleSheet(
                "WorkerStatusWidget { border: 1px solid #333; border-radius: 4px; "
                "background: rgba(76, 175, 80, 10); }"
            )
        else:
            self.setStyleSheet(
                f"WorkerStatusWidget {{ border: 1px solid {color}; border-radius: 4px; }}"
            )

    def tick(self):
        if self._phase != "running":
            return
        secs = self._elapsed.elapsed() // 1000
        self.time_label.setText(f"{secs}s")
        # Animate spinner
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        self.icon_label.setText(self._spinner_frames[self._spinner_idx])

    def append_output(self, text: str):
        self._output_chars += len(text)
        self._output_lines += text.count("\n")
        # Show last meaningful line
        lines = text.strip().split("\n")
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                self._last_line = stripped
                break
        if self._last_line:
            display = self._last_line[:120]
            if len(self._last_line) > 120:
                display += "..."
            self.preview_label.setText(display)
        self.chars_label.setText(f"{self._output_chars}자")

    def set_complete(self, status: str):
        self._phase = status
        secs = self._elapsed.elapsed() // 1000
        self.time_label.setText(f"{secs}s")
        icons = {"ok": "\u2714", "error": "\u2718", "timeout": "\u231b"}
        labels = {"ok": "완료", "error": "오류", "timeout": "타임아웃"}
        self.icon_label.setText(icons.get(status, "?"))
        self.status_label.setText(labels.get(status, status))
        if status == "ok":
            self.preview_label.setStyleSheet(
                self.preview_label.styleSheet().replace("#7aa2f7", "#4caf50")
            )
        elif status != "ok":
            self.preview_label.setStyleSheet(
                self.preview_label.styleSheet().replace("#7aa2f7", "#f44336")
            )
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
        self._est_secs = None

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

        # Status bar with progress
        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; padding: 4px;")
        status_row.addWidget(self.status_label)

        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color: #ff9800; padding: 4px; font-size: 11px;")
        self.eta_label.setAlignment(Qt.AlignRight)
        status_row.addWidget(self.eta_label)

        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet("color: #888; padding: 4px;")
        self.elapsed_label.setAlignment(Qt.AlignRight)
        status_row.addWidget(self.elapsed_label)
        layout.addLayout(status_row)

        # Overall progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #333; border: none; border-radius: 3px; }
            QProgressBar::chunk { background: #2196f3; border-radius: 3px; }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

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
        self.eta_label.setText("")
        self.status_label.setStyleSheet("color: #888;")
        self._clear_workers()

        # Estimated time
        self._est_secs = get_avg_elapsed()
        if self._est_secs:
            self.eta_label.setText(f"예상 ~{self._est_secs}초")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.show()

        self._global_timer.start()
        self._tick_timer.start()

        project_dir = get_project_dir()
        self._task_thread = TaskRunThread(task, model, str(project_dir) if project_dir else None)
        self._task_thread.status_update.connect(self._on_status)
        self._task_thread.subtasks_ready.connect(self._on_subtasks)
        self._task_thread.worker_started.connect(self._on_worker_started)
        self._task_thread.worker_output.connect(self._on_worker_output)
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
        pass

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
            self.progress_layout.insertWidget(self.progress_layout.count() - 1, widget)

    def _on_worker_output(self, name: str, text: str):
        if name in self._worker_widgets:
            self._worker_widgets[name].append_output(text)

    def _on_worker_result(self, result: dict):
        name = result["worker"]
        if name in self._worker_widgets:
            self._worker_widgets[name].set_complete(result["status"])

        icon = "\u2714" if result["status"] == "ok" else "\u2718"
        text = f"{icon} {result['worker']} ({result.get('model', '?')})\n"
        text += result.get("result", "")[:500] + "\n\n"
        self.individual_results.appendPlainText(text)

        # Update progress
        done = sum(1 for w in self._worker_widgets.values() if w._phase != "running")
        total = len(self._worker_widgets)
        if total > 0:
            self.status_label.setText(f"병렬 실행 중... ({done}/{total} 완료)")
            self.progress_bar.setValue(int(done / total * 100))

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
        self.eta_label.setText("")
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #333; border: none; border-radius: 3px; }
            QProgressBar::chunk { background: #4caf50; border-radius: 3px; }
        """)

    def _tick_workers(self):
        for w in self._worker_widgets.values():
            w.tick()
        secs = self._global_timer.elapsed() // 1000
        self.elapsed_label.setText(f"{secs}s")

        # Update ETA
        if self._est_secs and self._est_secs > 0:
            remaining = max(0, self._est_secs - secs)
            if remaining > 0:
                self.eta_label.setText(f"남은 시간 ~{remaining}초")
            else:
                self.eta_label.setText("예상 시간 초과")
                self.eta_label.setStyleSheet("color: #f44336; padding: 4px; font-size: 11px;")
            # Time-based progress if workers haven't started yet
            if not self._worker_widgets:
                pct = min(90, int(secs / self._est_secs * 100))
                self.progress_bar.setValue(pct)

    def _copy_result(self):
        from PySide6.QtWidgets import QApplication
        text = self.merged_result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("클립보드에 복사됨")

    def refresh(self):
        pass
