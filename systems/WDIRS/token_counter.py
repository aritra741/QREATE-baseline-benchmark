"""
Token Counter for WDIRS — Qwen2.5-7B-Instruct tokenizer via Ollama API.

Provides a process-wide singleton (GLOBAL_COUNTER) that accumulates input and
output token counts for every LLM call made through OllamaClient.generate().
Tokens are counted using Ollama's /api/tokenize endpoint (exact model tokens).
Tokens are attributed to the calling component (extractor, entity_anchor,
lattice_planner, etc.) by inspecting the Python call stack.

Usage
-----
    from token_counter import GLOBAL_COUNTER
    GLOBAL_COUNTER.record(input_tokens=42, output_tokens=17, operation="extraction")
    print(GLOBAL_COUNTER.summary_str())
"""

import inspect
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ollama tokenizer API client
# ---------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

_tokenizer_ready = False
_tokenizer_lock = threading.Lock()


def _verify_ollama_tokenize() -> bool:
    """Check if Ollama /api/tokenize endpoint is available."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/tokenize",
            json={"model": OLLAMA_MODEL, "prompt": "test"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"[TokenCounter] Ollama tokenize API check failed: {e}")
        return False


def count_tokens(text: str) -> int:
    """
    Return the number of tokens using Ollama's tokenize API.
    Counts tokens from the exact model being used.
    """
    if not text:
        return 0

    global _tokenizer_ready
    if not _tokenizer_ready:
        with _tokenizer_lock:
            if not _tokenizer_ready:
                if not _verify_ollama_tokenize():
                    raise RuntimeError(
                        f"[TokenCounter] Precise tokenization required: "
                        f"Ollama /api/tokenize endpoint unavailable at {OLLAMA_URL}. "
                        f"Ensure Ollama is running and accessible."
                    )
                _tokenizer_ready = True

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/tokenize",
            json={"model": OLLAMA_MODEL, "prompt": text},
            timeout=10,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"[TokenCounter] Ollama tokenize failed with status {resp.status_code}: {resp.text}"
            )
        data = resp.json()
        tokens = data.get("tokens", [])
        return len(tokens)
    except requests.RequestException as e:
        raise RuntimeError(
            f"[TokenCounter] Failed to call Ollama tokenize API: {e}"
        )


def ensure_precise_tokenizer_ready() -> None:
    """Fail-fast check for strict token counting setups."""
    if not _verify_ollama_tokenize():
        raise RuntimeError(
            f"[TokenCounter] Precise tokenization required: "
            f"Ollama /api/tokenize endpoint unavailable at {OLLAMA_URL}. "
            f"Ensure Ollama is running with model {OLLAMA_MODEL} loaded."
        )
    global _tokenizer_ready
    _tokenizer_ready = True
    logger.info(
        f"[TokenCounter] Verified Ollama tokenize API ready at {OLLAMA_URL} ({OLLAMA_MODEL})"
    )


# ---------------------------------------------------------------------------
# Operation attribution — map call-stack frame to a readable label
# ---------------------------------------------------------------------------

# Module-name substrings → human-readable operation label (first match wins)
_MODULE_LABELS = [
    ("sieve_synthesizer", "sieve_synthesis"),
    ("entity_anchor", "entity_anchor"),
    ("entity_resolver", "entity_resolution"),
    ("lattice_planner", "lattice_planner"),
    ("delta_engine", "runtime_delta"),
    ("wdirs_runner", "runner"),
    ("extractor", "extraction"),
]


def _infer_operation() -> str:
    """
    Walk the call stack (skipping token_counter and extractor frames) and
    return a label for the first recognisable WDIRS module found.
    """
    for frame_info in inspect.stack():
        filename = frame_info.filename or ""
        for substring, label in _MODULE_LABELS:
            if substring in filename:
                return label
    return "unknown"


# ---------------------------------------------------------------------------
# Thread-safe token counter
# ---------------------------------------------------------------------------


@dataclass
class _OperationStats:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class TokenCounter:
    """
    Process-wide, thread-safe accumulator for Qwen2.5 token usage.

    Attributes
    ----------
    input_tokens  : total prompt tokens sent to the LLM
    output_tokens : total completion tokens received
    total_tokens  : input_tokens + output_tokens
    call_count    : number of LLM calls recorded
    by_operation  : per-operation breakdown (dict of _OperationStats)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.call_count: int = 0
        self.by_operation: Dict[str, _OperationStats] = {}
        self._start_time: float = time.time()

    # ------------------------------------------------------------------
    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        operation: Optional[str] = None,
    ) -> None:
        """
        Add *input_tokens* and *output_tokens* to the running totals.

        Parameters
        ----------
        input_tokens  : number of prompt tokens in this call
        output_tokens : number of completion tokens in this call
        operation     : label for the calling component; inferred from the
                        call stack when None
        """
        if operation is None:
            operation = _infer_operation()

        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.call_count += 1

            stats = self.by_operation.setdefault(operation, _OperationStats())
            stats.calls += 1
            stats.input_tokens += input_tokens
            stats.output_tokens += output_tokens
            stats.total_tokens += input_tokens + output_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    # ------------------------------------------------------------------
    def summary_dict(self) -> dict:
        elapsed = time.time() - self._start_time
        ops = {
            op: {
                "calls": s.calls,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "total_tokens": s.total_tokens,
            }
            for op, s in sorted(
                self.by_operation.items(),
                key=lambda kv: kv[1].total_tokens,
                reverse=True,
            )
        }
        return {
            "model": OLLAMA_MODEL,
            "tokenizer": f"Ollama /api/tokenize ({OLLAMA_URL})",
            "elapsed_seconds": round(elapsed, 1),
            "llm_calls": self.call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "by_operation": ops,
        }

    def summary_str(self) -> str:
        d = self.summary_dict()
        lines = [
            "",
            "=" * 70,
            "  TOKEN COST SUMMARY  —  Qwen2.5-7B-Instruct",
            "=" * 70,
            f"  Model         : {d['model']}",
            f"  Tokenizer     : {d['tokenizer']}",
            f"  Elapsed       : {d['elapsed_seconds']}s",
            f"  LLM calls     : {d['llm_calls']:,}",
            f"  Input tokens  : {d['input_tokens']:,}",
            f"  Output tokens : {d['output_tokens']:,}",
            f"  TOTAL tokens  : {d['total_tokens']:,}",
            "",
            "  Breakdown by operation:",
        ]
        for op, stats in d["by_operation"].items():
            lines.append(
                f"    {op:<22}  calls={stats['calls']:>5,}  "
                f"in={stats['input_tokens']:>9,}  "
                f"out={stats['output_tokens']:>8,}  "
                f"total={stats['total_tokens']:>9,}"
            )
        lines.append("=" * 70)
        return "\n".join(lines)

    def save_json(self, path) -> None:
        """Write the summary dict as JSON to *path*."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(self.summary_dict(), fh, indent=2)
        logger.info(f"[TokenCounter] Token cost saved to {path}")

    def reset(self) -> None:
        with self._lock:
            self.input_tokens = 0
            self.output_tokens = 0
            self.call_count = 0
            self.by_operation.clear()
            self._start_time = time.time()


# ---------------------------------------------------------------------------
# Module-level singleton — import and use this everywhere
# ---------------------------------------------------------------------------

GLOBAL_COUNTER = TokenCounter()
