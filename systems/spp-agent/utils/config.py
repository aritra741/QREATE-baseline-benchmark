from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from utils.paths import SPP_AGENT_ROOT, resolve_benchu_root, resolve_results_dir

_ENV_FILE = SPP_AGENT_ROOT / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE)


def _apply_llm_profile(cfg: dict[str, Any]) -> None:
    llm = cfg.setdefault("llm", {})
    profiles = cfg.get("llm_profiles", {})

    profile_name = os.environ.get("SPP_LLM_PROFILE", llm.get("profile"))
    if profile_name:
        if profile_name not in profiles:
            raise ValueError(
                f"Unknown LLM profile '{profile_name}'. "
                f"Available: {', '.join(sorted(profiles)) or '(none)'}"
            )
        for key, value in profiles[profile_name].items():
            llm[key] = value
        llm["profile"] = profile_name


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or (SPP_AGENT_ROOT / "config" / "defaults.yaml")
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["paths"] = cfg.get("paths", {})
    cfg["paths"]["benchu_root"] = str(
        resolve_benchu_root(cfg["paths"].get("benchu_root", "../.."))
    )
    cfg["paths"]["results_dir"] = str(
        resolve_results_dir(cfg["paths"].get("results_dir", "./results"))
    )
    _apply_llm_profile(cfg)
    return cfg
