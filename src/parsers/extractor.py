"""필수 7항목 통합 추출 (DESIGN.md 3.1 src/parsers/extractor.py)

추출 항목: 투자명, 총 투자비, NPV, IRR, WACC, 회수기간, 기대효과

항목별로 출처 우선순위를 정해 조회하고, 값이 있는 첫 출처를 채택한다.
- 투자명 / 총 투자비 / 기대효과 : 투자계획서(PDF)가 1순위
- NPV / IRR / WACC / 회수기간  : 경제성검토(Excel)가 1순위, PDF가 2순위

어떤 출처에도 값이 없으면 추정하지 않고 `미확인`으로 남기며,
어디를 확인했는지를 근거로 함께 기록한다 (CLAUDE.md 원칙).
채택하지 않은 출처와는 값을 교차 검증해 불일치를 표로 제시한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from src import config, data_loader
from src.parsers import excel_parser, pdf_parser
from src.parsers.base import ParsedValue, format_number
from src.parsers.excel_parser import CashflowTable, ExcelTable
from src.parsers.pdf_parser import PdfDocument

STATUS_OK = "추출"
STATUS_MISSING = "미확인"


@dataclass
class ExtractedField:
    """화면 표시용 추출 결과 1행"""

    name: str
    display_value: str
    unit: str
    source_file: str
    source_locator: str
    status: str
    evidence: str = ""  # 원문 스니펫 또는 확인 경로
    note: str = ""  # 단위 정규화 등 처리 메모

    @property
    def is_missing(self) -> bool:
        return self.status == STATUS_MISSING


@dataclass
class ExtractionResult:
    dir_name: str
    fields: list[ExtractedField] = field(default_factory=list)
    cross_checks: list[dict] = field(default_factory=list)
    pdf: PdfDocument | None = None
    economics: dict[str, ParsedValue] = field(default_factory=dict)
    capex_table: ExcelTable | None = None
    effect_table: ExcelTable | None = None
    cashflow: CashflowTable | None = None
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def get(self, name: str) -> ExtractedField | None:
        return next((f for f in self.fields if f.name == name), None)

    def value_of(self, name: str) -> str:
        found = self.get(name)
        return found.display_value if found else config.NOT_FOUND

    @property
    def missing_names(self) -> list[str]:
        return [f.name for f in self.fields if f.is_missing]


# ----------------------------------------------------------------------
# 내부 유틸
# ----------------------------------------------------------------------
def _file_by_doc_type(project: data_loader.Project, doc_type: str) -> Path | None:
    for item in project.files:
        if item.doc_type == doc_type and item.is_input:
            return item.path
    return None


def _normalized(parsed: ParsedValue | None) -> tuple[float | str | None, str]:
    """비율로 저장된 %값(0.121)을 12.1 로 정규화한다."""
    if parsed is None or parsed.value is None:
        return None, ""
    value = parsed.value
    if isinstance(value, (int, float)) and parsed.unit == "%" and abs(value) <= 1:
        return round(value * 100, 4), f"원본 {value:g} (비율) → {value * 100:g}% 로 단위 정규화"
    return value, ""


def _pick(candidates: list[ParsedValue | None]) -> tuple[ParsedValue | None, list[ParsedValue]]:
    """값이 있는 첫 후보를 채택하고, 값이 없던 후보들을 함께 돌려준다."""
    chosen: ParsedValue | None = None
    empty: list[ParsedValue] = []
    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.value is None:
            empty.append(candidate)
        elif chosen is None:
            chosen = candidate
    return chosen, empty


def _build_field(
    name: str,
    unit: str,
    candidates: list[ParsedValue | None],
) -> ExtractedField:
    chosen, empty = _pick(candidates)

    if chosen is None:
        # 확인한 위치를 모두 근거로 남긴다 (값을 만들지 않는다)
        checked = "; ".join(
            f"{p.source} → {p.missing_marker or '값 없음'}" for p in empty
        ) or "해당 항목을 문서에서 찾지 못했습니다."
        return ExtractedField(
            name=name,
            display_value=config.NOT_FOUND,
            unit=unit,
            source_file="-",
            source_locator="-",
            status=STATUS_MISSING,
            evidence=checked,
        )

    value, note = _normalized(chosen)
    return ExtractedField(
        name=name,
        display_value=value if isinstance(value, str) else format_number(value),
        unit=unit,
        source_file=chosen.source.file,
        source_locator=chosen.source.locator,
        status=STATUS_OK,
        evidence=chosen.raw_text or "",
        note=note,
    )


def display_value(value: float | str | None) -> str:
    """표 표시용 문자열. 숫자와 '미확인'이 한 열에 섞이지 않게 통일한다."""
    if value is None:
        return config.NOT_FOUND
    if isinstance(value, str):
        return value
    return format_number(value)


def _cross_check(
    result: ExtractionResult,
    item: str,
    adopted: ParsedValue | None,
    other: ParsedValue | None,
    tolerance: float = 0.05,
) -> None:
    """채택 출처와 대조 출처의 값을 비교해 교차검증 표에 추가한다."""
    if adopted is None or other is None:
        return

    left, _ = _normalized(adopted)
    right, _ = _normalized(other)

    if left is None or right is None:
        verdict = "대조 불가 (값 없음)"
    elif isinstance(left, str) or isinstance(right, str):
        verdict = "일치" if str(left).strip() == str(right).strip() else "불일치"
    else:
        verdict = "일치" if abs(float(left) - float(right)) <= tolerance else "불일치"

    result.cross_checks.append(
        {
            "항목": item,
            "채택 값": display_value(left if left is not None else adopted.value),
            "채택 출처": str(adopted.source),
            "대조 값": display_value(right if right is not None else other.value),
            "대조 출처": str(other.source),
            "판정": verdict,
        }
    )


# ----------------------------------------------------------------------
# 추출 진입점
# ----------------------------------------------------------------------
@st.cache_data(show_spinner="투자 자료를 추출하고 있습니다...")
def extract(dir_name: str) -> ExtractionResult:
    """프로젝트 1건의 필수 7항목을 추출한다."""
    result = ExtractionResult(dir_name=dir_name)

    project = data_loader.get_project(dir_name)
    if project is None:
        result.errors.append(f"프로젝트를 찾을 수 없습니다: {dir_name}")
        return result

    plan_path = _file_by_doc_type(project, "투자계획서")
    econ_path = _file_by_doc_type(project, "경제성검토")
    capex_path = _file_by_doc_type(project, "투자비내역")
    effect_path = _file_by_doc_type(project, "기대효과산출")

    # --- 문서별 파싱 ---------------------------------------------------
    if plan_path:
        result.pdf = pdf_parser.parse_investment_plan(plan_path)
        result.errors.extend(result.pdf.errors)
    else:
        result.errors.append("투자계획서 PDF 파일을 찾을 수 없습니다.")

    if econ_path:
        result.economics = excel_parser.parse_economics(econ_path)
        result.cashflow = excel_parser.parse_cashflow(econ_path)
        result.errors.extend(result.cashflow.errors)
    else:
        result.errors.append("경제성검토 엑셀 파일을 찾을 수 없습니다.")

    if capex_path:
        result.capex_table = excel_parser.parse_capex_detail(capex_path)
        result.notes.extend(result.capex_table.notes)
        result.errors.extend(result.capex_table.errors)

    if effect_path:
        result.effect_table = excel_parser.parse_effect_detail(effect_path)
        result.notes.extend(result.effect_table.notes)
        result.errors.extend(result.effect_table.errors)

    pdf = result.pdf
    econ = result.economics

    # --- 항목별 출처 후보 ----------------------------------------------
    pdf_title = pdf.title if pdf else None
    pdf_capex_total = pdf.get("계획서 총투자비", "총투자비") if pdf else None
    pdf_effect_total = pdf.get("계획서 기재 연간효과", "연간 기대효과") if pdf else None
    excel_capex_total = (
        result.capex_table.totals.get("계획서 총투자비") if result.capex_table else None
    )
    excel_effect_total = (
        result.effect_table.totals.get("계획서 기재") if result.effect_table else None
    )

    result.fields = [
        _build_field("투자명", "-", [pdf_title, econ.get("프로젝트명")]),
        _build_field("총 투자비", "억원", [pdf_capex_total, excel_capex_total]),
        _build_field("NPV", "억원", [econ.get("NPV"), pdf.get("NPV") if pdf else None]),
        _build_field("IRR", "%", [econ.get("IRR"), pdf.get("IRR") if pdf else None]),
        _build_field("WACC", "%", [econ.get("WACC"), pdf.get("WACC") if pdf else None]),
        _build_field(
            "회수기간", "년", [econ.get("회수기간"), pdf.get("회수기간") if pdf else None]
        ),
        _build_field("기대효과", "억원/년", [pdf_effect_total, excel_effect_total]),
    ]

    # --- 교차 검증 ------------------------------------------------------
    _cross_check(result, "투자명", pdf_title, econ.get("프로젝트명"))
    _cross_check(result, "총 투자비", pdf_capex_total, excel_capex_total, tolerance=0.01)
    _cross_check(
        result, "총 투자비(경제성 적용)", pdf_capex_total, econ.get("경제성 적용 투자비"), tolerance=0.01
    )
    for name in ("NPV", "IRR", "WACC", "회수기간"):
        _cross_check(result, name, econ.get(name), pdf.get(name) if pdf else None)
    _cross_check(result, "기대효과", pdf_effect_total, excel_effect_total, tolerance=0.01)

    return result


def field_records(result: ExtractionResult) -> list[dict]:
    """정보추출 결과 화면의 표 데이터"""
    return [
        {
            "항목": f.name,
            "값": f.display_value,
            "단위": f.unit,
            "출처 파일": f.source_file,
            "위치": f.source_locator,
            "상태": f.status,
        }
        for f in result.fields
    ]
