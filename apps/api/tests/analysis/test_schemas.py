from __future__ import annotations

from typing import Any

import pytest
from mask_api.modules.analysis.contracts import AnalysisSchemaId
from mask_api.modules.analysis.schemas import (
    RelevanceOutput,
    output_model_for,
    strict_json_schema,
)
from pydantic import ValidationError


@pytest.mark.parametrize("schema_id", list(AnalysisSchemaId))
def test_every_v1_output_has_a_strict_closed_json_schema(schema_id: AnalysisSchemaId) -> None:
    schema = strict_json_schema(schema_id)

    assert output_model_for(schema_id)
    _assert_objects_are_closed_and_required(schema)


def test_relevance_semantics_require_a_span_for_positive_labels() -> None:
    with pytest.raises(ValidationError):
        RelevanceOutput(
            label="relevant",
            reasons=("mentions the market",),
            evidence_spans=(),
            confidence=0.8,
        )


def _assert_objects_are_closed_and_required(node: object) -> None:
    if isinstance(node, dict):
        typed: dict[str, Any] = node
        assert not {"allOf", "not", "if", "then", "else"}.intersection(typed)
        properties = typed.get("properties")
        if isinstance(properties, dict):
            assert typed.get("additionalProperties") is False
            assert typed.get("required") == list(properties)
        assert "default" not in typed
        for value in typed.values():
            _assert_objects_are_closed_and_required(value)
    elif isinstance(node, list):
        for value in node:
            _assert_objects_are_closed_and_required(value)
