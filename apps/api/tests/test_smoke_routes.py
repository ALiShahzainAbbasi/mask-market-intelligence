from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mask_api.config import Settings
from mask_api.main import create_app
from mask_api.modules.smoke.errors import SmokeNotFound, SmokeUnavailable
from mask_api.modules.smoke.services import SmokeService
from mask_api.modules.smoke.wiring import get_smoke_service


@pytest.mark.parametrize(
    "failure,status",
    [(SmokeNotFound("Missing"), 404), (SmokeUnavailable("private driver details"), 500)],
)
def test_lookup_preserves_safe_error_contract(failure: Exception, status: int) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+psycopg://localhost/test",
        enable_dev_routes=True,
        dev_token="x" * 40,
    )
    service = Mock(spec=SmokeService)
    service.get.side_effect = failure
    app = create_app(settings)
    app.dependency_overrides[get_smoke_service] = lambda: service
    with TestClient(app) as client:
        response = client.get("/dev/jobs/" + str(uuid4()), headers={"X-Dev-Token": "x" * 40})
    assert response.status_code == status
    assert "private" not in response.text
    assert response.headers["x-correlation-id"]
