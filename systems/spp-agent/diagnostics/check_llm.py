#!/usr/bin/env python3
"""Verify configured LLM models are reachable (vLLM, Ollama, or DeepSeek)."""

from __future__ import annotations

import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from llm.client import chat_completion, ensure_model_available, ModelNotAvailableError
from utils.config import load_config


def main() -> None:
    cfg = load_config()
    llm = cfg["llm"]
    profile = llm.get("profile", "(default)")
    provider = llm.get("provider")
    base_url = llm.get("base_url")

    print(f"LLM profile: {profile}")
    print(f"Provider: {provider}")
    print(f"Base URL: {base_url}")
    print()

    roles = ("extraction_model", "judge_model", "agent_model")
    for role in roles:
        model = llm[role]
        try:
            ensure_model_available(model, base_url, llm_cfg=llm)
            print(f"  OK  {role}: {model}")
        except ModelNotAvailableError as exc:
            print(f"  FAIL {role}: {model} — {exc}")
            if provider == "ollama":
                print(f"       Try: ollama pull {model}")
            sys.exit(1)

    model = llm["extraction_model"]
    try:
        text, tokens = chat_completion(
            model,
            [
                {"role": "system", "content": "Reply with JSON only."},
                {"role": "user", "content": 'Return {"status": "ok"}'},
            ],
            base_url=base_url,
            temperature=0.0,
            max_tokens=64,
            llm_cfg=llm,
        )
        print()
        print(f"Smoke completion OK ({tokens:.0f} tokens): {text[:120]!r}")
    except Exception as exc:
        print(f"\nSmoke completion failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
