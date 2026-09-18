"""4. AI 검증 결과 - 룰별 판정과 등급 배지 (DESIGN.md 2.3)"""

import streamlit as st

from src import config
from src.ui import components
from src.validators import rule_engine

project = components.require_project()

components.page_header("✅ AI 검증 결과", "룰 기반 검증 결과를 등급과 근거와 함께 확인합니다.")

if project is None:
    st.stop()

report = rule_engine.evaluate(project.dir_name)

for error in report.errors:
    st.error(error, icon="🚫")

st.markdown(
    f"**대상 투자건**: {project.label} &nbsp;&nbsp;"
    f"**최고 위험등급**: {components.grade_badge(report.worst_grade)}",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# 등급 종합
# ----------------------------------------------------------------------
components.grade_metric_row(
    {grade: report.count_of(grade) for grade in config.GRADE_ORDER},
    total_label="적용 룰",
    total=len(report.results),
)

st.divider()

# ----------------------------------------------------------------------
# 룰별 검증 결과 카드
# ----------------------------------------------------------------------
for rule in report.results:
    with st.container(border=True):
        components.rule_header(rule.rule_id, rule.name, rule.grade, rule.criteria)

        st.markdown(
            f"{components.fact_label('사실')} &nbsp;**판정**: {rule.message}",
            unsafe_allow_html=True,
        )

        if rule.comparisons:
            st.dataframe(
                [c.as_record() for c in rule.comparisons],
                width="stretch",
                hide_index=True,
            )

        if rule.evidence:
            st.markdown("**근거**")
            for line in rule.evidence:
                st.markdown(
                    f"<div style='font-size:0.86rem;color:#333;'>· {line}</div>",
                    unsafe_allow_html=True,
                )

        if rule.sources:
            with st.expander(f"출처 ({len(rule.sources)}건)"):
                for source in rule.sources:
                    st.markdown(f"- {source}")

        for note in rule.notes:
            st.caption(f"자료 메모: {note}")

st.divider()

# ----------------------------------------------------------------------
# 범례 및 원칙 안내
# ----------------------------------------------------------------------
st.markdown("**등급 범례**")
components.grade_legend()

st.caption(
    "본 화면은 자료 간 정합성과 지표 존재 여부만 판정합니다. "
    "투자 승인·부결 판단은 포함하지 않습니다. (CLAUDE.md 원칙)"
)

st.page_link("pages/5_투자검토_요약.py", label="투자검토 요약 생성", icon="📝")
