from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal

ROOT = Path(__file__).resolve().parents[3]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")
    database_url: str = "sqlite:///" + str(ROOT / "runtime/polylingo.db")
    admin_username: str = "admin"
    admin_password_hash: str = ""
    encryption_key: str = ""
    secure_cookies: bool = False
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    allowed_provider_hosts: str = ""
    adapter_path: str = str(ROOT / "models/polyligo_nllb_lora/best_adapter")
    hf_cache: str = str(ROOT / "data/hf_cache/hub")
    whisper_cache: str | None = None
    inference_queue_timeout: float = Field(default=30, gt=0, le=300)
    max_upload_mb: int = 15
    session_hours: int = 8
    auto_translate_voice: bool = True
    transcript_correction_enabled: bool = True
    transcript_correction_provider: Literal["hybrid", "rule_based", "llm"] = "hybrid"
    correction_confidence_threshold: float = Field(default=0.95, ge=0.8, le=1)
    version: str = "1.0.0"


config = Config()
(ROOT / "runtime").mkdir(exist_ok=True)
