"""첨부 Excel 파서 - openpyxl 기반 (DESIGN.md 3.1)

대상 파일
- 02_경제성검토.xlsx : `기본가정` 시트의 라벨(A열) / 입력값(B열) / 단위(C열)
- 03_투자비내역.xlsx : `투자비상세` 시트의 구분·금액 표
- 04_기대효과산출.xlsx : `기대효과` 시트의 효과 구분·산출금액·계획서 기재 표

모든 추출값의 출처는 `시트명!셀주소` 로 기록한다.
샘플 파일의 수식 셀에는 계산값이 저장되어 있지 않다. 이 경우 값을 직접
계산해 채우지 않고 수식 문자열을 근거로 남긴다 (CLAUDE.md 원칙).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from src.parsers.base import ParsedValue, SourceRef

# 02_경제성검토.xlsx 기본가정 시트에서 찾을 라벨
ECONOMICS_LABELS = {
    "프로젝트명",
    "경제성 적용 투자비",
    "WACC",
    "분석기간",
    "NPV",
    "IRR",
    "회수기간",
}

# 세부 항목 표에서 항목이 아닌 행(합계·차이 등)
NON_ITEM_NAMES = {"합계", "소계", "계획서 총투자비", "세부효과 합계", "차이"}

TOTAL_ROW_NAMES = {"계획서 총투자비"}


@dataclass
class CashflowTable:
    """02_경제성검토.xlsx 의 연도별 현금흐름"""

    file_name: str
    sheet_name: str
    years: list[int] = field(default_factory=list)
    effects: dict[int, float] = field(default_factory=dict)  # 연도 → 영업현금효과
    capex: dict[int, float] = field(default_factory=dict)  # 연도 → 투자비
    effect_cells: dict[int, str] = field(default_factory=dict)  # 연도 → 셀주소
    errors: list[str] = field(default_factory=list)

    @property
    def first_effect_year(self) -> int | None:
        """영업현금효과가 처음 발생하는 연도"""
        years = [year for year, value in self.effects.items() if value and value > 0]
        return min(years) if years else None

    def source_of(self, year: int) -> SourceRef:
        return SourceRef(self.file_name, f"{self.sheet_name}!{self.effect_cells.get(year, '-')}")


@dataclass
class ExcelTable:
    """세부 항목 표 1개의 파싱 결과"""

    file_name: str
    sheet_name: str
    items: list[ParsedValue] = field(default_factory=list)  # 항목별 금액
    totals: dict[str, ParsedValue] = field(default_factory=dict)  # 합계성 행
    notes: list[str] = field(default_factory=list)  # 수식 미계산 등 특이사항
    errors: list[str] = field(default_factory=list)


def _open(path: Path):
    """값 워크북과 수식 워크북을 함께 연다."""
    values = openpyxl.load_workbook(path, data_only=True)
    formulas = openpyxl.load_workbook(path, data_only=False)
    return values, formulas


def _cell_ref(file_name: str, sheet_name: str, coordinate: str) -> SourceRef:
    return SourceRef(file=file_name, locator=f"{sheet_name}!{coordinate}")


def parse_economics(path: Path) -> dict[str, ParsedValue]:
    """경제성검토 파일에서 라벨 기반으로 지표를 읽는다.

    라벨 셀의 오른쪽 셀을 입력값, 그 오른쪽을 단위로 해석한다.
    입력값 셀이 비어 있으면 value=None 으로 두고 '공란'을 근거로 남긴다.
    """
    result: dict[str, ParsedValue] = {}
    try:
        values, _ = _open(path)
    except Exception as exc:
        return {
            "__error__": ParsedValue(
                "오류", None, None, SourceRef(path.name, "-"), missing_marker=str(exc)
            )
        }

    for sheet in values.worksheets:
        for row in sheet.iter_rows():
            cells = list(row)
            for index, cell in enumerate(cells):
                label = cell.value.strip() if isinstance(cell.value, str) else None
                if label not in ECONOMICS_LABELS or label in result:
                    continue

                value_cell = cells[index + 1] if index + 1 < len(cells) else None
                unit_cell = cells[index + 2] if index + 2 < len(cells) else None
                unit = unit_cell.value if isinstance(getattr(unit_cell, "value", None), str) else None

                if value_cell is None or value_cell.value is None:
                    result[label] = ParsedValue(
                        label=label,
                        value=None,
                        unit=unit,
                        source=_cell_ref(
                            path.name,
                            sheet.title,
                            value_cell.coordinate if value_cell else cell.coordinate,
                        ),
                        raw_text=f"{label} 행의 입력값 셀이 비어 있음",
                        missing_marker="공란",
                    )
                else:
                    result[label] = ParsedValue(
                        label=label,
                        value=value_cell.value,
                        unit=unit,
                        source=_cell_ref(path.name, sheet.title, value_cell.coordinate),
                        raw_text=f"{label} = {value_cell.value}",
                    )

    return result


def _parse_item_table(
    path: Path, name_header: str, amount_header: str, extra_headers: tuple[str, ...] = ()
) -> ExcelTable:
    """`구분 / 금액` 형태의 표를 헤더 기준으로 파싱한다."""
    try:
        values, formulas = _open(path)
    except Exception as exc:
        table = ExcelTable(file_name=path.name, sheet_name="-")
        table.errors.append(f"Excel 열기 실패: {exc}")
        return table

    sheet = values.worksheets[0]
    formula_sheet = formulas[sheet.title]
    table = ExcelTable(file_name=path.name, sheet_name=sheet.title)

    # 헤더 행 탐색
    header_row = None
    columns: dict[str, int] = {}
    for row in sheet.iter_rows():
        labels = {
            cell.value.strip(): cell.column
            for cell in row
            if isinstance(cell.value, str)
        }
        if name_header in labels and amount_header in labels:
            header_row = row[0].row
            columns = labels
            break

    if header_row is None:
        table.errors.append(f"'{name_header} / {amount_header}' 헤더를 찾지 못했습니다.")
        return table

    name_col = columns[name_header]
    amount_col = columns[amount_header]

    for row in sheet.iter_rows(min_row=header_row + 1):
        name_cell = sheet.cell(row=row[0].row, column=name_col)
        if not isinstance(name_cell.value, str) or not name_cell.value.strip():
            continue

        item_name = name_cell.value.strip()
        amount_cell = sheet.cell(row=row[0].row, column=amount_col)
        formula_cell = formula_sheet.cell(row=row[0].row, column=amount_col)

        if amount_cell.value is None:
            formula = formula_cell.value if isinstance(formula_cell.value, str) else None
            parsed = ParsedValue(
                label=item_name,
                value=None,
                unit="억원",
                source=_cell_ref(path.name, sheet.title, amount_cell.coordinate),
                raw_text=f"수식 `{formula}` 의 계산값이 파일에 저장되어 있지 않음" if formula else "값 없음",
                missing_marker="수식 미계산" if formula else "공란",
            )
            if formula:
                table.notes.append(
                    f"{sheet.title}!{amount_cell.coordinate} ({item_name}) 는 수식 `{formula}` "
                    "이며 계산값이 파일에 저장되어 있지 않아 값을 표시하지 않습니다."
                )
        else:
            parsed = ParsedValue(
                label=item_name,
                value=amount_cell.value,
                unit="억원",
                source=_cell_ref(path.name, sheet.title, amount_cell.coordinate),
                raw_text=f"{item_name} = {amount_cell.value}",
            )

        # 부가 컬럼(기준 물량, 단가/율, 계획서 기재 등) 수집
        for header in extra_headers:
            if header not in columns:
                continue
            extra_cell = sheet.cell(row=row[0].row, column=columns[header])
            if extra_cell.value is None:
                continue
            if header in TOTAL_ROW_NAMES:
                continue
            table.totals.setdefault(
                header,
                ParsedValue(
                    label=header,
                    value=extra_cell.value,
                    unit="억원",
                    source=_cell_ref(path.name, sheet.title, extra_cell.coordinate),
                    raw_text=f"{header} = {extra_cell.value}",
                ),
            )

        if item_name in NON_ITEM_NAMES:
            table.totals.setdefault(item_name, parsed)
        else:
            table.items.append(parsed)

    return table


def parse_cashflow(path: Path) -> CashflowTable:
    """경제성검토 파일의 `연도별현금흐름` 시트를 파싱한다.

    효과 반영 시점과 가동 예정 시점을 비교하기 위한 입력이다.
    """
    try:
        values, _ = _open(path)
    except Exception as exc:
        table = CashflowTable(file_name=path.name, sheet_name="-")
        table.errors.append(f"Excel 열기 실패: {exc}")
        return table

    sheet = next(
        (ws for ws in values.worksheets if "현금흐름" in ws.title), None
    )
    if sheet is None:
        table = CashflowTable(file_name=path.name, sheet_name="-")
        table.errors.append("'연도별현금흐름' 시트를 찾지 못했습니다.")
        return table

    table = CashflowTable(file_name=path.name, sheet_name=sheet.title)
    year_columns: dict[int, int] = {}  # 연도 → 컬럼 번호

    for row in sheet.iter_rows():
        head = row[0].value
        if not isinstance(head, str):
            continue

        if head.strip() == "구분":
            for cell in row[1:]:
                if isinstance(cell.value, int):
                    year_columns[cell.value] = cell.column
            table.years = sorted(year_columns)
            continue

        if not year_columns:
            continue

        target = None
        if "영업현금효과" in head:
            target = table.effects
        elif head.strip() == "투자비":
            target = table.capex
        if target is None:
            continue

        for year, column in year_columns.items():
            cell = sheet.cell(row=row[0].row, column=column)
            if isinstance(cell.value, (int, float)):
                target[year] = float(cell.value)
                if target is table.effects:
                    table.effect_cells[year] = cell.coordinate

    if not table.effects:
        table.errors.append("영업현금효과 행을 찾지 못했습니다.")

    return table


def parse_capex_detail(path: Path) -> ExcelTable:
    """03_투자비내역.xlsx 의 투자비 구성 표를 파싱한다."""
    return _parse_item_table(path, name_header="구분", amount_header="금액")


def parse_effect_detail(path: Path) -> ExcelTable:
    """04_기대효과산출.xlsx 의 기대효과 산출 표를 파싱한다."""
    return _parse_item_table(
        path,
        name_header="효과 구분",
        amount_header="산출금액",
        extra_headers=("계획서 기재",),
    )
