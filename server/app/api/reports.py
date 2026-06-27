from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Annotation, Project, Report
from app.schemas import ReportCreate, ReportOut
from app.services.report_service import export_report_pdf


router = APIRouter(prefix="/api/reports", tags=["reports"])
settings = get_settings()


def _storage_url(absolute_path: str) -> str | None:
    try:
        rel = Path(absolute_path).resolve().relative_to(settings.active_storage_dir.resolve())
    except (ValueError, OSError):
        return None
    return "/storage/" + rel.as_posix()


@router.post("/start", response_model=ReportOut)
def start_report(payload: ReportCreate, db: Session = Depends(get_db)) -> Report:
    if db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="未找到该项目")
    report = Report(
        project_id=payload.project_id,
        session_id=payload.session_id,
        title=payload.title,
        location=payload.location,
        status="running",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.post("/{report_id}/stop", response_model=ReportOut)
def stop_report(report_id: int, db: Session = Depends(get_db)) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到该报告")
    report.status = "draft"
    report.ended_at = datetime.now()
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.started_at.desc())).all())


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到该报告")
    return report


@router.delete("/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到该报告")
    # Remove the generated PDF file if present. The inspection's annotations are
    # tied to the session (shared with the annotate page), not owned by the
    # report, so they are intentionally left intact.
    if report.pdf_path:
        try:
            Path(report.pdf_path).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(report)
    db.commit()
    return {"ok": True}


@router.post("/{report_id}/export-pdf")
def export_pdf(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到该报告")
    path = export_report_pdf(db, report)
    return {"ok": True, "pdfPath": path, "downloadUrl": f"/api/reports/{report_id}/pdf"}


@router.get("/{report_id}/detail")
def report_detail(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到该报告")
    project = db.get(Project, report.project_id)
    annotations = []
    if report.session_id:
        rows = db.scalars(
            select(Annotation).where(Annotation.session_id == report.session_id).order_by(Annotation.id)
        ).all()
        for row in rows:
            data = row.annotation_json or {}
            annotations.append(
                {
                    "id": row.id,
                    "renderedUrl": _storage_url(row.rendered_path) if row.rendered_path else None,
                    "sourceType": data.get("sourceType"),
                    "videoTime": data.get("videoTime"),
                    "defect": data.get("defect", {}),
                    "createdAt": row.created_at.isoformat(timespec="seconds"),
                }
            )
    return {
        "report": {
            "id": report.id,
            "title": report.title,
            "location": report.location,
            "status": report.status,
            "startedAt": report.started_at.isoformat(timespec="seconds"),
            "exportedAt": report.exported_at.isoformat(timespec="seconds") if report.exported_at else None,
            "pdfReady": bool(report.pdf_path and Path(report.pdf_path).exists()),
            "downloadUrl": f"/api/reports/{report.id}/pdf",
        },
        "project": None
        if project is None
        else {
            "name": project.name,
            "fanModel": project.fan_model,
            "fanNo": project.fan_no,
            "bladeModel": project.blade_model,
            "bladeLength": project.blade_length,
            "bladeFactoryNo": project.blade_factory_no,
            "location": project.location,
        },
        "annotations": annotations,
    }


@router.get("/{report_id}/pdf")
def download_pdf(report_id: int, db: Session = Depends(get_db)) -> FileResponse:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到该报告")
    # Generate on demand if not exported yet (or the file vanished).
    if not report.pdf_path or not Path(report.pdf_path).exists():
        export_report_pdf(db, report)
    pdf_path = Path(report.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 尚未生成，请先导出")
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"PipeSight_report_{report_id}.pdf",
    )

