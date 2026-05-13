"""PDF report export."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import BaseDocTemplate  # type: ignore[import-untyped]

from takeoff_pro.data.models import Job
from takeoff_pro.estimate.pricing import price_job
from takeoff_pro.reports.data import build_takeoff_rows, job_summary_rows


def export_pdf(job: Job, path: str | Path) -> Path:
    """Export a PDF summary report."""
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(output_path), pagesize=letter, title=f"{job.name} Report")
    story: list[object] = []
    story.append(Paragraph(f"{job.name} Report", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(_table([("Field", "Value"), *job_summary_rows(job)]))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Takeoff Detail", styles["Heading2"]))
    story.append(
        _table(
            [
                ("Section", "Measurement", "Kind", "Quantity", "Unit"),
                *[
                    (
                        row.section_name,
                        row.measurement_name,
                        row.kind,
                        f"{row.quantity:.2f}",
                        row.unit,
                    )
                    for row in build_takeoff_rows(job)
                ],
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(Paragraph("Cost Detail", styles["Heading2"]))
    story.append(
        _table(
            [
                ("Section", "Item", "Quantity", "Unit", "Total"),
                *[
                    (
                        line.section_name,
                        line.description,
                        f"{line.quantity:.2f}",
                        line.unit,
                        f"${line.total_cost:.2f}",
                    )
                    for line in price_job(job)
                ],
            ]
        )
    )
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return output_path


def _table(rows: list[tuple[object, ...]]) -> Table:
    table = Table(rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _draw_footer(canvas: Canvas, document: BaseDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(72, 36, "Takeoff Pro")
    canvas.drawRightString(letter[0] - 72, 36, f"Page {document.page}")
    canvas.restoreState()
