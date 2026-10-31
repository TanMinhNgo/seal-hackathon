"""judging

Revision ID: 0006_judging
Revises: 0005_submissions
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_judging"
down_revision = "0005_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publication_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "revision", name="uq_publication_revision"),
    )
    op.create_index(
        op.f("ix_publication_snapshots_round_id"),
        "publication_snapshots",
        ["round_id"],
        unique=False,
    )
    op.create_table(
        "round_judging",
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publication_revision", sa.Integer(), nullable=False),
        sa.Column("cache_revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.PrimaryKeyConstraint("round_id"),
    )
    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.CheckConstraint("weight >= 0 AND max_score > 0", name="ck_rubric_numbers"),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "order", name="uq_rubric_order"),
    )
    op.create_index(
        op.f("ix_rubric_criteria_round_id"), "rubric_criteria", ["round_id"], unique=False
    )
    op.create_table(
        "conflicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("judge_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["judge_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("judge_id", "team_id", name="uq_conflict_pair"),
    )
    op.create_index(op.f("ix_conflicts_event_id"), "conflicts", ["event_id"], unique=False)
    op.create_index(op.f("ix_conflicts_judge_id"), "conflicts", ["judge_id"], unique=False)
    op.create_index(op.f("ix_conflicts_team_id"), "conflicts", ["team_id"], unique=False)
    op.create_table(
        "mentor_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("mentor_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["mentor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mentor_assignments_event_id"), "mentor_assignments", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_mentor_assignments_mentor_id"), "mentor_assignments", ["mentor_id"], unique=False
    )
    op.create_index(
        op.f("ix_mentor_assignments_team_id"), "mentor_assignments", ["team_id"], unique=False
    )
    op.create_index(
        "uq_active_mentor_assignment",
        "mentor_assignments",
        ["mentor_id", "team_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "mentor_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("mentor_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("progress_status", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'feedback' AND progress_status IS NULL) OR "
            "(kind = 'progress' AND progress_status IN ('on_track','at_risk','blocked'))",
            name="ck_mentor_note_kind",
        ),
        sa.ForeignKeyConstraint(
            ["mentor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mentor_notes_mentor_id"), "mentor_notes", ["mentor_id"], unique=False)
    op.create_index(
        "ix_mentor_notes_team_commit", "mentor_notes", ["team_id", "commit_sha"], unique=False
    )
    op.create_index(op.f("ix_mentor_notes_team_id"), "mentor_notes", ["team_id"], unique=False)
    op.create_table(
        "mentor_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open','answered','resolved')", name="ck_mentor_question_status"
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mentor_questions_author_id"), "mentor_questions", ["author_id"], unique=False
    )
    op.create_index(
        op.f("ix_mentor_questions_team_id"), "mentor_questions", ["team_id"], unique=False
    )
    op.create_table(
        "result_emails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["publication_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "user_id", name="uq_result_email"),
    )
    op.create_index(
        op.f("ix_result_emails_snapshot_id"), "result_emails", ["snapshot_id"], unique=False
    )
    op.create_index(op.f("ix_result_emails_user_id"), "result_emails", ["user_id"], unique=False)
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("judge_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("general_comment", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','draft','submitted','cancelled')", name="ck_assignment_status"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_assignment_revision"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["judge_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assignments_event_id"), "assignments", ["event_id"], unique=False)
    op.create_index(op.f("ix_assignments_judge_id"), "assignments", ["judge_id"], unique=False)
    op.create_index(op.f("ix_assignments_round_id"), "assignments", ["round_id"], unique=False)
    op.create_index(
        op.f("ix_assignments_submission_id"), "assignments", ["submission_id"], unique=False
    )
    op.create_index(op.f("ix_assignments_team_id"), "assignments", ["team_id"], unique=False)
    op.create_index(
        "uq_active_assignment",
        "assignments",
        ["round_id", "judge_id", "team_id"],
        unique=True,
        postgresql_where=sa.text("status != 'cancelled'"),
        sqlite_where=sa.text("status != 'cancelled'"),
    )
    op.create_table(
        "mentor_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("mentor_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mentor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["mentor_questions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mentor_answers_mentor_id"), "mentor_answers", ["mentor_id"], unique=False
    )
    op.create_index(
        op.f("ix_mentor_answers_question_id"), "mentor_answers", ["question_id"], unique=False
    )
    op.create_table(
        "scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.CheckConstraint("score >= 0", name="ck_score_positive"),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["criterion_id"],
            ["rubric_criteria.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "criterion_id", name="uq_score_criterion"),
    )
    op.create_index(op.f("ix_scores_assignment_id"), "scores", ["assignment_id"], unique=False)
    op.create_index(op.f("ix_scores_criterion_id"), "scores", ["criterion_id"], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f("ix_scores_criterion_id"), table_name="scores")
    op.drop_index(op.f("ix_scores_assignment_id"), table_name="scores")
    op.drop_table("scores")
    op.drop_index(op.f("ix_mentor_answers_question_id"), table_name="mentor_answers")
    op.drop_index(op.f("ix_mentor_answers_mentor_id"), table_name="mentor_answers")
    op.drop_table("mentor_answers")
    op.drop_index(
        "uq_active_assignment",
        table_name="assignments",
        postgresql_where=sa.text("status != 'cancelled'"),
        sqlite_where=sa.text("status != 'cancelled'"),
    )
    op.drop_index(op.f("ix_assignments_team_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_submission_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_round_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_judge_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_event_id"), table_name="assignments")
    op.drop_table("assignments")
    op.drop_index(op.f("ix_result_emails_user_id"), table_name="result_emails")
    op.drop_index(op.f("ix_result_emails_snapshot_id"), table_name="result_emails")
    op.drop_table("result_emails")
    op.drop_index(op.f("ix_mentor_questions_team_id"), table_name="mentor_questions")
    op.drop_index(op.f("ix_mentor_questions_author_id"), table_name="mentor_questions")
    op.drop_table("mentor_questions")
    op.drop_index(op.f("ix_mentor_notes_team_id"), table_name="mentor_notes")
    op.drop_index("ix_mentor_notes_team_commit", table_name="mentor_notes")
    op.drop_index(op.f("ix_mentor_notes_mentor_id"), table_name="mentor_notes")
    op.drop_table("mentor_notes")
    op.drop_index(
        "uq_active_mentor_assignment",
        table_name="mentor_assignments",
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_index(op.f("ix_mentor_assignments_team_id"), table_name="mentor_assignments")
    op.drop_index(op.f("ix_mentor_assignments_mentor_id"), table_name="mentor_assignments")
    op.drop_index(op.f("ix_mentor_assignments_event_id"), table_name="mentor_assignments")
    op.drop_table("mentor_assignments")
    op.drop_index(op.f("ix_conflicts_team_id"), table_name="conflicts")
    op.drop_index(op.f("ix_conflicts_judge_id"), table_name="conflicts")
    op.drop_index(op.f("ix_conflicts_event_id"), table_name="conflicts")
    op.drop_table("conflicts")
    op.drop_index(op.f("ix_rubric_criteria_round_id"), table_name="rubric_criteria")
    op.drop_table("rubric_criteria")
    op.drop_table("round_judging")
    op.drop_index(op.f("ix_publication_snapshots_round_id"), table_name="publication_snapshots")
    op.drop_table("publication_snapshots")
    # ### end Alembic commands ###
