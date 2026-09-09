"""Move application tables into a private schema for managed PostgreSQL."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = (
    "organizations",
    "users",
    "user_roles",
    "markets",
    "market_definition_versions",
    "market_hypotheses",
    "research_plans",
    "jobs",
    "worker_heartbeats",
    "user_credentials",
    "server_sessions",
    "identity_security_events",
)


def _revoke_supabase_data_api_roles() -> None:
    # These roles exist on Supabase but not necessarily on a native PostgreSQL
    # development instance. The private schema is backend-only in both cases.
    op.execute(
        """
        DO $$
        DECLARE role_name text;
        BEGIN
          FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role']
          LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
              EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA mask FROM %I', role_name);
              EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA mask REVOKE ALL ON TABLES FROM %I',
                role_name
              );
            END IF;
          END LOOP;
        END $$
        """
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS mask")
    op.execute("REVOKE ALL ON SCHEMA mask FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA mask TO mask_app")
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" SET SCHEMA mask')
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA mask FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA mask REVOKE ALL ON TABLES FROM PUBLIC")
    _revoke_supabase_data_api_roles()


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f'ALTER TABLE mask."{table}" SET SCHEMA public')
    op.execute("DROP SCHEMA mask")
