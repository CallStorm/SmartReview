"""model_provider_settings for LLM vendor config

Revision ID: 005
Revises: 004
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "model_provider_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("default_provider", sa.String(length=32), nullable=True),
        sa.Column("volcengine_base_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("volcengine_api_key", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("volcengine_endpoint_id", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("minimax_base_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("minimax_api_key", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("minimax_group_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("minimax_model", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("model_provider_settings")
