"""add deepseek columns to model_provider_settings

Revision ID: 020
Revises: 019
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_provider_settings",
        sa.Column(
            "deepseek_base_url",
            sa.String(length=512),
            nullable=False,
            server_default="https://api.deepseek.com",
        ),
    )
    op.add_column(
        "model_provider_settings",
        sa.Column("deepseek_api_key", sa.String(length=2048), nullable=False, server_default=""),
    )
    op.add_column(
        "model_provider_settings",
        sa.Column("deepseek_model", sa.String(length=256), nullable=False, server_default="deepseek-v4-flash"),
    )


def downgrade() -> None:
    op.drop_column("model_provider_settings", "deepseek_model")
    op.drop_column("model_provider_settings", "deepseek_api_key")
    op.drop_column("model_provider_settings", "deepseek_base_url")
