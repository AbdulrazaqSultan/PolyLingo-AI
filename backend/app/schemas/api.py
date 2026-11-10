from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Translation(Strict):
    text: str = Field(min_length=1, max_length=5000)
    source: str = Field(min_length=2, max_length=16)
    target: str = Field(min_length=2, max_length=16)
    beams: int = Field(default=4, ge=1, le=8)
    mode: Literal["text", "speech"] = "text"


class Synthesis(Strict):
    text: str = Field(min_length=1, max_length=5000)
    language: str = Field(max_length=16)
    voice: str | None = Field(default=None, max_length=100)
    speed: int = Field(default=0, ge=-50, le=50)


class Login(Strict):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1024)


class Language(Strict):
    name: str = Field(min_length=1, max_length=80)
    native: str = Field(min_length=1, max_length=80)
    iso: str = Field(pattern=r"^[a-z]{2,3}$")
    nllb: str = Field(pattern=r"^[a-z]{3}_[A-Z][a-z]{3}$")
    stt: str = Field(min_length=2, max_length=16)
    tts: str = Field(min_length=2, max_length=24)
    direction: Literal["rtl", "ltr"] = "ltr"
    enabled: bool = True


class Model(Strict):
    name: str = Field(min_length=1, max_length=100)
    model_type: Literal["translation", "stt", "tts"]
    provider_type: Literal[
        "local_nllb", "whisper", "edge_tts", "custom_http", "openai_compatible"
    ]
    model_id: str = Field(default="", max_length=200)
    local_path: str = Field(default="", max_length=400)
    adapter_path: str = Field(default="", max_length=400)
    version: str = Field(default="1", max_length=40)
    description: str = Field(default="", max_length=500)
    languages: list[str] = Field(default_factory=list, max_length=200)
    device: Literal["auto", "cpu", "cuda"] = "auto"
    precision: Literal["auto", "float16", "float32"] = "auto"
    enabled: bool = True
    default: bool = False
    provider_id: int | None = None


class Provider(Strict):
    name: str = Field(min_length=1, max_length=100)
    provider_type: Literal["custom_http", "openai_compatible"]
    base_url: str = Field(min_length=8, max_length=500)
    model_name: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)
    timeout: int = Field(default=30, ge=1, le=120)
    enabled: bool = True
    priority: int = Field(default=10, ge=0, le=1000)


class Routing(Strict):
    source: str = Field(max_length=16)
    target: str = Field(max_length=16)
    model_id: int
    fallback_model_id: int | None = None
    enabled: bool = True


class Settings(Strict):
    application_name: str = Field(default="PolyLingo AI", min_length=1, max_length=100)
    description: str = Field(
        default="Intelligent Multilingual Speech Translation Platform", max_length=500
    )
    default_source: str = "en"
    default_target: str = "ar"
    max_text_length: int = Field(default=2000, ge=1, le=5000)
    max_audio_seconds: int = Field(default=60, ge=1, le=300)
    history_enabled: bool = True
    autoplay: bool = False
    maintenance: bool = False
    auto_translate_voice: bool = True
    transcript_correction_enabled: bool = True
    transcript_correction_provider: Literal["rule_based", "hybrid", "llm"] = "hybrid"
    correction_confidence_threshold: float = Field(default=0.95, ge=0.8, le=1)
    correction_languages: list[str] = Field(
        default_factory=lambda: ["ar", "en", "fr", "zh"], max_length=200
    )
    correction_api_provider_id: int | None = None
    correction_model_id: str = Field(default="", max_length=200)
    correction_timeout: float = Field(default=8, gt=0, le=30)
    correction_fallback: Literal["raw"] = "raw"
