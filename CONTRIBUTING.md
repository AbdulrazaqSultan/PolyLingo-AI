# Contributing

Keep the notebook, helper, datasets, adapters, training chart, and evaluation outputs intact. Run python scripts/verify_research.py before and after changes. New provider implementations belong behind the interfaces in backend/app/ai/interfaces.py and must report errors without leaking credentials.

Install Python requirements and frontend dependencies as described in README. Run python -m pytest tests -q and npm run build from frontend. Mock AI weights for unit tests; run a separate manual model smoke test when changing inference code. Exercise Arabic RTL, keyboard focus, microphone permission denial, provider failure, mobile layout, and history clearing.

Do not commit .env, databases, model weights, dataset caches, local session data, or dependency directories. Explain behavioral changes and verification in pull requests. Evaluation claims must cite an existing result file or reproducible experiment. Review upstream model/dataset licenses before redistributing any artifacts.

