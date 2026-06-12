from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from utils.logging import setup_logger

logger = setup_logger("spp.llm")

REQUIRED_MODEL_ERROR = "Required model not available: {model_name}"

MODEL_ALIASES: dict[str, list[str]] = {
    "deepseek-v4-flash": [
        "deepseek-v4-flash",
        "DeepSeek-V4-Flash",
        "deepseek/deepseek-v4-flash",
        "deepseek-ai/DeepSeek-V4-Flash",
        "deepseek-chat",
    ],
    "qwen2.5-7b-instruct": [
        "qwen2.5:7b-instruct",
        "qwen2.5:7b",
        "Qwen2.5:7B-Instruct",
        "Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "qwen2.5-7b-instruct",
    ],
    "qwen2.5-14b-instruct": [
        "Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "qwen2.5-14b-instruct",
        "qwen2.5:14b-instruct",
    ],
    "qwen2.5-32b-instruct": [
        "Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "qwen2.5-32b-instruct",
        "qwen2.5:32b-instruct",
    ],
}


class ModelNotAvailableError(RuntimeError):
    pass


def _normalize_model_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _expand_model_candidates(model_name: str) -> set[str]:
    candidates = {
        model_name,
        _normalize_model_name(model_name),
        model_name.split("/")[-1],
        _normalize_model_name(model_name.split("/")[-1]),
    }
    norm = _normalize_model_name(model_name)
    for _canonical, aliases in MODEL_ALIASES.items():
        alias_norms = {_normalize_model_name(a) for a in aliases}
        if norm in alias_norms or norm == _canonical:
            candidates.update(aliases)
            candidates.update(_normalize_model_name(a) for a in aliases)
    return candidates


def _ollama_root_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")


def _resolve_api_key(llm_cfg: dict[str, Any]) -> str:
    provider = llm_cfg.get("provider", "local_vllm")
    if provider == "deepseek":
        env_name = llm_cfg.get("api_key_env", "DEEPSEEK_API_KEY")
        key = os.environ.get(env_name) or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ModelNotAvailableError(
                f"DeepSeek API key not set. Export {env_name} before using profile deepseek_v4_flash."
            )
        return key
    if provider == "ollama":
        return os.environ.get("OLLAMA_API_KEY", "ollama")
    return os.environ.get("OPENAI_API_KEY", "EMPTY")


def _provider_label(base_url: str, provider: str) -> str:
    if provider == "deepseek":
        return "DeepSeek API"
    if provider == "ollama":
        return f"Ollama at {base_url}"
    return f"local vLLM at {base_url}"


def _list_ollama_native_models(base_url: str) -> set[str]:
    url = _ollama_root_url(base_url) + "/api/tags"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        raise ModelNotAvailableError(f"Cannot list Ollama models from {url}: {exc}") from exc

    names: set[str] = set()
    for item in payload.get("models", []):
        model_id = item.get("name") or item.get("model") or ""
        if model_id:
            names.update(_expand_model_candidates(model_id))
    return names


def _list_available_models(base_url: str, *, api_key: str, llm_cfg: dict[str, Any]) -> set[str]:
    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "EMPTY" else {}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        if llm_cfg.get("provider") == "ollama":
            logger.debug("OpenAI /models failed for Ollama; falling back to /api/tags: %s", exc)
            return _list_ollama_native_models(base_url)
        raise ModelNotAvailableError(f"Cannot list models from {base_url}: {exc}") from exc

    names: set[str] = set()
    for item in payload.get("data", []):
        model_id = item.get("id", "")
        names.update(_expand_model_candidates(model_id))
    return names


def ensure_model_available(
    model_name: str,
    base_url: str,
    *,
    llm_cfg: dict[str, Any] | None = None,
) -> None:
    llm_cfg = llm_cfg or {}
    if llm_cfg.get("skip_model_check"):
        logger.debug("Skipping model availability check for %s", model_name)
        return

    logger.debug("Checking model availability: %s at %s", model_name, base_url)

    api_key = _resolve_api_key(llm_cfg)
    available = _list_available_models(base_url, api_key=api_key, llm_cfg=llm_cfg)
    candidates = _expand_model_candidates(model_name)
    if not candidates & available:
        provider = llm_cfg.get("provider", "local_vllm")
        hint = ""
        if provider == "ollama":
            hint = f" Run: ollama pull {model_name}"
        raise ModelNotAvailableError(
            REQUIRED_MODEL_ERROR.format(model_name=model_name)
            + f" ({_provider_label(base_url, provider)})."
            + hint
        )


