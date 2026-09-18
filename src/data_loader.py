"""샘플팩 스캔 및 프로젝트/파일 목록 조회 (DESIGN.md 3.1 src/data_loader.py)

실제 파일 시스템을 읽어 Project_01 ~ Project_05 목록과 각 프로젝트의
PDF / 엑셀 파일 목록을 반환한다. 파일 내용 파싱은 src/parsers 가 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from src import config

# 폴더명 접미사(결함 유형) → 한글 라벨 (DESIGN.md 1.4 검증 시나리오)
CASE_LABELS = {
    "Normal": "정상 케이스",
    "CAPEX_Mismatch": "투자비 불일치",
    "Effect_Mismatch": "기대효과 불일치",
    "Missing_Economics": "경제성 지표 누락",
    "Timing_Overlap": "효과 시점 중복",
}


@dataclass
class ProjectFile:
    """프로젝트 폴더에 포함된 개별 파일 메타"""

    name: str
    path: Path
    extension: str
    kind: str  # 내부 코드 (config.KIND_PDF / KIND_EXCEL / KIND_WORD)
    kind_label: str  # 화면 표시 라벨 (PDF 문서 / 엑셀 (Excel) / 워드 (Word))
    doc_type: str  # 투자계획서 / 경제성검토 / ...
    size_kb: float
    is_input: bool  # 검증 입력 대상 여부 (정답본은 False)


@dataclass
class Project:
    """샘플팩의 투자건 1건"""

    dir_name: str  # 예: Project_02_CAPEX_Mismatch
    project_id: str  # 예: Project_02
    case_label: str  # 예: 투자비 불일치
    path: Path
    files: list[ProjectFile] = field(default_factory=list)

    @property
    def label(self) -> str:
        """사이드바·선택박스에 표시할 이름"""
        return f"{self.project_id} ({self.case_label})"

    @property
    def input_files(self) -> list[ProjectFile]:
        return [f for f in self.files if f.is_input]

    @property
    def pdf_files(self) -> list[ProjectFile]:
        return [f for f in self.files if f.kind == config.KIND_PDF]

    @property
    def excel_files(self) -> list[ProjectFile]:
        return [f for f in self.files if f.kind == config.KIND_EXCEL]


def _classify(path: Path) -> ProjectFile:
    """파일명 규칙(`01_투자계획서.pdf`)을 이용해 문서 유형을 분류한다."""
    extension = path.suffix.lower()
    prefix = path.stem.split("_")[0]

    return ProjectFile(
        name=path.name,
        path=path,
        extension=extension,
        kind=config.kind_of(extension),
        kind_label=config.kind_label(extension),
        doc_type=config.DOC_TYPE_BY_PREFIX.get(prefix, "기타"),
        size_kb=round(path.stat().st_size / 1024, 1),
        is_input=(
            extension in config.INPUT_EXTENSIONS
            and prefix not in config.REFERENCE_ONLY_PREFIXES
        ),
    )


@st.cache_data(show_spinner=False)
def load_projects() -> list[Project]:
    """샘플팩 폴더에서 Project_* 디렉터리를 스캔한다."""
    if not config.SAMPLE_PACK_DIR.exists():
        return []

    projects: list[Project] = []
    for directory in sorted(p for p in config.SAMPLE_PACK_DIR.iterdir() if p.is_dir()):
        if not directory.name.startswith("Project_"):
            continue

        parts = directory.name.split("_")
        project_id = "_".join(parts[:2])  # Project_01
        case_key = "_".join(parts[2:])  # CAPEX_Mismatch

        projects.append(
            Project(
                dir_name=directory.name,
                project_id=project_id,
                case_label=CASE_LABELS.get(case_key, case_key or "미분류"),
                path=directory,
                files=[_classify(f) for f in sorted(directory.iterdir()) if f.is_file()],
            )
        )
    return projects


def get_project(dir_name: str | None) -> Project | None:
    """폴더명으로 프로젝트 1건을 조회한다."""
    if not dir_name:
        return None
    return next((p for p in load_projects() if p.dir_name == dir_name), None)


def files_to_records(project: Project, input_only: bool = False) -> list[dict]:
    """파일 목록을 표 렌더링용 레코드로 변환한다."""
    files = project.input_files if input_only else project.files
    return [
        {
            "파일명": f.name,
            "파일 종류": f.kind_label,
            "문서 구분": f.doc_type,
            "크기(KB)": f.size_kb,
            "검증 입력": "사용" if f.is_input else "참조 전용",
        }
        for f in files
    ]
