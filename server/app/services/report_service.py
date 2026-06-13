from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Marker, Project, Report


settings = get_settings()


def export_report_pdf(db: Session, report: Report) -> str:
    report_dir = settings.active_storage_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = report_dir / f"PipeSight_report_{report.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    project = db.get(Project, report.project_id)
    markers = db.scalars(select(Marker).where(Marker.session_id == report.session_id)).all() if report.session_id else []

    try:
        _write_reportlab_pdf(pdf_path, report, project, markers)
    except Exception:
        _write_minimal_pdf(pdf_path, report, project, markers)

    report.pdf_path = str(pdf_path)
    report.exported_at = datetime.now()
    report.status = "exported"
    db.commit()
    return str(pdf_path)


def _write_reportlab_pdf(path: Path, report: Report, project: Project | None, markers: list[Marker]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_name = "Helvetica"
    for font_path in [
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    ]:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("CNFont", str(font_path)))
            font_name = "CNFont"
            break

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont(font_name, 18)
    c.drawString(50, y, report.title or "巡检报告")
    y -= 36
    c.setFont(font_name, 11)
    if project:
        lines = [
            f"项目名称: {project.name}",
            f"风机机型: {project.fan_model}",
            f"风机编号: {project.fan_no}",
            f"叶片型号: {project.blade_model}",
            f"叶片长度: {project.blade_length}",
            f"叶片出厂编号: {project.blade_factory_no}",
            f"地点: {report.location or project.location}",
        ]
        for line in lines:
            c.drawString(50, y, line)
            y -= 20
    y -= 12
    c.setFont(font_name, 13)
    c.drawString(50, y, "标记点")
    y -= 24
    c.setFont(font_name, 10)
    for marker in markers:
        text = (
            f"#{marker.id} 距离 {marker.distance_m:.2f}m "
            f"{marker.defect_type} {marker.severity} {marker.position} {marker.note}"
        )
        c.drawString(50, y, text[:100])
        y -= 18
        if y < 60:
            c.showPage()
            c.setFont(font_name, 10)
            y = height - 50
    c.save()


def _write_minimal_pdf(path: Path, report: Report, project: Project | None, markers: list[Marker]) -> None:
    title = (report.title or "PipeSight Report").encode("latin-1", errors="replace").decode("latin-1")
    lines = [title]
    if project:
        lines.append(f"Project: {project.name}")
    lines.append(f"Markers: {len(markers)}")
    body = "BT /F1 12 Tf 50 780 Td " + " Tj 0 -18 Td ".join(f"({line})" for line in lines) + " Tj ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(body)} >> stream\n{body}\nendstream endobj",
    ]
    content = "%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(content.encode("latin-1")))
        content += obj + "\n"
    xref = len(content.encode("latin-1"))
    content += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets[1:]:
        content += f"{off:010d} 00000 n \n"
    content += f"trailer << /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref}\n%%EOF\n"
    path.write_bytes(content.encode("latin-1"))
