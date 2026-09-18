"""파서 공통 자료구조 (DESIGN.md 3.1 src/parsers)"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SourceRef:
    """추출값의 출처. CLAUDE.md '모든 결과에 근거를 표시한다' 원칙의 최소 단위."""

    file: str  # 파일명 (예: 02_경제성검토.xlsx)
    locator: str  # 위치 (예: p.3 / 기본가정!B9)

    def __str__(self) -> str:
        return f"{self.file} · {self.locator}"


@dataclass
class ParsedValue:
    """문서에서 읽어낸 하나의 값.

    value 가 None 이면 '문서에 항목은 있으나 값이 없음'을 뜻한다.
    이 경우 파서는 값을 추정하지 않고 missing_marker 에 근거를 남긴다.
    """

    label: str
    value: float | str | None
    unit: str | None
    source: SourceRef
    raw_text: str | None = None  # 원문 스니펫
    missing_marker: str | None = None  # 예: '미기재', '공란'

    @property
    def is_missing(self) -> bool:
        return self.value is None


def to_number(text: str) -> float | None:
    """'320.0', '1,250' → float. 숫자가 아니면 None."""
    try:
        return float(text.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def format_number(value: float | str | None) -> str:
    """표 표시용 숫자 포맷. 정수는 소수점 1자리, 그 외는 유효값 유지."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if abs(value - round(value)) < 1e-9:
        return f"{value:.1f}"
    return f"{value:g}"
