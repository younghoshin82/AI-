"""2. 투자건 등록 - 검증 대상 자료 확정 (DESIGN.md 2.3)"""

import streamlit as st

from src import config, data_loader
from src.ui import components

project = components.sidebar_project_selector()

components.page_header("📁 투자건 등록", "검증할 투자 자료를 선택하거나 업로드합니다.")

source = st.radio(
    "데이터 소스",
    options=["샘플 프로젝트 사용", "직접 업로드"],
    horizontal=True,
    key="data_source",
)

st.divider()

if source == "샘플 프로젝트 사용":
    projects = data_loader.load_projects()
    if not projects:
        st.error(f"샘플 데이터를 찾을 수 없습니다. 경로: {config.SAMPLE_PACK_DIR}")
        st.stop()

    options = [p.dir_name for p in projects]
    labels = {p.dir_name: p.label for p in projects}
    current = st.session_state.get("selected_project", options[0])

    chosen = st.selectbox(
        "투자건 선택",
        options=options,
        index=options.index(current) if current in options else 0,
        format_func=lambda name: labels[name],
        key="register_selectbox",
    )

    if chosen != st.session_state.get("selected_project"):
        st.session_state["selected_project"] = chosen
        st.session_state.pop("project_selectbox", None)
        st.rerun()

    project = data_loader.get_project(chosen)
    if project is None:
        st.stop()

    st.success(f"선택된 투자건: **{project.label}** · 폴더 `{project.dir_name}`")

    # --- 선택된 프로젝트의 PDF / Excel 파일명 목록 -------------------
    st.subheader("제출 자료 목록")

    col1, col2, col3 = st.columns(3)
    col1.metric("전체 파일", f"{len(project.files)}건")
    col2.metric("PDF 문서", f"{len(project.pdf_files)}건")
    col3.metric("엑셀 파일", f"{len(project.excel_files)}건")

    components.file_list_table(project)

    pdf_col, excel_col = st.columns(2)
    with pdf_col:
        st.markdown("**PDF 문서**")
        for f in project.pdf_files:
            st.markdown(f"- `{f.name}` — {f.doc_type}")
    with excel_col:
        st.markdown("**엑셀 (Excel) 파일**")
        for f in project.excel_files:
            st.markdown(f"- `{f.name}` — {f.doc_type}")

    reference = [f for f in project.files if not f.is_input]
    if reference:
        names = ", ".join(f.name for f in reference)
        st.caption(f"참조 전용 문서(검증 입력에서 제외): {names}")

else:
    uploaded = st.file_uploader(
        "투자계획서(PDF)와 첨부 자료(엑셀)를 업로드하세요.",
        type=["pdf", "xlsx", "xls"],
        accept_multiple_files=True,
        key="uploaded_files",
    )

    if uploaded:
        st.subheader("업로드된 자료 목록")
        st.dataframe(
            [
                {
                    "파일명": f.name,
                    "파일 종류": config.kind_label("." + f.name.rsplit(".", 1)[-1]),
                    "크기(KB)": round(f.size / 1024, 1),
                }
                for f in uploaded
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("업로드 경로는 Phase 2에서 파서와 연결됩니다. 현재는 파일 목록만 표시합니다.")

st.divider()

if st.button("정보 추출 실행", type="primary", disabled=project is None):
    st.session_state["extraction_requested"] = True
    st.success("추출 요청이 등록되었습니다. '3. 정보추출 결과' 화면에서 확인하세요.")
    st.caption("실제 파싱 로직은 Phase 2에서 구현됩니다.")

st.page_link("pages/3_정보추출_결과.py", label="정보추출 결과로 이동", icon="🔍")
