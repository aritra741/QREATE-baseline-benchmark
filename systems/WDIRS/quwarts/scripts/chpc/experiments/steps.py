"""The experiment steps, in run order per lane (see runner.py and results/drift_design/EXPERIMENT_PLAN.md).

``gpu`` steps call the model and run one at a time; ``cpu`` steps make no model calls and run beside them.
Paths are relative to the repository root. Every command is resumable on its own: re-running it continues
from its journals. Adding a step here takes effect the next time the runner picks a step.
"""

EXP = "systems/WDIRS/quwarts/scripts/chpc/experiments"
SCRATCH = "/scratch/general/vast/u1592362/quwarts_exp"
FP16 = "qwen2.5:7b-instruct-fp16"
# E6.2, each on its own server. qwen32b replaced qwen14b (2026-10-02, before any 14B step ran): 4-bit, 4 slots at a
# 16k context (see ensure_server.sh), about 4-5x slower than 7B, so it runs fewer streams.
OTHER_MODELS = {"llama8b": "llama3.1:8b", "qwen32b": "qwen2.5:32b-instruct"}
# The extra servers' context (requests must match it, or Ollama reloads the model): Llama gets 16k so that it fits
# beside main on a 40 GB GPU; the 32B model 16k always.
MODEL_ENV = {"qwen32b": "OLLAMA_NUM_CTX=16384 ", "llama8b": "OLLAMA_NUM_CTX=16384 "}
MODEL_STREAMS = {"llama8b": [("player", "fixed4-attribute_pool/0,fixed4-attribute_pool/100"),
                             ("cspaper", "fixed4-attribute_pool/0,fixed4-attribute_pool/100")],
                 "qwen32b": [("cspaper", "fixed4-attribute_pool/0,fixed4-attribute_pool/100"),
                             ("player", "fixed4-attribute_pool/100")]}
SERVER_OF = {FP16: "fp16", **{m: n for n, m in OTHER_MODELS.items()}}
PRE = ("source ~/venvs/quwarts/quwarts.env && cd systems/WDIRS && export PYTHONPATH=$PWD QUWARTS_LLM=ollama "
       "OLLAMA_NUM_CTX=32768 QUWARTS_DRIFT_DESIGN=drift_paired && ")
CORPORA = ["cspaper", "player", "art", "med", "legal"]


def server(name: str) -> str:
    import os

    if name == "main":  # QUWARTS_RUNNER_SERVER=main2: the runner's own 4-bit server on GPU 1 (two-GPU nodes)
        name = os.environ.get("QUWARTS_RUNNER_SERVER", "main")
    return f'eval "$(bash ../../{EXP}/ensure_server.sh {name})" && '


def shared_read(sid: str, tag: str, model: str | None = None, deps: list[str] | None = None, extra: str = "",
                variant: str = "protocol") -> dict:
    env = (f"OLLAMA_MODEL={model} " if model else "") + extra
    folder = "shared_read_protocol" if variant == "protocol" else "shared_read"
    return {
        "id": sid, "lane": "gpu", "deps": (deps or []) + ["G0-prompt-guard"],
        "cmd": PRE + server(SERVER_OF.get(model, "main")) + env +
               f"python -u -m quwarts.eval.router_shared_read_run --corpus player --variant {variant} --blank-base "
               f"--tag {tag} --reads --score --workers 8",
        "outputs": [f"results/quwarts_router_v3/player_{tag}/{folder}/score_blank.json"],
    }


