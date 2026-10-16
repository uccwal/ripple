"""Event Analyst: 정책 발표 원문 → event 구조화. 필수 필드가 비면 사용자 확인이 필요하다고 표시한다."""
from __future__ import annotations

import re
from datetime import date

from .. import llm, prompts
from ..config import settings
from ..models.state import EventStruct, RunState
from ..models.tables import PolicyEvent
from .common import model_label

TYPE_NAME = {"tariff": "관세", "rate": "금리", "regulation": "규제"}
COUNTRY_NAME = {"US": "미국", "KR": "한국", "EU": "EU", "CN": "중국", "JP": "일본"}


def _offline(ev: PolicyEvent) -> EventStruct:
    """키 없이 실행할 때: DB에 저장된 구조화 필드를 그대로 쓰고 원문에서 수치만 재확인한다."""
    missing = []
    value = ev.value
    if value is None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", ev.raw_text or "")
        value = float(m.group(1)) if m else None
        if value is None:
            missing.append("value")
    return EventStruct(country=ev.country, type=ev.type, title=ev.title, summary=ev.summary or ev.title,
                       targets=list(ev.targets or []), value=value, value_text=ev.value_text or "",
                       missing_fields=missing)


def run(state: RunState, ev: PolicyEvent) -> tuple[dict, dict]:
    """반환: (event dict, step meta)"""
    user = (f"발표일: {ev.announced_at}\n출처: {ev.source} {ev.source_url}\n"
            f"국가(수집기 추정): {ev.country}\n유형(수집기 추정): {ev.type}\n\n원문:\n{ev.raw_text or ev.summary or ev.title}")
    res = llm.structured(prompts.EVENT_ANALYST, user, EventStruct, model=settings.model_default, effort="low")
    if res.parsed is None:
        if res.error != "offline":
            raise llm.LLMError(res.error or "Event Analyst 실패")
        parsed = _offline(ev)
    else:
        parsed = res.parsed
    # 발표일·출처는 레코드에서 확정되므로 LLM 이 '누락'이라 해도 무시한다. 수치는 실제로 비어 있을 때만 누락.
    missing = [f for f in parsed.missing_fields if f in ("country", "type", "value")]
    if "value" in missing and (parsed.value is not None or parsed.type == "regulation"):
        missing.remove("value")  # 규제·수출통제는 수치가 없는 게 정상이라 누락이 아니다
    parsed.missing_fields = missing
    event = {
        "event_id": ev.event_id, "country": parsed.country, "country_name": COUNTRY_NAME.get(parsed.country, parsed.country),
        "type": parsed.type, "type_name": TYPE_NAME[parsed.type], "title": parsed.title, "summary": parsed.summary,
        "targets": parsed.targets, "value": parsed.value, "value_text": parsed.value_text,
        "announced_at": ev.announced_at.isoformat() if isinstance(ev.announced_at, date) else str(ev.announced_at),
        "source": ev.source, "source_url": ev.source_url, "is_demo": ev.is_demo,
        "missing_fields": parsed.missing_fields,
    }
    meta = {"model": model_label(res.model), "tokens": (res.tokens_in, res.tokens_out),
            "summary": f"{event['country']} · {event['type_name']} · {', '.join(parsed.targets) or '-'} · {parsed.value_text}",
            "note": ("필수 필드 누락: " + ", ".join(parsed.missing_fields) + " — 사용자 확인 필요") if parsed.missing_fields else ""}
    return event, meta
