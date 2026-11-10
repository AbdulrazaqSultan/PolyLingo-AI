"""Prepare a complete Whisper checkpoint with resumable parallel HTTPS downloads."""

import concurrent.futures
import argparse
import hashlib
import os
import sys
from pathlib import Path
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def activate(model: str, directory: Path) -> None:
    """Select the verified checkpoint without changing translation models."""
    from backend.app.db.session import initialize, Session
    from backend.app.repositories.registry import records, seed
    from backend.app.models.database_models import Record
    from backend.app.schemas.api import Model

    initialize()
    with Session() as db:
        seed(db)
        models = records(db, "models")
        current = next(
            (
                r
                for r in models
                if r.data.get("provider_type") == "whisper"
                and r.data.get("model_id") == model
            ),
            None,
        )
        for row in models:
            if row.data.get("model_type") == "stt":
                row.data = {**row.data, "default": False}
        spec = Model(
            name=f"Whisper {model}",
            model_type="stt",
            provider_type="whisper",
            model_id=model,
            local_path=str(directory),
            device="cpu",
            languages=["ar", "en", "fr", "zh"],
            enabled=True,
            default=True,
        ).model_dump()
        if current:
            current.data = spec
        else:
            db.add(Record(kind="models", data=spec))
        db.commit()
    print(f"Active speech model: Whisper {model}", flush=True)


def main():
    import requests
    from huggingface_hub import get_hf_file_metadata, hf_hub_url, snapshot_download

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["tiny", "base", "small"], default="small")
    parser.add_argument("--workers", type=int, choices=range(1, 33), default=16)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Select the verified model for speech requests",
    )
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / f"runtime/whisper-{args.model}"
    repo = f"Systran/faster-whisper-{args.model}"
    url = hf_hub_url(repo, "model.bin")
    metadata = get_hf_file_metadata(url, timeout=20)
    size, revision = metadata.size, metadata.commit_hash
    if not size or not revision:
        raise RuntimeError("Checkpoint metadata is unavailable.")
    output.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo,
        revision=revision,
        local_dir=str(output),
        allow_patterns=[
            "config.json",
            "tokenizer.json",
            "vocabulary.*",
            "preprocessor_config.json",
        ],
    )
    checkpoint = output / "model.bin"
    if checkpoint.is_file() and checkpoint.stat().st_size == size:
        with checkpoint.open("rb") as stream:
            verified = hashlib.file_digest(
                stream, "sha256"
            ).hexdigest() == metadata.etag.strip('"')
        if verified:
            if args.activate:
                activate(args.model, output)
            print(
                f"Whisper checkpoint already verified and ready: {output}", flush=True
            )
            return
    previous_parts = output / ".download-parts"
    parts = output / ".download-parts-2m"
    parts.mkdir(exist_ok=True)
    chunk_size = 2 * 1024 * 1024
    ranges = [
        (start, min(start + chunk_size, size) - 1)
        for start in range(0, size, chunk_size)
    ]
    for index, (start, end) in enumerate(ranges):
        old_index, offset = divmod(start, 8 * 1024 * 1024)
        old = previous_parts / f"{revision}-{old_index:04d}.part"
        path = parts / f"{revision}-{index:04d}.part"
        available = (
            min(end - start + 1, max(0, old.stat().st_size - offset))
            if old.exists()
            else 0
        )
        if available and (not path.exists() or path.stat().st_size < available):
            with old.open("rb") as stream:
                stream.seek(offset)
                path.write_bytes(stream.read(available))
    from huggingface_hub.constants import HF_HUB_CACHE

    existing = (
        Path(HF_HUB_CACHE)
        / f"models--Systran--faster-whisper-{args.model}"
        / "blobs"
        / (metadata.etag.strip('"') + ".incomplete")
    )
    if existing.is_file():
        with existing.open("rb") as source:
            for index, (start, end) in enumerate(ranges):
                available = min(
                    end - start + 1, max(0, existing.stat().st_size - start)
                )
                path = parts / f"{revision}-{index:04d}.part"
                if available and (not path.exists() or path.stat().st_size < available):
                    source.seek(start)
                    path.write_bytes(source.read(available))

    def segment(item):
        index, (start, end) = item
        path = parts / f"{revision}-{index:04d}.part"
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(16):
            try:
                offset = path.stat().st_size if path.exists() else 0
                if offset == end - start + 1:
                    return path
                current = start + offset
                with requests.get(
                    url,
                    params={
                        "download": "true",
                        "segment": index,
                        "offset": offset,
                        "chunk_size": chunk_size,
                    },
                    headers={"Range": f"bytes={current}-{end}"},
                    stream=True,
                    timeout=(20, 45),
                ) as response:
                    response.raise_for_status()
                    if (
                        response.status_code != 206
                        or response.headers.get("Content-Range")
                        != f"bytes {current}-{end}/{size}"
                    ):
                        raise RuntimeError("Server did not honor the byte range.")
                    with path.open("ab") as stream:
                        for chunk in response.iter_content(64 * 1024):
                            stream.write(chunk)
                if path.stat().st_size != end - start + 1:
                    raise RuntimeError("Incomplete range.")
                return path
            except Exception:
                if attempt == 15:
                    raise RuntimeError(
                        f"Unable to download checkpoint segment {index + 1}."
                    ) from None
                time.sleep(min(2**attempt, 15))

    print(f"Preparing Whisper {args.model}: {size / 1048576:.1f} MB", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(segment, item) for item in enumerate(ranges)]
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += future.result().stat().st_size
            print(
                f"Downloaded {completed / 1048576:.1f} / {size / 1048576:.1f} MB",
                flush=True,
            )
    digest = hashlib.sha256()
    temp = output / "model.bin.assembling"
    with temp.open("wb") as stream:
        for index, _ in enumerate(ranges):
            with (parts / f"{revision}-{index:04d}.part").open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    stream.write(chunk)
    if digest.hexdigest() != metadata.etag.strip('"'):
        raise RuntimeError("Checkpoint SHA-256 verification failed.")
    temp.replace(output / "model.bin")
    if args.activate:
        activate(args.model, output)
    print(f"Whisper checkpoint verified and ready: {output}", flush=True)


if __name__ == "__main__":
    main()
