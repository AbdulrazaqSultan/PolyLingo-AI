import time
from fastapi import HTTPException
from backend.app.core.errors import ServiceError
from backend.app.models.database_models import Event, Record, OperationalLog
from backend.app.repositories.registry import records, settings
from backend.app.services.model_manager import manager


def language(db, iso):
    row = next(
        (
            r
            for r in records(db, "languages")
            if r.data["iso"] == iso and r.data["enabled"]
        ),
        None,
    )
    if not row:
        raise HTTPException(422, "Unsupported or disabled language.")
    return row.data


def translate(db, request):
    start = time.perf_counter()
    opts = settings(db)
    if opts["maintenance"]:
        raise HTTPException(503, "Translation is temporarily paused for maintenance.")
    if not request.text.strip() or len(request.text) > opts["max_text_length"]:
        raise HTTPException(422, "Text is empty or exceeds the configured limit.")
    source, target = language(db, request.source), language(db, request.target)
    route = next(
        (
            r.data
            for r in records(db, "routing")
            if r.data["enabled"]
            and r.data["source"] == request.source
            and r.data["target"] == request.target
        ),
        None,
    )
    row = (
        db.get(Record, route["model_id"])
        if route
        else manager.default(db, "translation")
    )
    used = row.data["name"] if row else "unavailable"
    success = False
    fallback = False
    try:
        with manager.execution():
            if request.source == request.target:
                output = request.text
            else:
                try:
                    output = manager.get(db, row).translate(
                        request.text, source, target, request.beams
                    )
                except Exception as error:
                    if isinstance(error, ServiceError) and error.status == 422:
                        raise
                    db.add(
                        OperationalLog(
                            category="translation", message="Primary provider failed."
                        )
                    )
                    if not route or not route.get("fallback_model_id"):
                        raise
                    row = db.get(Record, route["fallback_model_id"])
                    output = manager.get(db, row).translate(
                        request.text, source, target, request.beams
                    )
                    used = row.data["name"]
                    fallback = True
        success = True
        return {
            "translated_text": output,
            "source": request.source,
            "target": request.target,
            "provider": used,
            "fallback_used": fallback,
            "translation_ms": round((time.perf_counter() - start) * 1000, 1),
        }
    except ServiceError:
        raise
    except Exception:
        raise ServiceError(
            "Translation model is unavailable. Ask the administrator to check model health."
        ) from None
    finally:
        db.add(
            Event(
                source=request.source,
                target=request.target,
                provider=used,
                mode=request.mode,
                duration_ms=(time.perf_counter() - start) * 1000,
                success=success,
            )
        )
        db.commit()
