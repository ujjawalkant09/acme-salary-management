"""indexes for recent salary changes and the job-title filter

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_salary_records_created", "salary_records", ["created_at", "id"])
    op.create_index("ix_employees_job_title_lower", "employees", [sa.text("lower(job_title)")])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_employees_job_title_lower", table_name="employees")
    op.drop_index("ix_salary_records_created", table_name="salary_records")
