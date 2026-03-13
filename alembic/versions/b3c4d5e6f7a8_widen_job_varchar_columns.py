"""Widen jobs table VARCHAR(255) columns to TEXT.

title, company, department, location, and company_industry had a 255-char
limit which caused StringDataRightTruncation errors when Greenhouse returned
long department or location strings.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-13
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ["title", "company", "department", "location", "company_industry"]


def upgrade() -> None:
    for col in _COLUMNS:
        op.alter_column(
            "jobs",
            col,
            type_=sa.Text(),
            existing_type=sa.String(255),
            existing_nullable=True,
        )


def downgrade() -> None:
    for col in _COLUMNS:
        op.alter_column(
            "jobs",
            col,
            type_=sa.String(255),
            existing_type=sa.Text(),
            existing_nullable=True,
        )
