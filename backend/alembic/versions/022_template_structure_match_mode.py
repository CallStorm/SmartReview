# backend/alembic/versions/022_template_structure_match_mode.py
"""add structure_match_mode to templates

Revision ID: 022
Revises: 021
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column(
            "structure_match_mode",
            sa.String(length=16),
            nullable=False,
            server_default="exact",
        ),
    )


def downgrade() -> None:
    op.drop_column("templates", "structure_match_mode")