def _extract_message_text(message: Any) -> str:
    """Return assistant text; some providers put the answer in reasoning_content."""
    content = getattr(message, "content", None) or ""
    if isinstance(content, str) and content.strip():
        return content

    for attr in ("reasoning_content", "reasoning"):
        alt = getattr(message, attr, None)
        if isinstance(alt, str) and alt.strip():
            logger.debug("Using message.%s (%d chars) because content was empty", attr, len(alt))
            return alt

    model_extra = getattr(message, "model_extra", None) or {}
    if isinstance(model_extra, dict):
        for key in ("reasoning_content", "reasoning"):
            alt = model_extra.get(key)
            if isinstance(alt, str) and alt.strip():
                logger.debug("Using message.model_extra[%s] because content was empty", key)
                return alt

    return content if isinstance(content, str) else ""


def _chat_extra_kwargs(llm_cfg: dict[str, Any]) -> dict[str, Any]:
    extra_kwargs: dict[str, Any] = {}
    if llm_cfg.get("provider") == "deepseek" and llm_cfg.get("thinking"):
        extra_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        logger.debug("DeepSeek thinking mode enabled")
        return extra_kwargs

    if llm_cfg.get("provider") == "ollama":
        ollama_options = dict(llm_cfg.get("ollama_options") or {})
        if ollama_options:
            extra_kwargs["extra_body"] = {"options": ollama_options}
            logger.debug("Ollama options: %s", ollama_options)
    return extra_kwargs


def chat_completion(
    model_name: str,
    messages: list[dict[str, str]],
    *,
    base_url: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    llm_cfg: dict[str, Any] | None = None,
) -> tuple[str, float]:
    llm_cfg = llm_cfg or {}
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        "LLM request model=%s provider=%s messages=%d prompt_chars=%d max_tokens=%d",
        model_name,
        llm_cfg.get("provider"),
        len(messages),
        prompt_chars,
        max_tokens,
    )
    ensure_model_available(model_name, base_url, llm_cfg=llm_cfg)

    from openai import OpenAI

    api_key = _resolve_api_key(llm_cfg)
    timeout = float(llm_cfg.get("request_timeout", 300.0 if llm_cfg.get("provider") == "ollama" else 120.0))
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    extra_kwargs = _chat_extra_kwargs(llm_cfg)

    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **extra_kwargs,
    )
    text = _extract_message_text(response.choices[0].message)
    usage = response.usage
    token_cost = float((usage.prompt_tokens if usage else 0) + (usage.completion_tokens if usage else 0))
    elapsed = time.perf_counter() - started
    logger.info(
        "LLM response model=%s elapsed=%.2fs tokens=%.0f response_chars=%d",
        model_name,
        elapsed,
        token_cost,
        len(text),
    )
    return text, token_cost


def estimate_tokens(text: str, model_name: str = "Qwen/Qwen2.5-14B-Instruct") -> int:
    if "deepseek" in model_name.lower():
        return max(1, len(text) // 4)
    hf_name = model_name
    if "qwen2.5" in model_name.lower() or model_name.lower().startswith("qwen"):
        if ":" in model_name:
            # Ollama tag, e.g. qwen2.5:7b-instruct
            tag = model_name.split(":")[-1]
            size = "7B" if "7b" in tag else "14B" if "14b" in tag else "32B" if "32b" in tag else "7B"
            hf_name = f"Qwen/Qwen2.5-{size}-Instruct"
        elif "7b" in model_name.lower():
            hf_name = "Qwen/Qwen2.5-7B-Instruct"
    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(hf_name, trust_remote_code=True)
        return len(tokenizer.encode(text))
    except Exception:
        return max(1, len(text) // 4)
