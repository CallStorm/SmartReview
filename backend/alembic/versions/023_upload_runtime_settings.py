"""upload runtime settings

Revision ID: 023
Revises: 022
Create Date: 2026-08-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "upload_runtime_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("max_upload_mb", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("upload_runtime_settings")