def stream(sid: str, corpus: str, mode: str, key: str = "fixed4-attribute_pool/100", model: str | None = None,
           deps: list[str] | None = None, extra: str = "") -> dict:
    """One drift_live stream in its own root (clone.py ``mode``), never touching the recorded run."""

    root, scratch = f"results/experiments/{sid}/live", f"{SCRATCH}/{sid}"
    env = (f"QUWARTS_LIVE_ROOT=$OLDPWD/{root} QUWARTS_SCRATCH={scratch} QUWARTS_LIVE_ONLY={key} QUWARTS_KEEP_VIEWS=1 "
           + (f"OLLAMA_MODEL={model} " if model else "") + extra)
    return {
        "id": sid, "lane": "gpu", "deps": (deps or []) + ["G0-prompt-guard"],
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


def ablate(name: str, corpus: str, exp: str = "E13", lane: str | None = None, replay_only: bool = False) -> dict:
    """E13: the unlimited stream at 100% drift with one component of the controller turned off (drift_live ABLATE).
    From a replay clone, so every recorded read is reused and only reads the ablation changes are paid. (rawview and
    raw change no prompt, but their views change which documents later filters select, so they may read too.)"""

    tag = name.replace(",", "+")  # E14 combines factors (comma list)
    sid, root, scratch = f"{exp}-{tag}-{corpus}", f"results/experiments/{exp}-{tag}/live", f"{SCRATCH}/{exp}-{tag}"
    env = (f"QUWARTS_LIVE_ROOT=$OLDPWD/{root} QUWARTS_SCRATCH={scratch} QUWARTS_LIVE_ONLY=fixed4-attribute_pool/100 "
           f"QUWARTS_ABLATE={name} " + ("QUWARTS_LIVE_REPLAY=1 " if replay_only else ""))
    return {
        # gpu2 / gpu3: two more runners on another node's full GPU (one server, QUWARTS_RUNNER_SERVER=mainB) take the
        # heavy ones; two streams at once keep its 16 slots busy (one stream alone left it about 40% idle)
        # (nousage moved to this node's lane when it fell idle, except legal, which follows nodesc on gpu2)
        "id": sid, "lane": lane or {"nodesc": "gpu2", "noreuse": "gpu3"}.get(
            name, "gpu2" if (name, corpus) == ("nousage", "legal") else "gpu"),
        "deps": ["G0-prompt-guard"],
        "cmd": PRE + f"python ../../{EXP}/clone.py --mode replay --corpus {corpus} --root {root} --scratch {scratch} && "
               + ("" if replay_only else server("main")) + env + f"python -u -m quwarts.eval.drift_live --corpus {corpus} "
               f"--run --streams fixed --axes attribute_pool --deadline 0 --workers 8",
        "outputs": [f"{root}/{corpus}/streams/fixed4-attribute_pool_100.jsonl"],
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
           f"QUWARTS_BUDGET_ORACLE=$OLDPWD/results/experiments/E2.2-patches/{corpus}/patches.csv "
           f"QUWARTS_BUDGET_ALLOW=$OLDPWD/results/experiments/E3.1-knapsack/{corpus}/allow.json ")
    return {
        "id": sid, "lane": "gpu", "deps": [f"E2.2-patches-{corpus}", "G0-prompt-guard"],
        "cmd": PRE + f"python ../../{EXP}/clone.py --mode policy --corpus {corpus} --root {root} --scratch {scratch} && "
               + server("main") + env + f"python -u -m quwarts.eval.drift_live --corpus {corpus} --run --streams budget "
               f"--axes attribute_pool --deadline 0 --workers 8",
        "outputs": [f"{root}/{corpus}/streams/fixed4b{b:03d}-attribute_pool_{p}.jsonl" for b in (10, 25, 50, 75, 100)
                    for p in (0, 25, 50, 75, 100)],
    }


STEPS = [
    # ---- GPU lane, first: the default prompts still match the recorded runs (see prompt_guard.sh)
    {"id": "G0-prompt-guard", "lane": "gpu", "retries": 0, "cmd": f"bash {EXP}/prompt_guard.sh",
     "outputs": ["results/experiments/G0-prompt-guard/result.json"], "skip_if_outputs": False},
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
                   ("cspaper", "fixed4-attribute_pool/0,fixed4-attribute_pool/100")]],
    # ---- GPU lane: E7c, relax only the text fields whose description names an empty case (cspaper agent_framework)
    stream("E7c-stream-contradicted-cspaper", "cspaper", "fresh", key="fixed4-attribute_pool/0,fixed4-attribute_pool/100",
           extra="QUWARTS_NULLABLE_CONTRADICTED=1 "),
    # ---- GPU lane: E2.1b prompt width (RQ2): the same columns read 1, 3, 6 or 12 at a time on a fixed sample
    *[{"id": f"E2.1b-width-{c}", "lane": "gpu", "retries": 2, "deps": ["G0-prompt-guard"],
       "cmd": PRE + server("main") + f"python -u -m quwarts.eval.exp_width --corpus {c} --docs {n} --workers 8",
       "outputs": [f"results/experiments/E2.1b-width/{c}/summary.json"], "skip_if_outputs": False}
      for c, n in [("player", 141), ("art", 100), ("legal", 60), ("cspaper", 40), ("med", 40)]],
    # ---- GPU lane: E5.0, the shared read with the planner's field specs (name and SQL type only, no benchmark
    # descriptions): the fair comparison for the planner, whose reads use field_specs, not the protocol descriptions
    shared_read("E5.0-sr-plain", "ollama_plain", variant="plain"),
    # ---- GPU lane: E5.2, the planner with the benchmark's descriptions (QUWARTS_FIELDS=protocol), against the
    # protocol shared read (0.560); fractions of DocETL's player tokens as in the planner sweep
    *[{"id": f"E5.2-planner-protocol-f{round(f * 100):03d}", "lane": "gpu", "deps": ["G0-prompt-guard"],
       "cmd": PRE + server("main") + "export QUWARTS_FIELDS=protocol && "
              f"D=$OLDPWD/results/experiments/E5.2-planner-protocol/f{round(f * 100):03d} && "
              f"{{ [ -f $D/probe/plan.json ] || {{ rm -f $D/probe/probe_journal.jsonl; "
              f"python -u -m quwarts.eval.router_plan_v3 --corpus player --fraction {f} --probe --out $D; }}; }} && "
              f"python -u -m quwarts.eval.router_execute_v3 --corpus player --plan $D/probe/plan.json --reads --score "
              f"--workers 8 --out $D/execute",
       "outputs": [f"results/experiments/E5.2-planner-protocol/f{round(f * 100):03d}/execute/score.json"]}
      for f in (0.25, 0.75)],
    # ---- GPU lane: E5.3, as E5.2 plus join keys weighted as the whole query (QUWARTS_JOIN_WEIGHT=1)
    *[{"id": f"E5.3-planner-joinweight-f{round(f * 100):03d}", "lane": "gpu", "deps": ["G0-prompt-guard"],
       "cmd": PRE + server("main") + "export QUWARTS_FIELDS=protocol QUWARTS_JOIN_WEIGHT=1 && "
              f"D=$OLDPWD/results/experiments/E5.3-planner-joinweight/f{round(f * 100):03d} && "
              f"{{ [ -f $D/probe/plan.json ] || {{ rm -f $D/probe/probe_journal.jsonl; "
              f"python -u -m quwarts.eval.router_plan_v3 --corpus player --fraction {f} --probe --out $D; }}; }} && "
              f"python -u -m quwarts.eval.router_execute_v3 --corpus player --plan $D/probe/plan.json --reads --score "
              f"--workers 8 --out $D/execute",
       "outputs": [f"results/experiments/E5.3-planner-joinweight/f{round(f * 100):03d}/execute/score.json"]}
      for f in (0.25, 0.75)],
    # ---- GPU lane: E5.4, the planner (with descriptions) building on the protocol shared read (1.30M tokens): the
    # shared read is the fallback for "leave unread" and planned reads only fill its gaps; planner budgets are the 25%
    # and 75% targets minus the shared read (0.149 and 0.649 of DocETL's player tokens)
    *[{"id": f"E5.4-planner-on-shared-t{t:03d}", "lane": "gpu", "deps": ["G0-prompt-guard"],
       "cmd": PRE + server("main") + "export QUWARTS_FIELDS=protocol "
              "QUWARTS_INCUMBENT_DB=$OLDPWD/results/quwarts_router_v3/player_ollama/shared_read_protocol/read_first_blank.db && "
              f"D=$OLDPWD/results/experiments/E5.4-planner-on-shared/t{t:03d} && "
              f"{{ [ -f $D/probe/plan.json ] || {{ rm -f $D/probe/probe_journal.jsonl; "
              f"python -u -m quwarts.eval.router_plan_v3 --corpus player --fraction {f} --probe --out $D; }}; }} && "
              f"python -u -m quwarts.eval.router_execute_v3 --corpus player --plan $D/probe/plan.json --reads --score "
              f"--workers 8 --out $D/execute",
       "outputs": [f"results/experiments/E5.4-planner-on-shared/t{t:03d}/execute/score.json"]}
      for t, f in ((25, 0.149), (75, 0.649))],
    # ---- GPU lane: E11, other drift draws (QUWARTS_DRIFT_SEED): different withheld columns at about the same drift
    # levels, all five levels, unlimited patching (static comes with each stream); reads reused where prompts match
    *[{"id": f"E11-seed{sd}-{c}", "lane": "gpu", "deps": ["G0-prompt-guard"],
       "cmd": PRE + f"python ../../{EXP}/clone.py --mode seed --corpus {c} --root results/experiments/E11-seed{sd}/live "
              f"--scratch {SCRATCH}/E11-seed{sd} && " + server("main") +
              f"QUWARTS_DRIFT_SEED={sd} QUWARTS_LIVE_ROOT=$OLDPWD/results/experiments/E11-seed{sd}/live "
              f"QUWARTS_SCRATCH={SCRATCH}/E11-seed{sd} python -u -m quwarts.eval.drift_live --corpus {c} --run "
              f"--streams fixed --axes attribute_pool --deadline 0 --workers 8",
       "outputs": [f"results/experiments/E11-seed{sd}/live/{c}/streams/fixed4-attribute_pool_{p}.jsonl"
                   for p in (0, 25, 50, 75, 100)]}
      for sd in (1, 2, 3) for c in ("cspaper", "player")],
    # ---- GPU lane: E12, a smaller build workload ("train" share of W0: QUWARTS_W0_FRACTION) with the same test
    # queries; all five drift levels, unlimited patching (static comes with each stream). Shares that still drop
    # W0 columns: 10% and 25% on cspaper, player, art; also 50% on art. med and legal at 10/25/50%.
    *[{"id": f"E12-w0f{round(f * 100):03d}-{c}", "lane": "gpu", "deps": ["G0-prompt-guard"],
       "cmd": PRE + f"python ../../{EXP}/clone.py --mode w0 --corpus {c} "
              f"--root results/experiments/E12-w0f{round(f * 100):03d}/live --scratch {SCRATCH}/E12-w0f{round(f * 100):03d} && "
              + server("main") + f"QUWARTS_W0_FRACTION={f} "
              f"QUWARTS_LIVE_ROOT=$OLDPWD/results/experiments/E12-w0f{round(f * 100):03d}/live "
              f"QUWARTS_SCRATCH={SCRATCH}/E12-w0f{round(f * 100):03d} python -u -m quwarts.eval.drift_live --corpus {c} "
              f"--run --streams fixed --axes attribute_pool --deadline 0 --workers 8",
       "outputs": [f"results/experiments/E12-w0f{round(f * 100):03d}/live/{c}/streams/fixed4-attribute_pool_{p}.jsonl"
                   for p in (0, 25, 50, 75, 100)]}
      for c, f in (("cspaper", 0.1), ("cspaper", 0.25), ("player", 0.1), ("player", 0.25), ("art", 0.1),
                   ("art", 0.25), ("art", 0.5), ("med", 0.1), ("med", 0.25), ("med", 0.5), ("legal", 0.1),
                   ("legal", 0.25), ("legal", 0.5))],
    # ---- GPU lane: E3.1, the offline knapsack over patches (exp_analysis knapsack), re-scored by running it
    *[policy("knapsack", c) for c in ("cspaper", "player", "art", "legal", "med")],
    # ---- E13: component ablations, unlimited stream at 100% drift; no-call ones first (cpu lane), then the gpu ones
    # cheapest first, corpora cheapest first
    *[ablate(n, c) for n in ("rawview", "raw", "noscope", "nobatch", "nodesc", "nousage", "head", "noreuse")
      for c in ("cspaper", "player", "art", "med", "legal")],
    # ---- E14: prompt factors (build vs patch prompt for the same column). bprompt reads only the build's prompts, so it
    # runs with model calls refused (the check that it reproduces them); bprompt+noscope must equal the 0% build's cells
    *[ablate(n, c, exp="E14", lane="gpu", replay_only=n.startswith("bprompt"))
      for n in ("bprompt", "bprompt,noscope", "bfields", "bgroup") for c in ("cspaper", "player", "art", "med", "legal")],
    # ---- E6.3: Qwen 2.5 32B drift curve (0% and 100%) beyond cspaper, on the full-GPU node (lane gpu4); player reuses
    # E6.2's root (its 32B W0 build and 100% stream), so only the 0% level is new there
    {"id": "E6.3-qwen32b-player0", "lane": "gpu4", "deps": ["G0-prompt-guard"],
     "cmd": PRE + server("qwen32b") + "QUWARTS_LIVE_ROOT=$OLDPWD/results/experiments/E6.2-stream-qwen32b-player/live "
            f"QUWARTS_SCRATCH={SCRATCH}/E6.2-stream-qwen32b-player QUWARTS_LIVE_ONLY=fixed4-attribute_pool/0 "
            "QUWARTS_KEEP_VIEWS=1 OLLAMA_MODEL=qwen2.5:32b-instruct " + MODEL_ENV["qwen32b"]
            + "python -u -m quwarts.eval.drift_live --corpus player --run --streams fixed --axes attribute_pool "
              "--deadline 0 --workers 8",
     "outputs": ["results/experiments/E6.2-stream-qwen32b-player/live/player/streams/fixed4-attribute_pool_0.jsonl"]},
    *[{**stream(f"E6.3-qwen32b-{c}", c, "fresh", key="fixed4-attribute_pool/0,fixed4-attribute_pool/100",
                model=OTHER_MODELS["qwen32b"], extra=MODEL_ENV["qwen32b"]), "lane": "gpu4"}
      for c in ("art", "med", "legal")],
    # ---- GPU lane: Phase 3 budget policies on the corpora with budget anomalies, then the rest
    *[policy("fragile", c) for c in ("legal", "med", "cspaper")],
    *[policy(name, c) for c in ("cspaper", "legal", "med") for name in ("oracle", "cap", "pace")],
    # ---- GPU lane: Phase 6 other local models (E6.2): shared read, and adaptive vs static at 0% and 100% drift
    *[st for n, m in OTHER_MODELS.items() for st in [
        shared_read(f"E6.2-sr-{n}", f"ollama_{n}", m, deps=[f"P1-pull-{n}"], extra=MODEL_ENV.get(n, "")),
        *[stream(f"E6.2-stream-{n}-{c}", c, "fresh", key=k, model=m, deps=[f"P1-pull-{n}"], extra=MODEL_ENV.get(n, ""))
          for c, k in MODEL_STREAMS[n]]]],
    # ---- GPU lane: policies on player and art (no budget anomalies there; after the other models)
    *[policy(name, c) for c in ("player", "art") for name in ("oracle", "cap", "pace")],
    # ---- GPU lane: E7 on med and art (after the policies: E7 was slightly negative on player)
    *[stream(f"E7-stream-nullable-{c}", c, "fresh", key=k, extra="QUWARTS_NULLABLE_TEXT=1 ")
      for c, k in [("med", "fixed4-attribute_pool/0"), ("art", "fixed4-attribute_pool/0,fixed4-attribute_pool/100")]],
    # ---- CPU lane: model downloads (network, no GPU), to /scratch/general/vast/u1592362/ollama_models
    *[{"id": f"P1-pull-{n}", "lane": "cpu", "retries": 3,
       "cmd": PRE + server("main") + f"ollama pull {m} && ollama list | grep -q '{m.split(':')[0]}'", "outputs": []}
      for n, m in OTHER_MODELS.items()],
    # ---- CPU lane: Phase 2 replays (no model calls), the base of the per-query and per-patch analyses
    *[st for c in CORPORA for st in [replay(c)] + [analysis(w, c) for w in ("patches", "order", "columns", "components")]],
    {"id": "E9-query-types", "lane": "cpu", "deps": [f"E2-replay-{c}" for c in CORPORA],
     "cmd": PRE + "python -u -m quwarts.eval.exp_analysis querytypes",
     "outputs": ["results/experiments/E9-query-types/summary.json"], "skip_if_outputs": False},
    {"id": "Z-accounting", "lane": "cpu", "cmd": PRE + "python -u -m quwarts.eval.exp_analysis accounting",
     "outputs": ["results/experiments/ACCOUNTING.md"], "skip_if_outputs": False},
    {"id": "E1-reads-analysis", "lane": "cpu", "deps": ["E1.2-sr-fp16", "E1.1-sr-rep1", "E1.1-sr-rep2"],
     "cmd": PRE + "python -u -m quwarts.eval.exp_analysis reads", "outputs": ["results/experiments/E1-reads/summary.json"],
     "skip_if_outputs": False},
    {"id": "E1-variance-analysis", "lane": "cpu",
     "deps": ["E1.1-stream-rep-cspaper", "E1.1-stream-rep-player", "E1.2-stream-fp16-player"],
     "cmd": PRE + "python -u -m quwarts.eval.exp_analysis variance",
     "outputs": ["results/experiments/E1-variance/summary.json"], "skip_if_outputs": False},
]

# The 32B steps take the whole GPU on a GPU under 60 GB (gpu_exclusive.sh pauses DocETL, stops main, restores both).
import shlex as _shlex  # noqa: E402

for _s in STEPS:
    if _s["id"].startswith("E6.2-") and "qwen32b" in _s["id"]:
        _s["cmd"] = f"bash {EXP}/gpu_exclusive.sh bash -c {_shlex.quote(_s['cmd'])}"
