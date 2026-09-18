"""투자검토요약 내보내기: 마크다운 / 텍스트 / PDF (DESIGN.md 3.1)

PDF 는 reportlab 으로 생성하며, 한글 표시를 위해 시스템의 한글 TrueType 폰트를
등록한다. 등록할 폰트를 찾지 못하면 PDF 를 만들지 않고 이유를 돌려준다
(깨진 글자로 출력하지 않는다).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

# 한글 폰트 후보 (Windows / macOS / Linux)
FONT_CANDIDATES = [
    ("MalgunGothic", Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf")),
    ("NanumGothic", Path("C:/Windows/Fonts/NanumGothic.ttf"), Path("C:/Windows/Fonts/NanumGothicBold.ttf")),
    ("AppleGothic", Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"), None),
    # 리눅스 / Streamlit Cloud: packages.txt 의 `fonts-nanum` 으로 설치되는 경로
    (
        "NanumGothic",
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ),
]

TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
SEPARATOR_ROW_RE = re.compile(r"^\|[\s:\-|]+\|$")


def to_markdown_bytes(markdown: str) -> bytes:
    return markdown.encode("utf-8")


def to_text_bytes(markdown: str) -> bytes:
    """마크다운 기호를 덜어낸 평문으로 변환한다."""
    lines: list[str] = []
    for line in markdown.splitlines():
        if SEPARATOR_ROW_RE.match(line.strip()):
            continue
        text = line
        text = re.sub(r"^#{1,6}\s*", "", text)
        text = text.replace("**", "").replace("`", "")
        text = re.sub(r"^>\s*", "", text)
        if TABLE_ROW_RE.match(text.strip()):
            cells = [cell.strip() for cell in text.strip().strip("|").split("|")]
            text = " | ".join(cells)
        lines.append(text)
    return "\n".join(lines).encode("utf-8")


def _register_korean_font() -> tuple[str | None, str | None]:
    """한글 폰트를 등록하고 (본문 폰트명, 굵은 폰트명) 을 돌려준다."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for name, regular, bold in FONT_CANDIDATES:
        if not regular.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, str(regular)))
        except Exception:
            continue

        bold_name = name
        if bold and bold.exists():
            try:
                pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bold)))
                bold_name = f"{name}-Bold"
            except Exception:
                bold_name = name
        return name, bold_name

    return None, None


def to_pdf_bytes(markdown: str) -> tuple[bytes | None, str | None]:
    """마크다운 초안을 PDF 로 변환한다. 실패 시 (None, 이유) 를 돌려준다."""
    try:
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.lib import colors
    except ImportError:
        return None, "reportlab 패키지가 설치되어 있지 않습니다. `pip install reportlab` 후 다시 시도하세요."

    font, bold_font = _register_korean_font()
    if font is None:
        return None, "한글 TrueType 폰트를 찾지 못해 PDF를 생성하지 않았습니다. (맑은 고딕 또는 나눔고딕 필요)"

    styles = {
        "title": ParagraphStyle("title", fontName=bold_font, fontSize=16, leading=22, spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName=bold_font, fontSize=12, leading=17, spaceBefore=10, spaceAfter=5),
        "body": ParagraphStyle("body", fontName=font, fontSize=9.5, leading=14, alignment=TA_LEFT),
        "bullet": ParagraphStyle("bullet", fontName=font, fontSize=9.5, leading=14, leftIndent=10),
        "quote": ParagraphStyle("quote", fontName=font, fontSize=9, leading=13, textColor=colors.HexColor("#555555"), leftIndent=6),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=8.5, leading=12),
        "cellhead": ParagraphStyle("cellhead", fontName=bold_font, fontSize=8.5, leading=12),
    }

    def inline(text: str) -> str:
        """마크다운 강조를 reportlab 태그로 바꾸고 XML 특수문자를 escape 한다."""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`(.+?)`", r"<font color='#1565C0'>\1</font>", text)
        return text

    story: list = []
    table_buffer: list[list[str]] = []

    def flush_table() -> None:
        if not table_buffer:
            return
        header, *rows = table_buffer
        data = [[Paragraph(inline(c), styles["cellhead"]) for c in header]]
        data += [[Paragraph(inline(c), styles["cell"]) for c in row] for row in rows]
        table = Table(data, hAlign="LEFT", colWidths=[28 * mm, 40 * mm, 18 * mm, 74 * mm][: len(header)])
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDBDBD")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 5))
        table_buffer.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if SEPARATOR_ROW_RE.match(stripped):
            continue

        if TABLE_ROW_RE.match(stripped):
            table_buffer.append([c.strip() for c in stripped.strip("|").split("|")])
            continue
        flush_table()

        if not stripped:
            story.append(Spacer(1, 4))
        elif stripped == "---":
            story.append(Spacer(1, 6))
        elif stripped.startswith("# "):
            story.append(Paragraph(inline(stripped[2:]), styles["title"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(inline(stripped[3:]), styles["h2"]))
        elif stripped.startswith("> "):
            story.append(Paragraph(inline(stripped[2:]), styles["quote"]))
        elif stripped.startswith(("- ", "* ")):
            indent = len(line) - len(line.lstrip())
            style = ParagraphStyle(
                f"bullet{indent}", parent=styles["bullet"], leftIndent=10 + indent * 4
            )
            story.append(Paragraph("• " + inline(stripped[2:]), style))
        elif re.match(r"^\d+\.\s", stripped):
            story.append(Paragraph(inline(stripped), styles["bullet"]))
        else:
            story.append(Paragraph(inline(stripped), styles["body"]))

    flush_table()

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="투자검토요약 (초안)",
    )

    try:
        document.build(story)
    except Exception as exc:  # 레이아웃 실패
        return None, f"PDF 생성 중 오류가 발생했습니다: {exc}"

    return buffer.getvalue(), None
