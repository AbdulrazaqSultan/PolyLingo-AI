from unittest.mock import Mock
import pytest
from backend.app.services.model_manager import manager
from backend.app.db.session import Session
from backend.app.repositories.registry import records
from backend.app.core.config import config


def test_health_and_languages(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert {r["iso"] for r in client.get("/api/languages").json()} == {
        "ar",
        "en",
        "fr",
        "zh",
    }
    public = client.get("/api/models").text
    assert "adapter_path" not in public and "local_path" not in public


def test_translation_and_private_analytics(client, monkeypatch):
    fake = Mock()
    fake.translate.return_value = "مرحبا"
    monkeypatch.setattr(manager, "get", lambda db, row: fake)
    response = client.post(
        "/api/translate", json={"text": "Hello", "source": "en", "target": "ar"}
    )
    assert response.status_code == 200
    assert response.json()["translated_text"] == "مرحبا"
    from backend.app.models.database_models import Event

    with Session() as db:
        event = db.query(Event).order_by(Event.id.desc()).first()
        assert event.source == "en" and not hasattr(event, "text")


def test_unsupported_language(client):
    assert (
        client.post(
            "/api/translate", json={"text": "hello", "source": "xx", "target": "ar"}
        ).status_code
        == 422
    )


def test_validation_does_not_echo_secret(client):
    response = client.post(
        "/api/admin/login", json={"username": [], "password": "private-value"}
    )
    assert response.status_code == 422 and "private-value" not in response.text


def test_empty_text(client):
    assert (
        client.post(
            "/api/translate", json={"text": " ", "source": "en", "target": "ar"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "route",
    ["dashboard", "models", "providers", "languages", "routing", "logs", "settings"],
)
def test_admin_protected(client, route):
    assert client.get("/api/admin/" + route).status_code == 401


def test_login_csrf_logout(client):
    assert (
        client.post(
            "/api/admin/login", json={"username": "admin", "password": "wrong"}
        ).status_code
        == 401
    )
    login = client.post(
        "/api/admin/login", json={"username": "admin", "password": "test-password-only"}
    )
    assert login.status_code == 200
    assert (
        "HttpOnly" in login.headers["set-cookie"]
        and "SameSite=strict" in login.headers["set-cookie"]
    )
    opts = client.get("/api/admin/settings").json()
    assert client.patch("/api/admin/settings", json=opts).status_code == 403
    client.headers["X-CSRF-Token"] = login.json()["csrf"]
    assert client.post("/api/admin/logout").status_code == 200
    assert client.get("/api/admin/models").status_code == 401


def test_fallback_routing(admin, monkeypatch):
    models = admin.get("/api/admin/models").json()
    primary = next(m for m in models if m["model_type"] == "translation")
    other = {k: v for k, v in primary.items() if k != "id"}
    other.update(name="Fallback", default=False)
    fallback = admin.post("/api/admin/models", json=other).json()
    rule = admin.post(
        "/api/admin/routing",
        json={
            "source": "en",
            "target": "ar",
            "model_id": primary["id"],
            "fallback_model_id": fallback["id"],
            "enabled": True,
        },
    )
    assert rule.status_code == 200

    def provider(db, row):
        fake = Mock()
        if row.id == primary["id"]:
            fake.translate.side_effect = RuntimeError("private stack")
        else:
            fake.translate.return_value = "مرحبا"
        return fake

    monkeypatch.setattr(manager, "get", provider)
    response = admin.post(
        "/api/translate", json={"text": "hello", "source": "en", "target": "ar"}
    )
    assert response.json()["fallback_used"] is True
    assert response.json()["provider"] == "Fallback"
    assert "private stack" not in admin.get("/api/admin/logs").text


def test_encrypted_provider_and_ssrf(admin, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setattr(config, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(config, "allowed_provider_hosts", "api.example.com")
    data = {
        "name": "API",
        "provider_type": "custom_http",
        "base_url": "https://api.example.com/v1",
        "model_name": "x",
        "api_key": "secret-api-key",
    }
    response = admin.post("/api/admin/providers", json=data)
    assert response.status_code == 200 and "secret-api-key" not in response.text
    assert "secret-api-key" not in admin.get("/api/admin/providers").text
    with Session() as db:
        saved = records(db, "providers")[0]
        assert saved.secret and "secret-api-key" not in saved.secret
        assert "api_key" not in saved.data
    data["base_url"] = "http://127.0.0.1:8000"
    assert admin.post("/api/admin/providers", json=data).status_code == 422


def test_invalid_upload(client):
    response = client.post(
        "/api/speech/transcribe", files={"file": ("evil.txt", b"bad", "text/plain")}
    )
    assert response.status_code == 415


def test_language_edit_is_public(admin):
    data = {
        "name": "German",
        "native": "Deutsch",
        "iso": "de",
        "nllb": "deu_Latn",
        "stt": "de",
        "tts": "de-DE",
        "direction": "ltr",
        "enabled": True,
    }
    response = admin.post("/api/admin/languages", json=data)
    assert response.status_code == 200
    assert any(r["iso"] == "de" for r in admin.get("/api/languages").json())
    admin.patch(
        "/api/admin/languages/" + str(response.json()["id"]), json={"enabled": False}
    )
    assert not any(r["iso"] == "de" for r in admin.get("/api/languages").json())


def test_maintenance(admin):
    opts = admin.get("/api/admin/settings").json()
    admin.patch("/api/admin/settings", json={**opts, "maintenance": True})
    try:
        assert (
            admin.post(
                "/api/translate", json={"text": "hi", "source": "en", "target": "ar"}
            ).status_code
            == 503
        )
    finally:
        admin.patch("/api/admin/settings", json={**opts, "maintenance": False})


def test_failure_is_safe_and_counted(client, monkeypatch):
    from backend.app.models.database_models import Event

    fake = Mock()
    fake.translate.side_effect = RuntimeError("sensitive internal path and key")
    monkeypatch.setattr(manager, "get", lambda db, row: fake)
    response = client.post(
        "/api/translate", json={"text": "hello", "source": "en", "target": "ar"}
    )
    assert response.status_code == 503 and "sensitive" not in response.text
    with Session() as db:
        assert not db.query(Event).order_by(Event.id.desc()).first().success


def test_synthesis_audio_response(client, monkeypatch):
    class Voice:
        async def synthesize(self, *args):
            return b"test-mp3-bytes"

    monkeypatch.setattr(manager, "get", lambda db, row: Voice())
    response = client.post(
        "/api/speech/synthesize", json={"text": "hello", "language": "en"}
    )
    assert (
        response.status_code == 200 and response.headers["content-type"] == "audio/mpeg"
    )
    assert (
        response.content == b"test-mp3-bytes" and "x-synthesis-ms" in response.headers
    )


def test_synthesis_error_is_safe(client, monkeypatch):
    class Voice:
        async def synthesize(self, *args):
            raise RuntimeError("private-api-key")

    monkeypatch.setattr(manager, "get", lambda db, row: Voice())
    response = client.post(
        "/api/speech/synthesize", json={"text": "hello", "language": "en"}
    )
    assert response.status_code == 503 and "private-api-key" not in response.text


def test_admin_dashboard(admin):
    response = admin.get("/api/admin/dashboard")
    assert response.status_code == 200
    assert "requests_by_day" in response.json() and "active_models" in response.json()


def test_bad_login_rate_limit(client):
    from backend.app.api.admin import attempts

    attempts.clear()
    try:
        for _ in range(5):
            assert (
                client.post(
                    "/api/admin/login", json={"username": "admin", "password": "bad"}
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/admin/login", json={"username": "admin", "password": "bad"}
            ).status_code
            == 429
        )
    finally:
        attempts.clear()


def test_audio_decode_and_transcribe(client, monkeypatch):
    pytest.importorskip("av")
    import io, wave

    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    fake = Mock()
    fake.transcribe.return_value = {"text": "hello", "language": "en"}
    monkeypatch.setattr(manager, "get", lambda db, row: fake)
    response = client.post(
        "/api/speech/transcribe",
        files={"file": ("voice.wav", stream.getvalue(), "audio/wav")},
    )
    assert response.status_code == 200 and response.json()["language"] == "en"


def test_malformed_audio(client):
    pytest.importorskip("av")
    response = client.post(
        "/api/speech/transcribe",
        files={"file": ("voice.wav", b"not audio", "audio/wav")},
    )
    assert response.status_code == 422
