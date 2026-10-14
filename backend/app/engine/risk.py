"""Risk Engine. 팩터 모델 추정치와 과거 유사 국면 추정치를 함께 계산하고 계산 근거(calc_log)를 만든다.

이 모듈의 숫자만 보고서·화면에 쓰인다. LLM은 이 결과를 인용만 한다.
"""
from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import median

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.tables import FactorBeta, Holding, Portfolio
from . import fmt
from .catalog import FACTOR_BY_ID, FACTOR_IDS
from .data import (SeriesMeta, asset_returns, factor_returns, factor_window_changes, load_levels,
                   required_series, series_meta, window_return)
from .factors import BetaFit, fit_asset
from .hedge import suggest
from .regimes import Regime, analog_changes, historical_max, top_regimes

ENGINE_VERSION = "0.1.0"
Z95 = 1.96


def code_hash() -> str:
    """engine 패키지 소스의 해시. 계산 로그에 남겨 어떤 코드로 계산했는지 추적한다."""
    h = hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()[:16]


@dataclass
class Context:
    portfolio: Portfolio
    holdings: list[Holding]
    as_of: date
    horizon: int
    levels: pd.DataFrame
    factor_ret: pd.DataFrame
    asset_ret: dict[str, pd.Series]
    window_changes: pd.DataFrame
    meta: dict[str, SeriesMeta]
    fits: dict[str, BetaFit] = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        return any(m.synthetic for m in self.meta.values())

    def sources(self) -> list[dict]:
        out = []
        for m in self.meta.values():
            out.append({
                "series_id": m.series_id,
                "name": f"{m.source} · {m.name}",
                "collected_at": m.collected_at.date().isoformat() if m.collected_at else None,
                "last_date": m.last_date.isoformat() if m.last_date else None,
                "license": m.license,
                "url": m.source_url,
                "synthetic": m.synthetic,
            })
        return sorted(out, key=lambda s: s["series_id"])


def prepare(session: Session, portfolio_id: str, as_of: date | None, horizon: int) -> Context:
    pf = session.get(Portfolio, portfolio_id)
    if pf is None:
        raise ValueError(f"포트폴리오 없음: {portfolio_id}")
    holdings = list(session.scalars(select(Holding).where(Holding.portfolio_id == portfolio_id)))
    sids = required_series(holdings)
    levels = load_levels(session, sids, as_of)
    if levels.empty:
        raise ValueError("시계열 데이터가 없습니다. 수집기 또는 seed를 먼저 실행하세요.")
    missing = [s for s in sids if s not in levels or levels[s].notna().sum() == 0]
    if missing:
        raise ValueError(f"시계열 누락: {', '.join(missing)}")
    as_of_eff = levels.index[-1].date()
    ctx = Context(
        portfolio=pf, holdings=holdings, as_of=as_of_eff, horizon=horizon, levels=levels,
        factor_ret=factor_returns(levels),
        asset_ret={h.asset_id: asset_returns(h, levels) for h in holdings},
        window_changes=factor_window_changes(levels, horizon),
        meta=series_meta(session, sids, as_of),
    )
    for h in holdings:
        ctx.fits[h.asset_id] = fit_asset(h.asset_id, ctx.asset_ret[h.asset_id], ctx.factor_ret, list(h.factors),
                                         settings.beta_window_days, settings.beta_min_obs)
    _store_betas(session, ctx)
    return ctx


def _store_betas(session: Session, ctx: Context) -> None:
    for fit in ctx.fits.values():
        session.execute(delete(FactorBeta).where(FactorBeta.asset_id == fit.asset_id,
                                                 FactorBeta.window_end == fit.window_end.date()))
        for k, b in fit.betas.items():
            session.add(FactorBeta(asset_id=fit.asset_id, factor_id=k, beta=b, std_err=fit.std_err[k], r2=fit.r2,
                                   window_start=fit.window_start.date(), window_end=fit.window_end.date()))
    session.flush()


# ---------------------------------------------------------------- Scenario Builder 보조 통계

