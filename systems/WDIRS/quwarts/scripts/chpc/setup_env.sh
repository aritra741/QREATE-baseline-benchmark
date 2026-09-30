#!/usr/bin/env bash
# One-time setup on the GPU machine: Python env, Ollama, the model, and a smoke test. No root needed.
#
#   bash systems/WDIRS/quwarts/scripts/chpc/setup_env.sh        # from anywhere inside the repo
#
# Options (environment variables):
#   VENV           where the Python env goes           (default ~/venvs/quwarts)
#   OLLAMA_DIR     where Ollama is unpacked            (default ~/ollama; skipped if `ollama` is already on PATH)
#   OLLAMA_MODELS  where model weights go              (default /scratch/general/vast/$USER/ollama_models if that
#                                                       disk exists, else ~/ollama_models)
#   OLLAMA_MODEL   the model                           (default qwen2.5:7b-instruct; qwen2.5:7b-instruct-fp16 needs 24 GB+)
#   SKIP_OLLAMA=1  Python env only
# Safe to run again: every step checks what is already there.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
WDIRS=$REPO/systems/WDIRS
VENV=${VENV:-$HOME/venvs/quwarts}
OLLAMA_DIR=${OLLAMA_DIR:-$HOME/ollama}
if [ -z "${OLLAMA_MODELS:-}" ]; then
  if [ -d /scratch/general/vast ]; then OLLAMA_MODELS=/scratch/general/vast/$USER/ollama_models; else OLLAMA_MODELS=$HOME/ollama_models; fi
fi
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen2.5:7b-instruct}
say() { printf '\n== %s\n' "$*"; }

# ------------------------------------------------------------------ 1. Python >= 3.10 and the env
say "Python env at $VENV"
pick_python() {
  for p in python3.12 python3.11 python3.10 python3; do
    if command -v "$p" > /dev/null && "$p" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))' 2> /dev/null; then
      command -v "$p"; return 0
    fi
  done
  return 1
}
if [ ! -x "$VENV/bin/python" ]; then
  if PY=$(pick_python); then
    echo "using $PY ($("$PY" --version))"
    "$PY" -m venv "$VENV"
  else
    # No usable Python >= 3.10: uv downloads one into the user's home (no root).
    echo "no Python >= 3.10 with venv found; installing uv to get one"
    command -v uv > /dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH=$HOME/.local/bin:$PATH
    uv venv --python 3.10 --seed "$VENV"
  fi
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r "$WDIRS/quwarts/scripts/chpc/requirements-drift.txt" pytest zstandard
"$VENV/bin/python" -c 'import sys; print("python", sys.version.split()[0], "ok")'

# ------------------------------------------------------------------ 2. Ollama
if [ "${SKIP_OLLAMA:-0}" != "1" ]; then
  say "Ollama"
  if command -v ollama > /dev/null; then
    OLLAMA_BIN=$(command -v ollama)
  elif [ -x "$OLLAMA_DIR/bin/ollama" ]; then
    OLLAMA_BIN=$OLLAMA_DIR/bin/ollama
  else
    case "$(uname -m)" in x86_64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;; *) echo "unsupported CPU $(uname -m)"; exit 1 ;; esac
    URL=https://ollama.com/download/ollama-linux-$ARCH.tar.zst
    echo "downloading $URL to $OLLAMA_DIR (about 2 GB with the GPU libraries)"
    mkdir -p "$OLLAMA_DIR"
    TMP=$OLLAMA_DIR/ollama.tar.zst
    curl -fL --retry 3 -o "$TMP" "$URL"
    if tar --help 2> /dev/null | grep -q zstd && command -v zstd > /dev/null; then
      tar --zstd -xf "$TMP" -C "$OLLAMA_DIR"
    else  # no zstd on this machine: unpack with Python
      "$VENV/bin/python" - "$TMP" "$OLLAMA_DIR" <<'PY'
import sys, tarfile, zstandard
with open(sys.argv[1], "rb") as f, zstandard.ZstdDecompressor().stream_reader(f) as r, tarfile.open(fileobj=r, mode="r|") as t:
    t.extractall(sys.argv[2])
PY
    fi
    rm -f "$TMP"
    OLLAMA_BIN=$OLLAMA_DIR/bin/ollama
  fi
  echo "ollama: $OLLAMA_BIN ($("$OLLAMA_BIN" --version 2>&1 | tail -1))"
  if command -v nvidia-smi > /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  else
    echo "WARNING: no nvidia-smi: Ollama will run on the CPU (very slow). Run this on a GPU node."
  fi

  say "Model $OLLAMA_MODEL (weights in $OLLAMA_MODELS)"
  mkdir -p "$OLLAMA_MODELS" "$REPO/logs"
  PORT=$("$VENV/bin/python" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  export OLLAMA_HOST=127.0.0.1:$PORT OLLAMA_MODELS
  "$OLLAMA_BIN" serve > "$REPO/logs/ollama-setup.log" 2>&1 &
  OLPID=$!
  trap 'kill $OLPID 2> /dev/null || true' EXIT
  for _ in $(seq 1 60); do curl -sf "http://$OLLAMA_HOST/api/tags" > /dev/null && break; sleep 1; done
  "$OLLAMA_BIN" pull "$OLLAMA_MODEL"

  say "Smoke test: one call to the model"
  PYTHONPATH=$WDIRS OLLAMA_MODEL=$OLLAMA_MODEL "$VENV/bin/python" - <<'PY'
import time
from quwarts.core.llm import ollama
seen = []
caller = ollama.make_caller(on_usage=lambda p, u: seen.append(u), max_tokens=40)
t = time.time()
text = caller.complete('Return JSON with this shape and no other keys: {"fields": {"answer": <value>}}. What is 2+2?', "smoke")
print("model answered:", text.strip()[:80], f"({seen[0]['input']} in / {seen[0]['output']} out tokens, {time.time() - t:.1f}s)")
PY
fi

# ------------------------------------------------------------------ 3. The code runs here
say "Tests and a dry load of the experiment"
cd "$WDIRS"
PYTHONPATH=$WDIRS "$VENV/bin/python" -m pytest -q quwarts/tests/test_ollama_client.py quwarts/tests/test_router_probes.py
PYTHONPATH=$WDIRS QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama "$VENV/bin/python" - <<'PY' 2>&1 | grep -v "loaded\|derived"
from quwarts.eval import drift_live as L, drift_run as R
for c in L.CORPORA:
    ctx = R.context(c)
    test = dict.fromkeys(ctx.designs[0]["streams"]["attribute/100"])
    print(f"{c}: {sum(len(v) for v in ctx.names.values())} documents, {len(test)} test queries")
print("results will go to", L.BASE)
PY

# ------------------------------------------------------------------ 4. Settings for the run script
cat > "$VENV/quwarts.env" <<EOF
# written by setup_env.sh; sourced by run_drift.sh
export PATH=$(dirname "${OLLAMA_BIN:-/usr/bin/true}"):\$PATH
export OLLAMA_MODELS=$OLLAMA_MODELS
export OLLAMA_MODEL=$OLLAMA_MODEL
source $VENV/bin/activate
EOF
say "Done. Next:"
echo "  cd $REPO && nohup bash systems/WDIRS/quwarts/scripts/chpc/run_drift.sh > logs/run.out 2>&1 &"
echo "  tail -f logs/drift.log"
