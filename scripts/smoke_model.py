"""Run a real local adapter smoke test, separate from the mocked unit suite."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
from backend.app.ai.local import LocalNLLBProvider
from backend.app.core.config import config
from backend.app.schemas.api import Model

spec = Model(
    name="Smoke test",
    model_type="translation",
    provider_type="local_nllb",
    model_id="facebook/nllb-200-distilled-600M",
    adapter_path=config.adapter_path,
)
start = time.perf_counter()
provider = LocalNLLBProvider(spec.model_dump())
print("Device:", provider.device)
print(
    "Translation:",
    provider.translate(
        "Hello, how are you?", {"nllb": "eng_Latn"}, {"nllb": "fra_Latn"}, 1
    ),
)
print("Load and inference seconds:", round(time.perf_counter() - start, 2))
