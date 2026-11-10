"""Configure administrator credentials without exposing a password in command history."""

import getpass
from pathlib import Path
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

root = Path(__file__).resolve().parents[1]
env = root / ".env"
password = getpass.getpass("New admin password (at least 12 characters): ")
if len(password) < 12:
    raise SystemExit("Use at least 12 characters.")
if password != getpass.getpass("Confirm password: "):
    raise SystemExit("Passwords do not match.")
text = (
    env.read_text(encoding="utf-8")
    if env.exists()
    else (root / ".env.example").read_text(encoding="utf-8")
)
values = {"ADMIN_PASSWORD_HASH": PasswordHash.recommended().hash(password)}
if not any(
    line.startswith("ENCRYPTION_KEY=") and line.split("=", 1)[1].strip()
    for line in text.splitlines()
):
    values["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
lines = text.splitlines()
for key, value in values.items():
    lines = [line for line in lines if not line.startswith(key + "=")]
    lines.append(key + "=" + value)
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Administrator configured in .env. Restart the backend. Keep .env private.")
