"""numeric money fields

Revision ID: 20260427_0003
Revises: 20260423_0002
Create Date: 2026-04-27 14:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260427_0003"
down_revision: Union[str, Sequence[str], None] = "20260423_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exchange_requests", recreate="auto") as batch_op:
        batch_op.alter_column(
            "amount_send",
            existing_type=sa.Float(),
            type_=sa.Numeric(24, 8),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "amount_receive",
            existing_type=sa.Float(),
            type_=sa.Numeric(24, 8),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "base_rate",
            existing_type=sa.Float(),
            type_=sa.Numeric(24, 8),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "margin_percent",
            existing_type=sa.Float(),
            type_=sa.Numeric(10, 4),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "final_rate",
            existing_type=sa.Float(),
            type_=sa.Numeric(24, 8),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("exchange_requests", recreate="auto") as batch_op:
        batch_op.alter_column(
            "amount_send",
            existing_type=sa.Numeric(24, 8),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "amount_receive",
            existing_type=sa.Numeric(24, 8),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "base_rate",
            existing_type=sa.Numeric(24, 8),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "margin_percent",
            existing_type=sa.Numeric(10, 4),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "final_rate",
            existing_type=sa.Numeric(24, 8),
            type_=sa.Float(),
            existing_nullable=False,
        )
