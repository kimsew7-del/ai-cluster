"""Integrations tab - Git, Notion, Google Drive."""

import subprocess
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
    QFileDialog, QTabWidget, QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from cluster_core import load_config, save_config, RESULTS_DIR


# ─────────────────────────────────────────────
# Git Integration
# ─────────────────────────────────────────────

class GitThread(QThread):
    output = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, cmd: list[str], cwd: str = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd

    def run(self):
        try:
            result = subprocess.run(
                self.cmd, capture_output=True, text=True, cwd=self.cwd, timeout=30,
            )
            out = result.stdout + result.stderr
            self.output.emit(out)
            self.finished_signal.emit(result.returncode == 0, out)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class GitPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._thread = None
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Repo path
        repo_row = QHBoxLayout()
        repo_row.addWidget(QLabel("Git 저장소:"))
        self.repo_path = QLineEdit()
        self.repo_path.setPlaceholderText("저장소 경로 (예: ~/projects/my-repo)")
        config = load_config()
        self.repo_path.setText(config.get("integrations", {}).get("git", {}).get("repo_path", ""))
        repo_row.addWidget(self.repo_path)
        browse_btn = QPushButton("찾기")
        browse_btn.clicked.connect(self._browse_repo)
        repo_row.addWidget(browse_btn)
        layout.addLayout(repo_row)

        # Actions
        actions = QHBoxLayout()
        self.status_btn = QPushButton("git status")
        self.status_btn.clicked.connect(lambda: self._run_git(["git", "status"]))
        actions.addWidget(self.status_btn)

        self.log_btn = QPushButton("git log (최근 10)")
        self.log_btn.clicked.connect(lambda: self._run_git(["git", "log", "--oneline", "-10"]))
        actions.addWidget(self.log_btn)

        self.diff_btn = QPushButton("git diff")
        self.diff_btn.clicked.connect(lambda: self._run_git(["git", "diff"]))
        actions.addWidget(self.diff_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # Commit section
        commit_group = QGroupBox("결과 커밋")
        commit_layout = QVBoxLayout(commit_group)
        self.commit_msg = QLineEdit()
        self.commit_msg.setPlaceholderText("커밋 메시지 (비우면 자동 생성)")
        commit_layout.addWidget(self.commit_msg)

        commit_btns = QHBoxLayout()
        self.auto_commit_check = QCheckBox("태스크 완료 시 자동 커밋")
        commit_btns.addWidget(self.auto_commit_check)
        commit_btns.addStretch()
        commit_btn = QPushButton("결과 폴더 커밋")
        commit_btn.setObjectName("primary")
        commit_btn.clicked.connect(self._commit_results)
        commit_btns.addWidget(commit_btn)

        push_btn = QPushButton("Push")
        push_btn.clicked.connect(lambda: self._run_git(["git", "push"]))
        commit_btns.addWidget(push_btn)
        commit_layout.addLayout(commit_btns)
        layout.addWidget(commit_group)

        # Output
        self.git_output = QPlainTextEdit()
        self.git_output.setReadOnly(True)
        self.git_output.setFont(QFont("monospace", 10))
        self.git_output.setPlaceholderText("Git 명령 출력")
        layout.addWidget(self.git_output)

    def _browse_repo(self):
        path = QFileDialog.getExistingDirectory(self, "Git 저장소 선택")
        if path:
            self.repo_path.setText(path)
            self._save_git_config()

    def _save_git_config(self):
        config = load_config()
        if "integrations" not in config:
            config["integrations"] = {}
        config["integrations"]["git"] = {"repo_path": self.repo_path.text()}
        save_config(config)

    def _get_repo(self) -> str:
        path = self.repo_path.text().strip()
        if path:
            return str(Path(path).expanduser())
        return None

    def _run_git(self, cmd: list[str]):
        repo = self._get_repo()
        if not repo:
            self.git_output.setPlainText("저장소 경로를 설정하세요.")
            return
        self._save_git_config()
        self.git_output.setPlainText(f"$ {' '.join(cmd)}\n실행 중...")
        self._thread = GitThread(cmd, cwd=repo)
        self._thread.output.connect(lambda out: self.git_output.setPlainText(f"$ {' '.join(cmd)}\n{out}"))
        self._thread.start()

    def _commit_results(self):
        repo = self._get_repo()
        if not repo:
            self.git_output.setPlainText("저장소 경로를 설정하세요.")
            return
        msg = self.commit_msg.text().strip() or "Add AI cluster results"
        # Copy results to repo
        results_in_repo = Path(repo) / "ai-cluster-results"
        results_in_repo.mkdir(exist_ok=True)

        import shutil
        if RESULTS_DIR.exists():
            for f in RESULTS_DIR.glob("*.json"):
                shutil.copy2(f, results_in_repo / f.name)

        cmds = ["git", "add", "ai-cluster-results/", "&&", "git", "commit", "-m", msg]
        self._run_git(["bash", "-c", f'cd "{repo}" && git add ai-cluster-results/ && git commit -m "{msg}"'])


# ─────────────────────────────────────────────
# Notion Integration
# ─────────────────────────────────────────────

class NotionPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # API Key
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Notion API 키:"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("ntn_xxxxx...")
        config = load_config()
        self.api_key.setText(config.get("integrations", {}).get("notion", {}).get("api_key", ""))
        key_row.addWidget(self.api_key)
        save_key_btn = QPushButton("저장")
        save_key_btn.clicked.connect(self._save_notion_config)
        key_row.addWidget(save_key_btn)
        layout.addLayout(key_row)

        # Database ID
        db_row = QHBoxLayout()
        db_row.addWidget(QLabel("Database ID:"))
        self.db_id = QLineEdit()
        self.db_id.setPlaceholderText("Notion 데이터베이스 ID")
        self.db_id.setText(config.get("integrations", {}).get("notion", {}).get("database_id", ""))
        db_row.addWidget(self.db_id)
        layout.addLayout(db_row)

        # Actions
        actions = QHBoxLayout()
        export_btn = QPushButton("최신 결과 → Notion 저장")
        export_btn.setObjectName("primary")
        export_btn.clicked.connect(self._export_to_notion)
        actions.addWidget(export_btn)

        import_btn = QPushButton("Notion DB에서 태스크 가져오기")
        import_btn.clicked.connect(self._import_from_notion)
        actions.addWidget(import_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # Output
        self.notion_output = QPlainTextEdit()
        self.notion_output.setReadOnly(True)
        self.notion_output.setFont(QFont("monospace", 10))
        self.notion_output.setPlaceholderText("Notion API 연동 결과")
        layout.addWidget(self.notion_output)

    def _save_notion_config(self):
        config = load_config()
        if "integrations" not in config:
            config["integrations"] = {}
        config["integrations"]["notion"] = {
            "api_key": self.api_key.text(),
            "database_id": self.db_id.text(),
        }
        save_config(config)
        self.notion_output.setPlainText("Notion 설정 저장 완료")

    def _export_to_notion(self):
        api_key = self.api_key.text().strip()
        db_id = self.db_id.text().strip()
        if not api_key or not db_id:
            self.notion_output.setPlainText("API 키와 Database ID를 모두 입력하세요.")
            return

        self._save_notion_config()

        # Load latest result
        results_files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if not results_files:
            self.notion_output.setPlainText("저장된 결과가 없습니다.")
            return

        with open(results_files[0]) as f:
            data = json.load(f)

        # Create Notion page via API
        try:
            import urllib.request
            page_data = {
                "parent": {"database_id": db_id},
                "properties": {
                    "Name": {"title": [{"text": {"content": data.get("task", "AI Cluster Result")[:100]}}]},
                },
                "children": [
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"text": {"content": "태스크"}}]},
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": data.get("task", "")[:2000]}}]},
                    },
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"text": {"content": "통합 결과"}}]},
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": data.get("merged", "")[:2000]}}]},
                    },
                ],
            }
            req = urllib.request.Request(
                "https://api.notion.com/v1/pages",
                data=json.dumps(page_data).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                page_url = result.get("url", "")
                self.notion_output.setPlainText(f"Notion 페이지 생성 완료!\nURL: {page_url}")
        except Exception as e:
            self.notion_output.setPlainText(f"Notion API 오류:\n{e}")

    def _import_from_notion(self):
        api_key = self.api_key.text().strip()
        db_id = self.db_id.text().strip()
        if not api_key or not db_id:
            self.notion_output.setPlainText("API 키와 Database ID를 모두 입력하세요.")
            return

        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                data=json.dumps({"page_size": 10}).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                pages = data.get("results", [])
                lines = [f"Notion DB에서 {len(pages)}개 항목 조회:\n"]
                for p in pages:
                    props = p.get("properties", {})
                    title = ""
                    for key, val in props.items():
                        if val.get("type") == "title":
                            titles = val.get("title", [])
                            if titles:
                                title = titles[0].get("text", {}).get("content", "")
                            break
                    lines.append(f"  - {title or '(제목 없음)'}")
                self.notion_output.setPlainText("\n".join(lines))
        except Exception as e:
            self.notion_output.setPlainText(f"Notion API 오류:\n{e}")


# ─────────────────────────────────────────────
# Google Drive Integration
# ─────────────────────────────────────────────

class GoogleDrivePanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Credentials
        cred_row = QHBoxLayout()
        cred_row.addWidget(QLabel("서비스 계정 JSON:"))
        self.cred_path = QLineEdit()
        self.cred_path.setPlaceholderText("credentials.json 파일 경로")
        config = load_config()
        self.cred_path.setText(config.get("integrations", {}).get("gdrive", {}).get("credentials_path", ""))
        cred_row.addWidget(self.cred_path)
        browse_btn = QPushButton("찾기")
        browse_btn.clicked.connect(self._browse_cred)
        cred_row.addWidget(browse_btn)
        layout.addLayout(cred_row)

        # Folder ID
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Drive 폴더 ID:"))
        self.folder_id = QLineEdit()
        self.folder_id.setPlaceholderText("Google Drive 폴더 ID")
        self.folder_id.setText(config.get("integrations", {}).get("gdrive", {}).get("folder_id", ""))
        folder_row.addWidget(self.folder_id)
        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self._save_gdrive_config)
        folder_row.addWidget(save_btn)
        layout.addLayout(folder_row)

        # Actions
        actions = QHBoxLayout()
        upload_btn = QPushButton("결과 업로드")
        upload_btn.setObjectName("primary")
        upload_btn.clicked.connect(self._upload_results)
        actions.addWidget(upload_btn)

        list_btn = QPushButton("폴더 파일 목록")
        list_btn.clicked.connect(self._list_files)
        actions.addWidget(list_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # Status
        self.gdrive_output = QPlainTextEdit()
        self.gdrive_output.setReadOnly(True)
        self.gdrive_output.setFont(QFont("monospace", 10))
        self.gdrive_output.setPlaceholderText(
            "Google Drive 연동\n\n"
            "사용하려면:\n"
            "1. Google Cloud Console에서 서비스 계정 생성\n"
            "2. JSON 키 파일 다운로드\n"
            "3. pip install google-api-python-client google-auth\n"
            "4. 위에서 credentials.json 경로와 폴더 ID 설정"
        )
        layout.addWidget(self.gdrive_output)

    def _browse_cred(self):
        path, _ = QFileDialog.getOpenFileName(self, "서비스 계정 JSON 선택", "", "JSON (*.json)")
        if path:
            self.cred_path.setText(path)
            self._save_gdrive_config()

    def _save_gdrive_config(self):
        config = load_config()
        if "integrations" not in config:
            config["integrations"] = {}
        config["integrations"]["gdrive"] = {
            "credentials_path": self.cred_path.text(),
            "folder_id": self.folder_id.text(),
        }
        save_config(config)
        self.gdrive_output.setPlainText("Google Drive 설정 저장 완료")

    def _get_drive_service(self):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            self.gdrive_output.setPlainText(
                "google-api-python-client 패키지가 필요합니다:\n"
                "pip install google-api-python-client google-auth"
            )
            return None

        cred_path = self.cred_path.text().strip()
        if not cred_path or not Path(cred_path).exists():
            self.gdrive_output.setPlainText("서비스 계정 JSON 파일을 설정하세요.")
            return None

        creds = service_account.Credentials.from_service_account_file(
            cred_path, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=creds)

    def _upload_results(self):
        service = self._get_drive_service()
        if not service:
            return

        folder_id = self.folder_id.text().strip()
        if not folder_id:
            self.gdrive_output.setPlainText("Drive 폴더 ID를 입력하세요.")
            return

        try:
            from googleapiclient.http import MediaFileUpload
            uploaded = []
            for fp in sorted(RESULTS_DIR.glob("*.json"), reverse=True)[:5]:
                media = MediaFileUpload(str(fp), mimetype="application/json")
                file_meta = {"name": fp.name, "parents": [folder_id]}
                result = service.files().create(body=file_meta, media_body=media, fields="id,name").execute()
                uploaded.append(f"  {result['name']} (ID: {result['id']})")

            if uploaded:
                self.gdrive_output.setPlainText(f"업로드 완료 ({len(uploaded)}개):\n" + "\n".join(uploaded))
            else:
                self.gdrive_output.setPlainText("업로드할 결과 파일이 없습니다.")
        except Exception as e:
            self.gdrive_output.setPlainText(f"업로드 오류:\n{e}")

    def _list_files(self):
        service = self._get_drive_service()
        if not service:
            return

        folder_id = self.folder_id.text().strip()
        if not folder_id:
            self.gdrive_output.setPlainText("Drive 폴더 ID를 입력하세요.")
            return

        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents",
                pageSize=20,
                fields="files(id, name, modifiedTime, size)",
            ).execute()
            files = results.get("files", [])
            lines = [f"폴더 내 파일 ({len(files)}개):\n"]
            for f in files:
                size = f.get("size", "?")
                lines.append(f"  {f['name']}  ({size} bytes)  {f.get('modifiedTime', '')[:19]}")
            self.gdrive_output.setPlainText("\n".join(lines))
        except Exception as e:
            self.gdrive_output.setPlainText(f"목록 조회 오류:\n{e}")


# ─────────────────────────────────────────────
# Main Integrations Tab
# ─────────────────────────────────────────────

class IntegrationsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("서비스 연동")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #eee;")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(GitPanel(), "Git")
        tabs.addTab(NotionPanel(), "Notion")
        tabs.addTab(GoogleDrivePanel(), "Google Drive")
        layout.addWidget(tabs)

    def refresh(self):
        pass
