"""Core cluster operations - shared across tabs."""

import asyncio
import json
import subprocess
from pathlib import Path
from datetime import datetime

import yaml
from PySide6.QtCore import QThread, Signal

CONFIG_PATH = Path.home() / ".claude-cluster" / "config.yaml"
RESULTS_DIR = Path.home() / ".claude-cluster" / "results"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"workers": [], "roles": {}, "orchestrator": {"timeout": 300, "max_retries": 2, "results_dir": str(RESULTS_DIR)}}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def load_results() -> list[dict]:
    """Load all result JSON files, newest first."""
    results = []
    if not RESULTS_DIR.exists():
        return results
    for fp in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            with open(fp) as f:
                data = json.load(f)
                data["_file"] = fp.name
                results.append(data)
        except Exception:
            pass
    return results


class WorkerCheckThread(QThread):
    """Check worker SSH connectivity in background."""
    result = Signal(str, bool)  # worker_name, is_online
    finished_all = Signal()

    def __init__(self, workers: list):
        super().__init__()
        self.workers = workers

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._check_all())
        loop.close()
        self.finished_all.emit()

    async def _check_all(self):
        tasks = [self._check_one(w) for w in self.workers]
        await asyncio.gather(*tasks)

    async def _check_one(self, worker: dict):
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                f'{worker["user"]}@{worker["host"]}',
                "test -f ~/ai && echo ok",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
            online = stdout.decode().strip() == "ok"
        except Exception:
            online = False
        self.result.emit(worker["name"], online)


class TaskRunThread(QThread):
    """Run a task through the orchestrator in background."""
    status_update = Signal(str)  # status message
    subtasks_ready = Signal(list)  # subtask list
    worker_started = Signal(str, str)  # worker_name, task_snippet
    worker_result = Signal(dict)  # individual worker result
    task_complete = Signal(str, str)  # merged result, result file path

    def __init__(self, task: str, model: str = None):
        super().__init__()
        self.task = task
        self.model = model

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._execute())
        loop.close()

    async def _execute(self):
        config = load_config()
        workers = config.get("workers", [])
        timeout = config.get("orchestrator", {}).get("timeout", 300)

        # Check workers
        self.status_update.emit("워커 상태 확인 중...")
        online = []
        for w in workers:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                    f'{w["user"]}@{w["host"]}', "echo ok",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
                if stdout.decode().strip() == "ok":
                    online.append(w)
            except Exception:
                pass

        # Specific model
        if self.model:
            if self.model == "claude":
                self.status_update.emit("로컬 Claude 실행 중...")
                result = await self._run_local(self.task)
                self.task_complete.emit(result, "")
                return
            target = [w for w in online if w.get("model") == self.model]
            if not target:
                self.task_complete.emit(f"'{self.model}' 모델 워커가 오프라인입니다.", "")
                return
            self.status_update.emit(f"{target[0]['name']} 실행 중...")
            r = await self._run_remote(target[0], self.task, timeout)
            self.task_complete.emit(r.get("result", "오류"), "")
            return

        # Auto split
        self.status_update.emit("태스크 분석 및 분할 중...")
        subtasks = await self._split_task(self.task, online)
        self.subtasks_ready.emit(subtasks)

        # Parallel execution
        self.status_update.emit(f"병렬 실행 중... ({len(subtasks)}개 서브태스크)")
        start = datetime.now()
        assignments = []

        roles_map = config.get("roles", {})
        for st in subtasks:
            worker = self._assign_worker(st["role"], online, roles_map)
            assignments.append((st, worker))

        async def _tracked_run(st, worker):
            name = worker["name"] if worker else "local(claude)"
            model = worker.get("model") if worker else "claude"
            snippet = st["task"][:60]
            self.worker_started.emit(name, snippet)
            try:
                if worker is None:
                    raw = await self._run_local(st["task"])
                else:
                    raw = await self._run_remote(worker, st["task"], timeout)
                if isinstance(raw, str):
                    r = {"worker": name, "model": model, "status": "ok", "result": raw}
                else:
                    r = raw
            except Exception as e:
                r = {"worker": name, "model": model, "status": "error", "result": str(e)}
            self.worker_result.emit(r)
            return r

        results = await asyncio.gather(*[
            _tracked_run(st, w) for st, w in assignments
        ])
        elapsed = (datetime.now() - start).seconds

        # Merge
        success = [r for r in results if r["status"] == "ok"]
        if len(success) > 1:
            self.status_update.emit("결과 통합 중...")
            merged = await self._merge_results(self.task, results)
        elif success:
            merged = success[0]["result"]
        else:
            merged = "성공한 결과 없음"

        # Save
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        fname = RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump({
                "task": self.task,
                "subtasks": subtasks,
                "results": results,
                "merged": merged,
                "elapsed_sec": elapsed,
                "timestamp": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

        self.task_complete.emit(merged, str(fname))

    async def _run_local(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "-p", prompt,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

    async def _run_remote(self, worker: dict, task: str, timeout: int) -> dict:
        cmd = [
            "ssh", "-o", "ConnectTimeout=10",
            f'{worker["user"]}@{worker["host"]}',
            f'~/ai {json.dumps(task)}',
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode().strip()
            if not output:
                raise RuntimeError(stderr.decode().strip() or "빈 응답")
            return {"worker": worker["name"], "model": worker.get("model"), "status": "ok", "result": output}
        except asyncio.TimeoutError:
            return {"worker": worker["name"], "model": worker.get("model"), "status": "timeout", "result": "타임아웃"}
        except Exception as e:
            return {"worker": worker["name"], "model": worker.get("model"), "status": "error", "result": str(e)}

    async def _split_task(self, task: str, workers: list) -> list[dict]:
        roles_desc = "\n".join(
            f"- {w['name']} (model={w['model']}, role={w['role']})" for w in workers
        )
        roles_desc += "\n- local (model=claude, role=coding)"
        prompt = f"""다음 태스크를 주어진 AI 에이전트들에게 분배할 서브태스크로 나눠줘.
반드시 JSON 배열만 출력해 (다른 텍스트 없이).

사용 가능한 에이전트:
{roles_desc}

역할 기준:
- coding: 코드 작성, 디버깅, 기술 구현
- research: 리서치, 문서 분석, 정보 수집
- summary: 요약, 정리, 창작, 번역

출력 형식:
[{{"role": "coding", "task": "서브태스크 내용"}}]

분배할 태스크: {task}"""
        raw = await self._run_local(prompt)
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            return json.loads(raw[start:end])
        except Exception:
            result = [{"role": "local", "task": task}]
            for w in workers:
                result.append({"role": w["role"], "task": task})
            return result

    async def _merge_results(self, task: str, results: list[dict]) -> str:
        parts = []
        for r in results:
            if r["status"] == "ok":
                parts.append(f"[{r['worker']}]\n{r['result']}")
        combined = "\n\n---\n\n".join(parts)
        prompt = f"""원래 태스크: {task}

다음은 여러 AI 에이전트의 결과물입니다. 하나의 완성된 답변으로 통합 정리해줘:

{combined}"""
        return await self._run_local(prompt)

    def _assign_worker(self, role: str, workers: list, roles_map: dict):
        target = roles_map.get(role, roles_map.get("default", "round-robin"))
        if target == "local":
            return None
        for w in workers:
            if w["name"] == target or w["role"] == role:
                return w
        return workers[0] if workers else None
