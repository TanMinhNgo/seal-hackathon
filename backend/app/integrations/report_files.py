from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.core.errors import ApiError


def render(kind: str, format_: str, rows: list[dict]) -> bytes:
    output = BytesIO()
    if format_ == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = kind
        if rows:
            sheet.append(list(rows[0]))
        for row in rows:
            sheet.append(
                [
                    ILLEGAL_CHARACTERS_RE.sub("", str(v)) if v is not None else ""
                    for v in row.values()
                ]
            )
            for cell in sheet[sheet.max_row]:
                # Dữ liệu user luôn là text, kể cả chuỗi bắt đầu bằng '='.
                cell.data_type = "s"
        workbook.save(output)
    else:
        fonts = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
        font = next((p for p in fonts if p.is_file()), None)
        if font is None:
            raise ApiError(
                503, "PDF_FONT_UNAVAILABLE", "A Unicode font is required for PDF exports"
            )
        if "SEALUnicode" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("SEALUnicode", str(font)))
        style = ParagraphStyle(
            "report",
            fontName="SEALUnicode",
            fontSize=9,
            leading=12,
            wordWrap="CJK",
            splitLongWords=True,
        )
        story = [Paragraph(escape(kind), style), Spacer(1, 12)]
        for row in rows:
            for key, value in row.items():
                text = ILLEGAL_CHARACTERS_RE.sub("", str(value)) if value is not None else ""
                story.append(Paragraph(escape(f"{key}: {text}"), style))
            story.append(Spacer(1, 12))
        SimpleDocTemplate(output, title=f"SEAL {kind}", author="SEAL").build(story)
    return output.getvalue()
