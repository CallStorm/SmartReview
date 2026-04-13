"""dashboard summary snapshots

Revision ID: 011
Revises: 010
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "dashboard_summary_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("window_days", name="uq_dashboard_summary_window_days"),
    )


def downgrade() -> None:
    op.drop_table("dashboard_summary_snapshots")
