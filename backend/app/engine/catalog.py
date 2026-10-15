"""팩터 정의. 팩터 수익률은 원 시계열(series)의 일별 변화로 만든다.

- unit "%": 일별 변화율 × 100 (예: 원/달러 +0.4%)
- unit "%p": 일별 차분 (예: 국채 10년 +0.03%p)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Factor:
    factor_id: str
    name: str
    unit: str  # "%" | "%p"
    series_id: str
    group: str  # fx | equity | rate | commodity  (헤지 규칙 분류)

    @property
    def transform(self) -> str:
        return "pct" if self.unit == "%" else "diff"


FACTORS: list[Factor] = [
    Factor("USDKRW", "원/달러 환율", "%", "USDKRW", "fx"),
    Factor("DXY_BROAD", "달러 인덱스 (광의)", "%", "DXY_BROAD", "fx"),
    Factor("KOSPI", "KOSPI", "%", "KOSPI", "equity"),
    Factor("KOSPI_IT", "KOSPI IT 업종", "%", "KOSPI_IT", "equity"),
    Factor("US_EQ", "미국 주식 (국내 상장 S&P 500 ETF 대리)", "%", "US_EQ", "equity"),
    Factor("DGS10", "미국 국채 10년", "%p", "DGS10", "rate"),
    Factor("DGS2", "미국 국채 2년", "%p", "DGS2", "rate"),
    Factor("KTB3Y", "국고채 3년", "%p", "KTB3Y", "rate"),
    Factor("WTI", "WTI 유가", "%", "WTI", "commodity"),
]
FACTOR_BY_ID: dict[str, Factor] = {f.factor_id: f for f in FACTORS}
FACTOR_IDS: list[str] = [f.factor_id for f in FACTORS]

# 자연어·LLM 출력에서 팩터를 찾기 위한 별칭. 여러 팩터가 걸리면 가장 긴 별칭이 이긴다 ("달러 인덱스" > "달러").
FACTOR_ALIASES: dict[str, list[str]] = {
    "USDKRW": ["원/달러", "원달러", "환율", "원화", "달러"],
    "DXY_BROAD": ["달러 인덱스", "달러인덱스", "달러지수", "dxy", "달러 강세", "달러 약세"],
    "KOSPI": ["코스피", "kospi", "국내 증시", "국내 주식"],
    "KOSPI_IT": ["반도체", "it 업종", "it업종", "정보기술", "kospi it"],
    "US_EQ": ["미국 주식", "미국 증시", "s&p", "나스닥", "미국주식"],
    "DGS10": ["미국 금리", "미 국채", "미국 국채", "미국 기준금리", "연준", "fed", "미국금리", "10년"],
    "DGS2": ["미국 2년", "미 2년", "2년물", "2년 금리", "단기 금리", "단기금리"],
    "KTB3Y": ["국고채", "한국 금리", "국내 금리", "기준금리 (한국)", "한국은행"],
    "WTI": ["유가", "원유", "wti", "oil"],
}


def match_factor(text: str) -> str | None:
    """텍스트에 들어 있는 별칭 중 가장 긴 것의 팩터 id. 없으면 None."""
    low = text.lower()
    best: tuple[int, str] | None = None
    for fid, aliases in FACTOR_ALIASES.items():
        for a in aliases:
            if a in low and (best is None or len(a) > best[0]):
                best = (len(a), fid)
    return best[1] if best else None
