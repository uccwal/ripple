"""Agent 공통 도우미."""
from __future__ import annotations

from ..engine.catalog import FACTORS


def factor_list_text(exclude: list[str] | None = None) -> str:
    """프롬프트에 넣는 팩터 목록. 시계열이 없어 이번 계산에서 제외된 팩터는 뺀다."""
    return "\n  ".join(f"- {f.factor_id}: {f.name} (unit {f.unit})" for f in FACTORS if not exclude or f.factor_id not in exclude)


def analog_summary_text(stats: dict, types: list[str] | None = None) -> str:
    """유형·팩터별 과거 사례 요약 (엔진이 계산한 중앙값·사분위·방향 일치율)."""
    from ..engine.catalog import FACTOR_BY_ID  # noqa: PLC0415

    lines = []
    for t, summ in stats.get("analog_summary", {}).items():
        if types and t not in types:
            continue
        if not summ:
            continue
        lines.append(f"- [{t}] 사례 {next(iter(summ.values()))['n']}건:")
        for k, v in summ.items():
            if k not in FACTOR_BY_ID:
                continue
            u = FACTOR_BY_ID[k].unit
            lines.append(f"    {k}: 중앙값 {v['median']:+.2f}{u} (p25 {v['p25']:+.2f}, p75 {v['p75']:+.2f}), "
                         f"상승한 사례 비율 {v['up_share']*100:.0f}%")
    return "\n".join(lines) if lines else "- (요약 없음)"


def betas_text(stats: dict) -> str:
    """자산별 OLS 베타·t값 (거시 변수 → 자산군 단계의 정량 근거)."""
    lines = []
    for aid, b in stats.get("betas", {}).items():
        parts = ", ".join(f"{k} β={v['beta']:+.2f}" + (f" (t={v['t']:+.1f})" if v.get("t") is not None else "")
                          for k, v in b["factors"].items())
        lines.append(f"- {b['name']} ({aid}): {parts} · R² {b['r2']:.2f} · 관측 {b['n_obs']}일")
    return "\n".join(lines) if lines else "- (베타 없음)"


def model_label(result_model: str) -> str:
    return result_model if result_model != "offline" else "offline 규칙"


def fmt_pct(v: float, unit: str) -> str:
    d = 2 if unit == "%p" else 1
    return f"{v:+.{d}f}{unit}"
