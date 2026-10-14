"""과거 사례 재현 검증 (설계서 7장).

결정일(as_of) 이후 데이터를 계산에 넣지 않은 채 RIPPLE을 실행하고, 추정치를 발표 직후 horizon 영업일의
실제 움직임과 방향·크기로 비교한다. 결과는 docs/submission 의 '과거 사례 재현도' 지표에 쓴다.

    PYTHONPATH=backend python scripts/backtest.py            # 기본 2개 사례
    PYTHONPATH=backend python scripts/backtest.py --json out.json

주의: DB에 합성 시계열만 있으면 '실제 움직임'도 합성값이므로 수치는 의미가 없다 (파이프라인 점검용).
실제 수집 데이터(collectors)로 교체한 뒤 다시 실행해야 기획서에 쓸 수 있는 재현도가 나온다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import graph  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.engine.catalog import FACTOR_BY_ID  # noqa: E402
from app.engine.data import factor_window_changes, load_levels  # noqa: E402
from app.models.tables import Run, Series  # noqa: E402

CASES = [
    {"name": "2019-07 일본 수출규제", "event_id": "ev_hist_2019_jp_export", "as_of": "2019-07-01", "portfolio_id": "pf_a",
     "check": ["KOSPI", "KOSPI_IT", "USDKRW"]},
    {"name": "2025-04 미국 상호관세", "event_id": "ev_hist_2025_us_reciprocal", "as_of": "2025-04-03", "portfolio_id": "pf_a",
     "check": ["USDKRW", "KOSPI", "US_EQ"]},
]


def actual_moves(session, as_of: date, horizon: int) -> dict[str, float]:
    """결정일 직후 horizon 영업일 동안 각 팩터의 실제 변화 (결정일 종가 → horizon일 뒤 종가)."""
    sids = [f.series_id for f in FACTOR_BY_ID.values()]
    levels = load_levels(session, sids, None)
    pos = levels.index.searchsorted(str(as_of))
    end_pos = min(pos + horizon, len(levels) - 1)
    wc = factor_window_changes(levels, end_pos - pos)
    row = wc.iloc[end_pos]
    return {k: float(v) for k, v in row.items() if v == v}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="결과 저장 경로")
    ap.add_argument("--horizon", type=int, default=20)
    args = ap.parse_args()
    init_db()
    s = SessionLocal()
    synthetic = any(src.startswith("SYNTHETIC") for (src,) in s.execute(__import__("sqlalchemy").select(Series.source)).all())
    if synthetic:
        print("⚠ 합성 시계열이 포함되어 있습니다. 아래 수치는 파이프라인 점검용이며 실제 재현도가 아닙니다.\n")
    results = []
    for c in CASES:
        as_of = date.fromisoformat(c["as_of"])
        run = graph.create_run(s, "event", c["portfolio_id"], c["event_id"], None, args.horizon, as_of)
        rid = run.run_id
        s.close()
        t = time.time()
        graph.execute(rid)
        s = SessionLocal()
        run = s.get(Run, rid)
        st = run.state
        pred = {sh["variable"]: sh["change"] for sh in (st.get("scenario") or {}).get("shocks", [])}
        act = actual_moves(s, as_of, args.horizon)
        rows = []
        for k in c["check"]:
            p, a = pred.get(k), act.get(k)
            unit = FACTOR_BY_ID[k].unit
            rows.append({"factor": k, "predicted": p, "actual": a, "unit": unit,
                         "direction_ok": (p is not None and a is not None and (p > 0) == (a > 0)),
                         "abs_error": abs(p - a) if (p is not None and a is not None) else None})
        res = {"case": c["name"], "run_id": rid, "status": run.status, "as_of": c["as_of"], "elapsed_s": round(time.time() - t, 1),
               "portfolio_pnl": (st.get("result") or {}).get("portfolio_pnl"),
               "regime_median": ((st.get("result") or {}).get("regime_estimate") or {}).get("median"),
               "validation": (st.get("validation") or {}).get("status"), "factors": rows,
               "direction_hit_rate": sum(r["direction_ok"] for r in rows) / len(rows) if rows else None}
        results.append(res)
        print(f"■ {c['name']} (as_of {c['as_of']}, run {rid}, {res['status']}, {res['elapsed_s']}s)")
        print(f"  포트폴리오 추정 손익 {res['portfolio_pnl']:+.2f}% · 유사 국면 중앙값 {res['regime_median']}")
        for r in rows:
            pa = "—" if r["predicted"] is None else f"{r['predicted']:+.2f}{r['unit']}"
            aa = "—" if r["actual"] is None else f"{r['actual']:+.2f}{r['unit']}"
            print(f"  {r['factor']:<9} 추정 {pa:>10} · 실제 {aa:>10} · 방향 {'○' if r['direction_ok'] else '×'}")
        print(f"  방향 적중률 {res['direction_hit_rate']:.0%}\n")
    if args.json:
        Path(args.json).write_text(json.dumps({"synthetic": synthetic, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved → {args.json}")


if __name__ == "__main__":
    main()
