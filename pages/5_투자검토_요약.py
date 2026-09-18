"""5. 투자검토 요약 - LLM 분석 및 최종 산출물 (DESIGN.md 2.3)"""

import streamlit as st

from src import config
from src.llm import client
from src.report import exporter, summary_builder
from src.ui import components

project = components.require_project()

components.page_header(
    "📝 투자검토 요약", "검증 결과를 종합해 리스크·확인사항과 투자검토요약 초안을 생성합니다."
)

if project is None:
    st.stop()

state_key = f"use_llm_{project.dir_name}"
use_llm = st.session_state.get(state_key, False)
key_available = client.api_key_available()

# ----------------------------------------------------------------------
# 생성 방식 선택
# ----------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    if st.button(
        "Claude API로 AI 분석 생성",
        type="primary",
        disabled=not key_available,
        width="stretch",
    ):
        st.session_state[state_key] = True
        client.analyze.clear()
        st.rerun()

    if st.button("규칙 기반으로 다시 생성", width="stretch"):
        st.session_state[state_key] = False
        client.analyze.clear()
        st.rerun()

with right:
    if key_available:
        st.success(f"Claude API 사용 가능 · 모델 `{client.MODEL_ID}`", icon="🔑")
    else:
        st.warning(
            "Claude API 자격 증명이 없어 규칙 기반 템플릿으로 생성합니다.",
            icon="🔒",
        )
        st.caption(
            "로컬에서는 환경변수 `ANTHROPIC_API_KEY` 를, Streamlit Cloud 에서는 "
            "앱 설정의 Secrets 에 같은 이름의 키를 등록하면 LLM 분석으로 전환됩니다."
        )

analysis = client.analyze(project.dir_name, use_llm=use_llm)

for warning in analysis.warnings:
    st.info(warning, icon="ℹ️")

st.markdown(
    f"**생성 엔진**: {analysis.engine} &nbsp;·&nbsp; **생성 시각**: {analysis.generated_at}",
    unsafe_allow_html=True,
)

st.divider()

# ----------------------------------------------------------------------
# AI 분석 결과 (리스크 / 추가확인사항 / 현업 질문사항 / 코멘트)
# ----------------------------------------------------------------------
st.subheader("AI 분석")
st.markdown(
    f"{components.fact_label('AI 의견')} &nbsp;"
    "<span style='color:#666;font-size:0.85rem;'>아래 4개 탭의 내용은 모두 AI가 생성한 의견이며, "
    "각 항목에 근거를 함께 표시합니다. 투자 승인·부결 판단은 포함하지 않습니다.</span>",
    unsafe_allow_html=True,
)

risk_tab, check_tab, question_tab, comment_tab = st.tabs(
    [
        f"리스크 ({len(analysis.risks)})",
        f"추가확인사항 ({len(analysis.additional_checks)})",
        f"현업 질문사항 ({len(analysis.questions)})",
        "투자검토 코멘트",
    ]
)


def render_items(items, empty_message: str) -> None:
    if not items:
        st.caption(empty_message)
        return
    for index, item in enumerate(items, start=1):
        with st.container(border=True):
            st.markdown(
                f"{components.fact_label('AI 의견')} &nbsp;**{index}. {item.title}**",
                unsafe_allow_html=True,
            )
            st.markdown(item.detail)
            if item.basis:
                st.caption(f"근거: {item.basis}")


with risk_tab:
    render_items(analysis.risks, "검증 결과에서 도출된 리스크가 없습니다.")

with check_tab:
    render_items(analysis.additional_checks, "추가 확인이 필요한 항목이 없습니다.")

with question_tab:
    if analysis.questions:
        for index, question in enumerate(analysis.questions, start=1):
            st.markdown(f"{index}. {question}")
        st.caption("현업(사업 주관 부서)에 그대로 전달할 수 있는 질문 문장입니다.")
    else:
        st.caption("생성된 질문사항이 없습니다.")

with comment_tab:
    st.markdown(
        f"{components.fact_label('AI 의견')} &nbsp;**투자검토 코멘트**",
        unsafe_allow_html=True,
    )
    st.markdown(analysis.comment or "-")

st.divider()

# ----------------------------------------------------------------------
# 투자검토요약 초안 (7개 항목)
# ----------------------------------------------------------------------
st.subheader("투자검토요약 초안")

# 목차 (섹션 제목과 사실/의견 구분)
toc = "".join(
    f"<div style='margin:2px 0;'>{title} "
    f"{components.fact_label('사실' if kind == '사실' else 'AI 의견')}</div>"
    for title, kind in config.SUMMARY_SECTIONS
)
st.markdown(
    f"<div {components.NO_TRANSLATE} style='font-size:0.9rem;'>"
    f"<b>목차</b>{toc}</div>",
    unsafe_allow_html=True,
)
st.write("")

draft = summary_builder.build(project.dir_name, analysis)
st.session_state["summary_markdown"] = draft

with st.container(border=True):
    st.markdown(draft)

with st.expander("마크다운 원문 보기"):
    st.code(draft, language="markdown")

# ----------------------------------------------------------------------
# 다운로드 (마크다운 / 텍스트 / PDF)
# ----------------------------------------------------------------------
st.subheader("다운로드")

file_stem = f"투자검토요약_{project.project_id}"
pdf_bytes, pdf_error = exporter.to_pdf_bytes(draft)

col1, col2, col3 = st.columns(3)
with col1:
    st.download_button(
        "마크다운 문서 (.md)",
        data=exporter.to_markdown_bytes(draft),
        file_name=f"{file_stem}.md",
        mime="text/markdown",
        width="stretch",
    )
with col2:
    st.download_button(
        "텍스트 문서 (.txt)",
        data=exporter.to_text_bytes(draft),
        file_name=f"{file_stem}.txt",
        mime="text/plain",
        width="stretch",
    )
with col3:
    if pdf_bytes:
        st.download_button(
            "PDF 문서 (.pdf)",
            data=pdf_bytes,
            file_name=f"{file_stem}.pdf",
            mime="application/pdf",
            type="primary",
            width="stretch",
        )
    else:
        st.button("PDF 생성 불가", disabled=True, width="stretch")

if pdf_error:
    st.warning(pdf_error, icon="⚠️")

st.caption(
    "1~4항은 자료에서 추출·판정한 사실이고, 5~7항은 `[AI 의견]`입니다. "
    "자료에 없는 수치는 추정하지 않으며, 투자 승인·부결 판단은 포함하지 않습니다. (CLAUDE.md 원칙)"
)
