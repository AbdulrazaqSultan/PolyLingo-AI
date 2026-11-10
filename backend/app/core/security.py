import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from cryptography.fernet import Fernet
from pwdlib import PasswordHash
from backend.app.core.config import config
from backend.app.db.session import get_db
from backend.app.models.database_models import AdminSession

passwords = PasswordHash.recommended()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def encrypt(value):
    if not config.encryption_key:
        raise HTTPException(503, "Server encryption key is not configured.")
    return Fernet(config.encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt(value):
    return Fernet(config.encryption_key.encode()).decrypt(value.encode()).decode()


def require_admin(request: Request, db=Depends(get_db)):
    token = request.cookies.get("polylingo_admin", "")
    session = db.get(AdminSession, digest(token))
    if not session or session.expires.replace(tzinfo=timezone.utc) <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(401, "Administrator sign-in required.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and not secrets.compare_digest(
        request.headers.get("X-CSRF-Token", ""), session.csrf
    ):
        raise HTTPException(403, "Invalid CSRF token.")
    return session


def new_session(db):
    token = secrets.token_urlsafe(48)
    row = AdminSession(
        token_hash=digest(token),
        csrf=secrets.token_urlsafe(32),
        expires=datetime.now(timezone.utc) + timedelta(hours=config.session_hours),
    )
    db.add(row)
    db.commit()
    return token, row
