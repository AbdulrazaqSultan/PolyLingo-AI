import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///" + str(
    Path(tempfile.mkdtemp(prefix="polylingo-test-")) / "test.db"
)
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import Session
from backend.app.models.database_models import (
    Record,
    Event,
    OperationalLog,
    AdminSession,
)
from backend.app.core.config import config
from backend.app.core.security import passwords
from backend.app.services.model_manager import manager


@pytest.fixture
def client(monkeypatch):
    config.admin_password_hash = passwords.hash("test-password-only")
    with TestClient(app) as client:
        with Session() as db:
            from backend.app.repositories.registry import records

            for kind in ["routing", "providers"]:
                for r in records(db, kind):
                    db.delete(r)
            db.commit()
        yield client


@pytest.fixture
def admin(client):
    response = client.post(
        "/api/admin/login", json={"username": "admin", "password": "test-password-only"}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client
