"""add onboarding_completed to preferences

Revision ID: 0002_onboarding
Revises: f402f3909114
Create Date: 2026-05-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_onboarding"
down_revision: Union[str, Sequence[str], None] = "f402f3909114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "onboarding_completed",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("onboarding_completed")
