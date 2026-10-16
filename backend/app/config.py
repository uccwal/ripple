"""환경 변수 기반 설정. 값은 .env 또는 실행 환경에서 읽는다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

load_dotenv(REPO_ROOT / ".env")


def normalize_db_url(url: str) -> str:
    """Render 등이 주는 postgres:// · postgresql:// · postgresql+psycopg2:// 를 psycopg 3 드라이버 주소로 통일한다."""
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # .env 에 빈 값으로 적혀 있어도 기본값을 쓴다
    database_url: str = normalize_db_url(os.getenv("DATABASE_URL") or f"sqlite:///{REPO_ROOT / 'ripple.db'}")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    # LLM_MODE=offline 이면 API 키가 있어도 LLM을 호출하지 않는다 (규칙 기반 Agent로 실행).
    llm_mode_override: str | None = os.getenv("LLM_MODE") or None
    model_default: str = os.getenv("MODEL_DEFAULT") or "claude-haiku-5-5"
    # 파급 경로 추론은 가장 추론 품질에 민감한 단계라 기본값을 Sonnet 으로 둔다 (MODEL_IMPACT_MAPPER 로 변경 가능)
    model_impact_mapper: str = os.getenv("MODEL_IMPACT_MAPPER") or "claude-sonnet-5-5"
    llm_timeout_s: float = _float("LLM_TIMEOUT_S", 120.0)

    # 재시도 상한 (설계서 2장)
    max_retry_impact: int = 2
    max_retry_risk: int = 1

    # 헤지 규칙 기준값 (설계서 3장 ④, MVP 기본값)
    hedge_fx_share: float = _float("HEDGE_FX_SHARE", 0.30)
    hedge_sector_share: float = _float("HEDGE_SECTOR_SHARE", 0.40)
    hedge_rate_share: float = _float("HEDGE_RATE_SHARE", 0.25)

    # 팩터 회귀 창 (영업일)
    beta_window_days: int = int(os.getenv("BETA_WINDOW_DAYS") or 1250)  # 약 5년
    beta_min_obs: int = 250

    # 관리용 API (POST /api/admin/collect) 토큰. 비우면 관리용 API 비활성
    admin_token: str | None = os.getenv("ADMIN_TOKEN") or None
    # 매일 자동 수집 시각 (UTC 시, 0~23). 비우면 자동 수집 안 함. 0 = 09:00 KST
    collect_daily_hour_utc: int | None = int(os.environ["COLLECT_DAILY_HOUR_UTC"]) if os.getenv("COLLECT_DAILY_HOUR_UTC") else None
    # 서버 기동 직후 수집할 기간(일). 재배포마다 최근 데이터를 바로 채운다
    collect_startup_days: int = int(os.getenv("COLLECT_STARTUP_DAYS") or 30)

    # 수집 직후 자동 사전분석: 관련성 high · 최근 N일 · 아직 분석 없는 이벤트를 기본 포트폴리오로 분석 (0 이면 끔)
    auto_analyze_max: int = int(os.getenv("AUTO_ANALYZE_MAX") or 5)
    auto_analyze_days: int = int(os.getenv("AUTO_ANALYZE_DAYS") or 7)
    auto_analyze_portfolio: str = os.getenv("AUTO_ANALYZE_PORTFOLIO") or "pf_a"

    fred_api_key: str | None = os.getenv("FRED_API_KEY") or None
    ecos_api_key: str | None = os.getenv("ECOS_API_KEY") or None
    data_go_kr_api_key: str | None = os.getenv("DATA_GO_KR_API_KEY") or None

    cors_origins: list[str] = field(
        default_factory=lambda: (os.getenv("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173").split(",")
    )

    @property
    def llm_mode(self) -> str:
        if self.llm_mode_override == "offline":
            return "offline"
        return "anthropic" if self.anthropic_api_key else "offline"


settings = Settings()
