"""Claude API 호출 래퍼.

- 구조화 출력: output_config.format(json_schema)로 JSON만 받고, Pydantic으로 검증한 뒤에만 상태에 반영한다.
- LLM_MODE=offline(키 없음)이면 호출하지 않고 None을 돌려준다 → 각 Agent는 규칙 기반 대체 로직으로 동작한다.
- stop_reason이 refusal/max_tokens이면 실패로 처리한다. Haiku 5.5는 서버 측 fallback이 없다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    parsed: BaseModel | None
    model: str
    tokens_in: int
    tokens_out: int
    error: str | None = None


class LLMError(RuntimeError):
    pass


_client = None


def client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_s, max_retries=2)
    return _client


def _strip_schema(schema: dict) -> dict:
    """Pydantic JSON 스키마를 structured outputs가 받는 형태로 정리 ($defs 유지, additionalProperties false)."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
                if "properties" in node:
                    node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(schema)
    return schema


def structured(system: str, user: str, schema: type[T], model: str | None = None, effort: str = "medium",
               max_tokens: int = 8000) -> LLMResult:
    """JSON 스키마에 맞는 응답을 받아 schema 인스턴스로 검증한다."""
    if settings.llm_mode == "offline":
        return LLMResult(None, "offline", 0, 0, "offline")
    import anthropic

    model = model or settings.model_default
    json_schema = _strip_schema(schema.model_json_schema())
    try:
        resp = client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": json_schema}},
        )
    except anthropic.RateLimitError as e:
        raise LLMError(f"Claude API 요청 한도 초과: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"Claude API 연결 실패: {e}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API 오류 {e.status_code}: {e.message}") from e

    usage = resp.usage
    tin, tout = usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0), usage.output_tokens
    if resp.stop_reason == "refusal":
        cat = resp.stop_details.category if resp.stop_details else None
        return LLMResult(None, model, tin, tout, f"모델이 응답을 거부했습니다 (category={cat})")
    if resp.stop_reason == "max_tokens":
        return LLMResult(None, model, tin, tout, "응답이 max_tokens에서 잘렸습니다")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        parsed = schema.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as e:
        return LLMResult(None, model, tin, tout, f"JSON 스키마 검증 실패: {str(e)[:200]}")
    return LLMResult(parsed, model, tin, tout)
