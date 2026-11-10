# REST API

All paths are relative to the server. Errors return `{"detail":"safe message"}`. Invalid schema fields produce 422 without echoing submitted values. Interactive OpenAPI documentation is at /api/docs, with /docs redirecting there. The schema is at /api/openapi.json, also reachable through the frontend proxy. /redoc redirects to /api/redoc.

## Public

| Method | Path | Contract |
|---|---|---|
| GET | /api/health | API liveness, version, lazy model state; no model load |
| GET | /api/languages | Enabled language metadata |
| GET | /api/models | Safe enabled model summaries, no local paths |
| GET | /api/config | Public application settings and limits |
| POST | /api/translate | JSON text, source, target, optional beams (1–8), mode (text/speech) |
| POST | /api/speech/transcribe | Multipart file and optional ISO source; returns text, detected language, stt_ms |
| POST | /api/speech/translate | Multipart file, optional source, target, generate_voice, voice, speed; ASR → correction → translation → optional TTS. Add ?stream=true for real NDJSON stage events. |
| POST | /api/speech/synthesize | JSON text, language, optional voice and speed (-50..50); returns MP3 bytes and X-Synthesis-Ms |
| GET | /api/speech/voices?language=ar | Provider voice catalog for enabled language |

Translation request:

```json
{"text":"Hello, world.","source":"en","target":"ar","beams":4,"mode":"text"}
```

Translation response fields: translated_text, source, target, provider, fallback_used, translation_ms.

The combined speech endpoint preserves raw_transcript and corrected_transcript, uses the detected language, automatically translates the accepted transcript, and optionally returns audio_url as inline MP3 data. Results include correction_status, translation_status, tts_status and timings. TTS failure keeps translated text; translation failure keeps both transcripts. /api/speech/transcribe remains the raw-ASR compatibility endpoint. See [full speech contracts and events](transcript-correction.md#one-request-api-and-real-progress). The frontend uses a single streamed call and does not translate on every manual edit.

## Authentication

POST /api/admin/login accepts username/password JSON, sets an HttpOnly, SameSite=Strict session cookie scoped to /api/admin, and returns csrf. GET /api/admin/session recovers the CSRF token for an existing valid session. POST /api/admin/logout revokes the session and clears the cookie.

Admin mutations require `X-CSRF-Token`. Secure cookies must be enabled under HTTPS. Failed logins are limited per client address to five per five minutes in this single-process implementation.

## Admin

| Method | Path | Purpose |
|---|---|---|
| GET | /api/admin/dashboard | Counters, timeseries, directions, provider usage, GPU and model state |
| GET / POST | /api/admin/models | List / register model |
| PATCH | /api/admin/models/{id} | Edit, enable, choose default |
| POST | /api/admin/models/{id}/test | Real translation smoke test or speech provider initialization |
| GET / POST | /api/admin/languages | List / register language |
| PATCH | /api/admin/languages/{id} | Edit mappings or enable state |
| GET / POST | /api/admin/providers | List / register encrypted external integration |
| PATCH | /api/admin/providers/{id} | Edit integration; blank key preserves saved key |
| GET / POST | /api/admin/routing | Pair model and explicit fallback |
| PATCH | /api/admin/routing/{id} | Change routing |
| GET / PATCH | /api/admin/settings | Read / replace validated settings |
| GET | /api/admin/logs?category=translation | Latest 200 safe logs; optional category filter |

Registry fields are defined in backend/app/schemas/api.py and reflected in OpenAPI for typed endpoints. Registry mutation endpoints validate the body with the appropriate Pydantic schema selected by kind. Unknown fields are rejected.

## External translation contract

Custom HTTP providers receive POST {base_url}/translate with text, source and target ISO, and model. Return JSON with translated_text. OpenAI-compatible providers receive POST {base_url}/chat/completions with model and system/user messages. Set base_url to include /v1 if required. Bearer credentials are decrypted server-side only. HTTPS hostname allowlisting, bounded timeouts, disabled redirects, and no environment proxy inheritance apply.

## Status codes

401 invalid/missing admin session, 403 invalid CSRF, 409 duplicate language, 413 upload/request too large, 415 unsupported audio MIME, 422 validation/unsupported language/duration/token limit, 429 busy inference admission or login rate limit, 503 unavailable provider/maintenance/incomplete speech checkpoint/model-lock timeout. Inference 429 responses include Retry-After: 5. /api/health includes capacity (active_requests, limit, queue_timeout_seconds) and inference.loading_model/loading_seconds. Liveness is distinct from model readiness.

