"""Verify original research artifacts against the pre-implementation checksum manifest."""

import hashlib, json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "docs/research-manifest.json").read_text())
changed = [
    name
    for name, sha in manifest.items()
    if not (root / name).is_file()
    or hashlib.sha256((root / name).read_bytes()).hexdigest() != sha
]
if changed:
    raise SystemExit("Research verification failed: " + ", ".join(changed))
print(f"Verified {len(manifest)} original research files; all unchanged.")
