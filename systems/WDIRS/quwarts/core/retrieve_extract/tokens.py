"""Exact Qwen 2.5 tokenizer. Used for every routing measurement."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from tokenizers import Tokenizer

_TOKENIZER_PATH = Path(__file__).resolve().parents[2] / "assets" / "qwen25_tokenizer.json"


@lru_cache(maxsize=1)
def qwen_tokenizer() -> Tokenizer:
    if not _TOKENIZER_PATH.is_file():
        raise FileNotFoundError(f"Qwen tokenizer missing: {_TOKENIZER_PATH}")
    return Tokenizer.from_file(str(_TOKENIZER_PATH))


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(qwen_tokenizer().encode(text).ids)


def encode_offsets(text: str) -> tuple[list[int], list[tuple[int, int]]]:
    encoding = qwen_tokenizer().encode(text)
    offsets = [(int(start), int(end)) for start, end in encoding.offsets]
    return list(encoding.ids), offsets
