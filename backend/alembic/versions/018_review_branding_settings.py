"""review branding settings

Revision ID: 018
Revises: 017
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_runtime_settings",
        sa.Column("system_name", sa.String(length=100), nullable=False, server_default="智能方案审核"),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("brand_logo_object_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("brand_logo_content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("favicon_object_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "review_runtime_settings",
        sa.Column("favicon_content_type", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("review_runtime_settings", "favicon_content_type")
    op.drop_column("review_runtime_settings", "favicon_object_key")
    op.drop_column("review_runtime_settings", "brand_logo_content_type")
    op.drop_column("review_runtime_settings", "brand_logo_object_key")
    op.drop_column("review_runtime_settings", "system_name")
