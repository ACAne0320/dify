"""
Workflow Schedule Model
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from extensions.ext_database import db
from models.base import Base
from models.types import StringUUID


class WorkflowSchedule(Base):
    """
    WorkflowSchedule Model

    Attributes:
    - id (uuid) Schedule ID
    - tenant_id (uuid) Tenant ID
    - app_id (uuid) App ID
    - workflow_id (uuid) Workflow ID
    - name (string) Schedule name
    - description (string, nullable) Schedule description
    - cron_expression (string) Cron expression
    - timezone (string) Timezone
    - inputs (json, nullable) Workflow inputs
    - is_active (boolean) Whether the schedule is active
    - created_by (uuid) Creator user ID
    - created_at (timestamp) Created time
    - updated_at (timestamp) Updated time
    - last_run_at (timestamp, nullable) Last run time
    - next_run_at (timestamp, nullable) Next scheduled run time
    """

    __tablename__ = "workflow_schedules"
    __table_args__ = (
        db.PrimaryKeyConstraint("id", name="workflow_schedule_pkey"),
        db.Index("workflow_schedule_app_idx", "tenant_id", "app_id"),
        db.Index("workflow_schedule_workflow_idx", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(StringUUID, server_default=db.text("uuid_generate_v4()"))
    tenant_id: Mapped[str] = mapped_column(StringUUID)
    app_id: Mapped[str] = mapped_column(StringUUID)
    workflow_id: Mapped[str] = mapped_column(StringUUID)
    name: Mapped[str] = mapped_column(db.String(255))
    description: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(db.String(255))
    timezone: Mapped[str] = mapped_column(db.String(255))
    inputs: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True)
    created_by: Mapped[str] = mapped_column(StringUUID)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    last_run_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime, nullable=True)

    @hybrid_property
    def tenant(self):
        from models.account import Tenant

        return db.session.query(Tenant).filter(Tenant.id == self.tenant_id).first()

    @hybrid_property
    def app(self):
        from models.model import App

        return db.session.query(App).filter(App.id == self.app_id).first()

    @hybrid_property
    def workflow(self):
        from models.workflow import Workflow

        return db.session.query(Workflow).filter(Workflow.id == self.workflow_id).first()

    def to_dict(self):
        """
        Convert instance to dict
        """
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "app_id": self.app_id,
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "cron_expression": self.cron_expression,
            "timezone": self.timezone,
            "inputs": self.inputs,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
        }
