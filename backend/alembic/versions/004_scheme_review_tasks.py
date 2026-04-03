"""scheme_review_tasks for async plan review jobs

Revision ID: 004
Revises: 003
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "scheme_review_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_type_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("minio_bucket", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.ForeignKeyConstraint(["scheme_type_id"], ["scheme_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scheme_review_tasks_scheme_type_id"),
        "scheme_review_tasks",
        ["scheme_type_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_scheme_review_tasks_user_id"), "scheme_review_tasks", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scheme_review_tasks_user_id"), table_name="scheme_review_tasks")
    op.drop_index(op.f("ix_scheme_review_tasks_scheme_type_id"), table_name="scheme_review_tasks")
    op.drop_table("scheme_review_tasks")
