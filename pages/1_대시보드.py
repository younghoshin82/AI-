"""1. 대시보드 - 전체 투자건 현황 (DESIGN.md 2.3)"""

import streamlit as st

from src import config, data_loader
from src.parsers import extractor
from src.ui import components
from src.validators import rule_engine

project = components.sidebar_project_selector()

components.page_header("📊 대시보드", "등록된 투자건의 검증 현황을 한눈에 확인합니다.")

projects = data_loader.load_projects()
if not projects:
    st.stop()

reports = {p.dir_name: rule_engine.evaluate(p.dir_name) for p in projects}

# ----------------------------------------------------------------------
# 상단 지표 카드
# ----------------------------------------------------------------------
grades = [report.worst_grade for report in reports.values()]

cols = st.columns(5)
cols[0].metric("전체 투자건", f"{len(projects)}건")
for col, grade in zip(
    cols[1:],
    [config.GRADE_HIGH, config.GRADE_CAUTION, config.GRADE_CHECK, config.GRADE_NORMAL],
):
    col.metric(grade, f"{grades.count(grade)}건")

st.markdown("**등급 범례**")
components.grade_legend()

st.divider()

# ----------------------------------------------------------------------
# 투자건 목록 (행 선택 시 사이드바 선택 상태와 동기화)
# ----------------------------------------------------------------------
st.subheader("투자건 목록")

records = []
for p in projects:
    extraction = extractor.extract(p.dir_name)
    records.append(
        {
            "프로젝트": p.project_id,
            "투자명": extraction.value_of("투자명"),
            "총 투자비(억원)": extraction.value_of("총 투자비"),
            "NPV(억원)": extraction.value_of("NPV"),
            "IRR(%)": extraction.value_of("IRR"),
            "최고 위험등급": reports[p.dir_name].worst_grade,
            "케이스": p.case_label,
            "자료": f"{len(p.input_files)}건",
        }
    )

options = [p.dir_name for p in projects]

event = st.dataframe(
    records,
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="dashboard_table",
)

rows = event.selection["rows"] if event and "selection" in event else []
if rows and options[rows[0]] != st.session_state.get("selected_project"):
    st.session_state["selected_project"] = options[rows[0]]
    st.session_state.pop("project_selectbox", None)
    st.rerun()

st.caption("표의 행을 클릭하면 해당 투자건이 선택되고 모든 화면에 반영됩니다.")

# ----------------------------------------------------------------------
# 선택된 투자건 요약
# ----------------------------------------------------------------------
if project is None:
    st.stop()

st.divider()
st.subheader(f"선택된 투자건 · {project.label}")

left, right = st.columns([1, 2])

with left:
    st.markdown("**검증 등급 현황**")
    for rule in reports[project.dir_name].results:
        st.markdown(
            f"{components.grade_badge(rule.grade)} &nbsp;{rule.rule_id} {rule.name}",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='color:#666;font-size:0.78rem;margin:-6px 0 8px 4px;'>{rule.message}</div>",
            unsafe_allow_html=True,
        )

with right:
    st.markdown("**제출 자료 목록**")
    components.file_list_table(project)

st.page_link("pages/4_AI_검증_결과.py", label="AI 검증 결과 보기", icon="✅")
