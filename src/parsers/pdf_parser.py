"""투자계획서(PDF) 파서 - pdfplumber 기반 (DESIGN.md 3.1)

`01_투자계획서.pdf` 는 `라벨 값단위` 형태의 한 줄 항목과
`2. 투자비 구성` / `3. 기대효과` / `4. 경제성 검토 결과` 섹션으로 구성된다.
모든 추출값에 페이지 번호를 출처로 붙인다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from src.parsers.base import ParsedValue, SourceRef, to_number

# `설비비 205.0억원`, `IRR 12.1%`, `WACC 미기재` 형태의 한 줄 항목
LABEL_VALUE_RE = re.compile(
    r"^(?P<label>[가-힣A-Za-z·\s()]+?)\s+"
    r"(?P<value>-?[\d,]+(?:\.\d+)?|미기재|미제시|해당없음)"
    r"\s*(?P<unit>억원/년|억원|백만원|%|년|개월)?$"
)

# `2. 투자비 구성` 형태의 섹션 헤더
SECTION_RE = re.compile(r"^(?P<no>\d+)\.\s*(?P<title>.+)$")

# 값이 없음을 문서가 명시한 표기
MISSING_MARKERS = {"미기재", "미제시", "해당없음"}

# 투자명 후보에서 제외할 머리글·라벨
TITLE_EXCLUDE_PREFIXES = (
    "투자계획서",
    "가상 교육용",
    "작성부서",
    "투자 목적",
    "투자기간",
    "가동 예정",
    "총투자비",
    "연간 기대효과",
)

# 섹션 합계 라벨 (세부 항목 목록에서 제외)
CAPEX_TOTAL_LABELS = {"계획서 총투자비", "총투자비", "합계", "소계"}
EFFECT_TOTAL_LABELS = {"계획서 기재 연간효과", "연간 기대효과", "합계", "소계"}


@dataclass
class PdfDocument:
    """투자계획서 1건의 파싱 결과"""

    file_name: str
    page_count: int
    title: ParsedValue | None = None
    fields: dict[str, ParsedValue] = field(default_factory=dict)  # 라벨 → 값
    capex_items: list[ParsedValue] = field(default_factory=list)  # 투자비 구성 세부
    effect_items: list[ParsedValue] = field(default_factory=list)  # 기대효과 세부
    page_texts: dict[int, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def get(self, *labels: str) -> ParsedValue | None:
        """라벨 우선순위대로 조회한다."""
        for label in labels:
            if label in self.fields:
                return self.fields[label]
        return None


def _section_of(title: str) -> str | None:
    if "투자비" in title:
        return "capex"
    if "기대효과" in title:
        return "effect"
    if "경제성" in title:
        return "economics"
    return None


def _make_value(match: re.Match, file_name: str, page_no: int, line: str) -> ParsedValue:
    label = match.group("label").strip()
    raw_value = match.group("value")
    unit = match.group("unit")
    source = SourceRef(file=file_name, locator=f"p.{page_no}")

    if raw_value in MISSING_MARKERS:
        # 문서가 '미기재'로 명시한 항목은 값을 만들지 않는다 (CLAUDE.md 원칙)
        return ParsedValue(label, None, unit, source, line, missing_marker=raw_value)

    return ParsedValue(label, to_number(raw_value), unit, source, line)


def parse_investment_plan(path: Path) -> PdfDocument:
    """투자계획서 PDF 1건을 파싱한다."""
    doc = PdfDocument(file_name=path.name, page_count=0)

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:  # 손상 파일 등
        doc.errors.append(f"PDF 열기 실패: {exc}")
        return doc

    with pdf:
        doc.page_count = len(pdf.pages)

        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            doc.page_texts[page_no] = text
            section: str | None = None

            for line in (ln.strip() for ln in text.splitlines()):
                if not line:
                    continue

                section_match = SECTION_RE.match(line)
                if section_match:
                    section = _section_of(section_match.group("title"))
                    continue

                match = LABEL_VALUE_RE.match(line)
                if not match:
                    # 값이 없는 줄에서 투자명 후보를 찾는다 (1쪽 제목)
                    if (
                        page_no == 1
                        and doc.title is None
                        and not line.startswith(TITLE_EXCLUDE_PREFIXES)
                        and 3 <= len(line) <= 40
                    ):
                        doc.title = ParsedValue(
                            label="투자명",
                            value=line,
                            unit=None,
                            source=SourceRef(doc.file_name, f"p.{page_no}"),
                            raw_text=line,
                        )
                    continue

                parsed = _make_value(match, doc.file_name, page_no, line)
                doc.fields.setdefault(parsed.label, parsed)

                if section == "capex" and parsed.label not in CAPEX_TOTAL_LABELS:
                    doc.capex_items.append(parsed)
                elif section == "effect" and parsed.label not in EFFECT_TOTAL_LABELS:
                    doc.effect_items.append(parsed)

    if doc.title is None:
        doc.errors.append("1쪽에서 투자명을 찾지 못했습니다.")

    return doc
