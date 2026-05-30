"""ORM models for the instance store.

Schema mirrors what we defined in the architecture review:
- instances           : the entity rows themselves
- instance_relations  : typed edges between instances (Link Type)
- audit_log           : append-only history of every write
- harvest_jobs        : one row per worker invocation

All timestamps are UTC. All textual identifiers are case-sensitive.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String, nullable=False, index=True)
    label_zh: Mapped[str | None] = mapped_column(String)
    label_en: Mapped[str | None] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)

    # provenance
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String)
    source_id: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    # lifecycle
    status: Mapped[str] = mapped_column(String, nullable=False, default="candidate")
    harvested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    verified_by: Mapped[str | None] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    relations_out: Mapped[list[InstanceRelation]] = relationship(
        "InstanceRelation",
        foreign_keys="InstanceRelation.source_instance_id",
        back_populates="source_instance",
        cascade="all, delete-orphan",
    )
    relations_in: Mapped[list[InstanceRelation]] = relationship(
        "InstanceRelation",
        foreign_keys="InstanceRelation.target_instance_id",
        back_populates="target_instance",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate','accepted','rejected','archived')",
            name="ck_instances_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_instances_confidence_range",
        ),
        Index("ix_instances_status", "status"),
        Index("ix_instances_label_en_trgm", "label_en"),
        Index("ix_instances_label_zh_trgm", "label_zh"),
    )


class InstanceRelation(Base):
    __tablename__ = "instance_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_instance_id: Mapped[str] = mapped_column(
        String, ForeignKey("instances.id", ondelete="CASCADE"), nullable=False
    )
    relation_id: Mapped[str] = mapped_column(String, nullable=False)
    target_instance_id: Mapped[str] = mapped_column(
        String, ForeignKey("instances.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source_instance: Mapped[Instance] = relationship(
        "Instance", foreign_keys=[source_instance_id], back_populates="relations_out"
    )
    target_instance: Mapped[Instance] = relationship(
        "Instance", foreign_keys=[target_instance_id], back_populates="relations_in"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_instance_id",
            "relation_id",
            "target_instance_id",
            name="uq_instance_relation_triple",
        ),
        Index("ix_instance_relations_source", "source_instance_id"),
        Index("ix_instance_relations_target", "target_instance_id"),
        Index("ix_instance_relations_relation", "relation_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[str | None] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('create','update','verify','reject','delete')",
            name="ck_audit_log_action",
        ),
    )


class HarvestJob(Base):
    __tablename__ = "harvest_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    target_class: Mapped[str] = mapped_column(String, nullable=False, index=True)
    query: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','done','failed')",
            name="ck_harvest_jobs_status",
        ),
    )
