"""template image review missing text

Revision ID: 029
Revises: 028
Create Date: 2026-08-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("templates") as batch:
        batch.add_column(sa.Column("image_review_missing_text", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("templates") as batch:
        batch.drop_column("image_review_missing_text")
