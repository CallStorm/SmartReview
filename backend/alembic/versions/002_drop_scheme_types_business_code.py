"""drop scheme_types.business_code

Revision ID: 002
Revises: 001
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_scheme_types_business_code"), table_name="scheme_types")
    op.drop_column("scheme_types", "business_code")


def downgrade() -> None:
    op.add_column(
        "scheme_types",
        sa.Column("business_code", sa.String(length=64), nullable=True),
    )
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "mysql":
        conn.execute(sa.text("UPDATE scheme_types SET business_code = CONCAT('legacy-', CAST(id AS CHAR))"))
    else:
        conn.execute(sa.text("UPDATE scheme_types SET business_code = 'legacy-' || CAST(id AS TEXT)"))
    with op.batch_alter_table("scheme_types") as batch_op:
        batch_op.alter_column(
            "business_code",
            existing_type=sa.String(length=64),
            nullable=False,
        )
    op.create_index(
        op.f("ix_scheme_types_business_code"),
        "scheme_types",
        ["business_code"],
        unique=True,
    )
