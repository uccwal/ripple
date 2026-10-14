"""④ 헤지 제안 규칙. 제안 문장은 이 규칙의 결과로만 만든다 (LLM은 설명 문장만 다듬는다)."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from .catalog import FACTOR_BY_ID


@dataclass
class Hedge:
    rule_id: str
    title: str
    why: str
    rule: str
    key: str  # 계산 근거 패널 키
    share: float
    rule_tpl: str = ""  # 보고서용: 기준값을 {{rule.*}} 자리표시자로
    why_tpl: str = ""   # 보고서용: 기여도를 {{hedge.*.share}} 자리표시자로


def suggest(
    total_pnl: float,
    factor_contrib: dict[str, float],
    sector_contrib: dict[str, float],
    sector_top_asset: dict[str, str],
    fx_share: float | None = None,
    sector_share: float | None = None,
    rate_share: float | None = None,
) -> list[Hedge]:
    """손실(total_pnl < 0)일 때만 제안한다. share = 기여 / 전체 손실 (같은 부호일 때 양수)."""
    fx_share = settings.hedge_fx_share if fx_share is None else fx_share
    sector_share = settings.hedge_sector_share if sector_share is None else sector_share
    rate_share = settings.hedge_rate_share if rate_share is None else rate_share
    if total_pnl >= 0:
        return []
    out: list[Hedge] = []

    fx = factor_contrib.get("USDKRW", 0.0) / total_pnl
    if fx >= fx_share:
        out.append(Hedge("fx", "원화 자산 환헤지 비율 상향",
                         f"환율 팩터가 손실의 {fx * 100:.0f}% 기여",
                         f"환율 팩터 기여 ≥ 손실의 {fx_share * 100:.0f}%", "fc:USDKRW", fx,
                         "환율 팩터 기여 ≥ 손실의 {{rule.fx}}", "환율 팩터가 손실의 {{hedge.fx.share}} 기여"))

    if sector_contrib:
        sec, val = min(sector_contrib.items(), key=lambda kv: kv[1])
        share = val / total_pnl
        if share >= sector_share:
            out.append(Hedge("sector", f"{sec} 업종 비중 축소 · 분산",
                             f"{sec} 업종이 손실의 {share * 100:.0f}% 기여",
                             f"단일 업종 기여 ≥ 손실의 {sector_share * 100:.0f}%",
                             f"h:{sector_top_asset.get(sec, '')}", share,
                             "단일 업종 기여 ≥ 손실의 {{rule.sector}}", f"{sec} 업종이 손실의 {{{{hedge.sector.share}}}} 기여"))

    rate_ids = [k for k in factor_contrib if FACTOR_BY_ID[k].group == "rate"]
    rate = sum(factor_contrib[k] for k in rate_ids) / total_pnl
    if rate >= rate_share:
        top = min(rate_ids, key=lambda k: factor_contrib[k])
        out.append(Hedge("rate", "채권 듀레이션 축소",
                         f"금리 팩터가 손실의 {rate * 100:.0f}% 기여",
                         f"금리 팩터 기여 ≥ 손실의 {rate_share * 100:.0f}%", f"fc:{top}", rate,
                         "금리 팩터 기여 ≥ 손실의 {{rule.rate}}", "금리 팩터가 손실의 {{hedge.rate.share}} 기여"))
    return out
