"""Filesystem YAML loading with strict validation and reproducible hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError

from mask_api.research_runner.contracts import (
    FormulaConfiguration,
    MarketConfiguration,
    SourceProfile,
)


class ConfigurationError(ValueError):
    """A configuration file cannot be loaded or does not satisfy its contract."""


@dataclass(frozen=True)
class LoadedConfiguration[ConfigurationT: BaseModel]:
    path: Path
    value: ConfigurationT
    sha256: str


def _canonical_hash(value: BaseModel) -> str:
    serialized = json.dumps(
        value.model_dump(mode="json", exclude_none=False),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def load_configuration[ConfigurationT: BaseModel](
    path: Path, model: type[ConfigurationT]
) -> LoadedConfiguration[ConfigurationT]:
    resolved = path.resolve()
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"Unable to load configuration: {resolved.name}") from error
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Configuration root must be an object: {resolved.name}")
    try:
        value = model.model_validate(raw)
    except ValidationError as error:
        raise ConfigurationError(f"Configuration validation failed: {resolved.name}") from error
    return LoadedConfiguration(path=resolved, value=value, sha256=_canonical_hash(value))


def load_market_configuration(path: Path) -> LoadedConfiguration[MarketConfiguration]:
    return load_configuration(path, MarketConfiguration)


def load_formula_configuration(path: Path) -> LoadedConfiguration[FormulaConfiguration]:
    return load_configuration(path, FormulaConfiguration)


def load_source_profile(path: Path) -> LoadedConfiguration[SourceProfile]:
    return load_configuration(path, SourceProfile)
