"""add review_workflow to templates

Revision ID: 007
Revises: 006
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("review_workflow", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("templates", "review_workflow")
