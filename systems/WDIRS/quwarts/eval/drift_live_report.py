"""Report of the real drift runs (``drift_live``): accuracy, tokens, cost and runtime per stream."""

from __future__ import annotations

import json
import random
from pathlib import Path

from quwarts.eval import drift_live as L
from quwarts.eval import drift_run as R


def records(corpus: str, key: str) -> list[dict] | None:
    p = L.folder(corpus) / "streams" / f"{key.replace('/', '_')}.jsonl"
    if not p.exists():
        return None
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def reference(corpus: str, key: str) -> dict | None:
    """The replay on the full read of every column made before the stream (no drift cost), per position."""

    sp = R.sim_path(corpus, 0, key)
    scores = R.context(corpus).folder / "scores.json"
    if not sp.exists() or not scores.exists():
        return None
    sim, sc = json.loads(sp.read_text()), json.loads(scores.read_text())
    if not sim.get("scored"):
        return None
    return {m: [sc[m].get(f"{p['qid']}|{p['online']}") for p in sim["positions"]] for m in ("benchmark", "tolerant")} | \
        {"robust_build": sim["tokens"]["robust_build"], "lean_build": sim["tokens"]["lean_build"]}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def ci(diffs, n=2000, seed=0):
    rng = random.Random(seed)
    ms = sorted(mean([rng.choice(diffs) for _ in diffs]) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n)]


def summary() -> dict:
    out = {}
    for c in L.CORPORA:
        bpath = L.folder(c) / "build.json"
        if not bpath.exists():
            continue
        b = json.loads(bpath.read_text())
        per = {}
        for key in L.ORDER:
            rs = records(c, key)
            if rs is None:
                continue
            ref = reference(c, key)
            per[key] = {
                "n": len(rs), "drifted": sum(r["drift"] for r in rs),
                "live": mean([r["benchmark"] for r in rs]), "static": mean([r["static_benchmark"] for r in rs]),
                "reference": mean(ref["benchmark"]) if ref else None,
                "live_tol": mean([r["tolerant"] for r in rs]), "static_tol": mean([r["static_tolerant"] for r in rs]),
                "reference_tol": mean(ref["tolerant"]) if ref else None,
                "live_minus_reference": [r["benchmark"] - x for r, x in zip(rs, ref["benchmark"])] if ref else None,
                "patches": sum(r["action"] == "patch" for r in rs), "docs_read": sum(r["docs_read"] for r in rs),
                "input": sum(r["input_tokens"] for r in rs), "output": sum(r["output_tokens"] for r in rs),
                "cost": sum(r["cost_usd"] for r in rs), "runtime": sum(r["runtime_s"] for r in rs),
                "robust_build": ref["robust_build"] if ref else None,
            }
        out[c] = {"build": b, "streams": per}
    return out


def paired(corpus: str, axis: str) -> dict | None:
    """Drifted minus source on the same template: each query of ``axis/100`` against its base query in ``axis/0``."""

    hi, lo = records(corpus, f"{axis}/100"), records(corpus, f"{axis}/0")
    rh, rl = reference(corpus, f"{axis}/100"), reference(corpus, f"{axis}/0")
    if not (hi and lo and rh and rl):
        return None
    pairs = R.context(corpus).designs[0]["pairs"][f"{axis}/100"]
    base = {r["qid"]: (r, rl["benchmark"][i]) for i, r in enumerate(lo)}
    live, ref, static = [], [], []
    for i, r in enumerate(hi):
        b = base.get(pairs.get(r["qid"], r["qid"]))
        if b is None:
            continue
        live.append(r["benchmark"] - b[0]["benchmark"])
        ref.append(rh["benchmark"][i] - b[1])
        static.append(r["static_benchmark"] - b[0]["static_benchmark"])
    return {"n": len(live), "live": live, "reference": ref, "static": static}


def matched(corpus: str, axis: str, tol: float = 0.05) -> dict | None:
    """Difficulty-matched pairs: a drifted query and its source whose no-drift scores (the reference, which read
    every column before the stream) differ by at most ``tol``. The pair's difference in QuWARTS's live score is then
    not explained by one question being easier than the other. Gold is used only to build the evaluation set."""

    hi, lo = records(corpus, f"{axis}/100"), records(corpus, f"{axis}/0")
    rh, rl = reference(corpus, f"{axis}/100"), reference(corpus, f"{axis}/0")
    if not (hi and lo and rh and rl):
        return None
    pairs = R.context(corpus).designs[0]["pairs"][f"{axis}/100"]
    base = {r["qid"]: (r, rl["benchmark"][i]) for i, r in enumerate(lo)}
    out = {"n": 0, "of": 0, "source": [], "drifted": [], "ref_source": [], "ref_drifted": []}
    for i, r in enumerate(hi):
        s, rs = base[pairs[r["qid"]]]
        if r["qid"] == s["qid"]:
            continue
        out["of"] += 1
        if abs(rh["benchmark"][i] - rs) <= tol + 1e-9:
            out["n"] += 1
            out["source"].append(s["benchmark"]); out["drifted"].append(r["benchmark"])
            out["ref_source"].append(rs); out["ref_drifted"].append(rh["benchmark"][i])
    return out


