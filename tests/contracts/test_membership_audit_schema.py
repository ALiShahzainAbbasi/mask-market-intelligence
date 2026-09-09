"""Offline role-administration audit migration checks."""

import subprocess
import sys
from pathlib import Path

from mask_api.modules.identity.auth_models import IdentitySecurityEvent
from mask_api.modules.identity.domain import IdentityEventType
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION

ROOT = Path(__file__).resolve().parents[2]


def migration_sql(*arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *arguments, "--sql"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_role_audit_metadata_and_migration_are_scoped_and_reversible() -> None:
    assert EXPECTED_SCHEMA_REVISION == "0006"
    assert IdentityEventType.ROLES_CHANGED.value == "roles_changed"
    table = IdentitySecurityEvent.__table__
    assert table.c.subject_user_id.nullable
    assert not table.c.details_json.nullable
    assert {constraint.name for constraint in table.constraints} >= {
        "fk_identity_event_subject",
        "ck_identity_event_details_object",
        "ck_identity_event_type",
    }
    upgrade = migration_sql("upgrade", "0005:0006")
    downgrade = migration_sql("downgrade", "0006:0005")
    assert "ADD COLUMN subject_user_id UUID" in upgrade
    assert "ADD COLUMN details_json JSONB" in upgrade
    assert "roles_changed" in upgrade
    assert "GRANT DELETE ON mask.user_roles TO mask_app" in upgrade
    assert "cannot downgrade while role-change audit events exist" in downgrade
    assert "DROP COLUMN details_json" in downgrade
    assert "DROP COLUMN subject_user_id" in downgrade
