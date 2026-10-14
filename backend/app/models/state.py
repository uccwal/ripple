"""공유 상태 RunState와 Agent 입·출력 스키마 (설계서 2장)."""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

Confidence = Literal["high", "mid", "low"]
Direction = Literal["+", "-"]
Layer = Literal["policy", "industry", "macro", "asset"]
EventType = Literal["tariff", "rate", "regulation"]


# ------------------------------------------------------------------ LLM 출력 스키마 (검증 후에만 상태 반영)

class EventStruct(BaseModel):
    country: str = Field(description="ISO 2자리 국가 코드 (US, KR, EU, CN, JP ...)")
    type: EventType
    title: str = Field(description="한국어 제목, 40자 이내")
    summary: str = Field(description="한국어 한 문장 요약")
    targets: list[str] = Field(description="대상 산업·품목·변수 영문 소문자 키워드 (예: semiconductor, policy_rate)")
    value: float | None = Field(description="핵심 수치. 관세율·금리 변화는 % 단위, 없으면 null")
    value_text: str = Field(description="핵심 수치 표시 문자열 (예: '관세율 25%', '+0.25%p')")
    missing_fields: list[str] = Field(description="원문에서 확인하지 못한 필수 필드 이름 목록. 없으면 빈 배열")


class PathStep(BaseModel):
    from_node: str = Field(description="출발 노드 id")
    to_node: str = Field(description="도착 노드 id")
    direction: Direction = Field(description="출발 변수 증가 시 도착 변수의 방향")
    confidence: Confidence
    evidence_ids: list[str] = Field(description="근거 id 목록. 정량 근거가 없으면 빈 배열이고 confidence는 low")


class PathNode(BaseModel):
    id: str = Field(description="n1, n2 ... 형식")
    label: str = Field(description="한국어 노드 이름, 14자 이내")
    layer: Layer
    factor_id: str | None = Field(description="macro 노드가 대응하는 팩터 id (USDKRW, KOSPI, KOSPI_IT, US_EQ, DGS10, KTB3Y, WTI). 아니면 null")
    direction_text: str = Field(description="이 노드로 들어오는 영향 설명 한 줄 (예: '수출 감소 → 환율 (+)')")


class Evidence(BaseModel):
    id: str = Field(description="ev1, ev2 ... 형식")
    text: str = Field(description="근거 내용 한 문장. 제공된 통계에 있는 숫자만 인용")
    source: str = Field(description="제공된 통계의 출처 이름 그대로")


class ImpactPaths(BaseModel):
    nodes: list[PathNode]
    paths: list[list[PathStep]] = Field(description="최대 3개 경로, 경로당 최대 4단계")
    evidence: list[Evidence]


class ShockItem(BaseModel):
    variable: str = Field(description="팩터 id")
    change: float = Field(description="충격값. unit이 %면 변화율(%), %p면 금리 변화(%p)")
    basis: str = Field(description="충격값 근거 한 문장 (제공된 과거 사례 통계 인용)")


class ScenarioShocks(BaseModel):
    shocks: list[ShockItem]
    horizon_days: int


class ReportText(BaseModel):
    summary: str = Field(description="요약 단락 2~3문장. 숫자는 반드시 {{키}} 자리표시자로만 쓴다")
    path_commentary: str = Field(description="파급 경로 설명 1~2문장. 숫자 자리표시자 외 숫자 금지")
    hedge_commentary: str = Field(description="헤지 제안 설명 1~2문장. 숫자 자리표시자 외 숫자 금지")


# ------------------------------------------------------------------ 공유 상태

class RunState(TypedDict, total=False):
    run_id: str
    parent_run_id: str | None
    entry: Literal["event", "scenario"]
    input_text: str
    portfolio_id: str
    horizon_days: int
    as_of: str | None
    title: str
    event: dict[str, Any] | None
    impact_paths: list[dict]
    graph: dict | None
    scenario: dict | None
    regimes: list[dict]
    result: dict | None
    calc_log: dict | None
    validation: dict | None
    report: dict | None
    retries: dict[str, int]
    rejections: list[dict]      # Validator 반려 기록 [{to: agent, issues: [...]}]
    resume_from: str | None     # 재계산 시 시작 Agent
    partial: bool
    error: str | None
    _reject_to: str | None      # Validator 반려 대상 Agent (라우팅용, 직렬화 제외)


AGENTS = ["Event Analyst", "Impact Mapper", "Scenario Builder", "Regime Finder", "Risk Engine", "Validator", "Report Writer"]
AGENT_DESC = {
    "Event Analyst": "이벤트 구조화",
    "Impact Mapper": "파급 경로 추론",
    "Scenario Builder": "충격값 변환",
    "Regime Finder": "과거 유사 국면",
    "Risk Engine": "손익 계산",
    "Validator": "수치·근거 검증",
    "Report Writer": "보고서 작성",
}
