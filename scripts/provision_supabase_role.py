"""Provision the fixed least-privilege Supabase runtime login without printing secrets."""

from dataclasses import dataclass

from mask_api.config import Settings, get_settings
from mask_api.database import create_db_engine
from mask_api.persistence.targets import database_endpoint
from sqlalchemy import make_url, text
from sqlalchemy.engine import Connection

APPLICATION_ROLE = "mask_app"


@dataclass(frozen=True)
class RoleState:
    can_login: bool
    is_superuser: bool
    can_create_database: bool
    can_create_role: bool
    can_inherit: bool

    @property
    def is_restricted(self) -> bool:
        return (
            self.can_login
            and not self.is_superuser
            and not self.can_create_database
            and not self.can_create_role
            and not self.can_inherit
        )


def _role_state(connection: Connection) -> RoleState | None:
    row = connection.execute(
        text(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit "
            "FROM pg_roles WHERE rolname = :role"
        ),
        {"role": APPLICATION_ROLE},
    ).one_or_none()
    return (
        RoleState(
            can_login=bool(row[0]),
            is_superuser=bool(row[1]),
            can_create_database=bool(row[2]),
            can_create_role=bool(row[3]),
            can_inherit=bool(row[4]),
        )
        if row is not None
        else None
    )


def _create_role(connection: Connection, password: str) -> None:
    connection.execute(
        text("SELECT set_config('mask.provision_password', :password, true)"),
        {"password": password},
    )
    connection.execute(
        text(
            """
            DO $$
            BEGIN
              EXECUTE format(
                'CREATE ROLE mask_app WITH LOGIN PASSWORD %L '
                'NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
                current_setting('mask.provision_password')
              );
              PERFORM set_config('mask.provision_password', '', true);
            END $$
            """
        )
    )


def _rotate_role_password(connection: Connection, password: str) -> None:
    """Rotate only the secret after separately verifying least-privilege flags."""
    connection.execute(
        text("SELECT set_config('mask.provision_password', :password, true)"),
        {"password": password},
    )
    connection.execute(
        text(
            """
            DO $$
            BEGIN
              EXECUTE format(
                'ALTER ROLE mask_app PASSWORD %L',
                current_setting('mask.provision_password')
              );
              PERFORM set_config('mask.provision_password', '', true);
            END $$
            """
        )
    )


def provision_application_role(settings: Settings) -> str:
    if settings.database_target != "supabase" or settings.migration_database_url is None:
        raise ValueError("Supabase role provisioning requires the Supabase database target")
    application_url = settings.database_url.get_secret_value()
    password = make_url(application_url).password
    endpoint = database_endpoint(settings.database_url)
    if endpoint.role != APPLICATION_ROLE or password is None or len(password) < 20:
        raise ValueError("The Supabase application URL needs a strong mask_app password")

    migration_engine = create_db_engine(settings, migration=True)
    try:
        with migration_engine.begin() as connection:
            state = _role_state(connection)
            if state is not None and not state.is_restricted:
                raise RuntimeError("Existing mask_app role is not least privilege")
            if state is None:
                _create_role(connection, password)
                result = "created"
            else:
                _rotate_role_password(connection, password)
                result = "rotated"
    finally:
        migration_engine.dispose()

    application_engine = create_db_engine(settings)
    try:
        with application_engine.connect() as connection:
            if connection.scalar(text("SELECT current_user")) != APPLICATION_ROLE:
                raise RuntimeError("Supabase application role verification failed")
            state = _role_state(connection)
            if state is None or not state.is_restricted:
                raise RuntimeError("Supabase application role verification failed")
    finally:
        application_engine.dispose()
    return result


def main() -> int:
    try:
        result = provision_application_role(get_settings())
    except Exception:
        print(
            "Supabase role provisioning BLOCKED. Verify the two private TLS URLs, "
            "project state, and migration privileges. No credential was printed."
        )
        return 1
    print(
        "Supabase restricted runtime role created and verified."
        if result == "created"
        else "Supabase runtime role credential rotated and verified."
    )
    print("Next: run pnpm migrate, then pnpm check:services.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
