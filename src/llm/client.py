"""Claude API 호출 및 오프라인 폴백 (DESIGN.md 3.1 src/llm/client.py)

API 키가 설정되어 있으면 Claude 로 분석을 생성하고, 없거나 호출이 실패하면
룰 판정 결과에서 결정적으로 조립한 '규칙 기반 템플릿'으로 대체한다.
어느 경로로 생성했는지는 Analysis.engine 에 담아 화면에 그대로 표시한다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import streamlit as st

from src import config
from src.llm import prompts
from src.parsers import extractor
from src.validators import rule_engine

MODEL_ID = "claude-opus-5"
MAX_TOKENS = 16000

TEMPLATE_ENGINE = "규칙 기반 템플릿 (Claude API 미사용)"


@dataclass
class AnalysisItem:
    title: str
    detail: str
    basis: str


@dataclass
class Analysis:
    risks: list[AnalysisItem] = field(default_factory=list)
    additional_checks: list[AnalysisItem] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    comment: str = ""
    engine: str = TEMPLATE_ENGINE
    is_llm: bool = False
    generated_at: str = ""
    warnings: list[str] = field(default_factory=list)


def _secret(name: str) -> str | None:
    """Streamlit Secrets 에서 값을 읽는다 (secrets.toml 이 없으면 None).

    Streamlit Cloud 는 앱 설정의 Secrets 로 키를 전달하므로 환경변수와 함께 확인한다.
    """
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value) if value else None


def resolve_api_key() -> str | None:
    """환경변수 또는 Streamlit Secrets 에서 API 키를 찾는다."""
    return (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or _secret("ANTHROPIC_API_KEY")
    )


def api_key_available() -> bool:
    """Claude API 자격 증명이 있는지 확인한다.

    환경변수, Streamlit Secrets, 그리고 `ant auth login` 이 저장하는 프로필
    디렉터리를 확인한다. SDK 클라이언트는 자격 증명이 없어도 생성되고 호출
    시점에 실패하므로, 생성 성공 여부로는 판단할 수 없다. 이 판단이 틀린
    경우에도 호출 실패를 잡아 규칙 기반 결과로 대체한다.
    """
    if resolve_api_key():
        return True
    return (Path.home() / ".config" / "anthropic").exists()


# ----------------------------------------------------------------------
# 규칙 기반 폴백: 룰 판정 결과에서 결정적으로 조립한다 (추정 없음)
# ----------------------------------------------------------------------
def _template_analysis(extraction, report) -> Analysis:
    analysis = Analysis(engine=TEMPLATE_ENGINE, is_llm=False)

    # 리스크: 정상이 아닌 룰 + 투자계획서에 현업이 제시한 리스크
    for rule in report.results:
        if rule.is_normal:
            continue
        analysis.risks.append(
            AnalysisItem(
                title=f"{rule.name} {rule.grade}",
                detail=rule.message,
                basis=f"{rule.rule_id} 판정 결과"
                + (f" · {rule.evidence[0]}" if rule.evidence else ""),
            )
        )

    if extraction.pdf:
        for page_no, text in extraction.pdf.page_texts.items():
            in_section = False
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith(("5.", "6.")) and "리스크" in stripped:
                    in_section = True
                    continue
                if in_section and stripped.startswith("- "):
                    analysis.risks.append(
                        AnalysisItem(
                            title="현업 제시 리스크",
                            detail=stripped[2:].strip(),
                            basis=f"{extraction.pdf.file_name} p.{page_no} 기재",
                        )
                    )
                elif in_section and not stripped:
                    continue
                elif in_section:
                    in_section = False

    # 추가확인사항: 미확인 항목 + 교차검증 불일치
    for item in extraction.fields:
        if item.is_missing:
            analysis.additional_checks.append(
                AnalysisItem(
                    title=f"{item.name} 미확인",
                    detail=f"{item.name}을 자료에서 확인할 수 없어 산출 근거와 값을 추가로 받아야 함.",
                    basis=item.evidence,
                )
            )

    for check in extraction.cross_checks:
        if check["판정"] == "불일치":
            analysis.additional_checks.append(
                AnalysisItem(
                    title=f"{check['항목']} 자료 간 불일치",
                    detail=f"{check['채택 값']}({check['채택 출처']})와 "
                    f"{check['대조 값']}({check['대조 출처']})가 달라 기준 금액 확정이 필요함.",
                    basis="출처 간 교차검증",
                )
            )

    # 현업 질문사항: 판정 결과에 연동된 질문
    questions: list[str] = []
    capex = report.get("R-01")
    if capex and not capex.is_normal:
        questions.append("자료별 투자비 금액이 다른데, 최종 기준이 되는 총투자비는 어느 자료의 금액인가?")
    economics = report.get("R-02")
    if economics and not economics.is_normal:
        questions.append("경제성 검토서에서 확인되지 않는 지표는 산출 예정인가, 산출 대상이 아닌가?")
    effect = report.get("R-03")
    if effect and not effect.is_normal:
        questions.append("세부 기대효과 합계와 계획서 기재 효과의 차이는 어떤 항목에서 발생한 것인가?")
    overlap = report.get("R-04")
    if overlap and not overlap.is_normal:
        questions.append("기대효과 항목 간 중복 계상 여부와 효과 반영 시점의 근거는 무엇인가?")
    questions.append("기대효과의 기준 물량·단가·적용률 산출 근거 자료를 제시할 수 있는가?")
    analysis.questions = questions

    # 투자검토 코멘트
    grade_summary = ", ".join(
        f"{grade} {report.count_of(grade)}건"
        for grade in (
            config.GRADE_HIGH,
            config.GRADE_CAUTION,
            config.GRADE_CHECK,
            config.GRADE_NORMAL,
        )
        if report.count_of(grade)
    )
    analysis.comment = (
        f"검증 룰 {len(report.results)}건 적용 결과는 {grade_summary}이며, "
        f"최고 위험등급은 {report.worst_grade}임. "
        + (
            f"우선 확인이 필요한 항목은 "
            f"{', '.join(r.rule_id + ' ' + r.name for r in report.results if not r.is_normal)}임. "
            if any(not r.is_normal for r in report.results)
            else "자료 간 수치는 모두 일치함. "
        )
        + f"미확인 항목은 {len(extraction.missing_names)}건이며, 해당 값은 추정하지 않았음. "
        "본 코멘트는 검토 초안이며 최종 판단은 담당자가 근거자료를 확인한 후 확정함."
    )

    analysis.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return analysis


# ----------------------------------------------------------------------
# Claude API 호출
# ----------------------------------------------------------------------
def _llm_analysis(extraction, report) -> Analysis:
    """Claude 로 분석을 생성한다. 실패 시 예외 대신 경고를 담은 폴백을 돌려준다."""
    import anthropic

    fallback = _template_analysis(extraction, report)

    try:
        api_key = resolve_api_key()
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=prompts.SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"format": prompts.ANALYSIS_SCHEMA},
            messages=[
                {
                    "role": "user",
                    "content": prompts.build_user_prompt(extraction, report),
                }
            ],
        )
    except anthropic.NotFoundError as exc:
        fallback.warnings.append(f"모델을 찾을 수 없습니다 ({MODEL_ID}): {exc}")
        return fallback
    except anthropic.AuthenticationError:
        fallback.warnings.append("Claude API 인증에 실패했습니다. API 키를 확인하세요.")
        return fallback
    except anthropic.RateLimitError as exc:
        fallback.warnings.append(f"Claude API 호출이 제한되었습니다: {exc}")
        return fallback
    except anthropic.BadRequestError as exc:
        fallback.warnings.append(f"Claude API 요청이 거부되었습니다: {exc}")
        return fallback
    except anthropic.APIStatusError as exc:
        fallback.warnings.append(f"Claude API 오류({exc.status_code}): {exc}")
        return fallback
    except anthropic.APIConnectionError:
        fallback.warnings.append("Claude API에 연결할 수 없습니다. 네트워크를 확인하세요.")
        return fallback

    if response.stop_reason == "refusal":
        fallback.warnings.append("모델이 응답을 거부했습니다. 규칙 기반 결과로 대체했습니다.")
        return fallback

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fallback.warnings.append(f"모델 응답을 JSON으로 해석할 수 없습니다: {exc}")
        return fallback

    def items(key: str) -> list[AnalysisItem]:
        return [
            AnalysisItem(
                title=str(row.get("title", "")).strip(),
                detail=str(row.get("detail", "")).strip(),
                basis=str(row.get("basis", "")).strip(),
            )
            for row in data.get(key, [])
            if isinstance(row, dict)
        ]

    return Analysis(
        risks=items("risks"),
        additional_checks=items("additional_checks"),
        questions=[str(q).strip() for q in data.get("questions", []) if str(q).strip()],
        comment=str(data.get("comment", "")).strip(),
        engine=f"Claude API · {MODEL_ID}",
        is_llm=True,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


@st.cache_data(show_spinner="AI 분석을 생성하고 있습니다...")
def analyze(dir_name: str, use_llm: bool = True) -> Analysis:
    """프로젝트 1건의 AI 분석(리스크·추가확인·질문·코멘트)을 생성한다."""
    extraction = extractor.extract(dir_name)
    report = rule_engine.evaluate(dir_name)

    if use_llm and api_key_available():
        return _llm_analysis(extraction, report)

    analysis = _template_analysis(extraction, report)
    if use_llm:
        analysis.warnings.append(
            "Claude API 자격 증명을 찾지 못해 규칙 기반 템플릿으로 생성했습니다. "
            "ANTHROPIC_API_KEY 환경변수, Streamlit Secrets, 또는 `ant auth login` 프로필이 필요합니다."
        )
    return analysis
