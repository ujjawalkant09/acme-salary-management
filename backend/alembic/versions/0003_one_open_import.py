"""one open import at a time

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPEN = "status IN ('queued', 'validating', 'validated', 'commit_queued', 'committing')"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "uq_import_jobs_one_open",
        "import_jobs",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text(OPEN),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_import_jobs_one_open", table_name="import_jobs")
