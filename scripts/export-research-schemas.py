"""Export deterministic JSON Schemas for autonomous research configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mask_api.research_runner.contracts import MarketConfiguration, SourceProfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    ROOT / "configs" / "schemas" / "market.schema.json": MarketConfiguration,
    ROOT / "configs" / "schemas" / "source-profile.schema.json": SourceProfile,
}


def rendered_schema(model: type[MarketConfiguration] | type[SourceProfile]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        for target, model in TARGETS.items():
            rendered = rendered_schema(model)
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"research configuration schema is out of date: {target.name}")
        print("Research configuration schema is current.")
        return 0
    for target, model in TARGETS.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered_schema(model), encoding="utf-8", newline="\n")
        print(f"Wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
