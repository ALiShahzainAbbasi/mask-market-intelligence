"""Add atomic membership-role audit details and the required role privilege."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "identity_security_events",
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        schema="mask",
    )
    op.add_column(
        "identity_security_events",
        sa.Column(
            "details_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="mask",
    )
    op.create_foreign_key(
        "fk_identity_event_subject",
        "identity_security_events",
        "users",
        ["organization_id", "subject_user_id"],
        ["organization_id", "id"],
        source_schema="mask",
        referent_schema="mask",
    )
    op.create_check_constraint(
        "ck_identity_event_details_object",
        "identity_security_events",
        "jsonb_typeof(details_json) = 'object'",
        schema="mask",
    )
    op.drop_constraint(
        "ck_identity_event_type", "identity_security_events", schema="mask", type_="check"
    )
    op.create_check_constraint(
        "ck_identity_event_type",
        "identity_security_events",
        "event_type IN ('owner_bootstrapped', 'login_succeeded', 'login_failed', "
        "'login_throttled', 'session_rotated', 'session_revoked', 'roles_changed')",
        schema="mask",
    )
    op.execute("GRANT DELETE ON mask.user_roles TO mask_app")


def downgrade() -> None:
    # Never silently discard role-change audit evidence to satisfy a downgrade.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM mask.identity_security_events WHERE event_type = 'roles_changed'
          ) THEN
            RAISE EXCEPTION 'cannot downgrade while role-change audit events exist';
          END IF;
        END $$
        """
    )
    op.execute("REVOKE DELETE ON mask.user_roles FROM mask_app")
    op.drop_constraint(
        "ck_identity_event_type", "identity_security_events", schema="mask", type_="check"
    )
    op.create_check_constraint(
        "ck_identity_event_type",
        "identity_security_events",
        "event_type IN ('owner_bootstrapped', 'login_succeeded', 'login_failed', "
        "'login_throttled', 'session_rotated', 'session_revoked')",
        schema="mask",
    )
    op.drop_constraint(
        "ck_identity_event_details_object",
        "identity_security_events",
        schema="mask",
        type_="check",
    )
    op.drop_constraint(
        "fk_identity_event_subject",
        "identity_security_events",
        schema="mask",
        type_="foreignkey",
    )
    op.drop_column("identity_security_events", "details_json", schema="mask")
    op.drop_column("identity_security_events", "subject_user_id", schema="mask")
