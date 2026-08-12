import csv
import io
from dataclasses import dataclass

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class ReportData:
    title: str
    headers: list[str]
    rows: list[list]


def render_csv_response(*, data: ReportData, filename: str) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(data.headers)
    writer.writerows(data.rows)

    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    return response


def render_xlsx_response(*, data: ReportData, filename: str) -> HttpResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Report"
    sheet.append(data.headers)

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in data.rows:
        sheet.append(row)

    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 40)

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return response


def render_pdf_response(*, data: ReportData, filename: str) -> HttpResponse:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [Paragraph(data.title, styles["Title"]), Spacer(1, 12)]

    table_data = [data.headers, *[[str(cell) for cell in row] for row in data.rows]]
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
    return response


def render_report_response(*, data: ReportData, filename: str, export_format: str) -> HttpResponse:
    if export_format == "csv":
        return render_csv_response(data=data, filename=filename)
    if export_format == "xlsx":
        return render_xlsx_response(data=data, filename=filename)
    if export_format == "pdf":
        return render_pdf_response(data=data, filename=filename)
    raise ValueError(f"Unsupported export format: {export_format}")
