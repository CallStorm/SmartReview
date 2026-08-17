"""add review_result_cache table

Revision ID: 025
Revises: 024
Create Date: 2026-08-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_result_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=32), nullable=False),
        sa.Column("template_node_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_result_cache_fingerprint"),
        "review_result_cache",
        ["fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_review_result_cache_fingerprint"), table_name="review_result_cache"
    )
    op.drop_table("review_result_cache")
