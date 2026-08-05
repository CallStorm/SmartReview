"""add content_review_rules to templates

Revision ID: 024
Revises: 023
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("content_review_rules", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("templates", "content_review_rules")
