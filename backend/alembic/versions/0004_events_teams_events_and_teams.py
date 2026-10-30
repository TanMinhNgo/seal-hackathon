"""events and teams

Revision ID: 0004_events_teams
Revises: 0003_auth_admin
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_events_teams"
down_revision = "0003_auth_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rules", sa.Text(), nullable=False),
        sa.Column("banner_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("min_team_size", sa.Integer(), nullable=False),
        sa.Column("max_team_size", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft','open','ongoing','judging','closed')", name="ck_events_status"
        ),
        sa.CheckConstraint(
            "min_team_size >= 1 AND max_team_size >= min_team_size", name="ck_events_team_size"
        ),
        sa.CheckConstraint(
            "registration_opens_at < registration_closes_at "
            "AND registration_closes_at <= starts_at AND starts_at < ends_at",
            name="ck_events_schedule",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "prizes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.CheckConstraint("rank >= 1 AND value >= 0", name="ck_prizes_numbers"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prizes_event_id"), "prizes", ["event_id"], unique=False)
    op.create_table(
        "rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("required_judges", sa.Integer(), nullable=False),
        sa.CheckConstraint('"order" >= 1 AND required_judges >= 1', name="ck_rounds_numbers"),
        sa.CheckConstraint(
            "starts_at < submission_deadline AND submission_deadline <= ends_at",
            name="ck_rounds_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "order", name="uq_rounds_event_order"),
    )
    op.create_index(op.f("ix_rounds_event_id"), "rounds", ["event_id"], unique=False)
    op.create_table(
        "tracks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tracks_event_id"), "tracks", ["event_id"], unique=False)
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("leader_id", sa.Uuid(), nullable=False),
        sa.Column("invite_code", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repo_url", sa.String(length=2048), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disbanded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_teams_status"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["leader_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["tracks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "event_id", name="uq_teams_id_event"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_index(op.f("ix_teams_event_id"), "teams", ["event_id"], unique=False)
    op.create_index(op.f("ix_teams_leader_id"), "teams", ["leader_id"], unique=False)
    op.create_index(op.f("ix_teams_track_id"), "teams", ["track_id"], unique=False)
    op.create_table(
        "round_eligibilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("source_round_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_round_id"],
            ["rounds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "team_id", name="uq_round_eligibility"),
    )
    op.create_index(
        op.f("ix_round_eligibilities_round_id"), "round_eligibilities", ["round_id"], unique=False
    )
    op.create_index(
        op.f("ix_round_eligibilities_source_round_id"),
        "round_eligibilities",
        ["source_round_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_round_eligibilities_team_id"), "round_eligibilities", ["team_id"], unique=False
    )
    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('pending','active')", name="ck_team_members_status"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "event_id"],
            ["teams.id", "teams.event_id"],
            name="fk_team_members_team_event",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_team_members_event_user"),
    )
    op.create_index(op.f("ix_team_members_event_id"), "team_members", ["event_id"], unique=False)
    op.create_index(op.f("ix_team_members_team_id"), "team_members", ["team_id"], unique=False)
    op.create_index(op.f("ix_team_members_user_id"), "team_members", ["user_id"], unique=False)
    with op.batch_alter_table(
        "event_roles", recreate="always" if op.get_bind().dialect.name == "sqlite" else "auto"
    ) as batch:
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
        batch.create_foreign_key("fk_event_roles_event_id", "events", ["event_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("event_roles") as batch:
        batch.drop_constraint("fk_event_roles_event_id", type_="foreignkey")
        batch.drop_column("created_at")
    op.drop_index(op.f("ix_team_members_user_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_team_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_event_id"), table_name="team_members")
    op.drop_table("team_members")
    op.drop_index(op.f("ix_round_eligibilities_team_id"), table_name="round_eligibilities")
    op.drop_index(op.f("ix_round_eligibilities_source_round_id"), table_name="round_eligibilities")
    op.drop_index(op.f("ix_round_eligibilities_round_id"), table_name="round_eligibilities")
    op.drop_table("round_eligibilities")
    op.drop_index(op.f("ix_teams_track_id"), table_name="teams")
    op.drop_index(op.f("ix_teams_leader_id"), table_name="teams")
    op.drop_index(op.f("ix_teams_event_id"), table_name="teams")
    op.drop_table("teams")
    op.drop_index(op.f("ix_tracks_event_id"), table_name="tracks")
    op.drop_table("tracks")
    op.drop_index(op.f("ix_rounds_event_id"), table_name="rounds")
    op.drop_table("rounds")
    op.drop_index(op.f("ix_prizes_event_id"), table_name="prizes")
    op.drop_table("prizes")
    op.drop_table("events")
