"""add template_prompt_history table

Revision ID: 026
Revises: 025
Create Date: 2026-08-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "template_prompt_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("node_title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("old_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("changed_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_template_prompt_history_template_id"),
        "template_prompt_history",
        ["template_id"],
    )
    op.create_index(
        op.f("ix_template_prompt_history_node_id"),
        "template_prompt_history",
        ["node_id"],
    )
    op.create_index(
        op.f("ix_template_prompt_history_changed_at"),
        "template_prompt_history",
        ["changed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_template_prompt_history_changed_at"), table_name="template_prompt_history"
    )
    op.drop_index(
        op.f("ix_template_prompt_history_node_id"), table_name="template_prompt_history"
    )
    op.drop_index(
        op.f("ix_template_prompt_history_template_id"), table_name="template_prompt_history"
    )
    op.drop_table("template_prompt_history")
