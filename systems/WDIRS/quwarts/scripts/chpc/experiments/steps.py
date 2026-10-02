"""The experiment steps, in run order per lane (see runner.py and results/drift_design/EXPERIMENT_PLAN.md).

``gpu`` steps call the model and run one at a time; ``cpu`` steps make no model calls and run beside them.
Paths are relative to the repository root. Every command is resumable on its own: re-running it continues
from its journals. Adding a step here takes effect the next time the runner picks a step.
"""

EXP = "systems/WDIRS/quwarts/scripts/chpc/experiments"
SCRATCH = "/scratch/general/vast/u1592362/quwarts_exp"
FP16 = "qwen2.5:7b-instruct-fp16"
OTHER_MODELS = {"llama8b": "llama3.1:8b", "qwen14b": "qwen2.5:14b-instruct"}  # E6.2, each on its own server
SERVER_OF = {FP16: "fp16", **{m: n for n, m in OTHER_MODELS.items()}}
PRE = ("source ~/venvs/quwarts/quwarts.env && cd systems/WDIRS && export PYTHONPATH=$PWD QUWARTS_LLM=ollama "
       "OLLAMA_NUM_CTX=32768 QUWARTS_DRIFT_DESIGN=drift_paired && ")
CORPORA = ["cspaper", "player", "art", "med", "legal"]


def server(name: str) -> str:
    return f'eval "$(bash ../../{EXP}/ensure_server.sh {name})" && '


def shared_read(sid: str, tag: str, model: str | None = None, deps: list[str] | None = None, extra: str = "") -> dict:
    env = (f"OLLAMA_MODEL={model} " if model else "") + extra
    return {
        "id": sid, "lane": "gpu", "deps": deps or [],
        "cmd": PRE + server(SERVER_OF.get(model, "main")) + env +
               f"python -u -m quwarts.eval.router_shared_read_run --corpus player --variant protocol --blank-base "
               f"--tag {tag} --reads --score --workers 8",
        "outputs": [f"results/quwarts_router_v3/player_{tag}/shared_read_protocol/score_blank.json"],
    }


def stream(sid: str, corpus: str, mode: str, key: str = "fixed4-attribute_pool/100", model: str | None = None,
           deps: list[str] | None = None, extra: str = "") -> dict:
    """One drift_live stream in its own root (clone.py ``mode``), never touching the recorded run."""

    root, scratch = f"results/experiments/{sid}/live", f"{SCRATCH}/{sid}"
    env = (f"QUWARTS_LIVE_ROOT=$OLDPWD/{root} QUWARTS_SCRATCH={scratch} QUWARTS_LIVE_ONLY={key} QUWARTS_KEEP_VIEWS=1 "
           + (f"OLLAMA_MODEL={model} " if model else "") + extra)
    return {
        "id": sid, "lane": "gpu", "deps": deps or [],
        "cmd": PRE + f"python ../../{EXP}/clone.py --mode {mode} --corpus {corpus} --root {root} --scratch {scratch} && "
               + server(SERVER_OF.get(model, "main")) + env +
               f"python -u -m quwarts.eval.drift_live --corpus {corpus} --run --streams fixed --axes attribute_pool "
               f"--deadline 0 --workers 8",
        "outputs": [f"{root}/{corpus}/streams/{k.replace('/', '_')}.jsonl" for k in key.split(",")],
    }


def replay(corpus: str) -> dict:
    """Re-run every recorded fixed4 stream (unlimited and budgeted) from the journals, keeping each query's
    view: no model calls (QUWARTS_LIVE_REPLAY refuses any), then check it matches the recorded run."""

    sid, root, scratch = f"E2-replay-{corpus}", "results/experiments/E2-replay/live", f"{SCRATCH}/E2-replay"
    env = f"QUWARTS_LIVE_ROOT=$OLDPWD/{root} QUWARTS_SCRATCH={scratch} QUWARTS_LIVE_REPLAY=1 QUWARTS_KEEP_VIEWS=1 "
    run = f"python -u -m quwarts.eval.drift_live --corpus {corpus} --run --axes attribute_pool --deadline 0 --streams"
    return {
        "id": sid, "lane": "cpu", "retries": 0,
        "cmd": PRE + f"python ../../{EXP}/clone.py --mode replay --corpus {corpus} --root {root} --scratch {scratch} && "
               + env + f"{run} fixed && " + env + f"{run} budget && "
               f"python ../../{EXP}/verify_replay.py --root {root} --corpus {corpus}",
        "outputs": [f"{root}/{corpus}/verify.json"],
        "skip_if_outputs": False,
    }


def analysis(what: str, corpus: str) -> dict:
    folder = {"patches": "E2.2-patches", "order": "E2.3-order", "components": "E2.4-errors", "columns": "E2.1-columns"}[what]
    return {"id": f"{folder.split('-')[0]}-{what}-{corpus}", "lane": "cpu", "deps": [f"E2-replay-{corpus}"],
            "cmd": PRE + f"python -u -m quwarts.eval.exp_analysis {what} --corpus {corpus}",
            "outputs": [f"results/experiments/{folder}/{corpus}/summary.json"], "skip_if_outputs": False}


