"""review_stage, review_result_json, output_object_key on scheme_review_tasks

Revision ID: 009
Revises: 008
Create Date: 2026-04-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheme_review_tasks",
        sa.Column("review_stage", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("review_result_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "scheme_review_tasks",
        sa.Column("output_object_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheme_review_tasks", "output_object_key")
    op.drop_column("scheme_review_tasks", "review_result_json")
    op.drop_column("scheme_review_tasks", "review_stage")