def scenario_stats(ctx: Context) -> dict:
    """충격값 근거: 팩터별 과거 최대 변동폭, 유형별 과거 사례 직후 변화."""
    return {
        "hist_max": historical_max(ctx.window_changes),
        "analogs": {t: analog_changes(ctx.window_changes, ctx.horizon, t) for t in ("tariff", "rate", "regulation", "fx", "macro")},
    }


# ---------------------------------------------------------------- 유사 국면

def find_regimes(ctx: Context, shocks: dict[str, float]) -> list[Regime]:
    regs = top_regimes(ctx.window_changes, shocks, ctx.horizon)
    for r in regs:
        rets = {h.asset_id: window_return(ctx.asset_ret[h.asset_id], r.start, r.end) for h in ctx.holdings}
        r.asset_returns = rets
        # 한 자산이라도 데이터가 없는 구간은 손익을 내지 않는다 (일부 자산만 합산하면 편향)
        if any(math.isnan(v) for v in rets.values()):
            r.pnl = float("nan")
        else:
            r.pnl = float(sum((h.weight / 100) * rets[h.asset_id] for h in ctx.holdings))
    return [r for r in regs if not math.isnan(r.pnl)]


# ---------------------------------------------------------------- 손익 계산

def compute(ctx: Context, shocks: dict[str, float], regimes: list[Regime], run_id: str) -> dict:
    """② 충격 적용 + 범위 + 유사 국면 비교 + 헤지 규칙. 반환: {result, calc_log}."""
    shocks = {k: float(v) for k, v in shocks.items() if k in FACTOR_BY_ID}
    by_asset = []
    for h in ctx.holdings:
        fit = ctx.fits[h.asset_id]
        parts = {k: fit.betas[k] * shocks.get(k, 0.0) for k in fit.betas}
        ret = sum(parts.values())
        by_asset.append({
            "asset_id": h.asset_id, "name": h.name, "weight": h.weight, "currency": h.currency,
            "sector": h.sector, "asset_class": h.asset_class, "ret": ret,
            "contribution": h.weight / 100 * ret, "parts": parts,
        })
    total = float(sum(a["contribution"] for a in by_asset))

    # 포트폴리오 베타와 표준오차 (자산 간 추정오차 독립 가정)
    factor_rows = []
    for k in FACTOR_IDS:
        B = sum(h.weight / 100 * ctx.fits[h.asset_id].betas.get(k, 0.0) for h in ctx.holdings)
        SE = math.sqrt(sum((h.weight / 100 * ctx.fits[h.asset_id].std_err.get(k, 0.0)) ** 2 for h in ctx.holdings))
        if B == 0 and SE == 0:
            continue
        s = shocks.get(k, 0.0)
        factor_rows.append({"factor_id": k, "name": FACTOR_BY_ID[k].name, "unit": FACTOR_BY_ID[k].unit,
                            "beta": B, "se": SE, "shock": s, "contribution": B * s})
    se_total = math.sqrt(sum((f["se"] * f["shock"]) ** 2 for f in factor_rows))
    rng = {"low": total - Z95 * se_total, "high": total + Z95 * se_total}
    for f in factor_rows:
        f["share"] = round(f["contribution"] / total * 100) if total < 0 and f["contribution"] < 0 else None

    sector_contrib: dict[str, float] = {}
    sector_top: dict[str, str] = {}
    for a in sorted(by_asset, key=lambda a: a["contribution"]):
        # 업종 규칙은 환율 효과를 뺀 기여로 판단한다 (환율은 별도 규칙)
        non_fx = a["weight"] / 100 * sum(v for k, v in a["parts"].items() if FACTOR_BY_ID[k].group != "fx")
        sector_contrib[a["sector"]] = sector_contrib.get(a["sector"], 0.0) + non_fx
        sector_top.setdefault(a["sector"], a["asset_id"])
    hedges = suggest(total, {f["factor_id"]: f["contribution"] for f in factor_rows}, sector_contrib, sector_top)

    pnls = [r.pnl for r in regimes if not math.isnan(r.pnl)]
    regime_est = ({"median": float(median(pnls)), "low": float(min(pnls)), "high": float(max(pnls)), "n": len(pnls)}
                  if pnls else None)

    top = sorted(by_asset, key=lambda a: -abs(a["contribution"]))[:5]  # 절댓값 기준 상위 5
    calc_id = "calc_" + uuid.uuid4().hex[:12]
    aum = ctx.portfolio.aum
    result = {
        "portfolio_pnl": total,
        "pnl_amount": round(total / 100 * aum / 10) * 10,  # 10억 원 단위, 보고서·근거 패널과 동일
        "aum": aum,
        "range": rng,
        "by_asset": [{k: v for k, v in a.items() if k != "parts"} for a in by_asset],
        "top_contributors": [a["asset_id"] for a in top],
        "factor_contrib": factor_rows,
        "regime_estimate": regime_est,
        "hedges": [h.__dict__ for h in hedges],
        "calc_log_id": calc_id,
    }
    entries = _entries(ctx, shocks, by_asset, factor_rows, total, rng, regimes, regime_est, se_total)
    calc_log = {
        "calc_id": calc_id,
        "run_id": run_id,
        "code_hash": code_hash(),
        "engine_version": ENGINE_VERSION,
        "inputs": {
            "portfolio_id": ctx.portfolio.portfolio_id,
            "as_of": ctx.as_of.isoformat(),
            "horizon_days": ctx.horizon,
            "shocks": shocks,
            "betas": {aid: {"betas": f.betas, "std_err": f.std_err, "r2": f.r2, "n_obs": f.n_obs,
                            "window": [f.window_start.date().isoformat(), f.window_end.date().isoformat()]}
                      for aid, f in ctx.fits.items()},
            "weights": {h.asset_id: h.weight for h in ctx.holdings},
            "sources": ctx.sources(),
        },
        "outputs": _outputs(result, regimes),
        "entries": entries,
    }
    return {"result": result, "calc_log": calc_log}


