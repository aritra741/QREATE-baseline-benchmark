from __future__ import annotations

from surrogates.direct_probe_ranking import DirectProbeRankingSurrogate
from surrogates.glass_box_proxy import GlassBoxProxySurrogate
from surrogates.linear_proxy_glass import LinearProxyGlassSurrogate
from surrogates.llm_judge_btl import LLMJudgeBTLSurrogate
from surrogates.random_ranking import RandomRankingSurrogate
from surrogates.rf_proxy_glass import RFProxyGlassSurrogate

MAIN_SURROGATES: dict[str, type] = {
    "random_ranking": RandomRankingSurrogate,
    "direct_probe_ranking": DirectProbeRankingSurrogate,
    "glass_box_proxy": GlassBoxProxySurrogate,
    "llm_judge_btl": LLMJudgeBTLSurrogate,
    "linear_proxy_glass": LinearProxyGlassSurrogate,
    "rf_proxy_glass": RFProxyGlassSurrogate,
}


def build_surrogate(name: str, *, seed: int = 42):
    if name not in MAIN_SURROGATES:
        raise ValueError(f"Unknown surrogate '{name}'. Available: {sorted(MAIN_SURROGATES)}")
    cls = MAIN_SURROGATES[name]
    if name == "random_ranking":
        return cls(seed=seed)
    return cls()
