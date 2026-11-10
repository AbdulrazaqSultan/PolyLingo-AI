# Changelog

## 1.1.0 — 2026-11-10

- Added conservative modular transcript correction with multilingual local context rules, optional encrypted API integrations, safety checks, exact raw fallback, and preserved original/corrected text.
- Voice recordings and uploads now automatically continue through correction, translation, and optional TTS in one streamed request with real stage events.
- Added cancellation/supersession, four-stage feedback, transcript comparison, explicit translation of edits, private speech history, and a protected Transcript Correction settings page.
- Corrected admission accounting for streaming responses and added regression/security/state-machine tests. Translation model and research artifacts are preserved.

## 1.0.2 — 2026-11-10

- Added Arabic/English interface localization, a persistent language switcher, localized errors, Arabic typography, and logical layout properties for RTL across public and admin screens.
- Added a resumable speech-model setup command with SHA-256 verification and optional activation. Prepared multilingual Whisper tiny for CPU speech recognition; Small remains a separate option.
- Added frontend localization tests and a real bilingual speech-pipeline smoke test.

## 1.0.1 — 2026-11-10

- Prevented incomplete Whisper checkpoint downloads from holding the inference lock and blocking text translation. Added an explicit speech-checkpoint downloader and preserved resident translation models when speech weights are missing.
- Bounded model-lock waits, exposed request capacity/loading diagnostics, and added Retry-After to inference-capacity responses.
- Restored /docs and /redoc aliases and served the OpenAPI schema through /api so documentation works behind the frontend proxy.
- Added regression tests for capacity recovery, incomplete speech weights, queue timeouts, and documentation routing.

## 1.0.0 — 2026-11-10

- Added FastAPI translation and speech services with lazy NLLB/LoRA, Whisper, and Edge TTS providers.
- Added React/TypeScript translator with microphone levels, editable recognition, audio playback/download, RTL, history, pipeline, and real evaluation presentation.
- Added protected administrator configuration, encrypted integrations, model tests, explicit routing fallback, analytics, operational logs, and settings.
- Added SQLAlchemy persistence, session/CSRF security, upload limits, safe errors, Docker configuration, documentation, API tests, and research checksums.
- Preserved original research assets.

