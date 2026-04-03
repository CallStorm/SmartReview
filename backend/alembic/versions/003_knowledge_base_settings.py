"""knowledge_base_settings table for Dify config

Revision ID: 003
Revises: 002
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "knowledge_base_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dify_base_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("dify_api_key", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_base_settings")
