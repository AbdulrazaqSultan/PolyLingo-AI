import asyncio
import tempfile
import time
import anyio
from pathlib import Path
from fastapi import HTTPException, UploadFile
from backend.app.core.config import config
from backend.app.core.errors import ServiceError
from backend.app.repositories.registry import settings, records
from backend.app.services.model_manager import manager
from backend.app.services.translation_service import language

MIME = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/webm",
    "video/webm",
    "audio/ogg",
    "audio/flac",
}


async def transcribe(db, upload: UploadFile, source=None):
    if settings(db)["maintenance"]:
        raise HTTPException(503, "Service is paused for maintenance.")
    if upload.content_type not in MIME:
        raise HTTPException(415, "Unsupported audio file type.")
    selected = language(db, source) if source else None
    max_samples = settings(db)["max_audio_seconds"] * 16000
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="polylingo-") as directory:
        path = Path(directory) / "input.audio"
        size = 0
        with path.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > config.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Audio exceeds the upload size limit.")
                out.write(chunk)

        def run():
            import av

            try:
                with av.open(str(path)) as container:
                    if not container.streams.audio:
                        raise ValueError("no audio")
                # Decode at a low sample rate under a strict sample budget, including unknown-duration containers.
                with av.open(str(path)) as container:
                    resampler = av.AudioResampler(
                        format="s16", layout="mono", rate=16000
                    )
                    samples = 0
                    for frame in container.decode(audio=0):
                        for converted in resampler.resample(frame):
                            samples += converted.samples
                            if samples > max_samples:
                                raise HTTPException(
                                    422, "Audio exceeds the configured duration limit."
                                )
                if samples == 0:
                    raise ValueError("empty audio")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(422, "Invalid or unreadable audio.") from None
            try:
                with manager.execution():
                    model = manager.default(db, "stt")
                    result = manager.get(db, model).transcribe(
                        str(path), selected["stt"] if selected else None
                    )
            except ServiceError:
                raise
            except Exception:
                raise ServiceError(
                    "Speech recognition is unavailable. Check the Whisper model and dependencies."
                ) from None
            detected = next(
                (
                    r
                    for r in records(db, "languages")
                    if r.data["stt"] == result["language"] and r.data["enabled"]
                ),
                None,
            )
            if not detected:
                raise HTTPException(422, "Detected speech language is not enabled.")
            result["language"] = detected.data["iso"]
            result["stt_ms"] = round((time.perf_counter() - start) * 1000, 1)
            return result

        return await anyio.to_thread.run_sync(run)


async def synthesize(db, request):
    if settings(db)["maintenance"]:
        raise HTTPException(503, "Service is paused for maintenance.")
    if len(request.text) > settings(db)["max_text_length"]:
        raise HTTPException(422, "Text exceeds the configured limit.")
    lang = language(db, request.language)

    def acquire_provider():
        with manager.execution():
            return manager.get(db, manager.default(db, "tts"))

    provider = await anyio.to_thread.run_sync(acquire_provider)
    try:
        return await asyncio.wait_for(
            provider.synthesize(request.text, lang, request.voice, request.speed),
            timeout=45,
        )
    except ServiceError:
        raise
    except Exception:
        raise ServiceError(
            "Speech generation is unavailable. Text translation is still available."
        ) from None
