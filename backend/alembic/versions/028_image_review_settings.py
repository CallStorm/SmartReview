"""image review settings and template image rules

Revision ID: 028
Revises: 027
Create Date: 2026-08-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("model_provider_settings") as batch:
        batch.add_column(
            sa.Column("image_review_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("image_review_model", sa.String(length=256), nullable=False, server_default=""))
        batch.add_column(sa.Column("image_review_max_side", sa.Integer(), nullable=False, server_default="1536"))
        batch.add_column(
            sa.Column("image_review_max_per_node", sa.Integer(), nullable=False, server_default="10")
        )
    with op.batch_alter_table("templates") as batch:
        batch.add_column(sa.Column("image_review_rules", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("templates") as batch:
        batch.drop_column("image_review_rules")
    with op.batch_alter_table("model_provider_settings") as batch:
        batch.drop_column("image_review_max_per_node")
        batch.drop_column("image_review_max_side")
        batch.drop_column("image_review_model")
        batch.drop_column("image_review_enabled")
