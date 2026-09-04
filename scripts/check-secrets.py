"""Small local guard, not a replacement for CI secret scanning."""

import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = (
    subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    .decode()
    .split("\0")
)
patterns = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}"),
]
violations = []
for relative in filter(None, files):
    path = root / relative
    if path.name.startswith(".env") and path.name != ".env.example":
        violations.append(relative)
        continue
    if not path.is_file() or path.stat().st_size > 2_000_000:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        continue
    if any(pattern.search(text) for pattern in patterns):
        violations.append(relative)
if violations:
    raise SystemExit("Possible secrets in: " + ", ".join(violations))
print("Local secret guard PASS (private keys/token patterns; not a full security audit).")
