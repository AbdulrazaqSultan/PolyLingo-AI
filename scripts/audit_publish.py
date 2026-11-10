"""Audit the exact Git index before committing or publishing; never print secret values."""

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".ipynb_checkpoints",
    ".cache",
    ".ruff_cache",
    ".pytest_cache",
    "huggingface",
    "runtime",
    ".idea",
    ".vscode",
}
BLOCKED_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".safetensors",
    ".pt",
    ".pth",
    ".ckpt",
    ".onnx",
    ".gguf",
    ".bin",
    ".arrow",
    ".pyc",
    ".pem",
    ".key",
}
TOKEN_PATTERNS = {
    "GitHub credential": re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})"
    ),
    "Hugging Face credential": re.compile(rb"hf_[A-Za-z0-9]{20,}"),
    "API credential": re.compile(rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    "AWS access identifier": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "private key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def local_secret_values():
    values = []
    for path in (ROOT / ".env", ROOT / "frontend/.env.local"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if re.search(r"PASSWORD|SECRET|TOKEN|KEY", key, re.I) and len(value) >= 12:
                values.append(value.encode())
    return values


def main():
    entries = [
        entry for entry in git("ls-files", "--stage", "-z").split(b"\0") if entry
    ]
    if not entries:
        raise SystemExit("The index is empty. Stage the reviewed project files first.")
    problems = []
    files = []
    secrets = local_secret_values()
    for entry in entries:
        metadata, name = entry.split(b"\t", 1)
        mode, sha, stage = metadata.split()
        path = os.fsdecode(name)
        parts = PurePosixPath(path).parts
        basename = parts[-1]
        forbidden = (
            bool(set(parts) & BLOCKED_DIRS)
            or parts[0] == "models"
            or path.startswith(
                (
                    "data/hf_cache/",
                    "data/raw/",
                    "data/downloads/",
                    "data/processed/",
                    "frontend/dist/",
                )
            )
            or (basename.startswith(".env") and basename != ".env.example")
            or PurePosixPath(path).suffix.lower() in BLOCKED_SUFFIXES
        )
        if forbidden or mode not in (b"100644", b"100755") or stage != b"0":
            problems.append(
                {
                    "file": path,
                    "reason": "Excluded/sensitive path or unexpected index mode",
                }
            )
            continue
        content = git("cat-file", "blob", sha.decode())
        files.append({"path": path, "bytes": len(content)})
        if len(content) > 10 * 1024 * 1024:
            problems.append(
                {"file": path, "reason": "File exceeds 10 MiB publication limit"}
            )
        for label, pattern in TOKEN_PATTERNS.items():
            if pattern.search(content):
                problems.append({"file": path, "reason": label + " pattern"})
        if any(value in content for value in secrets):
            problems.append(
                {
                    "file": path,
                    "reason": "Contains a private value from the local environment",
                }
            )
    total = sum(item["bytes"] for item in files)
    if total > 25 * 1024 * 1024:
        problems.append({"reason": "Index exceeds 25 MiB publication limit"})
    report = {
        "file_count": len(files),
        "total_bytes": total,
        "largest_files": sorted(files, key=lambda item: item["bytes"], reverse=True)[
            :10
        ],
        "problems": problems,
    }
    (ROOT / "runtime").mkdir(exist_ok=True)
    (ROOT / "runtime/publish-audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if problems:
        raise SystemExit(
            "Publication audit failed. Resolve the listed files before publishing."
        )
    print(
        "PASS: staged paths, size limits, credential patterns and local secret-value checks."
    )


if __name__ == "__main__":
    main()
