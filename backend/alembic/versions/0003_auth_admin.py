"""Password reset, event roles and audit logs."""

import sqlalchemy as sa

from alembic import op

revision = "0003_auth_admin"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])
    op.create_table(
        "event_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.UniqueConstraint("user_id", "event_id", "role", name="uq_event_roles_user_event_role"),
        sa.CheckConstraint(
            "role IN ('organizer', 'judge', 'mentor', 'participant')", name="ck_event_roles_role"
        ),
    )
    op.create_index("ix_event_roles_user_id", "event_roles", ["user_id"])
    op.create_index("ix_event_roles_event_id", "event_roles", ["event_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for column in ("actor_id", "action", "created_at"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("event_roles")
    op.drop_table("password_reset_tokens")
