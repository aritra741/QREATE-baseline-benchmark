"""
Token Counter for WDIRS — Qwen2.5-7B-Instruct tokenizer.

Provides a process-wide singleton (GLOBAL_COUNTER) that accumulates input and
output token counts for every LLM call made through OllamaClient.generate().
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Qwen2.5-7B-Instruct tokenizer — loaded once, shared across all threads
# ---------------------------------------------------------------------------

_SNAPSHOT_PATH = Path(os.path.expanduser(
    "~/.cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-7B-Instruct/snapshots/"
    "a09a35458c702b33eeacc393d103063234e8bc28"
))
_TOKENIZER_FILE = _SNAPSHOT_PATH / "tokenizer.json"

_tokenizer = None
_tokenizer_lock = threading.Lock()


def _load_tokenizer():
    global _tokenizer
    if _tokenizer is not None:
        return _tokenizer
    with _tokenizer_lock:
        if _tokenizer is not None:
            return _tokenizer
        try:
            from transformers import PreTrainedTokenizerFast
            _tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(_TOKENIZER_FILE))
            logger.info(
                f"[TokenCounter] Loaded Qwen2.5-7B-Instruct tokenizer from {_TOKENIZER_FILE}"
            )
        except Exception as exc:
            logger.warning(
                f"[TokenCounter] Could not load Qwen tokenizer ({exc}); "
                "falling back to char-based estimate (÷4)."
            )
            _tokenizer = None
    return _tokenizer


def count_tokens(text: str) -> int:
    """Return the number of Qwen2.5-7B-Instruct tokens in *text*."""
    tok = _load_tokenizer()
    if tok is None:
        return max(1, len(text) // 4)
    return len(tok.encode(text))


# ---------------------------------------------------------------------------
# Operation attribution — map call-stack frame to a readable label
# ---------------------------------------------------------------------------

# Module-name substrings → human-readable operation label (first match wins)
_MODULE_LABELS = [
    ("sieve_synthesizer",   "sieve_synthesis"),
    ("entity_anchor",       "entity_anchor"),
    ("entity_resolver",     "entity_resolution"),
    ("lattice_planner",     "lattice_planner"),
    ("delta_engine",        "runtime_delta"),
    ("wdirs_runner",        "runner"),
    ("extractor",           "extraction"),
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
            "model": "qwen2.5:7b-instruct",
            "tokenizer": "Qwen/Qwen2.5-7B-Instruct (local)",
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
