"""dashboard runtime settings

Revision ID: 012
Revises: 011
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "dashboard_runtime_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("refresh_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("dashboard_runtime_settings")
