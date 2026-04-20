"""add dataset-name prefix filter in knowledge_base_settings

Revision ID: 019
Revises: 018
Create Date: 2026-04-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base_settings",
        sa.Column("dify_dataset_name_prefix", sa.String(length=255), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("knowledge_base_settings", "dify_dataset_name_prefix")
