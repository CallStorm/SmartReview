"""add review_audit_finding table

Revision ID: 027
Revises: 026
Create Date: 2026-08-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_audit_finding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("node_title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("check_item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("check_item_text", sa.Text(), nullable=False),
        sa.Column("finding_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("adjudicated_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("adjudicated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_audit_finding_task_id"), "review_audit_finding", ["task_id"])
    op.create_index(op.f("ix_review_audit_finding_status"), "review_audit_finding", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_review_audit_finding_status"), table_name="review_audit_finding")
    op.drop_index(op.f("ix_review_audit_finding_task_id"), table_name="review_audit_finding")
    op.drop_table("review_audit_finding")
