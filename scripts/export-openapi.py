"""Generate the source-of-truth API schema, without a database connection."""

import argparse
import json
from pathlib import Path

from mask_api.config import Settings
from mask_api.main import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
settings = Settings(
    _env_file=None,
    environment="test",
    database_url="postgresql+psycopg://localhost/schema_only",
    enable_dev_routes=True,
    dev_token="schema-generation-placeholder-only",
)
content = json.dumps(create_app(settings).openapi(), indent=2, sort_keys=True) + "\n"
target = Path(__file__).resolve().parents[1] / "packages/schemas/openapi.json"
if args.check:
    if not target.exists() or target.read_text(encoding="utf-8") != content:
        raise SystemExit("OpenAPI drift: run pnpm schemas:generate")
    print("OpenAPI matches backend")
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
