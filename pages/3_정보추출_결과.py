"""3. 정보추출 결과 - 필수 7항목과 출처 표시 (DESIGN.md 2.3)"""

import streamlit as st

from src.parsers import extractor
from src.ui import components

project = components.require_project()

components.page_header(
    "🔍 정보추출 결과", "PDF·엑셀 자료에서 추출한 필수 항목과 출처를 확인합니다."
)

if project is None:
    st.stop()

result = extractor.extract(project.dir_name)

st.markdown(
    f"**대상 투자건**: {project.label} &nbsp;&nbsp; {components.fact_label('사실')} "
    "&nbsp;<span style='color:#666;font-size:0.85rem;'>모든 값은 실제 제출 파일에서 파싱한 결과입니다.</span>",
    unsafe_allow_html=True,
)

for error in result.errors:
    st.error(error, icon="🚫")

# ----------------------------------------------------------------------
# 필수 7항목 추출 표 (값 + 단위 + 출처 파일 + 시트/페이지)
# ----------------------------------------------------------------------
st.subheader("필수 추출 항목")

st.dataframe(
    extractor.field_records(result),
    width="stretch",
    hide_index=True,
    column_config={
        "항목": st.column_config.TextColumn(width="small"),
        "값": st.column_config.TextColumn(width="medium"),
        "단위": st.column_config.TextColumn(width="small"),
        "출처 파일": st.column_config.TextColumn(width="medium"),
        "위치": st.column_config.TextColumn("시트/페이지", width="small"),
        "상태": st.column_config.TextColumn(width="small"),
    },
)

# ----------------------------------------------------------------------
# 미확인 항목 (CLAUDE.md: 자료에 없는 수치는 추정하지 않는다)
# ----------------------------------------------------------------------
missing = [f for f in result.fields if f.is_missing]
if missing:
    st.warning(
        f"다음 {len(missing)}개 항목을 자료에서 확인할 수 없습니다: "
        f"**{', '.join(f.name for f in missing)}**\n\n"
        "추정값을 생성하지 않으며, 해당 항목은 검증 시 `확인필요` 등급으로 처리됩니다.",
        icon="⚠️",
    )
    with st.expander("미확인 항목의 확인 경로", expanded=True):
        for item in missing:
            st.markdown(f"- **{item.name}** — {item.evidence}")
else:
    st.success("필수 7개 항목을 모두 추출했습니다.", icon="✅")

# ----------------------------------------------------------------------
# 근거 및 단위 처리 메모
# ----------------------------------------------------------------------
with st.expander("항목별 근거 원문"):
    for item in result.fields:
        if item.is_missing:
            continue
        st.markdown(
            f"**{item.name}** = {item.display_value} {item.unit} &nbsp; "
            f"<span style='color:#888;font-size:0.8rem;'>({item.source_file} · {item.source_locator})</span>",
            unsafe_allow_html=True,
        )
        if item.evidence:
            st.code(item.evidence, language="text")
        if item.note:
            st.caption(f"처리 메모: {item.note}")

# ----------------------------------------------------------------------
# 교차 검증 (채택 출처 vs 대조 출처)
# ----------------------------------------------------------------------
st.subheader("출처 간 교차 검증")

if result.cross_checks:
    mismatches = [c for c in result.cross_checks if c["판정"] == "불일치"]
    if mismatches:
        st.warning(
            f"자료 간 값이 다른 항목이 {len(mismatches)}건 있습니다. "
            "정합성 판정은 '4. AI 검증 결과'에서 수행합니다.",
            icon="⚠️",
        )
    st.dataframe(result.cross_checks, width="stretch", hide_index=True)
    st.caption("동일 항목을 서로 다른 문서에서 읽어 비교한 결과입니다. 값 자체는 보정하지 않습니다.")
else:
    st.caption("대조할 출처가 없습니다.")

st.divider()

# ----------------------------------------------------------------------
# 원본 상세
# ----------------------------------------------------------------------
st.subheader("원본 상세")

pdf = result.pdf

with st.expander("투자비 구성 상세"):
    if pdf and pdf.capex_items:
        st.markdown(f"**투자계획서 기재** · {pdf.file_name} · p.2")
        st.dataframe(
            [
                {
                    "항목": i.label,
                    "금액": extractor.display_value(i.value),
                    "단위": i.unit or "억원",
                    "출처": str(i.source),
                }
                for i in pdf.capex_items
            ],
            width="stretch",
            hide_index=True,
        )

    if result.capex_table and result.capex_table.items:
        st.markdown(f"**투자비내역 엑셀** · {result.capex_table.file_name}")
        st.dataframe(
            [
                {
                    "항목": i.label,
                    "금액": extractor.display_value(i.value),
                    "단위": i.unit or "억원",
                    "출처": str(i.source),
                    "비고": i.missing_marker or "",
                }
                for i in result.capex_table.items
            ],
            width="stretch",
            hide_index=True,
        )

with st.expander("기대효과 세부 항목"):
    if pdf and pdf.effect_items:
        st.markdown(f"**투자계획서 기재** · {pdf.file_name} · p.2")
        st.dataframe(
            [
                {
                    "효과 항목": i.label,
                    "연간 효과": extractor.display_value(i.value),
                    "단위": i.unit or "억원/년",
                    "출처": str(i.source),
                }
                for i in pdf.effect_items
            ],
            width="stretch",
            hide_index=True,
        )

    if result.effect_table and result.effect_table.items:
        st.markdown(f"**기대효과산출 엑셀** · {result.effect_table.file_name}")
        st.dataframe(
            [
                {
                    "효과 항목": i.label,
                    "산출금액": extractor.display_value(i.value),
                    "출처": str(i.source),
                    "비고": i.missing_marker or "",
                }
                for i in result.effect_table.items
            ],
            width="stretch",
            hide_index=True,
        )

with st.expander("경제성 지표 원본 (경제성검토 엑셀)"):
    rows = [
        {
            "항목": label,
            "입력값": extractor.display_value(parsed.value),
            "단위": parsed.unit or "",
            "출처": str(parsed.source),
            "비고": parsed.missing_marker or "",
        }
        for label, parsed in result.economics.items()
        if not label.startswith("__")
    ]
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("경제성검토 파일에서 읽은 값이 없습니다.")

if result.notes:
    with st.expander(f"파싱 특이사항 ({len(result.notes)}건)"):
        for note in result.notes:
            st.markdown(f"- {note}")
        st.caption(
            "수식 셀의 계산값이 파일에 저장되어 있지 않은 경우 값을 임의로 계산해 채우지 않습니다."
        )

with st.expander("투자계획서 원문 텍스트"):
    if pdf:
        for page_no, text in pdf.page_texts.items():
            st.markdown(f"**p.{page_no}**")
            st.code(text or "(텍스트 없음)", language="text")

with st.expander("추출 대상 파일"):
    components.file_list_table(project, input_only=True)

st.page_link("pages/4_AI_검증_결과.py", label="AI 검증 결과 보기", icon="✅")
