"""add review_log to scheme_review_tasks

Revision ID: 008
Revises: 007
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheme_review_tasks",
        sa.Column("review_log", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheme_review_tasks", "review_log")
