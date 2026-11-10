import gc
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from backend.app.ai.local import LocalNLLBProvider, WhisperProvider, EdgeTTSProvider
from backend.app.ai.external import HTTPTranslationProvider
from backend.app.core.errors import ServiceError
from backend.app.models.database_models import Record
from backend.app.repositories.registry import records
from backend.app.core.config import config


class ModelManager:
    """One local model resident at a time; all model work shares one lock."""

    def __init__(self):
        self.lock = threading.RLock()
        self.loaded = None
        self.instance = None
        self.last_used = None
        self.status = "idle"
        self.loading_model = None
        self.loading_started = None

    @contextmanager
    def execution(self):
        """Bound waiting for the resident model without interrupting active inference."""
        acquired = self.lock.acquire(timeout=config.inference_queue_timeout)
        if not acquired:
            raise ServiceError(
                "The model is still processing another request. Please retry shortly."
            )
        try:
            yield
        finally:
            self.lock.release()

    def invalidate(self):
        with self.execution():
            self.instance = None
            self.loaded = None
            self.status = "idle"
            self.loading_model = None
            self.loading_started = None
            gc.collect()
            import sys

            if "torch" in sys.modules:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    def default(self, db, typ):
        options = [
            r
            for r in records(db, "models")
            if r.data["enabled"] and r.data["model_type"] == typ
        ]
        if not options:
            raise ServiceError(f"No enabled {typ} model is configured.")
        return next((r for r in options if r.data["default"]), options[0])

    def get(self, db, row):
        if not row or row.kind != "models" or not row.data["enabled"]:
            raise ServiceError("The configured model is disabled or unavailable.")
        spec = row.data
        if spec["provider_type"] in ("custom_http", "openai_compatible"):
            provider = db.get(Record, spec["provider_id"])
            if (
                not provider
                or provider.kind != "providers"
                or not provider.data["enabled"]
            ):
                raise ServiceError("External provider is disabled or unavailable.")
            return HTTPTranslationProvider(spec, provider)
        if spec["provider_type"] == "edge_tts":
            return EdgeTTSProvider()
        if self.loaded != row.id:
            if spec["provider_type"] == "whisper":
                WhisperProvider.checkpoint_directory(spec)
            self.invalidate()
            self.status = "loading"
            self.loading_model = {"name": spec["name"], "type": spec["model_type"]}
            self.loading_started = time.monotonic()
            try:
                self.instance = {
                    "local_nllb": LocalNLLBProvider,
                    "whisper": WhisperProvider,
                }[spec["provider_type"]](spec)
                self.loaded = row.id
                self.status = "ready"
            except Exception:
                self.status = "error"
                raise
            finally:
                self.loading_model = None
                self.loading_started = None
        self.last_used = datetime.now(timezone.utc).isoformat()
        return self.instance

    def health(self):
        return {
            "loaded_model_id": self.loaded,
            "status": self.status,
            "last_used": self.last_used,
            "loading_model": self.loading_model,
            "loading_seconds": round(time.monotonic() - self.loading_started, 1)
            if self.loading_started is not None
            else None,
        }


manager = ModelManager()
