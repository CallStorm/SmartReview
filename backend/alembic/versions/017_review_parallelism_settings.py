"""review runtime parallelism settings

Revision ID: 017
Revises: 016
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_runtime_settings",
        sa.Column("worker_parallel_tasks", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("compilation_basis_concurrency", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("context_consistency_concurrency", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("content_concurrency", sa.Integer(), nullable=False, server_default="4"),
    )


def downgrade() -> None:
    op.drop_column("review_runtime_settings", "content_concurrency")
    op.drop_column("review_runtime_settings", "context_consistency_concurrency")
    op.drop_column("review_runtime_settings", "compilation_basis_concurrency")
    op.drop_column("review_runtime_settings", "worker_parallel_tasks")
