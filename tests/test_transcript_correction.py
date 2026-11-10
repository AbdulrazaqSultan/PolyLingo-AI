import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.app.db.session import Session
from backend.app.repositories.registry import records, settings
from backend.app.services.transcript_correction_service import (
    TranscriptCorrectionService,
)
from backend.app.ai.transcript_correction.base import CorrectionCandidate
from backend.app.core.errors import ServiceError


@contextmanager
def options(**changes):
    with Session() as db:
        row = records(db, "settings")[0]
        original = dict(row.data)
        row.data = {**settings(db), **changes}
        db.commit()
        try:
            yield db
        finally:
            row.data = original
            db.commit()


def correct(db, text, language, provider=None):
    return asyncio.run(
        TranscriptCorrectionService(provider).correct(db, text, language)
    )


@pytest.mark.parametrize(
    "language,text",
    [
        ("ar", "أنا أدرس الذكاء الاصطناعي في الجامعة"),
        ("en", "Please meet Alice at 10:30 on 2026-11-10."),
        ("fr", "Je travaille avec Marie à Paris."),
        ("zh", "我今天学习人工智能。"),
        ("ar", "اسم المستخدم حالب"),
        ("ar", "الخادم بحير"),
    ],
)
def test_clean_or_uncertain_transcript_is_preserved(client, language, text):
    with options() as db:
        result = correct(db, text, language)
    assert result["raw_transcript"] == result["corrected_transcript"] == text
    assert not result["correction_applied"]


@pytest.mark.parametrize(
    "language,raw,expected",
    [
        ("ar", "مرحباً حالب هل أنت بحير", "مرحباً، كيف حالك؟ هل أنت بخير؟"),
        (
            "ar",
            "السلام عليكم حالكم هل أنتم بحير",
            "السلام عليكم، كيف حالكم؟ هل أنتم بخير؟",
        ),
        ("ar", "هل أنت بحير اليوم", "هل أنت بخير اليوم"),
        ("en", "how our you", "How are you?"),
        ("fr", "comment aller vous", "Comment allez-vous ?"),
        ("zh", "你好   世界", "你好 世界"),
    ],
)
def test_contextual_rules_are_language_specific(client, language, raw, expected):
    with options() as db:
        result = correct(db, raw, language)
    assert result["corrected_transcript"] == expected
    assert result["raw_transcript"] == raw
    assert result["correction_applied"]
    assert result["changed_spans"]


def test_provider_failure_falls_back_to_exact_raw(client):
    class Broken:
        async def correct(self, *args):
            raise RuntimeError("private key and stack")

    raw = "hello   world"
    with options() as db:
        result = correct(db, raw, "en", Broken())
    assert result["correction_status"] == "fallback"
    assert result["corrected_transcript"] == raw


def test_timeout_falls_back(client):
    class Slow:
        async def correct(self, *args):
            await asyncio.sleep(1)
            return CorrectionCandidate("changed")

    with options(correction_timeout=0.01) as db:
        result = correct(db, "hello", "en", Slow())
    assert result["correction_status"] == "fallback"


@pytest.mark.parametrize(
    "raw,candidate,language",
    [
        ("Meet Alice at 10.", "Meet Alicia at 11.", "en"),
        ("قابل علي الساعة ١٠", "قابل على الساعة ١١", "ar"),
        ("أقابل علي اليوم", "أقابل على اليوم", "ar"),
        ("email me at a@example.com", "email me at b@example.com", "en"),
        ("Visit https://example.com/api_v2", "Visit https://other.com/api_v3", "en"),
        ("Use CUDA_12 on 2026-11-10", "Use CUDA_13 on 2026-11-11", "en"),
        ("run `x = 2` now", "run `x = 3` now", "en"),
        ("hello there", "مرحبا بك", "en"),
        ("how are you", "I am fine thank you", "en"),
        ("I met bob yesterday", "I met Bill yesterday", "en"),
        ("hello world", "hello wonderful world", "en"),
        ("Use C++ today", "Use C today", "en"),
        ("Use C# today", "Use C today", "en"),
        ("Use .NET today", "Use NET today", "en"),
        ("Call /api/v1 now", "Call api/v1 now", "en"),
        ('Say "how our you" exactly', 'Say "how are you" exactly', "en"),
        ("run pip --upgrade", "run pip upgrade", "en"),
    ],
)
def test_untrusted_correction_cannot_change_sensitive_content_or_translate(
    client, raw, candidate, language
):
    class Untrusted:
        async def correct(self, *args):
            return CorrectionCandidate(candidate, 1.0)

    with options() as db:
        result = correct(db, raw, language, Untrusted())
    assert result["corrected_transcript"] == raw
    assert result["correction_status"] == "fallback"


