"""who added each user, and when

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25 19:27:21.681252

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Users from before this migration (the seeded demo accounts) keep NULL for both.
    op.add_column("users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_created_by_users", "users", "users", ["created_by"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_users_created_by_users", "users", type_="foreignkey")
    op.drop_column("users", "created_by")
    op.drop_column("users", "created_at")