def policy(name: str, corpus: str) -> dict:
    """Budgeted streams (5 budgets x 5 drift levels) under budget policy ``name`` (drift_live.POLICY), from the
    recorded journals: reads already made are reused, new ones are paid. fcfs is the recorded sweep."""

    sid, root, scratch = f"E3.2-{name}-{corpus}", f"results/experiments/E3.2-{name}/live", f"{SCRATCH}/E3.2-{name}"
    env = (f"QUWARTS_LIVE_ROOT=$OLDPWD/{root} QUWARTS_SCRATCH={scratch} QUWARTS_BUDGET_POLICY={name} "
           f"QUWARTS_BUDGET_ORACLE=$OLDPWD/results/experiments/E2.2-patches/{corpus}/patches.csv ")
    return {
        "id": sid, "lane": "gpu", "deps": [f"E2.2-patches-{corpus}"],
        "cmd": PRE + f"python ../../{EXP}/clone.py --mode policy --corpus {corpus} --root {root} --scratch {scratch} && "
               + server("main") + env + f"python -u -m quwarts.eval.drift_live --corpus {corpus} --run --streams budget "
               f"--axes attribute_pool --deadline 0 --workers 8",
        "outputs": [f"{root}/{corpus}/streams/fixed4b{b:03d}-attribute_pool_{p}.jsonl" for b in (10, 25, 50, 75, 100)
                    for p in (0, 25, 50, 75, 100)],
    }


STEPS = [
    # ---- GPU lane: Phase 1 (is it real?)
    {"id": "P1-pull-fp16", "lane": "gpu",
     "cmd": PRE + server("fp16") + f"ollama pull {FP16} && ollama list | grep -q '{FP16}' && "
            f"ls $OLLAMA_MODELS/manifests/registry.ollama.ai/library/qwen2.5/7b-instruct-fp16",
     "outputs": [], "retries": 3},
    shared_read("E1.2-sr-fp16", "ollama_fp16", FP16, deps=["P1-pull-fp16"]),
    shared_read("E1.1-sr-rep1", "ollama_rep1"),
    shared_read("E1.1-sr-rep2", "ollama_rep2"),
    stream("E1.1-stream-rep-cspaper", "cspaper", "repeat"),
    stream("E1.1-stream-rep-player", "player", "repeat"),
    stream("E1.2-stream-fp16-player", "player", "fresh", model=FP16, deps=["P1-pull-fp16"]),
    # ---- GPU lane: E7, text fields allowed to be empty (drops "Never null" for text; see context_probe.FieldSpec.line)
    shared_read("E7-sr-nullable", "ollama_nullable", extra="QUWARTS_NULLABLE_TEXT=1 "),
    shared_read("E7b-sr-nullhint", "ollama_nullhint", extra="QUWARTS_NULLABLE_TEXT=1 QUWARTS_NULL_HINT=1 "),
    *[stream(f"E7-stream-nullable-{c}", c, "fresh", key=k, extra="QUWARTS_NULLABLE_TEXT=1 ")
      for c, k in [("player", "fixed4-attribute_pool/0,fixed4-attribute_pool/100"),
                   ("cspaper", "fixed4-attribute_pool/0,fixed4-attribute_pool/100"),
                   ("med", "fixed4-attribute_pool/0"),
                   ("art", "fixed4-attribute_pool/0,fixed4-attribute_pool/100")]],
    # ---- GPU lane: E2.1b prompt width (RQ2): the same columns read 1, 3, 6 or 12 at a time on a fixed sample
    *[{"id": f"E2.1b-width-{c}", "lane": "gpu", "retries": 2,
       "cmd": PRE + server("main") + f"python -u -m quwarts.eval.exp_width --corpus {c} --docs {n} --workers 8",
       "outputs": [f"results/experiments/E2.1b-width/{c}/summary.json"], "skip_if_outputs": False}
      for c, n in [("player", 141), ("art", 100), ("legal", 60), ("cspaper", 40), ("med", 40)]],
    # ---- GPU lane: Phase 3 budget policies on the corpora with budget anomalies, then the rest
    *[policy("fragile", c) for c in ("legal", "med", "cspaper")],
    *[policy(name, c) for c in ("cspaper", "legal", "player", "art", "med") for name in ("oracle", "cap", "pace")],
    # ---- GPU lane: Phase 6 other local models (E6.2): shared read, and adaptive vs static at 0% and 100% drift
    *[st for n, m in OTHER_MODELS.items() for st in [
        shared_read(f"E6.2-sr-{n}", f"ollama_{n}", m, deps=[f"P1-pull-{n}"]),
        *[stream(f"E6.2-stream-{n}-{c}", c, "fresh", key="fixed4-attribute_pool/0,fixed4-attribute_pool/100", model=m,
                 deps=[f"P1-pull-{n}"]) for c in ("player", "cspaper")]]],
    # ---- CPU lane: model downloads (network, no GPU), to /scratch/general/vast/u1592362/ollama_models
    *[{"id": f"P1-pull-{n}", "lane": "cpu", "retries": 3,
       "cmd": PRE + server("main") + f"ollama pull {m} && ollama list | grep -q '{m.split(':')[0]}'", "outputs": []}
      for n, m in OTHER_MODELS.items()],
    # ---- CPU lane: Phase 2 replays (no model calls), the base of the per-query and per-patch analyses
    *[st for c in CORPORA for st in [replay(c)] + [analysis(w, c) for w in ("patches", "order", "columns", "components")]],
    {"id": "E1-reads-analysis", "lane": "cpu", "deps": ["E1.2-sr-fp16", "E1.1-sr-rep1", "E1.1-sr-rep2"],
     "cmd": PRE + "python -u -m quwarts.eval.exp_analysis reads", "outputs": ["results/experiments/E1-reads/summary.json"],
     "skip_if_outputs": False},
    {"id": "E1-variance-analysis", "lane": "cpu",
     "deps": ["E1.1-stream-rep-cspaper", "E1.1-stream-rep-player", "E1.2-stream-fp16-player"],
     "cmd": PRE + "python -u -m quwarts.eval.exp_analysis variance",
     "outputs": ["results/experiments/E1-variance/summary.json"], "skip_if_outputs": False},
]
