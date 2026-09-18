"""경로, 상수, 검증 등급 등 전역 설정 (DESIGN.md 3.1 src/config.py)"""

from pathlib import Path

# ----------------------------------------------------------------------
# 경로
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_PACK_DIR = BASE_DIR / "AI_Investment_Validation_Sample_Pack"
OUTPUT_DIR = BASE_DIR / "output"

APP_TITLE = "AI 기반 투자계획서 검증 시스템"
APP_ICON = "📑"

# ----------------------------------------------------------------------
# 검증 등급 (CLAUDE.md 검증 등급 정의)
# ----------------------------------------------------------------------
GRADE_HIGH = "높음"
GRADE_CAUTION = "주의"
GRADE_CHECK = "확인필요"
GRADE_NORMAL = "정상"

# 심각도 순서: 값이 클수록 우선 표시 (대시보드 최고 위험등급 산출에 사용)
GRADE_ORDER = {
    GRADE_NORMAL: 0,
    GRADE_CHECK: 1,
    GRADE_CAUTION: 2,
    GRADE_HIGH: 3,
}

# DESIGN.md 2.3 - 등급별 배지 색상
# 심각도가 높을수록 진한 색: 높음(빨강) > 주의(주황) > 확인필요(노랑-주황) > 정상(초록)
GRADE_COLORS = {
    GRADE_HIGH: "#D32F2F",
    GRADE_CAUTION: "#EF6C00",
    GRADE_CHECK: "#F9A825",
    GRADE_NORMAL: "#388E3C",
}

GRADE_DESCRIPTIONS = {
    GRADE_HIGH: "중대한 문제가 확인됨",
    GRADE_CAUTION: "검토가 필요한 사항이 있음",
    GRADE_CHECK: "자료 부족으로 판단 불가, 추가 확인 필요",
    GRADE_NORMAL: "특이사항 없음",
}

# ----------------------------------------------------------------------
# 문서 유형 (파일명 접두 번호 기준)
# ----------------------------------------------------------------------
DOC_TYPE_BY_PREFIX = {
    "01": "투자계획서",
    "02": "경제성검토",
    "03": "투자비내역",
    "04": "기대효과산출",
    "05": "투자검토요약(정답본)",
}

# 검증 입력으로 사용하는 확장자
INPUT_EXTENSIONS = {".pdf", ".xlsx", ".xls"}

# 정답본 등 참조 전용 문서 (검증 로직 입력으로 사용하지 않음, DESIGN.md 1.4)
REFERENCE_ONLY_PREFIXES = {"05"}

# 파일 종류: 내부 코드값과 화면 표시 라벨을 분리한다
# (표시 라벨을 한글로 두어 브라우저 자동 번역이 영어 단어를 오역하지 않게 한다)
KIND_PDF = "PDF"
KIND_EXCEL = "EXCEL"
KIND_WORD = "WORD"
KIND_ETC = "ETC"

EXTENSION_KINDS = {
    ".pdf": KIND_PDF,
    ".xlsx": KIND_EXCEL,
    ".xls": KIND_EXCEL,
    ".docx": KIND_WORD,
}

KIND_LABELS = {
    KIND_PDF: "PDF 문서",
    KIND_EXCEL: "엑셀 (Excel)",
    KIND_WORD: "워드 (Word)",
    KIND_ETC: "기타",
}


def kind_of(extension: str) -> str:
    """확장자 → 내부 종류 코드"""
    return EXTENSION_KINDS.get(extension.lower(), KIND_ETC)


def kind_label(extension: str) -> str:
    """확장자 → 화면 표시용 한글 라벨"""
    return KIND_LABELS[kind_of(extension)]

# ----------------------------------------------------------------------
# 필수 추출 항목 (DESIGN.md 2.3 - 3번 페이지)
# ----------------------------------------------------------------------
EXTRACTION_FIELDS = [
    ("투자명", "-"),
    ("총 투자비", "억원"),
    ("NPV", "억원"),
    ("IRR", "%"),
    ("WACC", "%"),
    ("회수기간", "년"),
    ("기대효과", "억원/년"),
]

# 추출 실패 시 표기값 (CLAUDE.md: 자료에 없는 수치는 추정하지 않는다)
NOT_FOUND = "미확인"

# ----------------------------------------------------------------------
# 검증 룰 정의 (DESIGN.md 2.3 - 4번 페이지)
# ----------------------------------------------------------------------
RULES = [
    {
        "id": "R-01",
        "name": "투자비 정합성",
        "criteria": "계획서 총투자비 = 투자비 내역 합계 (허용오차 max(0.05억원, 0.1%)), 경제성 적용 투자비 부가 비교",
        "fail_grade": GRADE_HIGH,
    },
    {
        "id": "R-02",
        "name": "경제성 지표 존재",
        "criteria": "NPV·IRR·WACC·회수기간 4개 항목이 모두 존재",
        "fail_grade": GRADE_CHECK,
    },
    {
        "id": "R-03",
        "name": "기대효과 정합성",
        "criteria": "세부효과 합계 = 계획서 기재 효과",
        "fail_grade": GRADE_HIGH,
    },
    {
        "id": "R-04",
        "name": "기대효과 중복",
        "criteria": "효과 반영 시점 < 가동 예정 시점, 또는 동일 성격 효과 항목 2건 이상 계상",
        "fail_grade": GRADE_CAUTION,
    },
]

# ----------------------------------------------------------------------
# 투자검토요약 구성 (DESIGN.md 2.3 - 5번 페이지)
# ----------------------------------------------------------------------
SUMMARY_SECTIONS = [
    ("1. 투자개요", "사실"),
    ("2. 투자비 검토", "사실"),
    ("3. 경제성 검토", "사실"),
    ("4. 기대효과 검토", "사실"),
    ("5. 주요 리스크", "AI 의견"),
    ("6. 현업 추가 확인사항", "AI 의견"),
    ("7. 종합 의견", "AI 의견"),
]
