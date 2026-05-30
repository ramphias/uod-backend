"""initial schema — instances, instance_relations, audit_log, harvest_jobs

Revision ID: 001_initial
Revises:
Create Date: 2026-05-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instances",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("layer", sa.String(), nullable=False),
        sa.Column("label_zh", sa.String()),
        sa.Column("label_en", sa.String()),
        sa.Column("data", JSONB(), nullable=False, server_default="{}"),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_url", sa.String()),
        sa.Column("source_id", sa.String()),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("status", sa.String(), nullable=False, server_default="candidate"),
        sa.Column(
            "harvested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("verified_by", sa.String()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('candidate','accepted','rejected','archived')",
            name="ck_instances_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_instances_confidence_range",
        ),
    )
    op.create_index("ix_instances_type", "instances", ["type"])
    op.create_index("ix_instances_layer", "instances", ["layer"])
    op.create_index("ix_instances_status", "instances", ["status"])
    op.create_index("ix_instances_label_en_trgm", "instances", ["label_en"])
    op.create_index("ix_instances_label_zh_trgm", "instances", ["label_zh"])

    op.create_table(
        "instance_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_instance_id",
            sa.String(),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_id", sa.String(), nullable=False),
        sa.Column(
            "target_instance_id",
            sa.String(),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_instance_id",
            "relation_id",
            "target_instance_id",
            name="uq_instance_relation_triple",
        ),
    )
    op.create_index("ix_instance_relations_source", "instance_relations", ["source_instance_id"])
    op.create_index("ix_instance_relations_target", "instance_relations", ["target_instance_id"])
    op.create_index("ix_instance_relations_relation", "instance_relations", ["relation_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.String()),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("before", JSONB()),
        sa.Column("after", JSONB()),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action IN ('create','update','verify','reject','delete')",
            name="ck_audit_log_action",
        ),
    )
    op.create_index("ix_audit_log_instance_id", "audit_log", ["instance_id"])

    op.create_table(
        "harvest_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("target_class", sa.String(), nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("candidates", sa.Integer(), server_default="0"),
        sa.Column("accepted", sa.Integer(), server_default="0"),
        sa.Column("rejected", sa.Integer(), server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.String()),
        sa.CheckConstraint(
            "status IN ('pending','running','done','failed')",
            name="ck_harvest_jobs_status",
        ),
    )
    op.create_index("ix_harvest_jobs_target_class", "harvest_jobs", ["target_class"])


def downgrade() -> None:
    op.drop_index("ix_harvest_jobs_target_class", table_name="harvest_jobs")
    op.drop_table("harvest_jobs")
    op.drop_index("ix_audit_log_instance_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_instance_relations_relation", table_name="instance_relations")
    op.drop_index("ix_instance_relations_target", table_name="instance_relations")
    op.drop_index("ix_instance_relations_source", table_name="instance_relations")
    op.drop_table("instance_relations")
    op.drop_index("ix_instances_label_zh_trgm", table_name="instances")
    op.drop_index("ix_instances_label_en_trgm", table_name="instances")
    op.drop_index("ix_instances_status", table_name="instances")
    op.drop_index("ix_instances_layer", table_name="instances")
    op.drop_index("ix_instances_type", table_name="instances")
    op.drop_table("instances")
