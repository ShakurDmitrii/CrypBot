"""support chat messages

Revision ID: 20260503_0004
Revises: 20260427_0003
Create Date: 2026-05-03 21:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260503_0004"
down_revision: Union[str, Sequence[str], None] = "20260427_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sender_role", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("operator_telegram_id", sa.Integer(), nullable=True),
        sa.Column("is_read_by_user", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_read_by_operator", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_support_messages_user_id", "support_messages", ["user_id"], unique=False)
    op.create_index("ix_support_messages_created_at", "support_messages", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_support_messages_created_at", table_name="support_messages")
    op.drop_index("ix_support_messages_user_id", table_name="support_messages")
    op.drop_table("support_messages")
