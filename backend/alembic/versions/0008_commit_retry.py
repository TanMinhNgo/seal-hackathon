"""Track scheduled commit retries without releasing the lease."""

import sqlalchemy as sa

from alembic import op

revision = "0008_commit_retry"
down_revision = "0007_commits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commit_sync_states", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("commit_sync_states", "next_retry_at")