def _outputs(result: dict, regimes: list[Regime]) -> dict:
    """보고서가 참조하는 수치 키. Validator는 보고서의 모든 수치가 이 키에서 왔는지 확인한다."""
    out = {
        "pnl": result["portfolio_pnl"],
        "amt": result["pnl_amount"],
        "range.low": result["range"]["low"],
        "range.high": result["range"]["high"],
        "aum": result["aum"],
    }
    if result["regime_estimate"]:
        for k in ("median", "low", "high", "n"):
            out[f"reg.{k}"] = result["regime_estimate"][k]
    for a in result["by_asset"]:
        out[f"h:{a['asset_id']}.ret"] = a["ret"]
        out[f"h:{a['asset_id']}.contribution"] = a["contribution"]
        out[f"h:{a['asset_id']}.weight"] = a["weight"]
    for f in result["factor_contrib"]:
        out[f"fc:{f['factor_id']}"] = f["contribution"]
        out[f"f:{f['factor_id']}"] = f["shock"]
        if f.get("share") is not None:
            out[f"fc:{f['factor_id']}.share"] = f["share"]
    for i, r in enumerate(regimes):
        out[f"regime.{i}.similarity"] = r.similarity
        out[f"regime.{i}.pnl"] = None if math.isnan(r.pnl) else r.pnl
    for h in result["hedges"]:
        out[f"hedge.{h['rule_id']}.share"] = round(h["share"] * 100)
    out["rule.fx"] = round(settings.hedge_fx_share * 100)
    out["rule.sector"] = round(settings.hedge_sector_share * 100)
    out["rule.rate"] = round(settings.hedge_rate_share * 100)
    return out


def _cell(v: str, num: float | None = None) -> dict:
    return {"v": v} if num is None else {"v": v, "num": num}