def test_chinese_punctuation_preserves_all_characters(client):
    class Punctuation:
        async def correct(self, *args):
            return CorrectionCandidate("你好，你今天怎么样？")

    with options() as db:
        result = correct(db, "你好你今天怎么样", "zh", Punctuation())
    assert result["corrected_transcript"] == "你好，你今天怎么样？"


def test_disabled_language_and_high_threshold_keep_raw(client):
    with options(correction_languages=["en"]) as db:
        assert correct(db, "how our you", "fr")["correction_status"] == "disabled"
    with options(correction_confidence_threshold=1) as db:
        assert correct(db, "how our you", "en")["corrected_transcript"] == "how our you"


def mocks(
    monkeypatch,
    raw="how our you",
    detected="en",
    tts_failure=False,
    translation_failure=False,
):
    import backend.app.services.voice_pipeline as pipeline

    async def asr(*args):
        return {"text": raw, "language": detected, "stt_ms": 12}

    translator = Mock(
        return_value={
            "translated_text": "translated result",
            "provider": "PolyLingo test",
            "translation_ms": 14,
        }
    )
    if translation_failure:
        translator.side_effect = ServiceError("Translation model is unavailable.")

    async def tts(*args):
        if tts_failure:
            raise ServiceError(
                "Speech generation is unavailable. Text translation is still available."
            )
        return b"mp3-bytes"

    monkeypatch.setattr(pipeline, "transcribe", asr)
    monkeypatch.setattr(pipeline, "translate", translator)
    monkeypatch.setattr(pipeline, "synthesize", tts)
    return translator


def post(client, **kwargs):
    return client.post(
        "/api/speech/translate",
        files={"file": ("sample.wav", b"mock", "audio/wav")},
        data=kwargs,
    )


def test_voice_pipeline_auto_translates_corrected_text_and_keeps_raw(
    client, monkeypatch
):
    translator = mocks(monkeypatch, "مرحباً حالب هل أنت بحير", "ar")
    response = post(client, target="en", generate_voice="true")
    assert response.status_code == 200
    data = response.json()
    assert data["raw_transcript"] == "مرحباً حالب هل أنت بحير"
    assert data["corrected_transcript"] == "مرحباً، كيف حالك؟ هل أنت بخير؟"
    assert translator.call_count == 1
    assert translator.call_args.args[1].text == data["corrected_transcript"]
    assert data["translation_status"] == "complete" and data["tts_status"] == "complete"
    assert data["audio_url"].startswith("data:audio/mpeg;base64,")
    assert set(data["timings"]) == {
        "asr_ms",
        "correction_ms",
        "translation_ms",
        "tts_ms",
        "total_ms",
    }


@pytest.mark.parametrize(
    "detected,target,raw",
    [
        ("en", "ar", "how our you"),
        ("fr", "en", "comment aller vous"),
        ("zh", "ar", "你好世界"),
    ],
)
def test_detected_language_drives_correction_and_translation(
    client, monkeypatch, detected, target, raw
):
    translator = mocks(monkeypatch, raw, detected)
    data = post(client, target=target).json()
    assert data["detected_language"] == detected
    assert translator.call_args.args[1].source == detected


def test_empty_transcript_does_not_translate(client, monkeypatch):
    translator = mocks(monkeypatch, "", "en")
    assert post(client, target="ar").status_code == 422
    translator.assert_not_called()


def test_same_language_does_not_translate(client, monkeypatch):
    translator = mocks(monkeypatch)
    data = post(client, target="en").json()
    assert data["translation_status"] == "same_language"
    translator.assert_not_called()


def test_correction_failure_still_translates_raw(client, monkeypatch):
    import backend.app.services.voice_pipeline as pipeline

    class Broken:
        async def correct(self, *args):
            raise ValueError("private")

    translator = mocks(monkeypatch, "how our you")
    monkeypatch.setattr(
        pipeline, "correction_service", TranscriptCorrectionService(Broken())
    )
    data = post(client, target="ar").json()
    assert data["correction_status"] == "fallback"
    assert translator.call_args.args[1].text == "how our you"
    assert data["translated_text"]


def test_tts_failure_retains_translation(client, monkeypatch):
    mocks(monkeypatch, tts_failure=True)
    data = post(client, target="ar", generate_voice="true").json()
    assert (
        data["tts_status"] == "error" and data["translated_text"] == "translated result"
    )
    assert data["corrected_transcript"] == "How are you?"


def test_translation_failure_retains_transcripts(client, monkeypatch):
    mocks(monkeypatch, translation_failure=True)
    data = post(client, target="ar").json()
    assert data["translation_status"] == "error" and data["raw_transcript"]
    assert data["corrected_transcript"] == "How are you?"


def test_manual_voice_mode_stops_after_correction(client, monkeypatch):
    translator = mocks(monkeypatch)
    with options(auto_translate_voice=False):
        data = post(client, target="ar").json()
    assert data["translation_status"] == "manual"
    assert data["corrected_transcript"] == "How are you?"
    translator.assert_not_called()


