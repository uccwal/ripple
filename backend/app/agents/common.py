"""Agent 공통 도우미."""
from __future__ import annotations

from ..engine.catalog import FACTORS


def factor_list_text() -> str:
    return "\n  ".join(f"- {f.factor_id}: {f.name} (unit {f.unit})" for f in FACTORS)


def model_label(result_model: str) -> str:
    return result_model if result_model != "offline" else "offline 규칙"


def fmt_pct(v: float, unit: str) -> str:
    d = 2 if unit == "%p" else 1
    return f"{v:+.{d}f}{unit}"
