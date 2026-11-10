"""Download a Whisper checkpoint before starting speech inference."""

import argparse
import os
import sys
from pathlib import Path

# The Xet transport can stall on restricted networks. Direct HTTPS also resumes
# downloads and does not require the optional Xet service.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from faster_whisper.utils import download_model
    from backend.app.core.config import config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", default="small", help="Configured Whisper size or repository ID"
    )
    args = parser.parse_args()
    path = download_model(args.model, cache_dir=config.whisper_cache or None)
    print(f"Whisper checkpoint ready: {path}")
    print("Speech requests can now load the checkpoint without network access.")


if __name__ == "__main__":
    main()