def test_stream_has_real_ordered_pipeline_stages(client, monkeypatch):
    import json

    mocks(monkeypatch)
    response = client.post(
        "/api/speech/translate?stream=true",
        files={"file": ("sample.wav", b"mock", "audio/wav")},
        data={"target": "ar", "generate_voice": "true"},
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e["stage"] for e in events if e["event"] == "stage"] == [
        "transcribing",
        "correcting",
        "translating",
        "synthesizing",
    ]
    assert [e["event"] for e in events].count("result") == 1
    assert next(
        i for i, e in enumerate(events) if e["event"] == "raw_transcript"
    ) < next(i for i, e in enumerate(events) if e.get("stage") == "correcting")
    assert client.get("/api/health").json()["capacity"]["active_requests"] == 0


def test_admin_correction_settings_are_validated_and_private(admin):
    opts = admin.get("/api/admin/settings").json()
    assert opts["transcript_correction_provider"] == "hybrid"
    assert (
        admin.patch(
            "/api/admin/settings", json={**opts, "correction_api_provider_id": 987654}
        ).status_code
        == 422
    )
    assert (
        admin.patch(
            "/api/admin/settings", json={**opts, "correction_confidence_threshold": 1.5}
        ).status_code
        == 422
    )
    assert "correction_api_provider_id" not in admin.get("/api/config").json()


def test_external_correction_uses_allowlist_timeout_and_server_credentials(
    client, monkeypatch
):
    import json
    import httpx
    import backend.app.ai.transcript_correction.llm_provider as module
    from backend.app.ai.transcript_correction.llm_provider import LLMCorrectionProvider
    from backend.app.core.config import config
    from cryptography.fernet import Fernet
    from backend.app.core.security import encrypt

    monkeypatch.setattr(config, "allowed_provider_hosts", "correction.example.com")
    monkeypatch.setattr(config, "encryption_key", Fernet.generate_key().decode())
    provider = SimpleNamespace(
        data={
            "base_url": "https://correction.example.com/v1",
            "provider_type": "openai_compatible",
            "model_name": "corrector",
            "timeout": 20,
        },
        secret=encrypt("private-api-key"),
    )
    captured = []

    def handler(request):
        captured.append(request)
        assert request.headers["authorization"] == "Bearer private-api-key"
        assert b"private-api-key" not in request.content
        assert request.extensions["timeout"]["read"] == 3
        body = json.loads(request.content)
        assert "Source ISO language: en" in body["messages"][0]["content"]
        assert body["temperature"] == 0
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "How are you?"}}]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = asyncio.run(
        LLMCorrectionProvider(provider, "corrector", 3).correct("how our you", "en")
    )
    assert result.text == "How are you?" and result.confidence is None
    provider.data["base_url"] = "http://127.0.0.1:8000"
    with pytest.raises(ValueError):
        asyncio.run(
            LLMCorrectionProvider(provider, "corrector", 3).correct("hello", "en")
        )
    assert len(captured) == 1


def test_stream_capacity_is_held_until_pipeline_finishes(client, monkeypatch):
    import concurrent.futures
    import threading
    import anyio
    import backend.app.api.public as public

    condition = threading.Condition()
    release = threading.Event()
    entered = 0

    async def pipeline(*args):
        nonlocal entered
        yield {"event": "stage", "stage": "transcribing"}
        with condition:
            entered += 1
            condition.notify_all()
        await anyio.to_thread.run_sync(lambda: release.wait(5))
        yield {"event": "result", "data": {"translated_text": "done"}}

    monkeypatch.setattr(public, "voice_events", pipeline)

    def request():
        return client.post(
            "/api/speech/translate?stream=true",
            files={"file": ("test.wav", b"mock", "audio/wav")},
            data={"target": "ar"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses = [pool.submit(request) for _ in range(4)]
        try:
            with condition:
                assert condition.wait_for(lambda: entered == 4, timeout=3)
            assert request().status_code == 429
            assert client.get("/api/health").json()["capacity"]["active_requests"] == 4
        finally:
            release.set()
        assert all(
            response.result(timeout=3).status_code == 200 for response in responses
        )
    assert client.get("/api/health").json()["capacity"]["active_requests"] == 0


def test_unexpected_tts_failure_still_preserves_result(client, monkeypatch):
    import backend.app.services.voice_pipeline as pipeline

    mocks(monkeypatch)

    async def broken(*args):
        raise RuntimeError("private stack")

    monkeypatch.setattr(pipeline, "synthesize", broken)
    data = post(client, target="ar", generate_voice="true").json()
    assert data["translated_text"] and data["tts_status"] == "error"
    assert "private" not in data["tts_error"]
