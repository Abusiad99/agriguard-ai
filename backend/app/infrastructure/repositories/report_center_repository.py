"""Persistence for generated reports and their share links (migration 0007)."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.infrastructure.db.models.report_center_model import GeneratedReportModel, ReportShareModel


class SqlAlchemyReportCenterRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, row):
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def save(self, row):
        self.db.commit()
        return row

    def get(self, report_id: UUID) -> Optional[GeneratedReportModel]:
        return self.db.get(GeneratedReportModel, report_id)

    def latest_version(self, owner_id: UUID, report_type: str, subject_id: UUID) -> Optional[GeneratedReportModel]:
        return self.db.execute(select(GeneratedReportModel).where(
            GeneratedReportModel.owner_id == owner_id, GeneratedReportModel.report_type == report_type,
            GeneratedReportModel.subject_id == subject_id).order_by(GeneratedReportModel.version.desc()).limit(1)).scalar_one_or_none()

    def versions(self, owner_id: UUID, report_type: str, subject_id: UUID) -> List[GeneratedReportModel]:
        return list(self.db.execute(select(GeneratedReportModel).where(
            GeneratedReportModel.owner_id == owner_id, GeneratedReportModel.report_type == report_type,
            GeneratedReportModel.subject_id == subject_id).order_by(GeneratedReportModel.version.desc())).scalars())

    def list(self, owner_id: Optional[UUID], report_type: Optional[str], q: Optional[str], crop: Optional[str],
             disease: Optional[str], date_from: Optional[date], date_to: Optional[date], subject_id: Optional[UUID],
             page: int, page_size: int) -> Tuple[List[GeneratedReportModel], int]:
        r = GeneratedReportModel
        conditions = []
        if owner_id is not None:
            conditions.append(r.owner_id == owner_id)
        if report_type:
            conditions.append(r.report_type == report_type)
        if subject_id:
            conditions.append(r.subject_id == subject_id)
        if crop:
            conditions.append(func.lower(r.crop) == crop.lower())
        if disease:
            conditions.append(func.lower(r.disease) == disease.lower())
        if date_from:
            conditions.append(r.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
        if date_to:
            conditions.append(r.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
        if q:
            like = f"%{q.lower()}%"
            conditions.append(or_(func.lower(r.title).like(like), func.lower(r.crop).like(like),
                                  func.lower(r.disease).like(like), func.lower(r.status_summary).like(like)))
        total = self.db.execute(select(func.count()).select_from(r).where(*conditions)).scalar_one()
        rows = self.db.execute(select(r).where(*conditions).order_by(r.created_at.desc(), r.version.desc())
                               .offset((page - 1) * page_size).limit(page_size)).scalars()
        return list(rows), total

    # --------------------------------------------------------------- shares
    def shares(self, report_id: UUID) -> List[ReportShareModel]:
        return list(self.db.execute(select(ReportShareModel).where(ReportShareModel.report_id == report_id)
                                    .order_by(ReportShareModel.created_at.desc())).scalars())

    def get_share(self, report_id: UUID, share_id: UUID) -> Optional[ReportShareModel]:
        return self.db.execute(select(ReportShareModel).where(
            ReportShareModel.report_id == report_id, ReportShareModel.id == share_id)).scalar_one_or_none()

    def share_by_token_hash(self, token_hash: str) -> Optional[ReportShareModel]:
        return self.db.execute(select(ReportShareModel).where(ReportShareModel.token_hash == token_hash)).scalar_one_or_none()
