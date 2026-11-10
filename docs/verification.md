# Verification record

## Automatic interpreter and conservative refinement

- 80 backend tests and 7 frontend tests passed; TypeScript/Vite production build and Python compilation passed. All 21 original research artifacts match their checksum manifest.
- The exact requested corrupted Arabic ASR string was simulated at the ASR boundary. The real default Hybrid corrected it to “مرحباً، كيف حالك؟ هل أنت بخير؟”, retained the raw input, and automatically invoked real NLLB/LoRA translation and TTS. That translation returned “Hey, how are you?”; it omitted the final source question, an existing model-quality limitation rather than a corrected-text loss. No semantic accuracy claim is inferred from a successful pipeline.
- Real streamed requests through the frontend proxy passed for Arabic → English, English → Arabic, French → English, Chinese → Arabic, with actual Whisper recognition, real refinement, existing translation weights, and generated MP3 output. Event order matched actual stages. Runtime sample results are in the ignored runtime/interpreter-smoke-results.json and runtime/refinement-example-result.json.
- New tests exercise protected names/numbers/code/URLs/technical tokens, exact fallback on failure/timeout/low score, multilingual grammar, empty/same-language safety, detected-language routing, retained outputs after stage failures, streamed capacity recovery, optional API host/key/timeout protections, and frontend stale-result/cancellation behavior.
- The active corrector is Hybrid with local rules; no external correction API is configured by default. Optional API transport was mocked in security tests. Correction adds no GPU model. Physical microphone/browser interaction remains a manual check.
- See [implementation report](interpreter-improvements.md) and [correction administration](transcript-correction.md) for changed files, defaults and limitations.

## Speech installation and bilingual interface

- Prepared and activated multilingual Whisper tiny on CPU. The complete 75,538,270-byte checkpoint was assembled from resumable HTTPS byte ranges and verified against the official Hugging Face SHA-256 metadata before activation. Small remains registered as an alternative; its earlier partial download was not treated as an installed model.
- Real local API pipeline passed in both directions, including generated speech input, Whisper recognition, the original NLLB + LoRA translator, and translated MP3 output. English → Arabic recognition took 912.5 ms and translation 3715.0 ms; Arabic → English recognition took 943.1 ms and translation 4033.7 ms. These are single short-sample observations, not performance guarantees.
- English sample recognition: “Hello, how are you?”; output: “مرحباً، كيف حالك؟”. Arabic sample recognition: “مرحضًا كيف حالك اليوم”; output: “Hey, how you doing today?”. The Arabic transcription contains a character error, demonstrating why editable transcription is retained. Tiny favors low CPU cost; larger Whisper variants may improve recognition quality.
- Added Arabic/English interface dictionaries, persistent switching, document lang/dir updates, RTL layout, Arabic typography, translated common errors, and admin localization. Interface switching preserves the translation language choices and text.
- Four frontend rendering/localization tests passed; frontend production build passed. Backend regression suite passed 32 tests. Browser microphone permission and visual interaction remain manual acceptance checks.

## Availability fix verification

- Regression suite: 32 tests passed; frontend production build passed.
- Thread-stack inspection identified the actual 429 trigger: the first Whisper checkpoint download stalled in the Xet transport while holding the shared model lock; three translations were waiting behind it.
- Speech requests now use only complete local checkpoints. An incomplete cache produces a prompt 503, preserves a resident NLLB provider, and releases request capacity. The explicit checkpoint-download script defaults to direct HTTPS and runs independently from inference.
- Model-lock acquisition has a configurable timeout; tests verify timeout recovery and that four occupied request slots become available again after completion.
- Restarted the stalled local backend. Real English → French translation through the frontend proxy succeeded. /docs and the proxied OpenAPI schema return HTTP 200.
- A real request against the incomplete Whisper cache returned the missing-model message, left zero active requests, and preserved the loaded translation model. The missing checkpoint was subsequently resolved by preparing and activating Whisper tiny, as recorded above.

Verified on 2026-11-10 in the project workspace:

- Frontend TypeScript check and Vite production build passed.
- FastAPI unit/integration suite passed: 25 tests. Expensive translation and STT calls are mocked; audio decoding and validation are exercised with real WAV bytes.
- Original research checksum verification passed for all 21 recorded artifacts, including notebook, helper, adapters, processed datasets, and evaluation outputs.
- Real CPU inference loaded the original best adapter and cached NLLB weights. English “Hello, how are you?” returned French “Salut, comment allez-vous ?”.
- Full frontend proxy → FastAPI → local adapter translation succeeded. One warmed short request took 482.7 ms; this is a single observation, not a performance guarantee.
- Real Edge TTS request returned HTTP 200 and 11,232 bytes of encoded MP3 audio for a neutral greeting.
- Frontend preview returned HTTP 200; API startup and health/language endpoints were exercised through the frontend proxy.
- Python import/compilation checks passed. Speech dependencies installed successfully.

The saved tokenizer uses Transformers 5's list-shaped extra_special_tokens metadata. The service normalizes this option at runtime for Transformers 4 while preserving token IDs in tokenizer.json and leaving original files untouched. Cache-first base-model resolution avoids unnecessary remote metadata checks when the weights are already present.

## Remaining acceptance checks

- Headless Chrome verification now covers real browser recording with a synthetic microphone fixture, automatic translation, playback, history, locale switching, and ten Arabic/English viewport checks. Real screenshots and a recording are available in [the demo report](demo.md). Physical microphone devices, permission denial, keyboard-only interaction, and Arabic editing still need interactive acceptance checks.
- Real Whisper transcription is now verified with English and Arabic sample audio. Physical microphone capture still needs an interactive browser check. The larger small checkpoint remains incomplete and is not the active STT model.
- This Python installation reports PyTorch 2.8 CPU and CUDA unavailable. GPU inference and VRAM limits need validation in the intended CUDA environment.
- Docker configuration is supplied but no container build or cloud deployment was performed.
- Administrator credentials are intentionally unconfigured. Run scripts/setup_admin.py to choose your password and generate the local encryption key before sign-in.
- Starlette currently emits a TestClient deprecation warning recommending httpx2; tests still pass with the installed httpx client.

The local application is implemented; these checks do not constitute a security audit or approval for unrestricted public deployment. Follow the upstream NLLB license/intended-use constraints and deployment hardening instructions.
