"""One request orchestrates speech, conservative refinement, translation and voice."""

import base64
from functools import partial
import time
import anyio
from fastapi import HTTPException
from backend.app.core.errors import ServiceError
from backend.app.schemas.api import Translation, Synthesis
from backend.app.schemas.speech import SpeechTranslationResult, SpeechTimings
from backend.app.repositories.registry import settings
from backend.app.services.speech_service import transcribe, synthesize
from backend.app.services.translation_service import translate
from backend.app.services.transcript_correction_service import correction_service


async def voice_events(
    db, upload, source, target, generate_voice=False, voice=None, speed=0
):
    start = time.perf_counter()
    yield {"event": "stage", "stage": "transcribing"}
    asr = await transcribe(db, upload, source)
    raw = asr["text"]
    detected = asr["language"]
    if not raw.strip():
        raise ServiceError("No speech was detected. Try a clearer recording.", 422)
    yield {
        "event": "raw_transcript",
        "data": {
            "raw_transcript": raw,
            "detected_language": detected,
            "stt_ms": asr["stt_ms"],
        },
    }
    yield {"event": "stage", "stage": "correcting"}
    correction = await correction_service.correct(
        db, raw, detected, asr_confidence=asr.get("confidence")
    )
    result = SpeechTranslationResult(
        **correction,
        detected_language=detected,
        language=detected,
        source=detected,
        target=target,
        text=correction["corrected_transcript"],
        stt_ms=asr["stt_ms"],
    )
    result.timings = SpeechTimings(
        asr_ms=asr["stt_ms"], correction_ms=correction["correction_ms"]
    )
    yield {"event": "transcript", "data": result.model_dump()}
    if detected == target:
        result.translation_status = "same_language"
    elif not settings(db)["auto_translate_voice"]:
        result.translation_status = "manual"
    else:
        yield {"event": "stage", "stage": "translating"}
        try:
            translated = await anyio.to_thread.run_sync(
                partial(
                    translate,
                    db,
                    Translation(
                        text=result.corrected_transcript,
                        source=detected,
                        target=target,
                        mode="speech",
                    ),
                )
            )
            result.translated_text = translated["translated_text"]
            result.provider = translated["provider"]
            result.fallback_used = translated.get("fallback_used", False)
            result.translation_ms = translated["translation_ms"]
            result.timings.translation_ms = translated["translation_ms"]
            result.translation_status = "complete"
        except (ServiceError, HTTPException) as error:
            result.translation_status = "error"
            result.error = (
                error.message if isinstance(error, ServiceError) else str(error.detail)
            )
        except Exception:
            result.translation_status = "error"
            result.error = "Translation model is unavailable. Ask the administrator to check model health."
        if result.translation_status == "complete":
            yield {"event": "translation", "data": result.model_dump()}
            if generate_voice:
                yield {"event": "stage", "stage": "synthesizing"}
                stage_start = time.perf_counter()
                try:
                    audio = await synthesize(
                        db,
                        Synthesis(
                            text=result.translated_text,
                            language=target,
                            voice=voice,
                            speed=speed,
                        ),
                    )
                    result.audio_url = "data:audio/mpeg;base64," + base64.b64encode(
                        audio
                    ).decode("ascii")
                    result.tts_status = "complete"
                except (ServiceError, HTTPException) as error:
                    result.tts_status = "error"
                    result.tts_error = (
                        error.message
                        if isinstance(error, ServiceError)
                        else str(error.detail)
                    )
                except Exception:
                    result.tts_status = "error"
                    result.tts_error = "Speech generation is unavailable. Text translation is still available."
                result.timings.tts_ms = round(
                    (time.perf_counter() - stage_start) * 1000, 1
                )
    result.timings.total_ms = round((time.perf_counter() - start) * 1000, 1)
    yield {"event": "result", "data": result.model_dump()}
