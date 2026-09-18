"""등급 배지, 출처 표기 등 공통 UI 위젯 (DESIGN.md 3.1 src/ui/components.py)"""

from __future__ import annotations

import streamlit as st

from src import config, data_loader
from src.data_loader import Project

# 브라우저(Chrome 등) 자동 번역이 한글 라벨을 다시 번역해 왜곡하지 않도록
# 직접 삽입하는 HTML에는 번역 제외 속성을 붙인다.
NO_TRANSLATE = 'translate="no" class="notranslate" lang="ko"'

PHASE_NOTICE = (
    "추출 항목과 검증 등급은 실제 제출 파일을 파싱·판정한 결과입니다. "
    "리스크·추가확인사항 등 AI 생성 영역은 Phase 4(LLM 연동)에서 채워집니다."
)


def page_header(title: str, description: str) -> None:
    st.title(title)
    st.caption(description)


def phase_notice() -> None:
    """현재 단계에서 실제 판정값과 미구현 영역을 구분해 명시한다."""
    st.info(PHASE_NOTICE, icon="🧩")


def grade_color(grade: str) -> str:
    return config.GRADE_COLORS.get(grade, "#616161")


def grade_badge(grade: str) -> str:
    """등급 색상 배지 HTML을 반환한다 (DESIGN.md 2.3)."""
    color = grade_color(grade)
    return (
        f'<span {NO_TRANSLATE} style="background-color:{color};color:#fff;padding:2px 10px;'
        f'border-radius:12px;font-size:0.85rem;font-weight:600;white-space:nowrap;">'
        f"{grade}</span>"
    )


def render_grade_badge(grade: str, prefix: str = "") -> None:
    st.markdown(f"{prefix}{grade_badge(grade)}", unsafe_allow_html=True)


