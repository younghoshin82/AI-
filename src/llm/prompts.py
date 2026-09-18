"""CLAUDE.md 원칙을 주입한 LLM 프롬프트 (DESIGN.md 3.1 src/llm/prompts.py)"""

from __future__ import annotations

from src import config
from src.parsers.extractor import ExtractionResult
from src.validators.rule_engine import ValidationReport

SYSTEM_PROMPT = f"""당신은 철강회사 투자기획팀의 심사 담당자입니다.
제출된 투자계획서와 첨부 자료의 추출 결과 및 룰 기반 검증 결과를 받아,
심사 담당자가 확인해야 할 사항을 정리합니다.

반드시 지켜야 할 원칙:
1. 자료에 없는 수치는 추정하지 않는다. 제공된 값과 검증 결과만 사용하고,
   값이 '{config.NOT_FOUND}'인 항목은 '{config.NOT_FOUND}'으로 다룬다. 새로운 숫자를 만들지 않는다.
2. 사실과 의견을 구분한다. 당신이 작성하는 내용은 모두 '의견'이며,
   각 항목에는 어떤 검증 결과(룰 ID)나 자료 항목에 근거했는지를 basis에 적는다.
3. 투자 승인·부결을 판단하지 않는다. '승인', '부결', '추진 권고', '반대' 같은 표현을 쓰지 않는다.
   확인이 필요한 사항과 그 이유만 제시한다.
4. 모든 항목에 근거를 표시한다. 근거를 댈 수 없는 내용은 작성하지 않는다.

검증 등급 체계: {config.GRADE_HIGH}(중대한 문제 확인) / {config.GRADE_CAUTION}(검토 필요) /
{config.GRADE_CHECK}(자료 부족으로 판단 불가) / {config.GRADE_NORMAL}(특이사항 없음).

작성 지침:
- risks: 이 투자 건에서 확인된 리스크. 검증 등급이 높음·주의·확인필요인 항목을 우선한다.
- additional_checks: 자료만으로 판단할 수 없어 추가 자료·근거가 필요한 사항.
- questions: 현업(사업 주관 부서)에 그대로 전달할 수 있는 질문 문장.
- comment: 투자검토 코멘트. 검증 결과를 종합해 담당자가 유의할 점을 3~5문장으로 서술한다.
- 모든 문장은 한국어 존댓말 없이 보고서 문체(~함, ~필요)로 간결하게 쓴다.
"""

# 구조화 출력 스키마 (output_config.format)
ANALYSIS_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "리스크 제목 (20자 이내)"},
                        "detail": {"type": "string", "description": "리스크 내용 (2문장 이내)"},
                        "basis": {"type": "string", "description": "근거가 된 룰 ID 또는 자료 항목"},
                    },
                    "required": ["title", "detail", "basis"],
                    "additionalProperties": False,
                },
            },
            "additional_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "확인사항 제목 (20자 이내)"},
                        "detail": {"type": "string", "description": "필요한 자료·근거 (2문장 이내)"},
                        "basis": {"type": "string", "description": "근거가 된 룰 ID 또는 자료 항목"},
                    },
                    "required": ["title", "detail", "basis"],
                    "additionalProperties": False,
                },
            },
            "questions": {
                "type": "array",
                "items": {"type": "string", "description": "현업에 전달할 질문 문장"},
            },
            "comment": {"type": "string", "description": "투자검토 코멘트 3~5문장"},
        },
        "required": ["risks", "additional_checks", "questions", "comment"],
        "additionalProperties": False,
    },
}


def build_user_prompt(extraction: ExtractionResult, report: ValidationReport) -> str:
    """추출 결과와 검증 결과를 LLM 입력 텍스트로 정리한다."""
    lines: list[str] = ["# 1. 추출된 주요 정보 (출처 포함)"]
    for item in extraction.fields:
        unit = "" if item.unit == "-" else f" {item.unit}"
        source = (
            f"{item.source_file} {item.source_locator}"
            if not item.is_missing
            else f"확인 경로: {item.evidence}"
        )
        lines.append(f"- {item.name}: {item.display_value}{unit} ({source})")

    lines.append("")
    lines.append("# 2. 룰 기반 검증 결과")
    for rule in report.results:
        lines.append(f"## {rule.rule_id} {rule.name} — 등급 {rule.grade}")
        lines.append(f"- 판정: {rule.message}")
        for evidence in rule.evidence:
            lines.append(f"- 근거: {evidence}")
        for note in rule.notes:
            lines.append(f"- 자료 메모: {note}")

    mismatches = [c for c in extraction.cross_checks if c["판정"] != "일치"]
    if mismatches:
        lines.append("")
        lines.append("# 3. 자료 간 교차검증 결과 (일치하지 않는 항목)")
        for check in mismatches:
            lines.append(
                f"- {check['항목']}: {check['채택 값']} ({check['채택 출처']}) vs "
                f"{check['대조 값']} ({check['대조 출처']}) → {check['판정']}"
            )

    if extraction.pdf:
        lines.append("")
        lines.append("# 4. 투자계획서 원문 (참고)")
        for page_no, text in extraction.pdf.page_texts.items():
            lines.append(f"## p.{page_no}")
            lines.append(text.strip())

    lines.append("")
    lines.append(
        "위 자료만 근거로 리스크(risks), 추가확인사항(additional_checks), "
        "현업 질문사항(questions), 투자검토 코멘트(comment)를 작성하십시오."
    )
    return "\n".join(lines)
