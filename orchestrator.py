#!/usr/bin/env python3
"""
멀티 AI 클러스터 오케스트레이터
- 오케스트레이터 (이 PC): Claude  → 코딩/태스크분할/결과통합
- 워커 A (노트북):          Gemini → 리서치/문서분석
- 워커 B (맥북):            GPT    → 요약/창작

사용법:
  python3 orchestrator.py --check
  python3 orchestrator.py "머신러닝 모델 비교 보고서 작성해줘"
  python3 orchestrator.py --model gemini "논문 요약해줘"
"""

import asyncio
import subprocess
import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime

CONFIG_PATH = Path.home() / ".claude-cluster" / "config.yaml"
RESULTS_DIR = Path.home() / ".claude-cluster" / "results"

# ─────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"설정 파일 없음: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# 워커 상태 확인
# ─────────────────────────────────────────────

async def check_worker(worker: dict) -> bool:
    """SSH 연결 및 ai 래퍼 존재 확인"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
            f'{worker["user"]}@{worker["host"]}',
            "test -f ~/ai && echo ok",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        return stdout.decode().strip() == "ok"
    except Exception:
        return False


async def check_all_workers(workers: list) -> list:
    print("워커 상태 확인 중...\n")
    online = []
    tasks = [check_worker(w) for w in workers]
    results = await asyncio.gather(*tasks)
    for w, ok in zip(workers, results):
        icon = "✅" if ok else "❌"
        model = w.get("model", "?").upper()
        role = w.get("role", "?")
        print(f"  {icon} {w['name']} ({w['host']}) [{model}] - {role}")
        if ok:
            online.append(w)
    return online


# ─────────────────────────────────────────────
# AI 호출
# ─────────────────────────────────────────────

async def run_local_claude(prompt: str) -> str:
    """로컬 Claude 실행"""
    proc = await asyncio.create_subprocess_exec(
        "claude", "--print", "-p", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


async def run_remote_ai(worker: dict, task: str, timeout: int) -> dict:
    """SSH로 워커의 ~/ai 래퍼 호출"""
    cmd = [
        "ssh", "-o", "ConnectTimeout=10",
        f'{worker["user"]}@{worker["host"]}',
        f'~/ai {json.dumps(task)}',
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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


# ─────────────────────────────────────────────
# 태스크 분할 (Claude가 역할 태그 포함)
# ─────────────────────────────────────────────

async def split_task(task: str, workers: list) -> list[dict]:
    """
    Claude가 태스크를 서브태스크로 분할하고 각 역할을 지정.
    반환: [{"role": "research", "task": "..."}, ...]
    """
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
[
  {{"role": "coding", "task": "서브태스크 내용"}},
  {{"role": "research", "task": "서브태스크 내용"}},
  {{"role": "summary", "task": "서브태스크 내용"}}
]

분배할 태스크: {task}"""

    raw = await run_local_claude(prompt)
    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        return json.loads(raw[start:end])
    except Exception:
        print(f"⚠️  자동 분할 실패 (raw: {raw[:100]}), 전체 태스크를 모든 에이전트에 전송")
        result = [{"role": "local", "task": task}]
        for w in workers:
            result.append({"role": w["role"], "task": task})
        return result


# ─────────────────────────────────────────────
# 역할 → 워커 매핑
# ─────────────────────────────────────────────

def assign_worker(role: str, workers: list, config: dict):
    """역할에 맞는 워커 반환. None이면 로컬 실행."""
    role_map = config.get("roles", {})
    target = role_map.get(role, role_map.get("default", "round-robin"))
    if target == "local":
        return None
    for w in workers:
        if w["name"] == target or w["role"] == role:
            return w
    # round-robin fallback
    if workers:
        return workers[0]
    return None


# ─────────────────────────────────────────────
# 결과 통합
# ─────────────────────────────────────────────

async def merge_results(original_task: str, results: list[dict]) -> str:
    parts = []
    for r in results:
        if r["status"] == "ok":
            parts.append(f"[{r['worker']} / {r.get('model','?')}]\n{r['result']}")
    if not parts:
        return "통합할 성공 결과 없음"
    combined = "\n\n---\n\n".join(parts)
    prompt = f"""원래 태스크: {original_task}

다음은 여러 AI 에이전트의 결과물입니다. 하나의 완성된 답변으로 통합 정리해줘:

{combined}"""
    return await run_local_claude(prompt)