def rule_header(rule_id: str, name: str, grade: str, criteria: str) -> None:
    """룰 카드 머리글: 등급 색상 띠 + 배지 (DESIGN.md 2.3 등급 시각화)"""
    st.markdown(
        f"""
        <div {NO_TRANSLATE} style="border-left:6px solid {grade_color(grade)};padding:2px 0 2px 12px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-weight:700;font-size:1.02rem;">{rule_id} · {name}</span>
            {grade_badge(grade)}
          </div>
          <div style="color:#777;font-size:0.8rem;margin-top:2px;">판정 기준: {criteria}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def grade_metric_row(counts: dict[str, int], total_label: str | None = None, total: int = 0) -> None:
    """4개 검증 등급 건수를 가로 한 줄에 균등 배치한다.

    st.columns 는 내용 길이에 따라 카드 폭이 흔들려 마지막 항목이 잘려 보이므로,
    CSS Grid 로 같은 너비의 카드를 만들어 배치한다. 좁은 화면에서는 자동 줄바꿈된다.
    """
    cards = []
    if total_label is not None:
        cards.append(
            f"""<div style="flex:1 1 0;min-width:130px;border:1px solid #E0E0E0;border-radius:10px;
                 padding:12px 14px;background:#FAFAFA;">
              <div style="font-size:0.82rem;color:#555;margin-bottom:6px;">{total_label}</div>
              <div style="font-size:1.7rem;font-weight:700;line-height:1.9rem;">{total}
                <span style="font-size:0.9rem;font-weight:400;color:#555;">건</span></div>
            </div>"""
        )

    for grade in (config.GRADE_HIGH, config.GRADE_CAUTION, config.GRADE_CHECK, config.GRADE_NORMAL):
        count = counts.get(grade, 0)
        color = grade_color(grade)
        dim = "" if count else "opacity:0.55;"
        cards.append(
            f"""<div style="flex:1 1 0;min-width:130px;border:1px solid #E0E0E0;border-top:3px solid {color};
                 border-radius:10px;padding:12px 14px;{dim}">
              <div style="margin-bottom:6px;">{grade_badge(grade)}</div>
              <div style="font-size:1.7rem;font-weight:700;line-height:1.9rem;color:{color};">{count}
                <span style="font-size:0.9rem;font-weight:400;color:#555;">건</span></div>
            </div>"""
        )

    st.markdown(
        f"""<div {NO_TRANSLATE} style="display:flex;flex-wrap:wrap;gap:12px;margin:4px 0 12px 0;">
          {"".join(cards)}
        </div>""",
        unsafe_allow_html=True,
    )


def sync_selected_project(dir_name: str | None) -> bool:
    """선택된 투자건을 세션 상태에 반영한다.

    사이드바 selectbox 는 위젯 키(`project_selectbox`)에 저장된 값을 우선하므로,
    표에서 다른 투자건을 고른 경우 해당 위젯 키를 지워 다음 실행에서 새 값으로
    다시 만들어지게 한다. 값이 실제로 바뀌었을 때만 True 를 돌려준다.
    """
    if not dir_name or dir_name == st.session_state.get("selected_project"):
        return False

    st.session_state["selected_project"] = dir_name
    st.session_state.pop("project_selectbox", None)
    return True


def selected_rows(event) -> list[int]:
    """st.dataframe(on_select=...) 반환값에서 선택된 행 번호를 꺼낸다."""
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if not selection:
        return []
    rows = selection["rows"] if "rows" in selection else getattr(selection, "rows", [])
    return list(rows or [])


def grade_legend() -> None:
    """등급 색상 범례"""
    chips = " ".join(
        f"{grade_badge(grade)}<span style='color:#666;font-size:0.78rem;'> {desc}</span>"
        for grade, desc in config.GRADE_DESCRIPTIONS.items()
    )
    st.markdown(f"<div {NO_TRANSLATE}>{chips}</div>", unsafe_allow_html=True)


def fact_label(kind: str) -> str:
    """`[사실]` / `[AI 의견]` 라벨 (CLAUDE.md: AI의 의견과 사실을 구분)."""
    color = "#1565C0" if kind == "사실" else "#6A1B9A"
    return (
        f'<span {NO_TRANSLATE} style="border:1px solid {color};color:{color};padding:1px 8px;'
        f'border-radius:4px;font-size:0.78rem;">[{kind}]</span>'
    )


def sidebar_project_selector() -> Project | None:
    """모든 페이지가 공유하는 사이드바 프로젝트 선택 박스 (DESIGN.md 2.2)."""
    projects = data_loader.load_projects()

    with st.sidebar:
        st.markdown("### 투자건 선택")

        if not projects:
            st.error(f"샘플 데이터를 찾을 수 없습니다.\n\n경로: {config.SAMPLE_PACK_DIR}")
            return None

        options = [p.dir_name for p in projects]
        labels = {p.dir_name: p.label for p in projects}

        current = st.session_state.get("selected_project")
        index = options.index(current) if current in options else 0

        selected = st.selectbox(
            "프로젝트",
            options=options,
            index=index,
            format_func=lambda name: labels[name],
            key="project_selectbox",
            label_visibility="collapsed",
        )
        st.session_state["selected_project"] = selected

        project = data_loader.get_project(selected)
        if project:
            st.caption(
                f"입력 자료 {len(project.input_files)}건 "
                f"· PDF {len(project.pdf_files)}건 / 엑셀 {len(project.excel_files)}건"
            )
            st.session_state["project_files"] = data_loader.files_to_records(project)

        st.divider()
        st.caption("검증 등급")
        for grade, desc in config.GRADE_DESCRIPTIONS.items():
            st.markdown(
                f"<div {NO_TRANSLATE}>{grade_badge(grade)} "
                f"<span style='font-size:0.78rem;color:#666;'>{desc}</span></div>",
                unsafe_allow_html=True,
            )

    return data_loader.get_project(st.session_state.get("selected_project"))


def require_project() -> Project | None:
    """페이지 진입 시 선택된 프로젝트를 보장한다."""
    project = sidebar_project_selector()
    if project is None:
        st.warning("먼저 사이드바에서 투자건을 선택하세요.")
    return project


def file_list_table(project: Project, input_only: bool = False) -> None:
    """선택 프로젝트의 PDF / 엑셀 파일명 목록을 표로 표시한다."""
    records = data_loader.files_to_records(project, input_only=input_only)
    if not records:
        st.warning("표시할 파일이 없습니다.")
        return

    st.dataframe(
        records,
        width="stretch",
        hide_index=True,
        column_config={
            "파일명": st.column_config.TextColumn(width="large"),
            "파일 종류": st.column_config.TextColumn(width="small"),
            "크기(KB)": st.column_config.NumberColumn("크기(KB)", format="%.1f"),
        },
    )
