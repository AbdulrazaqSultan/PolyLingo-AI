# Audit and implementation plan

The original notebook and helper are the research source of truth. `helper.py` contains `NLLBTranslator` and `load_adapter_for_inference`; no Gradio or Streamlit application exists. Best and last adapters are in `models/polyligo_nllb_lora/`. Adapter configuration confirms rank 16, alpha 32, dropout 0.05, and attention q/k/v/out projections. The base weights are cached in `data/hf_cache/hub`. Processed train/validation/test Parquet files and six evaluation artifacts are present. CSV macro results match the request.

1. Add FastAPI, SQLAlchemy registries, secure admin sessions, encrypted provider secrets, and validated API schemas.
2. Adapt the helper's proven loading/generation logic into a lazy, locked inference provider, leaving the helper unchanged. Use database language mappings, reject oversized token input, and support routing and explicit fallback.
3. Add local Whisper transcription, Edge TTS, bounded temporary audio processing, and extensible provider contracts.
4. Build a React/TypeScript translator with editable transcription, staged feedback, microphone visualization, private browser history, pipeline, and research presentation.
5. Build a separately authenticated administration workspace for models, languages, providers, routing, analytics, operational logs, and settings.
6. Verify with mocked API/security tests, frontend compilation, real inference where dependencies permit, and research checksum comparison. Add Docker, environment examples, operational documentation, and contributor guidance.

Single backend process serializes local AI work to keep an 8 GB GPU within a predictable memory budget. Whisper defaults to CPU. Heavy model imports are lazy so API startup and unit tests do not load weights. No research asset is modified. Deployment is prepared locally; no external publishing is performed.