def _entries(ctx: Context, shocks, by_asset, factor_rows, total, rng, regimes, regime_est, se_total) -> dict:
    pf = ctx.portfolio
    tot = fmt.signed(total)
    amt = fmt.amount(total / 100 * pf.aum)
    win = next(iter(ctx.fits.values()))
    window_txt = f"{win.window_start.date()} ~ {win.window_end.date()}"
    fac_rows = [[_cell(f["name"]), _cell(fmt.plain(f["beta"])),
                 _cell(fmt.signed(f["shock"], fmt.shock_digits(f["unit"]), f["unit"])),
                 _cell(fmt.signed(f["contribution"], 2, "%p"), f["contribution"])] for f in factor_rows if f["shock"] != 0]
    model_note = (f"포트폴리오 β = Σᵢ wᵢ·βᵢₖ. 자산별 베타는 {window_txt} 일별 수익률(USD 기준) OLS 회귀로 추정했습니다. "
                  f"충격이 0인 팩터는 표에서 생략했습니다.")
    e: dict[str, dict] = {}
    e["pnl"] = {
        "title": "포트폴리오 예상 손익", "value": total, "value_text": tot,
        "sub": f"{amt} · {ctx.horizon}영업일 · {pf.name}",
        "formula": "ΔRᵢ = Σₖ βᵢₖ · Δfₖ\nΔP = Σᵢ wᵢ · ΔRᵢ = Σₖ (Σᵢ wᵢβᵢₖ) · Δfₖ",
        "columns": ["팩터", "포트폴리오 β", "충격값", "기여"], "rows": fac_rows, "note": model_note,
    }
    e["model"] = {**e["pnl"], "title": "팩터 모델 추정"}
    e["amt"] = {
        "title": "예상 손익 금액", "value": total / 100 * pf.aum, "value_text": amt,
        "sub": f"운용자산 {pf.aum:,.0f}억 원 기준 · {ctx.horizon}영업일",
        "formula": f"금액 = ΔP × AUM\n= {tot} × {pf.aum:,.0f}억 원",
        "columns": ["항목", "값"],
        "rows": [[_cell("ΔP"), _cell(tot, total)], [_cell("AUM"), _cell(f"{pf.aum:,.0f}억 원")],
                 [_cell("금액"), _cell(amt, total)]],
        "note": "금액은 10억 원 단위로 반올림했습니다. 가상 모델 포트폴리오의 가정 운용자산입니다.",
    }
    e["range"] = {
        "title": "추정 범위 (95%)", "value": None,
        "value_text": f"{fmt.signed(rng['low'])} ~ {fmt.signed(rng['high'])}",
        "sub": "베타 추정 표준오차를 반영한 상·하한",
        "formula": "SEₖ = √(Σᵢ (wᵢ·SEᵢₖ)²)\nSE = √(Σₖ (SEₖ·Δfₖ)²)\n범위 = ΔP ∓ 1.96·SE",
        "columns": ["팩터", "포트폴리오 β", "SEₖ", "SEₖ·Δfₖ"],
        "rows": [[_cell(f["name"]), _cell(fmt.plain(f["beta"])), _cell(fmt.plain(f["se"])),
                  _cell(fmt.plain(abs(f["se"] * f["shock"]), 3) + "%p")] for f in factor_rows if f["shock"] != 0],
        "note": f"합성 표준오차 SE = {se_total:.3f}%p. 자산 간 추정오차는 독립으로 가정했습니다.",
    }
    if regimes:
        e["reg"] = {
            "title": "과거 유사 국면 추정", "value": regime_est["median"], "value_text": fmt.signed(regime_est["median"]),
            "sub": f"유사도 상위 {regime_est['n']}개 구간의 실제 손익 중앙값 · {fmt.signed(regime_est['low'])} ~ {fmt.signed(regime_est['high'])}",
            "formula": "pnlⱼ = Σᵢ wᵢ · Rᵢ⁽ʲ⁾ (구간 j의 실제 자산 수익률)\n추정 = median(pnl₁ … pnlₙ)",
            "columns": ["구간", "유사도", "실제 손익"],
            "rows": [[_cell(f"{r.start.date()} ~ {r.end.date()}" + (f" · {r.tag}" if r.tag else "")),
                      _cell(f"{r.similarity:.2f}"), _cell(fmt.signed(r.pnl), r.pnl)] for r in regimes],
            "note": (f"{ctx.horizon}영업일 구간의 팩터 변화 벡터를 표준화한 뒤 시나리오 벡터와 코사인 유사도(크기 가중)로 비교했습니다. "
                     "겹치는 구간은 제외했습니다."),
        }
    for a in by_asset:
        h = next(x for x in ctx.holdings if x.asset_id == a["asset_id"])
        fit = ctx.fits[a["asset_id"]]
        e[f"h:{a['asset_id']}"] = {
            "title": a["name"], "value": a["ret"], "value_text": fmt.signed(a["ret"]),
            "sub": f"비중 {a['weight']:.1f}% · 포트폴리오 기여 {fmt.signed(a['contribution'], 2, '%p')}",
            "formula": f"ΔR = Σₖ βₖ · Δfₖ\n기여 = w × ΔR = {a['weight']:.1f}% × {fmt.signed(a['ret'], 2)}",
            "columns": ["팩터", "β", "충격값", "기여"],
            "rows": [[_cell(FACTOR_BY_ID[k].name), _cell(fmt.plain(b, 2)),
                      _cell(fmt.signed(shocks.get(k, 0.0), fmt.shock_digits(FACTOR_BY_ID[k].unit), FACTOR_BY_ID[k].unit)),
                      _cell(fmt.signed(a["parts"][k], 2, "%"), a["parts"][k])] for k, b in fit.betas.items()],
            "note": (f"통화 {h.currency} · USD 기준 손익. R² {fit.r2:.2f}, 관측치 {fit.n_obs}일 ({window_txt})."
                     + (" 원화 자산은 원/달러 상승 시 환산 손실이 발생합니다." if h.currency == "KRW" else "")),
        }
    for f in factor_rows:
        k = f["factor_id"]
        rows = []
        for a in by_asset:
            b = ctx.fits[a["asset_id"]].betas.get(k)
            if b is None:
                continue
            c = a["weight"] / 100 * b * f["shock"]
            rows.append([_cell(a["name"]), _cell(f"{a['weight']:.1f}%"), _cell(fmt.plain(b, 2)),
                         _cell(fmt.signed(c, 2, "%p"), c)])
        share_txt = f"손실의 {f['share']}%" if f.get("share") is not None else "손실 기여 없음"
        e[f"fc:{k}"] = {
            "title": f"{f['name']} 팩터 기여", "value": f["contribution"],
            "value_text": fmt.signed(f["contribution"], 2, "%p"), "sub": share_txt,
            "formula": "기여ₖ = Σᵢ wᵢ · βᵢₖ · Δfₖ", "columns": ["자산", "비중", "β", "기여"], "rows": rows,
            "note": "헤지 규칙: 환율 팩터 기여 ≥ 손실의 30% → 환헤지 상향, 단일 업종 ≥ 40% → 비중 축소, 금리 팩터 ≥ 25% → 듀레이션 축소.",
        }
    hist = historical_max(ctx.window_changes)
    for k, s in shocks.items():
        unit = FACTOR_BY_ID[k].unit
        d = fmt.shock_digits(unit)
        hm = hist.get(k, float("nan"))
        e[f"f:{k}"] = {
            "title": f"{FACTOR_BY_ID[k].name} 충격값", "value": s, "value_text": fmt.signed(s, d, unit),
            "sub": f"과거 {ctx.horizon}영업일 최대 변동폭 ±{hm:.{d}f}{unit} 대비 {abs(s) / hm * 100:.0f}% 위치" if hm == hm and hm > 0 else "",
            "formula": "과거 최대 대비 = |충격값| / max |Δf⁽ʲ⁾|",
            "columns": ["유사 구간", "유사도", "당시 변화"],
            "rows": [[_cell(f"{r.start.date()} ~ {r.end.date()}"), _cell(f"{r.similarity:.2f}"),
                      _cell(fmt.signed(r.factor_changes.get(k, float('nan')), d, unit))] for r in regimes],
            "note": "충격값의 근거와 과거 유사 국면에서 같은 변수가 실제로 움직인 크기입니다.",
        }
    return e