def report() -> str:
    S = summary()
    L_ = ["# Real drift runs (template-paired streams, seed 0)", "",
          "Nothing is read ahead. The build reads every document once with the build workload's columns and descriptions; a query "
          "that needs a column not yet extracted reads, at that moment, only the documents that can affect its answer, with that "
          "column's description (given with the query, never before). Tokens and cost are OpenRouter's reported usage "
          "(qwen/qwen-2.5-7b-instruct); the build's input/output split is estimated from its responses (its calls were made before "
          "usage was recorded).", "",
          "* live: QuWARTS on the stream, real reads. static: the build as it is (no adaptation). reference: the replay on a full "
          "read of every column made before the stream (what live would score with no drift cost).",
          "* Accuracy: benchmark metric (structure F2 x cell F1 within 20%), mean over the stream's queries.", ""]
    for key in ["attribute/100", "value/100", "attribute/0", "combined/0", "value/0"]:
        L_ += [f"## {key}", "",
               "| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c, s in S.items():
            p = s["streams"].get(key)
            if p is None:
                continue
            b = s["build"]
            d = p["live_minus_reference"]
            dci = f"{mean(d):+.3f} [{ci(d)[0]:+.3f}, {ci(d)[1]:+.3f}]" if d else "-"
            total = b["tokens"] + p["input"] + p["output"]
            ratio = f"{total / p['robust_build']:.2f}" if p["robust_build"] else "-"
            ref = f"{p['reference']:.3f}" if p["reference"] is not None else "-"
            L_.append(f"| {c} | {p['n']} | {p['live']:.3f} | {p['static']:.3f} | {ref} | {dci} | {p['patches']} | {p['docs_read']} | "
                      f"{p['input'] / 1e6:.2f}M / {p['output'] / 1e3:.0f}k | ${p['cost']:.3f} | {b['tokens'] / 1e6:.2f}M | ${b['cost']:.3f} | "
                      f"{(p['robust_build'] or 0) / 1e6:.2f}M | {ratio} | {p['runtime']:.0f}s |")
        L_.append("")
    L_ += ["## Drifted minus source, same template (attribute axis)", "",
           "Each attribute/100 query minus its base query in attribute/0, so query difficulty cancels.", "",
           "| Corpus | Pairs | Live [95% CI] | Reference [95% CI] | Static |", "|---|---|---|---|---|"]
    for c in S:
        p = paired(c, "attribute")
        if p and p["n"]:
            lc, rc = ci(p["live"]), ci(p["reference"])
            L_.append(f"| {c} | {p['n']} | {mean(p['live']):+.3f} [{lc[0]:+.3f}, {lc[1]:+.3f}] | {mean(p['reference']):+.3f} [{rc[0]:+.3f}, {rc[1]:+.3f}] | {mean(p['static']):+.3f} |")
    for axis in ("attribute", "value"):
        L_ += ["", f"## Difficulty-matched pairs ({axis} axis, no-drift scores within 0.05)", "",
               "Only pairs whose source and drifted query score the same (within 0.05) when every column was read before the "
               "stream, so neither question is easier. QuWARTS's live score at 0% (the sources) and 100% (the drifted queries).", "",
               "| Corpus | Pairs kept | QuWARTS 0% | QuWARTS 100% | Change [95% CI] | No-drift 0% | No-drift 100% |", "|---|---|---|---|---|---|---|"]
        for c in S:
            m = matched(c, axis)
            if m and m["n"]:
                d = [b - a for a, b in zip(m["source"], m["drifted"])]
                lo_, hi_ = ci(d)
                L_.append(f"| {c} | {m['n']}/{m['of']} | {mean(m['source']):.3f} | {mean(m['drifted']):.3f} | {mean(d):+.3f} [{lo_:+.3f}, {hi_:+.3f}] | "
                          f"{mean(m['ref_source']):.3f} | {mean(m['ref_drifted']):.3f} |")
    return "\n".join(L_)


def write() -> str:
    text = report()
    (L.LIVE / "RESULTS.md").write_text(text)
    (L.LIVE / "summary.json").write_text(json.dumps(summary(), indent=1))
    return text
