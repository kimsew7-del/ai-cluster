#!/usr/bin/env python3
"""AI Cluster Manager - PySide6 GUI"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStatusBar, QMenuBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont

from dashboard import DashboardTab
from task_runner import TaskRunnerTab
from history import HistoryTab
from integrations import IntegrationsTab
from settings import SettingsTab

CONFIG_PATH = Path.home() / ".claude-cluster" / "config.yaml"
RESULTS_DIR = Path.home() / ".claude-cluster" / "results"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Cluster Manager")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        self._setup_menubar()
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
        self.setCentralWidget(self.tabs)

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
