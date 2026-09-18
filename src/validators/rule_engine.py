"""검증 룰 엔진 R-01 ~ R-04 (DESIGN.md 2.3 / 3.1)

R-01 투자비 정합성   : 계획서 총투자비 = 투자비 내역 합계          → 불일치 시 `높음`
R-02 경제성 지표 존재 : WACC·NPV·IRR·회수기간 존재 여부            → 누락 시 `확인필요`
R-03 기대효과 정합성  : 세부효과 합계 = 계획서 기재 연간효과        → 불일치 시 `높음`
R-04 기대효과 중복    : 효과 반영시점 / 효과 항목 간 중복 가능성    → 해당 시 `주의`

판정은 등급 부여까지만 수행하며 투자 승인·부결은 판단하지 않는다.
모든 판정에 비교값·계산식·출처를 근거로 남긴다 (CLAUDE.md 원칙).

투자비·기대효과의 세부 항목 합계는 투자계획서(PDF) 기재 항목을 기준으로 한다.
샘플팩의 `03_투자비내역.xlsx` / `04_기대효과산출.xlsx` 는 합계·차이 행이 항목 행
자리를 차지해 항목이 일부 누락되어 있어, 합계 비교의 기준으로 쓰지 않고
항목 수 차이를 자료 품질 메모로만 표시한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from src import config
from src.parsers import extractor
from src.parsers.base import ParsedValue, format_number
from src.parsers.extractor import ExtractionResult

# 금액 비교 허용오차: 절대 0.05억원 또는 기준값의 0.1% 중 큰 값
ABS_TOLERANCE = 0.05
REL_TOLERANCE = 0.001

# R-02 에서 존재해야 하는 경제성 지표
REQUIRED_ECONOMICS = ("WACC", "NPV", "IRR", "회수기간")

# R-04 효과 항목 중복 후보 그룹 (같은 성격의 효과가 2건 이상이면 중복 확인 대상)
OVERLAP_GROUPS: dict[str, tuple[str, ...]] = {
    "생산·조업 효과": ("생산성", "생산차질", "조업", "가동률"),
    "품질·검사 비용": ("클레임", "재검사", "품질", "불량"),
    "정비·보전 비용": ("정비", "보전", "수선"),
    "인력·물류 효율": ("인력", "물류", "운송"),
    "에너지 비용": ("에너지", "연료", "전력"),
}


@dataclass
class Comparison:
    """룰이 사용한 값 비교 1건"""

    label: str
    left_label: str
    left_value: float | None
    right_label: str
    right_value: float | None
    unit: str = "억원"
    verdict: str = ""

    @property
    def difference(self) -> float | None:
        if self.left_value is None or self.right_value is None:
            return None
        return round(self.left_value - self.right_value, 4)

    def as_record(self) -> dict:
        diff = self.difference
        base = self.right_value or 0
        ratio = f"{abs(diff) / base * 100:.1f}%" if diff and base else "-"
        return {
            "비교": self.label,
            self.left_label: extractor.display_value(self.left_value),
            self.right_label: extractor.display_value(self.right_value),
            "차이": extractor.display_value(diff),
            "차이율": ratio,
            "판정": self.verdict,
        }


@dataclass
class RuleResult:
    rule_id: str
    name: str
    criteria: str
    grade: str
    message: str
    evidence: list[str] = field(default_factory=list)  # 계산식·확인 경로
    sources: list[str] = field(default_factory=list)  # 출처 목록
    comparisons: list[Comparison] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # 자료 품질 메모

    @property
    def is_normal(self) -> bool:
        return self.grade == config.GRADE_NORMAL


@dataclass
class ValidationReport:
    dir_name: str
    results: list[RuleResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def get(self, rule_id: str) -> RuleResult | None:
        return next((r for r in self.results if r.rule_id == rule_id), None)

    @property
    def worst_grade(self) -> str:
        if not self.results:
            return config.GRADE_CHECK
        return max(
            (r.grade for r in self.results),
            key=lambda g: config.GRADE_ORDER.get(g, 0),
        )

    def count_of(self, grade: str) -> int:
        return sum(1 for r in self.results if r.grade == grade)


# ----------------------------------------------------------------------
# 내부 유틸
# ----------------------------------------------------------------------
def _rule_meta(rule_id: str) -> dict:
    return next(r for r in config.RULES if r["id"] == rule_id)


def _numeric(parsed: ParsedValue | None) -> float | None:
    if parsed is None or not isinstance(parsed.value, (int, float)):
        return None
    return float(parsed.value)


def _matches(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    tolerance = max(ABS_TOLERANCE, abs(right) * REL_TOLERANCE)
    return abs(left - right) <= tolerance


def _sum_items(items: list[ParsedValue]) -> tuple[float | None, str]:
    """세부 항목 합계와 계산식을 만든다. 값이 없는 항목은 합계에서 제외한다."""
    numbers = [(i.label, float(i.value)) for i in items if isinstance(i.value, (int, float))]
    if not numbers:
        return None, "합산 가능한 항목이 없습니다."
    total = round(sum(value for _, value in numbers), 4)
    formula = " + ".join(format_number(value) for _, value in numbers)
    return total, f"{formula} = {format_number(total)}"


# ----------------------------------------------------------------------
# R-01 투자비 정합성
# ----------------------------------------------------------------------
def _rule_capex(result: ExtractionResult) -> RuleResult:
    meta = _rule_meta("R-01")
    rule = RuleResult(meta["id"], meta["name"], meta["criteria"], config.GRADE_NORMAL, "")

    pdf = result.pdf
    plan = pdf.get("계획서 총투자비", "총투자비") if pdf else None
    plan_total = _numeric(plan)
    detail_total, formula = _sum_items(pdf.capex_items if pdf else [])
    econ_capex = result.economics.get("경제성 적용 투자비")

    if plan_total is None or detail_total is None:
        rule.grade = config.GRADE_CHECK
        rule.message = "총투자비 또는 투자비 내역을 확인할 수 없어 정합성 판정 불가"
        rule.evidence.append(formula if detail_total is None else "계획서 총투자비 미확인")
        return rule

    main = Comparison(
        label="계획서 총투자비 vs 내역 합계",
        left_label="내역 합계",
        left_value=detail_total,
        right_label="계획서 총투자비",
        right_value=plan_total,
    )
    main.verdict = "일치" if _matches(detail_total, plan_total) else "불일치"
    rule.comparisons.append(main)
    rule.evidence.append(f"투자비 내역 합계: {formula}")
    if plan:
        rule.sources.append(f"계획서 총투자비 {format_number(plan_total)}억원 · {plan.source}")
    if pdf and pdf.capex_items:
        rule.sources.append(f"투자비 구성 {len(pdf.capex_items)}개 항목 · {pdf.capex_items[0].source}")

    # 부가 비교: 경제성 검토서가 적용한 투자비
    econ_value = _numeric(econ_capex)
    if econ_value is not None:
        sub = Comparison(
            label="계획서 총투자비 vs 경제성 적용 투자비",
            left_label="경제성 적용 투자비",
            left_value=econ_value,
            right_label="계획서 총투자비",
            right_value=plan_total,
        )
        sub.verdict = "일치" if _matches(econ_value, plan_total) else "불일치"
        rule.comparisons.append(sub)
        rule.sources.append(
            f"경제성 적용 투자비 {format_number(econ_value)}억원 · {econ_capex.source}"
        )

    mismatched = [c for c in rule.comparisons if c.verdict == "불일치"]
    if mismatched:
        rule.grade = meta["fail_grade"]
        details = "; ".join(
            f"{c.left_label} {format_number(c.left_value)} ≠ 계획서 {format_number(c.right_value)}"
            f" (차이 {format_number(c.difference)})"
            for c in mismatched
        )
        rule.message = f"투자비가 자료 간 불일치 — {details}"
    else:
        rule.message = (
            f"계획서 총투자비 {format_number(plan_total)}억원과 내역 합계가 일치"
        )

    # 자료 품질 메모: Excel 내역표 항목 수 부족
    if result.capex_table and pdf:
        excel_count = len(result.capex_table.items)
        pdf_count = len(pdf.capex_items)
        if excel_count < pdf_count:
            rule.notes.append(
                f"{result.capex_table.file_name} 의 항목 행은 {excel_count}건으로 "
                f"투자계획서 기재 {pdf_count}건보다 적습니다(합계·차이 행이 항목 행 자리를 차지). "
                "합계 비교 기준은 투자계획서 기재 항목을 사용했습니다."
            )

    return rule


# ----------------------------------------------------------------------
# R-02 경제성 지표 존재
# ----------------------------------------------------------------------
def _rule_economics(result: ExtractionResult) -> RuleResult:
    meta = _rule_meta("R-02")
    rule = RuleResult(meta["id"], meta["name"], meta["criteria"], config.GRADE_NORMAL, "")

    missing: list[str] = []
    for name in REQUIRED_ECONOMICS:
        item = result.get(name)
        if item is None or item.is_missing:
            missing.append(name)
            if item is not None:
                rule.evidence.append(f"{name}: {item.evidence}")
        else:
            rule.sources.append(
                f"{name} {item.display_value}{item.unit} · {item.source_file} · {item.source_locator}"
            )

    if missing:
        rule.grade = meta["fail_grade"]
        rule.message = (
            f"경제성 지표 {len(missing)}건 미확인 — {', '.join(missing)} "
            f"(확인 {len(REQUIRED_ECONOMICS) - len(missing)}/{len(REQUIRED_ECONOMICS)}건)"
        )
    else:
        rule.message = f"필수 경제성 지표 {len(REQUIRED_ECONOMICS)}건 모두 확인"

    return rule


# ----------------------------------------------------------------------
# R-03 기대효과 정합성
# ----------------------------------------------------------------------
def _rule_effect(result: ExtractionResult) -> RuleResult:
    meta = _rule_meta("R-03")
    rule = RuleResult(meta["id"], meta["name"], meta["criteria"], config.GRADE_NORMAL, "")

    pdf = result.pdf
    plan = pdf.get("계획서 기재 연간효과", "연간 기대효과") if pdf else None
    plan_value = _numeric(plan)
    detail_total, formula = _sum_items(pdf.effect_items if pdf else [])

    if plan_value is None or detail_total is None:
        rule.grade = config.GRADE_CHECK
        rule.message = "기대효과 기재값 또는 세부 항목을 확인할 수 없어 정합성 판정 불가"
        rule.evidence.append(formula if detail_total is None else "계획서 기재 효과 미확인")
        return rule

    comparison = Comparison(
        label="계획서 기재 효과 vs 세부효과 합계",
        left_label="세부효과 합계",
        left_value=detail_total,
        right_label="계획서 기재 효과",
        right_value=plan_value,
        unit="억원/년",
    )
    comparison.verdict = "일치" if _matches(detail_total, plan_value) else "불일치"
    rule.comparisons.append(comparison)
    rule.evidence.append(f"세부효과 합계: {formula}")
    if plan:
        rule.sources.append(
            f"계획서 기재 연간효과 {format_number(plan_value)}억원/년 · {plan.source}"
        )
    if pdf and pdf.effect_items:
        rule.sources.append(
            f"기대효과 {len(pdf.effect_items)}개 항목 · {pdf.effect_items[0].source}"
        )

    if comparison.verdict == "불일치":
        rule.grade = meta["fail_grade"]
        rule.message = (
            f"기대효과 합계 불일치 — 세부효과 {format_number(detail_total)} ≠ "
            f"계획서 기재 {format_number(plan_value)} (차이 {format_number(comparison.difference)})"
        )
    else:
        rule.message = (
            f"계획서 기재 연간효과 {format_number(plan_value)}억원/년과 세부효과 합계가 일치"
        )

    # 자료 품질 메모: Excel 산출금액이 수식이라 합계 대조 불가
    if result.effect_table and result.effect_table.notes:
        rule.notes.append(
            f"{result.effect_table.file_name} 의 산출금액 열은 수식이며 계산값이 저장되어 있지 않아 "
            "합계 대조에 사용하지 않았습니다."
        )

    return rule


# ----------------------------------------------------------------------
# R-04 기대효과 중복 가능성
# ----------------------------------------------------------------------
def _rule_overlap(result: ExtractionResult) -> RuleResult:
    meta = _rule_meta("R-04")
    rule = RuleResult(meta["id"], meta["name"], meta["criteria"], config.GRADE_NORMAL, "")

    findings: list[str] = []
    pdf = result.pdf

    # (1) 효과 반영 시점 vs 가동 예정 시점
    start_year = _numeric(pdf.get("가동 예정")) if pdf else None
    cashflow = result.cashflow
    first_effect = cashflow.first_effect_year if cashflow else None

    if start_year is not None and first_effect is not None:
        rule.sources.append(f"가동 예정 {int(start_year)}년 · {pdf.get('가동 예정').source}")
        rule.sources.append(
            f"영업현금효과 최초 발생 {first_effect}년 · {cashflow.source_of(first_effect)}"
        )
        if first_effect < int(start_year):
            findings.append(
                f"가동 예정은 {int(start_year)}년이나 현금흐름에는 {first_effect}년부터 "
                "효과가 반영되어 있습니다."
            )
            rule.evidence.append(
                f"효과 반영 시점 {first_effect}년 < 가동 예정 {int(start_year)}년"
            )
        else:
            rule.evidence.append(
                f"효과 반영 시점 {first_effect}년 ≥ 가동 예정 {int(start_year)}년 (시점 정합)"
            )
    else:
        rule.evidence.append("가동 예정 또는 효과 반영 시점을 확인할 수 없어 시점 대조를 생략했습니다.")

    # (2) 효과 항목 간 중복 가능성 (성격이 같은 항목이 2건 이상)
    labels = [item.label for item in (pdf.effect_items if pdf else [])]
    for group_name, keywords in OVERLAP_GROUPS.items():
        hits = [label for label in labels if any(k in label for k in keywords)]
        if len(hits) >= 2:
            findings.append(
                f"{group_name} 범주에 '{', '.join(hits)}' 항목이 함께 계상되어 효과 범위가 "
                "중복될 가능성이 있습니다."
            )
            rule.evidence.append(f"{group_name}: {len(hits)}건 ({', '.join(hits)})")

    if labels:
        rule.sources.append(f"기대효과 항목 {len(labels)}건 · {pdf.effect_items[0].source}")

    if findings:
        rule.grade = meta["fail_grade"]
        rule.message = " ".join(findings)
        rule.notes.append(
            "중복 가능성은 항목명의 성격과 시점 대조로 도출한 확인 대상이며, "
            "중복 여부 자체는 현업 확인이 필요합니다."
        )
    else:
        rule.message = f"효과 항목 {len(labels)}건에서 시점·범위 중복 징후 없음"

    return rule


# ----------------------------------------------------------------------
# 진입점
# ----------------------------------------------------------------------
@st.cache_data(show_spinner="검증 룰을 적용하고 있습니다...")
def evaluate(dir_name: str) -> ValidationReport:
    """프로젝트 1건에 R-01 ~ R-04 를 적용한다."""
    result = extractor.extract(dir_name)
    report = ValidationReport(dir_name=dir_name, errors=list(result.errors))
    report.results = [
        _rule_capex(result),
        _rule_economics(result),
        _rule_effect(result),
        _rule_overlap(result),
    ]
    return report


def worst_grade(dir_name: str) -> str:
    """대시보드 표시용 최고 위험등급"""
    return evaluate(dir_name).worst_grade
