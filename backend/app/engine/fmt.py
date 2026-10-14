"""계산 근거 패널용 숫자 서식. 음수는 유니코드 마이너스(U+2212)를 쓴다."""
from __future__ import annotations

import math

MINUS = "−"


def signed(v: float | None, digits: int = 1, unit: str = "%") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    r = round(v, digits)
    if r == 0:
        return f"{0:.{digits}f}{unit}"
    sign = "+" if r > 0 else MINUS
    return f"{sign}{abs(r):,.{digits}f}{unit}"


def plain(v: float, digits: int = 3) -> str:
    s = f"{abs(v):,.{digits}f}"
    return (MINUS + s) if round(v, digits) < 0 else s


def shock_digits(unit: str) -> int:
    return 2 if unit == "%p" else 1


def amount(v: float) -> str:
    """억 원 금액 (10억 단위 반올림)."""
    r = round(v / 10) * 10
    if r == 0:
        return "0억 원"
    return f"{'+' if r > 0 else MINUS}{abs(r):,.0f}억 원"
