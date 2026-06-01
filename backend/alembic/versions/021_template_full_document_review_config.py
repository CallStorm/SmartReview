"""add full_document_review_config to templates

Revision ID: 021
Revises: 020
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("full_document_review_config", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("templates", "full_document_review_config")
