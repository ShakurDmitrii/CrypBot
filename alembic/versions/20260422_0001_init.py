"""init

Revision ID: 20260422_0001
Revises:
Create Date: 2026-04-22 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260422_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

request_status_enum = sa.Enum(
    "new",
    "waiting_payment",
    "payment_received",
    "processing",
    "done",
    "canceled",
    "disputed",
    name="request_status",
)
aml_status_enum = sa.Enum("pending", "low", "medium", "high", "rejected", name="aml_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "exchange_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="telegram"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("direction", sa.String(length=64), nullable=False),
        sa.Column("amount_send", sa.Float(), nullable=False),
        sa.Column("amount_receive", sa.Float(), nullable=False),
        sa.Column("base_rate", sa.Float(), nullable=False),
        sa.Column("margin_percent", sa.Float(), nullable=False),
        sa.Column("final_rate", sa.Float(), nullable=False),
        sa.Column("user_requisites", sa.Text(), nullable=True),
        sa.Column("exchange_requisites", sa.Text(), nullable=True),
        sa.Column("status", request_status_enum, nullable=False, server_default="new"),
        sa.Column("status_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exchange_requests_user_id", "exchange_requests", ["user_id"], unique=False)

    op.create_table(
        "request_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("exchange_requests.id"), nullable=False),
        sa.Column("status", request_status_enum, nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_request_status_history_request_id",
        "request_status_history",
        ["request_id"],
        unique=False,
    )

    op.create_table(
        "aml_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("exchange_requests.id"), nullable=True),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("check_type", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("status", aml_status_enum, nullable=False, server_default="pending"),
        sa.Column("result_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_aml_checks_request_id", "aml_checks", ["request_id"], unique=False)
    op.create_index("ix_aml_checks_telegram_user_id", "aml_checks", ["telegram_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_aml_checks_telegram_user_id", table_name="aml_checks")
    op.drop_index("ix_aml_checks_request_id", table_name="aml_checks")
    op.drop_table("aml_checks")

    op.drop_index("ix_request_status_history_request_id", table_name="request_status_history")
    op.drop_table("request_status_history")

    op.drop_index("ix_exchange_requests_user_id", table_name="exchange_requests")
    op.drop_table("exchange_requests")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
