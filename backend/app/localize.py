"""수집된 정책 이벤트의 한국어 구조화 (수집 직후 1회).

Federal Register 같은 외국 관보는 제목·요약이 영어라 대시보드 카드가 읽기 어렵다. 수집이 끝나면 아직 한국어화되지
않은 이벤트를 Claude(구조화 출력)로 한 번에 정리해 title/summary/type/targets/value/value_text 를 채운다.
원문 제목은 title_orig 에 보존한다. LLM_MODE=offline 이면 아무것도 하지 않는다 (영어 제목 그대로).
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field
from sqlalchemy import select

from . import llm
from .config import settings
from .db import session_scope
from .models.state import EventType
from .models.tables import PolicyEvent

log = logging.getLogger("ripple.localize")
HANGUL = re.compile(r"[가-힣]")
MAX_PER_RUN = 400

SYSTEM = """당신은 RIPPLE의 Event Analyst다. 외국 정부 발표(관보·보도자료)의 제목과 요약을 한국 기관투자자가 읽는 형태로 구조화한다.

규칙
- title: 한국어, 40자 이내, 핵심(국가·조치·대상)을 담는다. 예: "미국, 한국·대만산 반도체에 25% 관세 부과"
- summary: 한국어 한 문장(60자 이내). 원문에 있는 사실만 쓴다.
- type: 관세·수입제한·반덤핑/상계관세 → tariff, 기준금리·정책금리 → rate, 수출통제·규제·제도·조사 → regulation
- targets: 영향 산업·품목·변수의 영문 소문자 키워드 (semiconductor, steel, automobile, solar, all_imports, policy_rate ...)
- value: 원문의 핵심 수치(관세율 %, 금리 변화 %p). 없으면 null. value_text: 표시 문자열(예 "관세율 25%", "+0.25%p"). 수치가 없으면 빈 문자열.
- relevance: 한국 포트폴리오(국내 주식·채권·환율·해외 주식·원자재)에 영향을 줄 가능성. high | mid | low.
  개별 기업 대상 반덤핑 예비판정, 절차 공고, 소규모 품목은 low.
- 숫자는 원문에 있는 값만 쓴다. 지정된 JSON 스키마로만 답한다.
"""


class Localized(BaseModel):
    title: str
    summary: str
    type: EventType
    targets: list[str]
    value: float | None
    value_text: str
    relevance: str = Field(description="high | mid | low")


def needs_localization(ev: PolicyEvent) -> bool:
    """예시가 아니고 제목에 한글이 없으면 대상. (재수집으로 영어 제목이 되돌아온 경우도 포함)"""
    return not ev.is_demo and not HANGUL.search(ev.title or "")


def localize_pending(limit: int = MAX_PER_RUN) -> dict:
    """한국어화되지 않은 이벤트를 처리한다. 반환: {"done": n, "failed": m, "skipped": reason}"""
    if settings.llm_mode == "offline":
        return {"done": 0, "failed": 0, "skipped": "offline"}
    done = failed = 0
    with session_scope() as s:
        pending = [e for e in s.scalars(select(PolicyEvent).order_by(PolicyEvent.announced_at.desc())) if needs_localization(e)][:limit]
        log.info("한국어 구조화 대상 %d건", len(pending))
        for ev in pending:
            user = (f"국가: {ev.country}\n출처: {ev.source}\n발표일: {ev.announced_at}\n수집기 추정 유형: {ev.type}\n\n"
                    f"제목: {ev.title}\n\n본문/요약:\n{(ev.raw_text or ev.summary or '')[:3000]}")
            try:
                res = llm.structured(SYSTEM, user, Localized, model=settings.model_default, effort="low", max_tokens=2000)
            except llm.LLMError as e:
                log.warning("LLM 오류로 중단: %s", e)
                failed += 1
                break
            if res.parsed is None:
                failed += 1
                log.warning("%s: %s", ev.event_id, res.error)
                continue
            p = res.parsed
            if not ev.title_orig:
                ev.title_orig = ev.title
            ev.title = p.title[:300]
            ev.summary = p.summary
            ev.type = p.type
            ev.targets = p.targets
            ev.value = p.value
            ev.value_text = p.value_text
            ev.relevance = p.relevance if p.relevance in ("high", "mid", "low") else "mid"
            done += 1
            if done % 20 == 0:
                s.commit()
        s.commit()
    log.info("한국어 구조화 완료 %d건, 실패 %d건", done, failed)
    return {"done": done, "failed": failed}


RATE_SYSTEM = """당신은 RIPPLE의 Event Analyst다. 이미 한국어로 된 정책 발표 제목·요약을 보고 한국 기관투자자 포트폴리오(국내 주식·채권·환율·해외 주식·원자재) 관련성을 매긴다.

- relevance: high(시장·업종 전반에 영향: 관세·수출통제·기준금리·대규모 규제·환율/외환 정책) | mid(특정 업종·제도 변화) | low(행사·인사·홍보·절차 공고·소규모 지원).
- type: 관세·수입제한 → tariff, 기준금리·정책금리 → rate, 그 밖 → regulation.
- targets: 영향 산업·품목·변수 영문 소문자 키워드 (semiconductor, automobile, steel, policy_rate, fx ...). 없으면 빈 배열.
- 지정된 JSON 스키마로만 답한다."""


class Rated(BaseModel):
    relevance: str = Field(description="high | mid | low")
    type: EventType
    targets: list[str]


def rate_pending(limit: int = MAX_PER_RUN) -> dict:
    """관련성이 매겨지지 않은(한국어 원문 등) 이벤트에 relevance 를 매긴다. 자동 사전분석·대시보드 필터가 이 값을 쓴다."""
    if settings.llm_mode == "offline":
        return {"done": 0, "failed": 0, "skipped": "offline"}
    done = failed = 0
    with session_scope() as s:
        pending = list(s.scalars(select(PolicyEvent).where(PolicyEvent.relevance.is_(None), PolicyEvent.is_demo.is_(False))
                                 .order_by(PolicyEvent.announced_at.desc()).limit(limit)))
        log.info("관련성 평가 대상 %d건", len(pending))
        for ev in pending:
            user = (f"국가: {ev.country}\n출처: {ev.source}\n발표일: {ev.announced_at}\n수집기 추정 유형: {ev.type}\n\n"
                    f"제목: {ev.title}\n요약: {ev.summary}\n\n본문 일부:\n{(ev.raw_text or '')[:1500]}")
            try:
                res = llm.structured(RATE_SYSTEM, user, Rated, model=settings.model_default, effort="low", max_tokens=600)
            except llm.LLMError as e:
                log.warning("LLM 오류로 중단: %s", e)
                failed += 1
                break
            if res.parsed is None:
                failed += 1
                continue
            p = res.parsed
            ev.relevance = p.relevance if p.relevance in ("high", "mid", "low") else "mid"
            if p.type in ("tariff", "rate", "regulation"):
                ev.type = p.type
            if p.targets and not ev.targets:
                ev.targets = p.targets
            done += 1
            if done % 20 == 0:
                s.commit()
        s.commit()
    return {"done": done, "failed": failed}
