"""drop minimax_group_id from model_provider_settings

Revision ID: 006
Revises: 005
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("model_provider_settings", "minimax_group_id")


def downgrade() -> None:
    op.add_column(
        "model_provider_settings",
        sa.Column("minimax_group_id", sa.String(length=128), nullable=False, server_default=""),
    )
