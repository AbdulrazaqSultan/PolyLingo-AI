import asyncio
import time
import json
from io import BytesIO
from starlette.datastructures import Headers
from fastapi.responses import StreamingResponse
from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    Form,
    Response,
    HTTPException,
    Request,
)
from backend.app.core.config import config
from backend.app.db.session import get_db, Session
from backend.app.repositories.registry import records, settings
from backend.app.schemas.api import Translation, Synthesis
from backend.app.services.translation_service import translate
from backend.app.services.speech_service import transcribe, synthesize
from backend.app.services.model_manager import manager
from backend.app.services.voice_pipeline import voice_events
from backend.app.schemas.speech import SpeechTranslationResult
from backend.app.core.errors import ServiceError

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "inference": manager.health(),
        "version": config.version,
        "capacity": {
            "active_requests": request.app.state.in_flight,
            "limit": 4,
            "queue_timeout_seconds": config.inference_queue_timeout,
        },
    }


@router.get("/languages")
def languages(db=Depends(get_db)):
    return [r.data for r in records(db, "languages") if r.data["enabled"]]


@router.get("/models")
def models(db=Depends(get_db)):
    return [
        {
            "name": r.data["name"],
            "model_type": r.data["model_type"],
            "default": r.data["default"],
            "languages": r.data["languages"],
        }
        for r in records(db, "models")
        if r.data["enabled"]
    ]


@router.get("/config")
def public_config(db=Depends(get_db)):
    return {
        key: value
        for key, value in settings(db).items()
        if key
        not in (
            "correction_api_provider_id",
            "correction_model_id",
            "correction_timeout",
            "correction_confidence_threshold",
        )
    }


@router.post("/translate")
def translation(body: Translation, db=Depends(get_db)):
    return translate(db, body)


@router.post("/speech/transcribe")
async def transcription(
    file: UploadFile = File(...), source: str | None = Form(None), db=Depends(get_db)
):
    return await transcribe(db, file, source or None)


@router.post("/speech/synthesize")
async def synthesis(body: Synthesis, db=Depends(get_db)):
    start = time.perf_counter()
    audio = await synthesize(db, body)
    return Response(
        audio,
        media_type="audio/mpeg",
        headers={
            "X-Synthesis-Ms": str(round((time.perf_counter() - start) * 1000, 1)),
            "Cache-Control": "no-store",
        },
    )


@router.get("/speech/voices")
async def voices(language: str, db=Depends(get_db)):
    from backend.app.services.translation_service import language as get_language

    lang = get_language(db, language)
    import edge_tts

    try:
        available = await asyncio.wait_for(edge_tts.list_voices(), timeout=15)
        return [
            {"id": v["ShortName"], "name": v["FriendlyName"]}
            for v in available
            if v["Locale"] == lang["tts"]
        ]
    except Exception:
        raise HTTPException(503, "Voice catalog is unavailable.") from None


@router.post("/speech/translate", response_model=SpeechTranslationResult)
async def speech_translation(
    file: UploadFile = File(...),
    source: str | None = Form(None),
    target: str = Form(..., min_length=2, max_length=16),
    generate_voice: bool = Form(False),
    voice: str | None = Form(None, max_length=100),
    speed: int = Form(0, ge=-50, le=50),
    stream: bool = False,
    db=Depends(get_db),
):
    from backend.app.services.translation_service import language
    from backend.app.services.speech_service import MIME

    language(db, target)
    if source:
        language(db, source)
    if file.content_type not in MIME:
        raise HTTPException(415, "Unsupported audio file type.")
    # Own the bounded upload beyond the route lifetime, including streamed responses.
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > config.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, "Audio exceeds the upload size limit.")
    owned = UploadFile(
        BytesIO(content),
        filename="speech.audio",
        headers=Headers({"content-type": file.content_type}),
    )

    async def events():
        try:
            with Session() as pipeline_db:
                async for event in voice_events(
                    pipeline_db,
                    owned,
                    source or None,
                    target,
                    generate_voice,
                    voice,
                    speed,
                ):
                    yield event
        except (ServiceError, HTTPException) as error:
            if not stream:
                raise
            yield {
                "event": "error",
                "detail": error.message
                if isinstance(error, ServiceError)
                else str(error.detail),
            }
        except Exception:
            if not stream:
                raise
            yield {
                "event": "error",
                "detail": "The speech request could not be completed. Please retry.",
            }
        finally:
            await owned.close()

    if stream:

        async def chunks():
            async for event in events():
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(
            chunks(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )
    result = None
    async for event in events():
        if event["event"] == "result":
            result = event["data"]
    return result
