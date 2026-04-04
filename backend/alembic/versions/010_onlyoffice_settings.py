"""onlyoffice_settings table

Revision ID: 010
Revises: 009
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "onlyoffice_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("docs_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("jwt_secret", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("callback_base_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("editor_lang", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("onlyoffice_settings")
