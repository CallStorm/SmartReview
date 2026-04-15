"""add duration and token usage fields to review tasks

Revision ID: 014
Revises: 013
Create Date: 2026-04-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheme_review_tasks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("input_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("total_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheme_review_tasks", "total_tokens")
    op.drop_column("scheme_review_tasks", "output_tokens")
    op.drop_column("scheme_review_tasks", "input_tokens")
    op.drop_column("scheme_review_tasks", "duration_ms")
    op.drop_column("scheme_review_tasks", "finished_at")
    op.drop_column("scheme_review_tasks", "started_at")
