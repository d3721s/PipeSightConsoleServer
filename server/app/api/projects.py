from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InspectionSession, Project
from app.schemas import ProjectCreate, ProjectOut, SessionCreate, SessionOut


router = APIRouter(prefix="/api", tags=["projects"])


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(
        name=payload.name,
        fan_model=payload.fan_model,
        fan_no=payload.fan_no,
        blade_model=payload.blade_model,
        blade_length=payload.blade_length,
        blade_factory_no=payload.blade_factory_no,
        location=payload.location,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())).all())


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="未找到该项目")
    return project


@router.post("/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> InspectionSession:
    if db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="未找到该项目")
    session = InspectionSession(
        project_id=payload.project_id,
        report_title=payload.report_title,
        report_location=payload.report_location,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)) -> InspectionSession:
    session = db.get(InspectionSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="未找到该任务")
    return session


@router.post("/sessions/{session_id}/finish", response_model=SessionOut)
def finish_session(session_id: int, db: Session = Depends(get_db)) -> InspectionSession:
    session = db.get(InspectionSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="未找到该任务")
    session.status = "finished"
    session.ended_at = datetime.now()
    db.commit()
    db.refresh(session)
    return session

