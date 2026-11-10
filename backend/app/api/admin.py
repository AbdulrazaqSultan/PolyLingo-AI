import secrets
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, delete
from backend.app.core.config import config
from backend.app.core.security import require_admin, passwords, new_session, encrypt
from backend.app.db.session import get_db
from backend.app.models.database_models import (
    Record,
    Event,
    OperationalLog,
    AdminSession,
)
from backend.app.repositories.registry import records, public_record, settings
from backend.app.schemas.api import Login, Model, Provider, Language, Routing, Settings
from backend.app.services.model_manager import manager

router = APIRouter(prefix="/api/admin")
attempts = {}


@router.post("/login")
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = [t for t in attempts.get(host, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many login attempts. Try again in five minutes.")
    if len(attempts) > 10000:
        attempts.clear()
    attempts[host] = recent + [now]
    valid = False
    if config.admin_password_hash:
        try:
            valid = passwords.verify(body.password, config.admin_password_hash)
        except Exception:
            pass
    if not valid or not secrets.compare_digest(body.username, config.admin_username):
        raise HTTPException(401, "Invalid administrator credentials.")
    attempts.pop(host, None)
    token, row = new_session(db)
    response.set_cookie(
        "polylingo_admin",
        token,
        httponly=True,
        secure=config.secure_cookies,
        samesite="strict",
        max_age=config.session_hours * 3600,
        path="/api/admin",
    )
    return {"csrf": row.csrf, "username": config.admin_username}


@router.get("/session")
def session(session=Depends(require_admin)):
    return {"csrf": session.csrf, "username": config.admin_username}


@router.post("/logout")
def logout(response: Response, session=Depends(require_admin), db=Depends(get_db)):
    db.delete(session)
    db.commit()
    response.delete_cookie("polylingo_admin", path="/api/admin")
    return {"ok": True}


@router.get("/dashboard", dependencies=[Depends(require_admin)])
def dashboard(db=Depends(get_db)):
    events = list(
        db.scalars(select(Event).order_by(Event.timestamp.desc()).limit(10000))
    )
    today = datetime.now(timezone.utc).date()
    import torch

    gpu = torch.cuda.is_available()
    return {
        "total_requests": len(events),
        "today": sum(e.timestamp.date() == today for e in events),
        "average_ms": round(sum(e.duration_ms for e in events) / len(events), 1)
        if events
        else 0,
        "failures": sum(not e.success for e in events),
        "active_sessions": len(
            list(
                db.scalars(
                    select(AdminSession).where(
                        AdminSession.expires > datetime.now(timezone.utc)
                    )
                )
            )
        ),
        "languages": sum(r.data["enabled"] for r in records(db, "languages")),
        "active_models": {
            typ: next(
                (
                    r.data["name"]
                    for r in records(db, "models")
                    if r.data["model_type"] == typ
                    and r.data["enabled"]
                    and r.data["default"]
                ),
                None,
            )
            for typ in ["translation", "stt", "tts"]
        },
        "requests_by_day": dict(
            sorted(Counter(e.timestamp.strftime("%Y-%m-%d") for e in events).items())
        ),
        "languages_usage": dict(Counter(e.target for e in events)),
        "directions": dict(Counter(e.source + " → " + e.target for e in events)),
        "providers": dict(Counter(e.provider for e in events)),
        "latency_by_day": {
            day: round(
                sum(
                    e.duration_ms
                    for e in events
                    if e.timestamp.strftime("%Y-%m-%d") == day
                )
                / count,
                1,
            )
            for day, count in Counter(
                e.timestamp.strftime("%Y-%m-%d") for e in events
            ).items()
        },
        "failures_by_day": dict(
            Counter(e.timestamp.strftime("%Y-%m-%d") for e in events if not e.success)
        ),
        "cuda": gpu,
        "device": torch.cuda.get_device_name(0) if gpu else "CPU",
        "gpu_memory_mb": round(torch.cuda.memory_allocated() / 1048576)
        if gpu
        else None,
        "version": config.version,
        "model_health": manager.health(),
        "window": "Most recent 10,000 requests",
    }


SCHEMAS = {
    "models": Model,
    "providers": Provider,
    "languages": Language,
    "routing": Routing,
}


def validate_registry(db, kind, data, row_id=None):
    if kind == "providers":
        url = urlsplit(data["base_url"])
        allowed = {
            h.strip() for h in config.allowed_provider_hosts.split(",") if h.strip()
        }
        if (
            url.scheme != "https"
            or not url.hostname
            or url.hostname not in allowed
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port not in (None, 443)
        ):
            raise HTTPException(
                422,
                "Use an HTTPS provider host listed in ALLOWED_PROVIDER_HOSTS, without credentials, query, or a custom port.",
            )
    if kind == "languages" and any(
        r.id != row_id and r.data["iso"] == data["iso"] for r in records(db, kind)
    ):
        raise HTTPException(409, "Language ISO code already exists.")
    if kind == "models":
        supported = {
            "translation": {"local_nllb", "custom_http", "openai_compatible"},
            "stt": {"whisper"},
            "tts": {"edge_tts"},
        }
        if data["provider_type"] not in supported[data["model_type"]]:
            raise HTTPException(
                422, "This provider does not implement the selected model type."
            )
        if data["default"] and not data["enabled"]:
            raise HTTPException(422, "A default model must be enabled.")
        if data["provider_type"] in ("custom_http", "openai_compatible"):
            p = db.get(Record, data["provider_id"])
            if not p or p.kind != "providers":
                raise HTTPException(422, "Select a registered external provider.")
    if kind == "routing":
        for key in ["model_id", "fallback_model_id"]:
            if data.get(key) is not None:
                r = db.get(Record, data[key])
                if not r or r.kind != "models" or r.data["model_type"] != "translation":
                    raise HTTPException(
                        422, "Routing requires registered translation models."
                    )
        if data["model_id"] == data.get("fallback_model_id"):
            raise HTTPException(422, "Fallback must use a different model.")
        for iso in [data["source"], data["target"]]:
            if not any(r.data["iso"] == iso for r in records(db, "languages")):
                raise HTTPException(422, "Routing language is not registered.")


@router.get("/settings", dependencies=[Depends(require_admin)])
def get_settings(db=Depends(get_db)):
    return settings(db)


@router.patch("/settings", dependencies=[Depends(require_admin)])
def change_settings(body: Settings, db=Depends(get_db)):
    if body.correction_api_provider_id is not None:
        provider = db.get(Record, body.correction_api_provider_id)
        if not provider or provider.kind != "providers" or not provider.data["enabled"]:
            raise HTTPException(422, "Select an enabled correction API provider.")
    if (
        body.transcript_correction_provider == "llm"
        and body.correction_api_provider_id is None
    ):
        raise HTTPException(
            422, "Configure a correction API provider before selecting LLM correction."
        )
    enabled = {r.data["iso"] for r in records(db, "languages") if r.data["enabled"]}
    if not set(body.correction_languages) <= enabled:
        raise HTTPException(422, "Correction languages must be enabled languages.")
    for iso in [body.default_source, body.default_target]:
        if not any(
            r.data["iso"] == iso and r.data["enabled"] for r in records(db, "languages")
        ):
            raise HTTPException(422, "Default languages must be enabled.")
    row = records(db, "settings")[0]
    row.data = body.model_dump()
    db.commit()
    return row.data


@router.get("/logs", dependencies=[Depends(require_admin)])
def logs(category: str = "", db=Depends(get_db)):
    query = select(OperationalLog).order_by(OperationalLog.id.desc()).limit(200)
    if category:
        query = (
            select(OperationalLog)
            .where(OperationalLog.category == category)
            .order_by(OperationalLog.id.desc())
            .limit(200)
        )
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "category": r.category,
            "message": r.message,
        }
        for r in db.scalars(query)
    ]


