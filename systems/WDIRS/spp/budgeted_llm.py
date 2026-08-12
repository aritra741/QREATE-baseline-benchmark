"""Ledger-enforcing adapter for existing WDIRS-compatible LLM clients."""

from __future__ import annotations

import hashlib
import inspect
from typing import Any, Optional

from spp.budget_ledger import GlobalBudgetLedger
from token_counter import GLOBAL_COUNTER, count_tokens


class BudgetedLLMClient:
    """Wrap ``generate`` so every synthesis call reserves and reconciles tokens."""

    def __init__(
        self,
        client: Any,
        ledger: GlobalBudgetLedger,
        *,
        default_stage: str,
        config_id: Optional[str] = None,
        query_id: Optional[str] = None,
    ):
        self.client = client
        self.ledger = ledger
        self.default_stage = default_stage
        self.config_id = config_id
        self.query_id = query_id
        self.model = getattr(client, "model", type(client).__name__)
        try:
            parameters = inspect.signature(client.generate).parameters
        except (TypeError, ValueError):
            parameters = {}
        self._supports_request_identity = (
            "request_seed" in parameters
            and "request_key" in parameters
        ) or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        # Prevent the wrapped client from hiding unaccounted retry attempts.
        setattr(self.client, "external_budget_retry_control", True)

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
        *,
        stage: Optional[str] = None,
        operation: str = "llm_generate",
        shared_key: Optional[str] = None,
    ) -> str:
        input_text = " ".join(
            text for text in (system_prompt, prompt) if text
        )
        # Hosted providers may use a different tokenizer than WDIRS's local
        # Qwen counter. Reserve the larger of the local exact count and a
        # conservative two-characters-per-token bound; actual provider usage
        # is reconciled after the response.
        conservative_estimate = (len(input_text.encode("utf-8")) + 1) // 2
        try:
            local_estimate = count_tokens(input_text)
        except RuntimeError:
            # Hosted APIs report actual usage after dispatch. A broken or
            # unavailable local tokenizer must not block them; reserve a
            # conservative character-based upper estimate instead.
            local_estimate = conservative_estimate
        input_estimate = max(local_estimate, conservative_estimate)
        stage_name = stage or self.default_stage
        call_key = hashlib.sha256(
            (
                f"{shared_key or ''}\0{stage_name}\0{operation}\0{self.model}\0"
                f"{max_tokens}\0{temperature}\0{input_text}"
            ).encode("utf-8")
        ).hexdigest()
        base_seed = getattr(self.client, "seed", None)
        request_seed = (
            int.from_bytes(
                hashlib.sha256(
                    f"{int(base_seed)}\0{call_key}".encode("utf-8")
                ).digest()[:4],
                "big",
            )
            & 0x7FFFFFFF
            if base_seed is not None
            else None
        )
        reservation_id = self.ledger.reserve(
            stage=stage_name,
            operation=operation,
            input_tokens=input_estimate,
            max_output_tokens=max_tokens,
            config_id=self.config_id,
            query_id=self.query_id,
            shared_key=shared_key,
        )
        if reservation_id is None:
            raise RuntimeError(
                "shared artifact already exists; caller must load it from cache "
                "instead of dispatching the LLM call"
            )
        clear_usage = getattr(self.client, "clear_last_usage", None)
        consume_usage = getattr(self.client, "consume_last_usage", None)
        if callable(clear_usage):
            clear_usage()
        before_in = GLOBAL_COUNTER.input_tokens
        before_out = GLOBAL_COUNTER.output_tokens
        try:
            request_identity = (
                {
                    "request_seed": request_seed,
                    "request_key": call_key,
                }
                if self._supports_request_identity
                else {}
            )
            response = self.client.generate(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
                **request_identity,
            )
        except Exception as exc:
            # Provider usage may be unavailable after transport failures. Charge
            # any globally observed usage; otherwise conservatively charge the
            # prompt because it may already have reached the provider.
            exact_usage = (
                consume_usage() if callable(consume_usage) else None
            )
            if exact_usage is not None:
                observed_in, observed_out = map(int, exact_usage)
            elif callable(consume_usage):
                observed_in, observed_out = 0, 0
            else:
                observed_in = GLOBAL_COUNTER.input_tokens - before_in
                observed_out = GLOBAL_COUNTER.output_tokens - before_out
            self.ledger.reconcile(
                reservation_id,
                input_tokens=max(observed_in, input_estimate),
                output_tokens=max(observed_out, 0),
                error=str(exc),
            )
            raise
        observed_in = GLOBAL_COUNTER.input_tokens - before_in
        observed_out = GLOBAL_COUNTER.output_tokens - before_out
        exact_usage = consume_usage() if callable(consume_usage) else None
        if exact_usage is not None:
            observed_in, observed_out = map(int, exact_usage)
            reconciled_output = observed_out
        elif observed_out > 0:
            reconciled_output = observed_out
        else:
            try:
                reconciled_output = count_tokens(response or "")
            except RuntimeError:
                reconciled_output = (
                    len((response or "").encode("utf-8")) + 1
                ) // 2
        self.ledger.reconcile(
            reservation_id,
            input_tokens=observed_in if observed_in > 0 else input_estimate,
            output_tokens=reconciled_output,
        )
        return response
