from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Annotation, Project, Report


settings = get_settings()


def _report_annotations(db: Session, report: Report) -> list[Annotation]:
    if not report.session_id:
        return []
    return list(
        db.scalars(
            select(Annotation)
            .where(Annotation.session_id == report.session_id)
            .order_by(Annotation.id)
        ).all()
    )


def export_report_pdf(db: Session, report: Report) -> str:
    report_dir = settings.active_storage_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = report_dir / f"PipeSight_report_{report.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    project = db.get(Project, report.project_id)
    annotations = _report_annotations(db, report)

    try:
        _write_reportlab_pdf(pdf_path, report, project, annotations)
    except Exception:
        _write_minimal_pdf(pdf_path, report, project, annotations)

    report.pdf_path = str(pdf_path)
    report.exported_at = datetime.now()
    report.status = "exported"
    db.commit()
    return str(pdf_path)


def _register_cn_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for font_path in [
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    ]:
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont("CNFont", str(font_path)))
                return "CNFont"
            except Exception:
                continue
    return "Helvetica"


def _write_reportlab_pdf(path: Path, report: Report, project: Project | None, annotations: list[Annotation]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    font_name = _register_cn_font()
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    margin = 50
    y = height - margin

    c.setFont(font_name, 18)
    c.drawString(margin, y, report.title or "巡检报告")
    y -= 34
    c.setFont(font_name, 11)
    if project:
        for line in [
            f"项目名称: {project.name}",
            f"风机机型: {project.fan_model}",
            f"风机编号: {project.fan_no}",
            f"叶片型号: {project.blade_model}",
            f"叶片长度: {project.blade_length}",
            f"叶片出厂编号: {project.blade_factory_no}",
            f"地点: {report.location or project.location}",
            f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]:
            c.drawString(margin, y, line)
            y -= 18
    y -= 8
    c.setFont(font_name, 13)
    c.drawString(margin, y, f"标记点（{len(annotations)}）")
    y -= 22

    for idx, ann in enumerate(annotations, start=1):
        data = ann.annotation_json or {}
        defect = data.get("defect", {})
        info_lines = [
            f"#{idx}  {defect.get('type', '') or '—'}  {defect.get('code', '')}".strip(),
            f"等级: {defect.get('severity', '') or '-'}   方向: {defect.get('direction', '') or '-'}   "
            f"位置: {defect.get('position', '') or '-'}   里程: {_fmt_distance(defect.get('distanceM'))}",
        ]
        note = defect.get("note", "")
        if note:
            info_lines.append(f"备注: {note}")
        if data.get("sourceType") == "video" and data.get("videoTime") is not None:
            info_lines.append(f"来源: 视频帧 {float(data['videoTime']):.1f}s")

        # Estimate height needed: text + image.
        img_reader, img_w, img_h = _load_image(ann.rendered_path, max_w=width - 2 * margin, max_h=260)
        needed = len(info_lines) * 16 + (img_h + 14 if img_reader else 0) + 16
        if y - needed < margin:
            c.showPage()
            y = height - margin
            c.setFont(font_name, 13)

        c.setFont(font_name, 10)
        for line in info_lines:
            c.drawString(margin, y, line[:120])
            y -= 16
        if img_reader:
            y -= 6
            c.drawImage(img_reader, margin, y - img_h, width=img_w, height=img_h, preserveAspectRatio=True, anchor="sw")
            y -= img_h + 8
        y -= 10

    c.save()


def _fmt_distance(value) -> str:
    try:
        return f"{float(value):.2f}m"
    except (TypeError, ValueError):
        return "-"


def _load_image(rendered_path: str, *, max_w: float, max_h: float):
    """Return (ImageReader, draw_w, draw_h) scaled to fit, or (None, 0, 0)."""
    if not rendered_path:
        return None, 0, 0
    p = Path(rendered_path)
    if not p.exists():
        return None, 0, 0
    try:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(str(p))
        iw, ih = reader.getSize()
        if iw <= 0 or ih <= 0:
            return None, 0, 0
        scale = min(max_w / iw, max_h / ih, 1.0)
        return reader, iw * scale, ih * scale
    except Exception:
        return None, 0, 0


def _write_minimal_pdf(path: Path, report: Report, project: Project | None, annotations: list[Annotation]) -> None:
    title = (report.title or "PipeSight Report").encode("latin-1", errors="replace").decode("latin-1")
    lines = [title]
    if project:
        lines.append(f"Project: {project.name}")
    lines.append(f"Annotations: {len(annotations)}")
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