@router.post("/models/{row_id}/test", dependencies=[Depends(require_admin)])
def test_model(row_id: int, db=Depends(get_db)):
    row = db.get(Record, row_id)
    if not row or row.kind != "models":
        raise HTTPException(404, "Model not found.")
    from backend.app.services.translation_service import language

    try:
        with manager.execution():
            provider = manager.get(db, row)
            if row.data["model_type"] == "translation":
                provider.translate("Hello.", language(db, "en"), language(db, "fr"), 1)
        return {
            "status": "ready",
            "detail": "Translation inference passed."
            if row.data["model_type"] == "translation"
            else "Provider initialized. Run a speech request to verify inference.",
        }
    except Exception:
        db.add(
            OperationalLog(
                category="model",
                message="Model health test failed. Check installed dependencies and configured resources.",
            )
        )
        db.commit()
        raise HTTPException(
            503,
            "Model test failed. Verify dependencies, paths, and provider connectivity.",
        ) from None


@router.get("/{kind}", dependencies=[Depends(require_admin)])
def list_registry(kind: str, db=Depends(get_db)):
    if kind not in SCHEMAS:
        raise HTTPException(404, "Registry not found.")
    return [public_record(r) for r in records(db, kind)]


def save(db, kind, payload, row=None):
    if kind not in SCHEMAS:
        raise HTTPException(404, "Registry not found.")
    from pydantic import ValidationError

    try:
        data = SCHEMAS[kind].model_validate(payload).model_dump()
    except ValidationError:
        raise HTTPException(
            422,
            "Invalid registry configuration. Check required fields and supported values.",
        ) from None
    validate_registry(db, kind, data, row.id if row else None)
    secret = data.pop("api_key", None)
    if kind == "models" and data["default"]:
        for other in records(db, kind):
            if other.data["model_type"] == data["model_type"]:
                other.data = {**other.data, "default": False}
    if row is None:
        row = Record(kind=kind, data=data)
        db.add(row)
    else:
        row.data = data
    if secret:
        row.secret = encrypt(secret)
    db.commit()
    if kind in ("models", "providers"):
        manager.invalidate()
    return public_record(row)


@router.post("/{kind}", dependencies=[Depends(require_admin)])
def add_registry(kind: str, payload: dict, db=Depends(get_db)):
    return save(db, kind, payload)


@router.patch("/{kind}/{row_id}", dependencies=[Depends(require_admin)])
def edit_registry(kind: str, row_id: int, payload: dict, db=Depends(get_db)):
    row = db.get(Record, row_id)
    if not row or row.kind != kind:
        raise HTTPException(404, "Registry record not found.")
    return save(db, kind, {**row.data, **payload}, row)
