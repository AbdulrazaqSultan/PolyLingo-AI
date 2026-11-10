from typing import Literal
from pydantic import BaseModel, Field


class SpeechTimings(BaseModel):
    asr_ms: float = 0
    correction_ms: float = 0
    translation_ms: float = 0
    tts_ms: float = 0
    total_ms: float = 0


class SpeechTranslationResult(BaseModel):
    detected_language: str
    language: str
    source: str
    target: str
    raw_transcript: str
    corrected_transcript: str
    text: str
    correction_applied: bool = False
    correction_status: str = "unchanged"
    correction_provider: str = ""
    correction_confidence: float | None = None
    correction_safety_score: float | None = None
    changed_spans: list[dict] = Field(default_factory=list)
    correction_ms: float = 0
    stt_ms: float = 0
    translated_text: str = ""
    provider: str = ""
    fallback_used: bool = False
    translation_ms: float = 0
    translation_status: Literal["complete", "error", "manual", "same_language"] = (
        "manual"
    )
    tts_status: Literal["complete", "error", "skipped"] = "skipped"
    audio_url: str | None = None
    error: str | None = None
    tts_error: str | None = None
    timings: SpeechTimings = Field(default_factory=SpeechTimings)
    synthesis_endpoint: str = "/api/speech/synthesize"
