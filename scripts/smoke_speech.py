"""Exercise real speech recognition, translation, and synthesis against the local API."""

import json
from pathlib import Path
import sys

import httpx


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    output = Path(__file__).resolve().parents[1] / "runtime"
    output.mkdir(exist_ok=True)
    results = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=180) as client:
        for source, target, text in [
            ("en", "ar", "Hello, how are you?"),
            ("ar", "en", "مرحبًا، كيف حالك اليوم؟"),
        ]:
            voice = client.post(
                "/api/speech/synthesize", json={"text": text, "language": source}
            )
            voice.raise_for_status()
            (output / f"speech-input-{source}.mp3").write_bytes(voice.content)
            result = client.post(
                "/api/speech/translate",
                files={"file": ("sample.mp3", voice.content, "audio/mpeg")},
                data={"source": source, "target": target},
            )
            result.raise_for_status()
            data = result.json()
            assert data["text"].strip() and data["translated_text"].strip()
            translated_audio = client.post(
                "/api/speech/synthesize",
                json={
                    "text": data["translated_text"],
                    "language": target,
                },
            )
            translated_audio.raise_for_status()
            (output / f"speech-output-{target}.mp3").write_bytes(
                translated_audio.content
            )
            data["audio_bytes"] = len(translated_audio.content)
            results.append(data)
            print(json.dumps(data, ensure_ascii=False), flush=True)
        assert client.get("/api/health").json()["capacity"]["active_requests"] == 0
    (output / "speech-smoke-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Both real speech pipelines passed.")


if __name__ == "__main__":
    main()
