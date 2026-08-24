"""review runtime llm settings (disable_reasoning / max tokens / text cap)

Revision ID: 030
Revises: 029
Create Date: 2026-08-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("review_runtime_settings") as batch:
        batch.add_column(
            sa.Column("disable_reasoning", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(
            sa.Column("llm_max_output_tokens", sa.Integer(), nullable=False, server_default="32768")
        )
        batch.add_column(
            sa.Column("content_text_cap_chars", sa.Integer(), nullable=False, server_default="16000")
        )


def downgrade() -> None:
    with op.batch_alter_table("review_runtime_settings") as batch:
        batch.drop_column("content_text_cap_chars")
        batch.drop_column("llm_max_output_tokens")
        batch.drop_column("disable_reasoning")
