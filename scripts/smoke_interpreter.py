"""Run real streamed interpreter requests through the frontend proxy in four languages."""

import base64
import json
from pathlib import Path
import sys

import httpx


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    output = Path(__file__).resolve().parents[1] / "runtime"
    records = []
    with httpx.Client(base_url="http://127.0.0.1:5173", timeout=180) as client:
        for source, target, text in [
            ("ar", "en", "مرحباً، كيف حالك؟ هل أنت بخير؟"),
            ("en", "ar", "Hello, how are you? Are you okay?"),
            ("fr", "en", "Bonjour, comment allez-vous ?"),
            ("zh", "ar", "你好，你今天怎么样？"),
        ]:
            audio = client.post(
                "/api/speech/synthesize", json={"text": text, "language": source}
            )
            audio.raise_for_status()
            stages = []
            result = None
            with client.stream(
                "POST",
                "/api/speech/translate?stream=true",
                files={"file": ("sample.mp3", audio.content, "audio/mpeg")},
                data={"source": source, "target": target, "generate_voice": "true"},
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event["event"] == "error":
                        raise RuntimeError(event["detail"])
                    if event["event"] == "stage":
                        stages.append(event["stage"])
                        print(
                            source + " → " + target + ": " + event["stage"], flush=True
                        )
                    if event["event"] == "result":
                        result = event["data"]
            assert stages == [
                "transcribing",
                "correcting",
                "translating",
                "synthesizing",
            ]
            assert (
                result
                and result["translated_text"]
                and result["tts_status"] == "complete"
            )
            (output / f"interpreter-output-{source}-{target}.mp3").write_bytes(
                base64.b64decode(result.pop("audio_url").split(",", 1)[1])
            )
            records.append(result)
            print(
                json.dumps(
                    {
                        key: result[key]
                        for key in [
                            "raw_transcript",
                            "corrected_transcript",
                            "translated_text",
                            "correction_status",
                            "timings",
                        ]
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        assert client.get("/api/health").json()["capacity"]["active_requests"] == 0
    (output / "interpreter-smoke-results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Four real streamed interpreter pipelines passed.", flush=True)


if __name__ == "__main__":
    main()
