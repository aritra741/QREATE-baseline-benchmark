from __future__ import annotations

from surrogates.direct_probe_ranking import DirectProbeRankingSurrogate
from surrogates.gbdt_proxy_glass import GBDTProxyGlassSurrogate
from surrogates.glass_box_proxy import GlassBoxProxySurrogate
from surrogates.gp_proxy_glass import GPProxyGlassSurrogate
from surrogates.linear_proxy_glass import LinearProxyGlassSurrogate
from surrogates.llm_judge_btl import LLMJudgeBTLSurrogate
from surrogates.random_ranking import RandomRankingSurrogate
from surrogates.rf_proxy_glass import RFProxyGlassSurrogate
from surrogates.structural_probe_ranking import StructuralProbeRankingSurrogate
from surrogates.tpe_proxy import TPEProxySurrogate

MAIN_SURROGATES: dict[str, type] = {
    "random_ranking": RandomRankingSurrogate,
    "direct_probe_ranking": DirectProbeRankingSurrogate,
    "structural_probe_ranking": StructuralProbeRankingSurrogate,
    "glass_box_proxy": GlassBoxProxySurrogate,
    "llm_judge_btl": LLMJudgeBTLSurrogate,
    "linear_proxy_glass": LinearProxyGlassSurrogate,
    "rf_proxy_glass": RFProxyGlassSurrogate,
}

ALL_SURROGATES: dict[str, type] = {
    **MAIN_SURROGATES,
    "gbdt_proxy_glass": GBDTProxyGlassSurrogate,
    "gp_proxy_glass": GPProxyGlassSurrogate,
    "tpe_proxy": TPEProxySurrogate,
}


def build_surrogate(name: str, *, seed: int = 42):
    if name not in ALL_SURROGATES:
        raise ValueError(f"Unknown surrogate '{name}'. Available: {sorted(ALL_SURROGATES)}")
    cls = ALL_SURROGATES[name]
    if name == "random_ranking":
        return cls(seed=seed)
    return cls()