# ─────────────────────────────────────────────
# 결과 저장
# ─────────────────────────────────────────────

def save_results(task: str, subtasks: list, results: list, merged: str, elapsed: int):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fname = RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump({
            "task": task,
            "subtasks": subtasks,
            "results": results,
            "merged": merged,
            "elapsed_sec": elapsed,
            "timestamp": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    return fname


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="멀티 AI 클러스터 오케스트레이터")
    parser.add_argument("task", nargs="?", help="실행할 태스크")
    parser.add_argument("--check", action="store_true", help="워커 상태만 확인")
    parser.add_argument("--model", help="특정 모델에만 전송 (claude/gemini/openai)")
    args = parser.parse_args()

    config = load_config()
    workers = config.get("workers", [])
    timeout = config.get("orchestrator", {}).get("timeout", 300)

    # 워커 상태 확인
    online = await check_all_workers(workers)
    if args.check:
        print(f"\n온라인: {len(online)}/{len(workers)}")
        return

    if not online and not args.model == "claude":
        print("\n⚠️  온라인 워커 없음. 로컬 Claude로만 실행합니다.")

    task = args.task or input("\n태스크 입력: ").strip()
    if not task:
        print("태스크가 없습니다.")
        sys.exit(1)

    # 특정 모델 직접 지정
    if args.model:
        if args.model == "claude":
            print(f"\n[로컬 Claude] 실행 중...")
            result = await run_local_claude(task)
            print(result)
            return
        target_workers = [w for w in online if w.get("model") == args.model]
        if not target_workers:
            print(f"'{args.model}' 모델 워커 없음")
            sys.exit(1)
        r = await run_remote_ai(target_workers[0], task, timeout)
        print(r["result"])
        return

    # 자동 분할 & 배분
    print(f"\n태스크 분석 및 분할 중...")
    subtasks = await split_task(task, online)

    print(f"\n서브태스크 ({len(subtasks)}개):")
    for i, st in enumerate(subtasks):
        print(f"  [{i+1}] [{st['role']}] {st['task'][:70]}")

    # 병렬 실행
    print(f"\n병렬 실행 중...")
    start_time = datetime.now()
    coros = []
    assignments = []  # (subtask, worker_or_none)

    for st in subtasks:
        worker = assign_worker(st["role"], online, config)
        assignments.append((st, worker))
        if worker is None:
            coros.append(run_local_claude(st["task"]))
        else:
            coros.append(run_remote_ai(worker, st["task"], timeout))

    raw_results = await asyncio.gather(*coros)
    elapsed = (datetime.now() - start_time).seconds

    # 결과 정규화
    results = []
    for (st, worker), raw in zip(assignments, raw_results):
        if isinstance(raw, str):
            results.append({"worker": "local(claude)", "model": "claude", "status": "ok", "result": raw})
        else:
            results.append(raw)

    # 결과 출력
    print(f"\n{'='*60}")
    print(f"완료: {elapsed}초\n")
    for r, (st, _) in zip(results, assignments):
        icon = "✅" if r["status"] == "ok" else "❌"
        print(f"{icon} [{r['worker']}] — {st['task'][:50]}")
        if r["status"] == "ok":
            preview = r["result"][:300] + ("..." if len(r["result"]) > 300 else "")
            print(f"   {preview}\n")
        else:
            print(f"   오류: {r['result']}\n")

    # 결과 통합
    success_count = sum(1 for r in results if r["status"] == "ok")
    if success_count > 1:
        print(f"{'='*60}")
        print("결과 통합 중 (Claude)...\n")
        merged = await merge_results(task, results)
        print("통합 결과:")
        print(merged)
    else:
        merged = results[0]["result"] if results else ""

    # 저장
    fname = save_results(task, subtasks, results, merged, elapsed)
    print(f"\n결과 저장: {fname}")


if __name__ == "__main__":
    asyncio.run(main())
