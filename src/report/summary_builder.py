"""투자검토요약 초안 조립 (DESIGN.md 3.1 src/report/summary_builder.py)

구성: 1. 투자개요 / 2. 투자비 검토 / 3. 경제성 검토 / 4. 기대효과 검토 /
      5. 주요 리스크 / 6. 현업 추가 확인사항 / 7. 종합 의견

1~4는 추출값과 룰 판정에서 온 사실이며 `[사실]`,
5~7은 LLM(또는 규칙 기반 템플릿)이 생성한 의견이며 `[AI 의견]`으로 표기한다.
"""

from __future__ import annotations

from src import config, data_loader
from src.llm.client import Analysis
from src.parsers import extractor
from src.validators import rule_engine

FACT = "[사실]"
OPINION = "[AI 의견]"

ECONOMIC_FIELDS = ("NPV", "IRR", "WACC", "회수기간")


def _heading(index: int) -> str:
    """`config.SUMMARY_SECTIONS` 의 제목과 사실/의견 표기를 합쳐 소제목을 만든다."""
    title, kind = config.SUMMARY_SECTIONS[index]
    label = FACT if kind == "사실" else OPINION
    return f"{title} `{label}`"


def _rule_block(report, rule_id: str) -> list[str]:
    rule = report.get(rule_id)
    if rule is None:
        return [f"- {rule_id} 판정 결과가 없습니다."]

    lines = [
        f"- **{rule.rule_id} {rule.name}**: `{rule.grade}` — {rule.message}",
        f"  - 판정 기준: {rule.criteria}",
    ]
    lines += [f"  - 근거: {line}" for line in rule.evidence]
    lines += [f"  - 출처: {line}" for line in rule.sources]
    lines += [f"  - 자료 메모: {line}" for line in rule.notes]
    return lines


def _items_block(items, empty_message: str) -> list[str]:
    if not items:
        return [f"- {empty_message}"]
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. **{item.title}** — {item.detail}")
        if item.basis:
            lines.append(f"   - 근거: {item.basis}")
    return lines


def build(dir_name: str, analysis: Analysis) -> str:
    """투자검토요약 초안 마크다운을 생성한다."""
    project = data_loader.get_project(dir_name)
    extraction = extractor.extract(dir_name)
    report = rule_engine.evaluate(dir_name)

    title = extraction.value_of("투자명")
    label = project.label if project else dir_name

    lines: list[str] = [
        f"# 투자검토요약 (초안) — {title}",
        "",
        f"- 대상 투자건: {label}",
        f"- 최고 위험등급: **{report.worst_grade}**",
        f"- 등급 종합: "
        + ", ".join(
            f"{grade} {report.count_of(grade)}건"
            for grade in (
                config.GRADE_HIGH,
                config.GRADE_CAUTION,
                config.GRADE_CHECK,
                config.GRADE_NORMAL,
            )
        ),
        f"- AI 분석 생성: {analysis.engine} ({analysis.generated_at})",
        "",
        f"> 1~4항은 자료에서 추출·판정한 사실이며, 5~7항은 AI가 생성한 의견입니다. "
        f"자료에 없는 수치는 추정하지 않았고, 투자 승인·부결 판단은 포함하지 않습니다.",
        "",
        "---",
        "",
        f"## {_heading(0)}",
        "",
        "| 항목 | 값 | 단위 | 출처 |",
        "|------|----|------|------|",
    ]

    for item in extraction.fields:
        unit = "-" if item.unit == "-" else item.unit
        source = (
            f"{item.source_file} {item.source_locator}"
            if not item.is_missing
            else "자료에서 확인 불가"
        )
        lines.append(f"| {item.name} | {item.display_value} | {unit} | {source} |")

    if extraction.missing_names:
        lines.append("")
        lines.append(
            f"- 미확인 항목: {', '.join(extraction.missing_names)} "
            "(값을 추정하지 않고 미확인으로 표기)"
        )

    lines += ["", f"## {_heading(1)}", ""]
    lines += _rule_block(report, "R-01")

    lines += ["", f"## {_heading(2)}", ""]
    for name in ECONOMIC_FIELDS:
        item = extraction.get(name)
        if item is None:
            continue
        source = (
            f"{item.source_file} {item.source_locator}"
            if not item.is_missing
            else "자료에서 확인 불가"
        )
        lines.append(f"- {name}: {item.display_value} {item.unit} ({source})")
    lines.append("")
    lines += _rule_block(report, "R-02")

    lines += ["", f"## {_heading(3)}", ""]
    lines += _rule_block(report, "R-03")
    lines.append("")
    lines += _rule_block(report, "R-04")

    lines += ["", f"## {_heading(4)}", ""]
    lines += _items_block(analysis.risks, "검증 결과에서 도출된 리스크가 없습니다.")

    lines += ["", f"## {_heading(5)}", ""]
    lines += _items_block(analysis.additional_checks, "추가 확인이 필요한 항목이 없습니다.")
    if analysis.questions:
        lines += ["", "**현업 질문사항**", ""]
        lines += [f"- {question}" for question in analysis.questions]

    lines += ["", f"## {_heading(6)}", "", analysis.comment or "-"]

    if analysis.warnings:
        lines += ["", "**생성 관련 참고**", ""]
        lines += [f"- {warning}" for warning in analysis.warnings]

    lines += [
        "",
        "---",
        "",
        "본 문서는 AI 검증 결과를 정리한 검토 초안이며, 투자 승인·부결 판단을 포함하지 않습니다. "
        "최종 판단은 담당자가 근거자료를 확인한 후 확정합니다.",
    ]

    return "\n".join(lines)
