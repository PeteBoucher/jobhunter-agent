"""Add is_approved column to user table.

New users default to False (unapproved) so sign-ups are gated.
Existing rows get server_default=true so current users keep access.

Revision ID: a1b2c3d4e5f6
Revises: 03e39dd3f7ed
Create Date: 2026-03-09
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "03e39dd3f7ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="true" so all existing rows (current approved users) get True.
    # New rows created by auth_router explicitly set is_approved=False.
    op.add_column(
        "user",
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "is_approved")
