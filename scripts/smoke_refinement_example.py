"""Simulate the requested corrupted ASR example; use real correction, NLLB and TTS."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.app.main import app


async def simulated_asr(*args):
    return {"text": "مرحباً حالب هل أنت بحير", "language": "ar", "stt_ms": 0}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with patch("backend.app.services.voice_pipeline.transcribe", simulated_asr):
        with TestClient(app) as client:
            response = client.post(
                "/api/speech/translate",
                files={"file": ("simulated.wav", b"ASR simulated", "audio/wav")},
                data={"target": "en", "generate_voice": "true"},
            )
            response.raise_for_status()
            data = response.json()
    assert data["raw_transcript"] == "مرحباً حالب هل أنت بحير"
    assert data["corrected_transcript"] == "مرحباً، كيف حالك؟ هل أنت بخير؟"
    assert data["translation_status"] == "complete" and data["translated_text"]
    assert data["tts_status"] == "complete" and data["audio_url"]
    data.pop("audio_url")
    output = (
        Path(__file__).resolve().parents[1] / "runtime/refinement-example-result.json"
    )
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False), flush=True)
    print("Simulated ASR with real correction, translation and TTS passed.")


if __name__ == "__main__":
    main()
