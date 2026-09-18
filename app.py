"""AI 기반 투자계획서 검증 시스템 - Streamlit 엔트리

사이드바 메뉴 5개를 st.navigation으로 구성한다.
실행: streamlit run app.py
"""

import streamlit as st

from src import config

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    st.Page("pages/1_대시보드.py", title="1. 투자계획서 검증", icon="📊", default=True),
    st.Page("pages/2_투자건_등록.py", title="2. 투자건 등록", icon="📁"),
    st.Page("pages/3_정보추출_결과.py", title="3. 정보추출 결과", icon="🔍"),
    st.Page("pages/4_AI_검증_결과.py", title="4. AI 검증 결과", icon="✅"),
    st.Page("pages/5_투자검토_요약.py", title="5. 투자검토 요약", icon="📝"),
]

st.sidebar.title(f"{config.APP_ICON} AI 투자계획서 검증")
st.sidebar.caption("투자기획팀 심사 지원 도구")

st.navigation(PAGES).run()
