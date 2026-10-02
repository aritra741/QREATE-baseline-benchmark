"""Resumable runner for the experiment plan (results/drift_design/EXPERIMENT_PLAN.md).

Steps are defined in ``steps.py`` (re-read before every pick, so steps can be added while the runner runs).
Each step has a lane (``gpu`` steps run one at a time; ``cpu`` steps run beside them), dependencies, a
command, an environment, and the output files that must exist for it to count as done.

Everything is recorded under ``results/experiments/``:
  status.jsonl   one event per line: start / ok / fail / retry / skip / blocked, with time, host, Slurm job,
                 git commit, exit code, attempt, seconds, and the last lines of the log on a failure
  done/<id>.json the step finished and its outputs were checked (a later run skips it)
  STATUS.md      the current state of every step, rewritten after every event
  logs/<id>.log  the step's output, appended across attempts with a header per attempt

Resuming: run the same command again. Done steps are skipped; a failed or interrupted step is run again
(the underlying scripts resume from their own journals, so finished reads are not repeated). A step whose
dependency failed is blocked, not run; independent steps continue.

    python runner.py                 # run everything that is not done
    python runner.py --status        # print STATUS.md
    python runner.py --only E1.2-sr-fp16
    python runner.py --skip ID --reason "why"     # mark a step skipped (its dependents may then run)
    python runner.py --reset ID      # forget a step's done marker (its outputs are kept)
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
OUT = REPO / "results" / "experiments"
DONE, LOGS = OUT / "done", OUT / "logs"
STATUS, SUMMARY = OUT / "status.jsonl", OUT / "STATUS.md"
LOCK = threading.Lock()


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def load_steps() -> list[dict]:
    spec = importlib.util.spec_from_file_location("steps", HERE / "steps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    steps = mod.STEPS
    ids = [s["id"] for s in steps]
    assert len(ids) == len(set(ids)), "duplicate step ids"
    for s in steps:
        for d in s.get("deps", []):
            assert d in ids, f"{s['id']}: unknown dependency {d}"
    return steps


def event(step: str, kind: str, **extra) -> None:
    row = {"time": now(), "step": step, "event": kind, "host": socket.gethostname(),
           "slurm_job": os.environ.get("SLURM_JOB_ID", ""), **extra}
    with LOCK:
        OUT.mkdir(parents=True, exist_ok=True)
        with STATUS.open("a") as h:
            h.write(json.dumps(row) + "\n")
    write_summary()


def history() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if STATUS.exists():
        for line in STATUS.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault(r["step"], []).append(r)
    return out


def state(step: dict, hist: dict[str, list[dict]]) -> str:
    sid = step["id"]
    if (DONE / f"{sid}.json").exists():
        return json.loads((DONE / f"{sid}.json").read_text()).get("state", "done")
    evs = [e for e in hist.get(sid, []) if e["event"] in ("start", "ok", "fail", "blocked")]
    if not evs:
        return "pending"
    last = evs[-1]["event"]
    return {"start": "running-or-interrupted", "fail": "failed", "blocked": "blocked", "ok": "pending"}[last]


def write_summary() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        steps = load_steps()
    except Exception as exc:  # noqa: BLE001
        SUMMARY.write_text(f"steps.py does not load: {exc}\n")
        return
    hist = history()
    lines = [f"# Experiment status ({now()})", "",
             "| Step | Lane | State | Attempts | Last event | Note |", "|---|---|---|---|---|---|"]
    for s in steps:
        evs = hist.get(s["id"], [])
        attempts = sum(e["event"] == "start" for e in evs)
        last = evs[-1] if evs else None
        note = ""
        if last and last["event"] == "fail":
            note = f"exit {last.get('exit')}: {last.get('reason', '')}"[:120]
        elif last and last["event"] in ("skip", "blocked"):
            note = last.get("reason", "")[:120]
        lines.append(f"| {s['id']} | {s['lane']} | {state(s, hist)} | {attempts} | "
                     f"{(last['event'] + ' ' + last['time']) if last else ''} | {note.replace('|', '/')} |")
    lines += ["", "Logs: `results/experiments/logs/<step>.log`. Events: `results/experiments/status.jsonl`."]
    SUMMARY.write_text("\n".join(lines) + "\n")


def outputs_ok(step: dict) -> list[str]:
    return [p for p in step.get("outputs", []) if not (REPO / p).exists()]


def run_step(step: dict) -> bool:
    sid = step["id"]
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{sid.replace('/', '_')}.log"
    env = {**os.environ, **{k: str(v) for k, v in step.get("env", {}).items()},
           # every model call a step makes through router_plan_v3.llm_caller is logged here (tokens, seconds)
           "QUWARTS_USAGE_LOG": str(OUT / "usage" / f"{sid.replace('/', '_')}.jsonl")}
    retries = int(step.get("retries", 1))
    for attempt in range(1, retries + 2):
        missing = outputs_ok(step)
        if step.get("outputs") and not missing and step.get("skip_if_outputs", True):
            mark_done(step, "done", note="outputs already present")
            event(sid, "ok", attempt=attempt, note="outputs already present")
            return True
        t0 = time.monotonic()
        event(sid, "start", attempt=attempt, commit=git_commit(), log=str(log.relative_to(REPO)))
        with log.open("a") as h:
            h.write(f"\n===== {sid} attempt {attempt} {now()} host {socket.gethostname()} "
                    f"job {os.environ.get('SLURM_JOB_ID', '')} =====\n$ {step['cmd']}\n")
            h.flush()
            proc = subprocess.run(["bash", "-lc", step["cmd"]], cwd=str(REPO), env=env, stdout=h, stderr=subprocess.STDOUT)
        secs = round(time.monotonic() - t0, 1)
        missing = outputs_ok(step)
        if proc.returncode == 0 and not missing:
            mark_done(step, "done", seconds=secs, attempt=attempt)
            event(sid, "ok", attempt=attempt, seconds=secs)
            return True
        tail = log.read_text(errors="replace").splitlines()[-25:]
        reason = f"missing outputs {missing}" if proc.returncode == 0 else next(
            (l for l in reversed(tail) if "Error" in l or "error" in l), tail[-1] if tail else "")
        event(sid, "fail" if attempt > retries else "retry", attempt=attempt, exit=proc.returncode, seconds=secs,
              reason=reason.strip()[:300], log_tail=tail)
        if attempt <= retries:
            time.sleep(min(60 * attempt, 300))
    return False


def mark_done(step: dict, st: str, **extra) -> None:
    DONE.mkdir(parents=True, exist_ok=True)
    (DONE / f"{step['id']}.json").write_text(json.dumps({"state": st, "time": now(), "commit": git_commit(),
                                                         "outputs": step.get("outputs", []), **extra}, indent=1))


def lane_worker(lane: str, only: set[str] | None, failed: set[str]) -> None:
    attempted: set[str] = set()
    while True:
        steps = load_steps()
        by_id = {s["id"]: s for s in steps}
        hist = history()
        nxt = None
        for s in steps:
            if s["lane"] != lane or s["id"] in attempted or (only and s["id"] not in only):
                continue
            if state(s, hist) in ("done", "skipped"):
                continue
            deps = s.get("deps", [])
            # Only failures of this run block: a step that failed in an earlier run is retried first.
            if any(d in failed for d in deps):
                attempted.add(s["id"])
                failed.add(s["id"])
                event(s["id"], "blocked", reason="dependency failed: " + ",".join(d for d in deps if d in failed))
                continue
            if all(state(by_id[d], hist) in ("done", "skipped") for d in deps):
                nxt = s
                break
        if nxt is None:
            pending = [s for s in steps if s["lane"] == lane and s["id"] not in attempted
                       and (not only or s["id"] in only) and state(s, hist) not in ("done", "skipped")]
            if not pending:
                return
            time.sleep(30)  # waiting for a dependency in another lane
            continue
        attempted.add(nxt["id"])
        if not run_step(nxt):
            failed.add(nxt["id"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--only", help="comma list of step ids")
    ap.add_argument("--skip")
    ap.add_argument("--reset")
    ap.add_argument("--reason", default="")
    ap.add_argument("--lanes", default="gpu,cpu")
    a = ap.parse_args()
    steps = {s["id"]: s for s in load_steps()}
    if a.status:
        write_summary()
        print(SUMMARY.read_text())
        return 0
    if a.skip:
        mark_done(steps[a.skip], "skipped", reason=a.reason)
        event(a.skip, "skip", reason=a.reason)
        return 0
    if a.reset:
        (DONE / f"{a.reset}.json").unlink(missing_ok=True)
        event(a.reset, "reset", reason=a.reason)
        return 0
    only = set(a.only.split(",")) if a.only else None
    event("runner", "start", commit=git_commit(), pid=os.getpid())
    failed: set[str] = set()
    threads = [threading.Thread(target=lane_worker, args=(lane, only, failed)) for lane in a.lanes.split(",")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    event("runner", "ok", failed=sorted(failed))
    write_summary()
    print(SUMMARY.read_text())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
