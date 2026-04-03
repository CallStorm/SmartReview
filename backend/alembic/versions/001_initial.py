"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)

    op.create_table(
        "scheme_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("business_code", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scheme_types_business_code"), "scheme_types", ["business_code"], unique=True
    )

    op.create_table(
        "basis_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("basis_id", sa.String(length=64), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("standard_no", sa.String(length=128), nullable=False),
        sa.Column("doc_name", sa.String(length=512), nullable=False),
        sa.Column("effect_status", sa.String(length=64), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column("scheme_category", sa.String(length=255), nullable=False),
        sa.Column("scheme_name", sa.String(length=255), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_basis_items_basis_id"), "basis_items", ["basis_id"], unique=True)
    op.create_index(op.f("ix_basis_items_standard_no"), "basis_items", ["standard_no"], unique=False)

    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_type_id", sa.Integer(), nullable=False),
        sa.Column("minio_bucket", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("parsed_structure", sa.Text(), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_ts, nullable=True),
        sa.ForeignKeyConstraint(["scheme_type_id"], ["scheme_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_templates_scheme_type_id"), "templates", ["scheme_type_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_templates_scheme_type_id"), table_name="templates")
    op.drop_table("templates")
    op.drop_index(op.f("ix_basis_items_standard_no"), table_name="basis_items")
    op.drop_index(op.f("ix_basis_items_basis_id"), table_name="basis_items")
    op.drop_table("basis_items")
    op.drop_index(op.f("ix_scheme_types_business_code"), table_name="scheme_types")
    op.drop_table("scheme_types")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
