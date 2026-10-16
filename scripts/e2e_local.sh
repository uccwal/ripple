#!/usr/bin/env bash
# 로컬 E2E: 합성 데이터로 서버를 띄우고 분석 몇 건을 돌린 뒤 화면을 캡처한다 (실제 Claude 호출은 .env 의 키를 쓴다).
#
#   scripts/e2e_local.sh            # 포트 8010, 결과 ./.e2e/ (DB·로그·캡처)
#   PORT=8020 scripts/e2e_local.sh
#
# 끝나면 .e2e/shots/*.png 와 .e2e/summary.json 을 확인한다. 서버는 스크립트가 끝날 때 함께 내려간다.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PORT=${PORT:-8010}
OUT="$ROOT/.e2e"
rm -rf "$OUT" && mkdir -p "$OUT"
export DATABASE_URL="sqlite:///$OUT/e2e.db" ADMIN_TOKEN=e2e COLLECT_DAILY_HOUR_UTC= AUTO_ANALYZE_MAX=2

echo "▶ 프론트엔드 빌드 (같은 서버에서 서빙)"
(cd "$ROOT/frontend" && VITE_API_BASE= VITE_BASE=/ npm run build >/dev/null)

echo "▶ 시드 + 서버 기동 :$PORT"
(cd "$ROOT/backend" && python -m app.seed --synthetic >/dev/null)
(cd "$ROOT/backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$OUT/server.log" 2>&1) &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && break; sleep 1; done

B="http://127.0.0.1:$PORT"
echo "▶ 분석 실행 (동시 3건: 과거 이벤트·예시 이벤트·시나리오)"
R1=$(curl -s -X POST "$B/api/runs" -H 'content-type: application/json' -d '{"entry":"event","event_id":"ev_hist_2022_us_chip_export","portfolio_id":"pf_a"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
R2=$(curl -s -X POST "$B/api/runs" -H 'content-type: application/json' -d '{"entry":"event","event_id":"ev_demo_us_semis_tariff","portfolio_id":"pf_a"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
R3=$(curl -s -X POST "$B/api/runs" -H 'content-type: application/json' -d '{"entry":"scenario","scenario_text":"유가 30% 급등 + 원화 5% 약세","portfolio_id":"pf_b"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
for _ in $(seq 1 60); do
  S=$(curl -s "$B/api/runs?limit=3" | python3 -c 'import sys,json;print(" ".join(r["status"] for r in json.load(sys.stdin)))')
  echo "$S" | grep -qE "queued|running" || break
  sleep 5
done
curl -s "$B/api/runs?limit=3" | python3 -c '
import sys,json
rows=json.load(sys.stdin); bad=[r for r in rows if r["status"] not in ("done","partial")]
for r in rows: print(f"  {r["run_id"]} {r["status"]:8s} 검증 {r["validation_status"]!s:5s} 손익 {r["portfolio_pnl"]} 실제 {r.get("actual_pnl")} 적중 {r.get("direction_hit")}  {r["title"][:40]}")
sys.exit(1 if bad else 0)' || { echo "✗ 실패한 실행이 있습니다 — $OUT/server.log 확인"; }

echo "▶ 화면 캡처"
PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers} python "$ROOT/scripts/e2e_shots.py" "$B" "$OUT/shots" "$R1" "$R3" | tee "$OUT/summary.json" | python3 -c '
import sys,json; d=json.load(sys.stdin)
issues=[c for c in d["console"] if "pretendard" not in c["text"] and "ERR_TUNNEL" not in c["text"]]
print(f"  캡처 {len(d["pages"])}장 · 콘솔 문제 {len(issues)}건"); [print("   ", i) for i in issues]'
echo "완료 → $OUT/shots"
