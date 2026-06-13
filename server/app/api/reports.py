from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Project, Report
from app.schemas import ReportCreate, ReportOut
from app.services.report_service import export_report_pdf


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/start", response_model=ReportOut)
def start_report(payload: ReportCreate, db: Session = Depends(get_db)) -> Report:
    if db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
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
        raise HTTPException(status_code=404, detail="report not found")
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
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.post("/{report_id}/export-pdf")
def export_pdf(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    path = export_report_pdf(db, report)
    return {"ok": True, "pdfPath": path}

