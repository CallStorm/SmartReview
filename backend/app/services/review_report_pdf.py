"""Generate audit report PDF documents from ReviewReportV1 JSON."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.scheme_review_task import SchemeReviewTask
from app.schemas.review_report import ReportStep, ReviewReportV1
from app.services import review_report_content as content

_FONT_NAME = "NotoSansSC"
_FONT_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansSC-Regular.ttf"
)
# Owner password only locks permissions; documents open without a user password.
_PDF_OWNER_PASSWORD = "SmartReviewAuditReport"


@lru_cache(maxsize=1)
def _ensure_font_registered() -> str:
    if not _FONT_PATH.is_file():
        raise FileNotFoundError(f"Missing Chinese font for PDF export: {_FONT_PATH}")
    pdfmetrics.registerFont(TTFont(_FONT_NAME, str(_FONT_PATH)))
    return _FONT_NAME


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _styles() -> dict[str, ParagraphStyle]:
    _ensure_font_registered()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AuditTitle",
            parent=base["Heading1"],
            fontName=_FONT_NAME,
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "AuditH2",
            parent=base["Heading2"],
            fontName=_FONT_NAME,
            fontSize=13,
            leading=18,
            alignment=TA_LEFT,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "AuditH3",
            parent=base["Heading3"],
            fontName=_FONT_NAME,
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "AuditBody",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=10.5,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "quote": ParagraphStyle(
            "AuditQuote",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#444444"),
            leftIndent=6,
            spaceAfter=6,
        ),
        "cell": ParagraphStyle(
            "AuditCell",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=12,
            alignment=TA_LEFT,
        ),
        "cell_bold": ParagraphStyle(
            "AuditCellBold",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=12,
            alignment=TA_LEFT,
        ),
    }


def _make_table(headers: list[str], rows: list[list[str]], styles: dict[str, ParagraphStyle]) -> Table:
    data: list[list[Paragraph]] = [
        [_p(h, styles["cell_bold"]) for h in headers]
    ]
    for row in rows:
        data.append([_p(str(cell), styles["cell"]) for cell in row])
    col_count = len(headers)
    available = A4[0] - 40 * mm
    col_width = available / col_count
    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _make_kv_table(
    rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]
) -> Table:
    data: list[list[Paragraph]] = [
        [_p("项目", styles["cell_bold"]), _p("内容", styles["cell_bold"])]
    ]
    for label, value in rows:
        data.append([_p(label, styles["cell_bold"]), _p(value, styles["cell"])])
    available = A4[0] - 40 * mm
    table = Table(data, colWidths=[available * 0.22, available * 0.78])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _append_step(
    story: list,
    section_num: int,
    step: ReportStep,
    styles: dict[str, ParagraphStyle],
) -> None:
    story.append(_p(content.section_heading(section_num, step), styles["h2"]))
    if step.summary:
        story.append(_p(f"步骤摘要：{step.summary}", styles["body"]))

    desc = content.STEP_DESCRIPTION.get(step.step_id, "")
    if desc:
        story.append(_p(desc, styles["quote"]))

    if not step.issues:
        story.append(_p("本步骤无问题项。", styles["body"]))
        return

    if step.step_id == "structure":
        story.append(
            _make_table(
                ["章节", "问题类型", "说明"],
                content.structure_table_rows(step),
                styles,
            )
        )
    elif step.step_id == "compilation_basis":
        story.append(
            _make_table(
                ["问题", "类别", "章节", "原文", "修改建议", "标准依据"],
                content.compilation_basis_table_rows(step),
                styles,
            )
        )
    elif step.step_id == "context_consistency":
        story.append(
            _make_table(
                ["章节", "对比章节", "问题", "优化建议"],
                content.context_consistency_table_rows(step),
                styles,
            )
        )
    else:
        for chapter, rows in content.content_like_groups(step):
            story.append(_p(chapter, styles["h3"]))
            story.append(
                _make_table(
                    ["序号", "问题", "原文内容", "修改建议"],
                    rows,
                    styles,
                )
            )
    story.append(Spacer(1, 6))


def build_audit_report_pdf(
    task: SchemeReviewTask,
    report: ReviewReportV1,
    *,
    system_name: str = "智能方案审核",
) -> bytes:
    styles = _styles()
    buf = io.BytesIO()

    # Soft edit restriction: open without password; modify/assemble disabled.
    # reportlab.pdfencrypt.StandardEncryption also works via encrypt= on canvas.
    from reportlab.lib.pdfencrypt import StandardEncryption

    encrypt = StandardEncryption(
        userPassword="",
        ownerPassword=_PDF_OWNER_PASSWORD,
        canPrint=1,
        canModify=0,
        canCopy=1,
        canAnnotate=0,
        strength=128,
    )

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"[{content.scheme_display_name(task)}]审核报告",
        author=system_name,
        encrypt=encrypt,
    )

    story: list = []
    scheme_name = content.scheme_display_name(task)
    story.append(_p(f"[{scheme_name}]审核报告", styles["title"]))
    story.append(_make_kv_table(content.meta_kv_rows(task, report, system_name=system_name), styles))
    story.append(Spacer(1, 8))

    for section_num, step in enumerate(content.iter_ordered_steps(report), start=1):
        _append_step(story, section_num, step, styles)

    story.append(Spacer(1, 10))
    story.append(_p(content.DISCLAIMER, styles["body"]))

    # Ensure font is registered on the canvas as well when building.
    def _on_first_page(canvas: Canvas, _doc: SimpleDocTemplate) -> None:
        _ensure_font_registered()
        canvas.setTitle(f"[{scheme_name}]审核报告")

    doc.build(story, onFirstPage=_on_first_page, onLaterPages=_on_first_page)
    return buf.getvalue()
