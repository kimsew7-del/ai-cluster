#!/usr/bin/env python3
"""AI Cluster Manager - PySide6 GUI"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStatusBar, QMenuBar,
    QHBoxLayout, QLabel, QPushButton, QWidget, QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont

from dashboard import DashboardTab
from task_runner import TaskRunnerTab
from history import HistoryTab
from integrations import IntegrationsTab
from settings import SettingsTab
from cluster_core import load_config, set_project, detect_git_repo, get_project_dir, ProjectSyncThread

CONFIG_PATH = Path.home() / ".claude-cluster" / "config.yaml"
RESULTS_DIR = Path.home() / ".claude-cluster" / "results"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Cluster Manager")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self._sync_thread = None

        self._setup_menubar()
        self._setup_project_bar()
        self._setup_tabs()
        self._setup_statusbar()

    def _setup_menubar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("파일(&F)")

        refresh_action = QAction("새로고침(&R)", self)
        refresh_action.setShortcut("Ctrl+R")
        refresh_action.triggered.connect(self._refresh)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        quit_action = QAction("종료(&Q)", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _setup_project_bar(self):
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)

        layout.addWidget(QLabel("프로젝트:"))

        self.project_label = QLabel("선택되지 않음")
        self.project_label.setStyleSheet("color: #aaa; font-weight: bold; padding: 0 8px;")
        layout.addWidget(self.project_label)

        self.repo_label = QLabel("")
        self.repo_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self.repo_label)

        layout.addStretch()

        self.sync_btn = QPushButton("동기화")
        self.sync_btn.setToolTip("워커들에 프로젝트 동기화 (push + pull)")
        self.sync_btn.clicked.connect(self._sync_project)
        self.sync_btn.setEnabled(False)
        layout.addWidget(self.sync_btn)

        open_btn = QPushButton("폴더 열기")
        open_btn.clicked.connect(self._open_project)
        layout.addWidget(open_btn)

        self.setMenuWidget(None)  # clear if any
        # Insert project bar above tabs
        central = QWidget()
        self._central_layout = __import__('PySide6.QtWidgets', fromlist=['QVBoxLayout']).QVBoxLayout(central)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_layout.setSpacing(0)
        self._central_layout.addWidget(bar)
        self.setCentralWidget(central)

        # Load saved project
        project_dir = get_project_dir()
        if project_dir and project_dir.exists():
            self._set_project_display(str(project_dir))

    def _open_project(self):
        folder = QFileDialog.getExistingDirectory(self, "프로젝트 폴더 선택", str(Path.home()))
        if not folder:
            return
        repo_url = detect_git_repo(Path(folder))
        set_project(folder, repo_url)
        self._set_project_display(folder)
        self.statusBar().showMessage(f"프로젝트 설정: {folder}")

    def _set_project_display(self, path: str):
        name = Path(path).name
        self.project_label.setText(name)
        self.project_label.setStyleSheet("color: #4caf50; font-weight: bold; padding: 0 8px;")
        repo_url = detect_git_repo(Path(path))
        if repo_url:
            self.repo_label.setText(repo_url)
            self.sync_btn.setEnabled(True)
        else:
            self.repo_label.setText("(git repo 없음)")
            self.sync_btn.setEnabled(False)

    def _sync_project(self):
        project_dir = get_project_dir()
        if not project_dir:
            return
        config = load_config()
        workers = config.get("workers", [])
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("동기화 중...")
        self._sync_thread = ProjectSyncThread(str(project_dir), workers)
        self._sync_thread.status.connect(lambda msg: self.statusBar().showMessage(msg))
        self._sync_thread.finished_ok.connect(self._on_sync_done)
        self._sync_thread.start()

    def _on_sync_done(self, repo_url: str):
        self.sync_btn.setEnabled(True)
        self.sync_btn.setText("동기화")
        if repo_url:
            self.statusBar().showMessage("워커 동기화 완료")
        else:
            self.statusBar().showMessage("동기화 실패 - git remote를 확인하세요")

    def _setup_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.dashboard_tab = DashboardTab()
        self.task_tab = TaskRunnerTab()
        self.history_tab = HistoryTab()
        self.integrations_tab = IntegrationsTab()
        self.settings_tab = SettingsTab()

        self.tabs.addTab(self.dashboard_tab, "대시보드")
        self.tabs.addTab(self.task_tab, "태스크 실행")
        self.tabs.addTab(self.history_tab, "히스토리")
        self.tabs.addTab(self.integrations_tab, "연동")
        self.tabs.addTab(self.settings_tab, "설정")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._central_layout.addWidget(self.tabs)

    def _setup_statusbar(self):
        self.statusBar().showMessage("준비 완료")

    def _refresh(self):
        idx = self.tabs.currentIndex()
        self._on_tab_changed(idx)

    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark theme
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(40, 40, 40))
    palette.setColor(QPalette.AlternateBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.Link, QColor(90, 160, 255))
    palette.setColor(QPalette.Highlight, QColor(70, 130, 230))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet("""
        QTabWidget::pane { border: 1px solid #444; }
        QTabBar::tab {
            background: #2a2a2a; color: #bbb; padding: 8px 20px;
            border: 1px solid #444; border-bottom: none;
            margin-right: 2px; border-radius: 4px 4px 0 0;
        }
        QTabBar::tab:selected { background: #3a3a3a; color: #fff; }
        QTabBar::tab:hover { background: #333; }
        QPushButton {
            background: #4a4a4a; border: 1px solid #555; padding: 6px 16px;
            border-radius: 4px; color: #ddd;
        }
        QPushButton:hover { background: #555; }
        QPushButton:pressed { background: #666; }
        QPushButton#primary {
            background: #2d6bcf; border-color: #3d7bdf;
        }
        QPushButton#primary:hover { background: #3d7bdf; }
        QTextEdit, QPlainTextEdit {
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            padding: 4px; color: #ddd;
        }
        QLineEdit {
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            padding: 4px 8px; color: #ddd;
        }
        QComboBox {
            background: #3a3a3a; border: 1px solid #444; border-radius: 4px;
            padding: 4px 8px; color: #ddd;
        }
        QGroupBox {
            border: 1px solid #444; border-radius: 6px;
            margin-top: 10px; padding-top: 16px; color: #ccc;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
        QTableWidget {
            background: #2a2a2a; gridline-color: #444;
            border: 1px solid #444; border-radius: 4px;
        }
        QHeaderView::section {
            background: #3a3a3a; color: #ccc; padding: 6px;
            border: 1px solid #444;
        }
        QScrollBar:vertical {
            background: #2a2a2a; width: 10px; border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background: #555; border-radius: 5px; min-height: 20px;
        }
        QLabel#status-online { color: #4caf50; font-weight: bold; }
        QLabel#status-offline { color: #f44336; font-weight: bold; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
