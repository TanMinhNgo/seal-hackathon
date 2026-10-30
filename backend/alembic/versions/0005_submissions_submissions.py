"""submissions

Revision ID: 0005_submissions
Revises: 0004_events_teams
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_submissions"
down_revision = "0004_events_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deadline_reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "round_id", "hours", name="uq_deadline_reminder"),
    )
    op.create_index(
        op.f("ix_deadline_reminders_round_id"), "deadline_reminders", ["round_id"], unique=False
    )
    op.create_index(
        op.f("ix_deadline_reminders_team_id"), "deadline_reminders", ["team_id"], unique=False
    )
    op.create_table(
        "file_uploads",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        op.f("ix_file_uploads_created_at"), "file_uploads", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_file_uploads_team_id"), "file_uploads", ["team_id"], unique=False)
    op.create_index(
        op.f("ix_file_uploads_uploaded_by"), "file_uploads", ["uploaded_by"], unique=False
    )
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("repo_url", sa.String(length=2048), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("demo_url", sa.String(length=2048), nullable=True),
        sa.Column("video_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_submission_version"),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submitted_by", "team_id", "round_id", "idempotency_key", name="uq_submission_receipt"
        ),
        sa.UniqueConstraint("team_id", "round_id", "version", name="uq_submission_version"),
    )
    op.create_index(op.f("ix_submissions_round_id"), "submissions", ["round_id"], unique=False)
    op.create_index(
        op.f("ix_submissions_submitted_by"), "submissions", ["submitted_by"], unique=False
    )
    op.create_index(op.f("ix_submissions_team_id"), "submissions", ["team_id"], unique=False)
    op.create_table(
        "submission_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_submission_files_submission_id"),
        "submission_files",
        ["submission_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_submission_files_submission_id"), table_name="submission_files")
    op.drop_table("submission_files")
    op.drop_index(op.f("ix_submissions_team_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_submitted_by"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_round_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_index(op.f("ix_file_uploads_uploaded_by"), table_name="file_uploads")
    op.drop_index(op.f("ix_file_uploads_team_id"), table_name="file_uploads")
    op.drop_index(op.f("ix_file_uploads_created_at"), table_name="file_uploads")
    op.drop_table("file_uploads")
    op.drop_index(op.f("ix_deadline_reminders_team_id"), table_name="deadline_reminders")
    op.drop_index(op.f("ix_deadline_reminders_round_id"), table_name="deadline_reminders")
    op.drop_table("deadline_reminders")
