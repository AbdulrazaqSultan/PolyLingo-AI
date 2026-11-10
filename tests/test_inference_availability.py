import concurrent.futures
import io
import threading
import time
import wave
from unittest.mock import Mock

import pytest

from backend.app.core.config import config
from backend.app.core.errors import ServiceError
from backend.app.services.model_manager import ModelManager, manager


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_documentation_aliases(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.history[0].status_code == 307
    assert response.url.path == "/api" + path


def test_swagger_schema_works_through_api_proxy(client):
    assert "/api/openapi.json" in client.get("/api/docs").text
    schema = client.get("/api/openapi.json")
    assert schema.status_code == 200
    assert "/api/translate" in schema.json()["paths"]


def test_model_queue_wait_is_bounded_and_recovers(monkeypatch):
    model_manager = ModelManager()
    acquired = threading.Event()
    release = threading.Event()

    def hold_lock():
        with model_manager.lock:
            acquired.set()
            release.wait(5)

    worker = threading.Thread(target=hold_lock)
    worker.start()
    try:
        assert acquired.wait(2)
        monkeypatch.setattr(config, "inference_queue_timeout", 0.03)
        start = time.monotonic()
        with pytest.raises(ServiceError, match="still processing"):
            with model_manager.execution():
                pytest.fail("The occupied model lock must not be acquired.")
        assert time.monotonic() - start < 1
    finally:
        release.set()
        worker.join(2)
    with model_manager.execution():
        pass


def test_missing_whisper_does_not_download_or_block_translation(
    client, monkeypatch, tmp_path
):
    import faster_whisper
    import faster_whisper.utils
    import backend.app.services.model_manager as module

    # A failed download can leave a valid snapshot directory without its weights.
    resolver = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(faster_whisper.utils, "download_model", resolver)
    constructor = Mock()
    monkeypatch.setattr(faster_whisper, "WhisperModel", constructor)
    translation = Mock()
    translation.translate.return_value = "Bonjour"
    monkeypatch.setattr(module, "LocalNLLBProvider", lambda spec: translation)
    for key, value in [("loaded", None), ("instance", None), ("status", "idle")]:
        monkeypatch.setattr(manager, key, value)

    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    body = {"text": "Hello", "source": "en", "target": "fr"}
    assert client.post("/api/translate", json=body).status_code == 200
    resident = manager.loaded
    response = client.post(
        "/api/speech/transcribe",
        files={
            "file": ("voice.wav", audio.getvalue(), "audio/wav"),
        },
    )
    assert response.status_code == 503
    assert "not installed" in response.json()["detail"]
    assert resolver.call_args.kwargs["local_files_only"] is True
    constructor.assert_not_called()
    assert manager.loaded == resident
    assert manager.instance is translation
    response = client.post(
        "/api/translate",
        json={
            "text": "Hello",
            "source": "en",
            "target": "fr",
        },
    )
    assert response.status_code == 200
    assert response.json()["translated_text"] == "Bonjour"
    assert client.get("/api/health").json()["capacity"]["active_requests"] == 0


def test_busy_capacity_recovers_after_requests_complete(client, monkeypatch):
    import backend.app.api.public as public

    condition = threading.Condition()
    release = threading.Event()
    entered = 0

    def blocked_translation(db, body):
        nonlocal entered
        with condition:
            entered += 1
            condition.notify_all()
        assert release.wait(5)
        return {"translated_text": "Bonjour"}

    monkeypatch.setattr(public, "translate", blocked_translation)
    body = {"text": "Hello", "source": "en", "target": "fr"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        requests = [
            pool.submit(client.post, "/api/translate", json=body) for _ in range(4)
        ]
        try:
            with condition:
                assert condition.wait_for(lambda: entered == 4, timeout=3)
            rejected = client.post("/api/translate", json=body)
            assert rejected.status_code == 429
            assert rejected.headers["retry-after"] == "5"
            assert client.get("/api/health").json()["capacity"]["active_requests"] == 4
        finally:
            release.set()
        assert all(request.result(timeout=3).status_code == 200 for request in requests)
    assert client.get("/api/health").json()["capacity"]["active_requests"] == 0
    assert client.post("/api/translate", json=body).status_code == 200
