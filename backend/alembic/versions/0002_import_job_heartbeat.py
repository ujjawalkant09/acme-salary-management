"""import job heartbeat

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("import_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("import_jobs", schema=None) as batch_op:
        batch_op.drop_column("heartbeat_at")
