from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.analysis.cache import ArtifactAnalysisCache
from mask_api.modules.analysis.contracts import (
    AnalysisRequest,
    AnalysisSchemaId,
    AnalysisStatus,
    AnalysisType,
    ModelExecutionPolicy,
)
from mask_api.modules.analysis.openai_responses import (
    OpenAIResponsesAdapter,
    OpenAIResponsesError,
    OpenAIResponsesSettings,
    OpenAITransportResponse,
    build_responses_payload,
    parse_responses_result,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits
from mask_api.research_runner.local_artifacts import LocalArtifactStore
from pydantic import SecretStr

FIXTURE = Path(__file__).parent / "fixtures/relevance_completed.json"
NOW = datetime(2026, 9, 10, 1, 0, tzinfo=UTC)


def policy(**changes: object) -> ModelExecutionPolicy:
    values: dict[str, object] = {
        "model_reference": "fixture-model",
        "input_token_budget": 500,
        "max_output_tokens": 100,
        "input_usd_per_million_tokens": Decimal("1"),
        "output_usd_per_million_tokens": Decimal("2"),
        "max_call_cost_usd": Decimal("0.001"),
    }
    values.update(changes)
    return ModelExecutionPolicy(**values)  # type: ignore[arg-type]


def request(**changes: object) -> AnalysisRequest:
    values: dict[str, object] = {
        "analysis_type": AnalysisType.RELEVANCE,
        "schema_id": AnalysisSchemaId.RELEVANCE_V1,
        "analysis_version": "v1",
        "prompt_version": "v1",
        "schema_version": "v1",
        "taxonomy_version": "relevance-v1",
        "normalization_version": "normalize-v1",
        "normalized_document_sha256": "a" * 64,
        "market_definition": "US HVAC contractors with 10-99 employees",
        "task_instructions": "Classify relevance to dispatch workflow pain.",
        "source_text": "Our dispatch delays cost us hours every week.",
        "model_policy": policy(),
    }
    values.update(changes)
    return AnalysisRequest(**values)  # type: ignore[arg-type]


def ledger() -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=2,
            max_documents=2,
            max_total_bytes=2_000_000,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal("0.01"),
        )
    )


@dataclass
class FakeTransport:
    responses: list[OpenAITransportResponse]
    calls: list[dict[str, object]] = field(default_factory=list)

    def create_response(self, payload: object, **kwargs: object) -> OpenAITransportResponse:
        self.calls.append({"payload": payload, **kwargs})
        return self.responses.pop(0)


def response(body: bytes | None = None) -> OpenAITransportResponse:
    return OpenAITransportResponse(200, "application/json", body or FIXTURE.read_bytes())


def enabled_settings(**changes: object) -> OpenAIResponsesSettings:
    values: dict[str, object] = {
        "enabled": True,
        "policy_approved": True,
        "api_key": SecretStr("fixture-not-a-real-key"),
        "timeout_seconds": 5,
        "max_response_bytes": 100_000,
    }
    values.update(changes)
    return OpenAIResponsesSettings(**values)  # type: ignore[arg-type]


def test_request_cache_identity_ignores_pricing_but_not_model_or_output_limit() -> None:
    original = request()
    repriced = request(
        model_policy=policy(
            input_usd_per_million_tokens=Decimal("1.5"),
            output_usd_per_million_tokens=Decimal("3"),
            max_call_cost_usd=Decimal("0.002"),
        )
    )
    different_limit = request(model_policy=policy(max_output_tokens=101))

    assert original.cache_key == repriced.cache_key
    assert original.cache_key != different_limit.cache_key


def test_payload_is_stateless_tool_free_strict_and_separates_untrusted_text() -> None:
    payload = build_responses_payload(request())

    assert payload["store"] is False
    assert payload["tools"] == []
    assert payload["model"] == "fixture-model"
    text = payload["text"]
    assert isinstance(text, dict)
    output_format = text["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert "api_key" not in json.dumps(payload)
    serialized_input = json.dumps(payload["input"])
    assert "untrusted_source_text" in serialized_input
    assert "dispatch delays" in serialized_input


def test_parser_validates_schema_preserves_usage_and_calculates_cost() -> None:
    result = parse_responses_result(FIXTURE.read_bytes(), request(), created_at=NOW)

    assert result.status == AnalysisStatus.COMPLETED
    assert result.structured_output is not None
    assert result.structured_output["label"] == "relevant"
    assert result.usage.total_tokens == 150
    assert result.usage.cost_usd == Decimal("0.00018")
    assert result.raw_response == FIXTURE.read_bytes()
    assert len(result.response_sha256) == 64


def test_disabled_adapter_stops_before_transport_when_cache_is_empty(tmp_path: Path) -> None:
    transport = FakeTransport([])
    adapter = OpenAIResponsesAdapter(
        OpenAIResponsesSettings(),
        transport,
        ArtifactAnalysisCache(LocalArtifactStore(tmp_path)),
        now=lambda: NOW,
    )

    with pytest.raises(OpenAIResponsesError) as captured:
        adapter.analyze(request(), ledger())

    assert captured.value.code == "openai.disabled"
    assert transport.calls == []


def test_fake_transport_result_is_budgeted_cached_and_reused_while_disabled(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([response()])
    cache = ArtifactAnalysisCache(LocalArtifactStore(tmp_path))
    active = OpenAIResponsesAdapter(enabled_settings(), transport, cache, now=lambda: NOW)
    budget = ledger()

    first = active.analyze(request(), budget)
    held = OpenAIResponsesAdapter(OpenAIResponsesSettings(), transport, cache, now=lambda: NOW)
    second = held.analyze(request(), budget)

    assert first == second
    assert len(transport.calls) == 1
    assert budget.usage.requests == 1
    assert budget.usage.total_bytes == len(FIXTURE.read_bytes())
    assert budget.usage.paid_cost_usd == Decimal("0.00018")
    assert isinstance(transport.calls[0]["api_key"], SecretStr)
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert "fixture-not-a-real-key" not in json.dumps(payload)


def test_refusal_and_incomplete_responses_remain_explicit_and_are_not_cached(
    tmp_path: Path,
) -> None:
    refusal = json.dumps(
        {
            "id": "r1",
            "model": "fixture",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "cannot process"}],
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        }
    ).encode()
    incomplete = json.dumps(
        {
            "id": "r2",
            "model": "fixture",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [],
            "usage": {"input_tokens": 10, "output_tokens": 100, "total_tokens": 110},
        }
    ).encode()
    cache = ArtifactAnalysisCache(LocalArtifactStore(tmp_path))

    refused = OpenAIResponsesAdapter(
        enabled_settings(), FakeTransport([response(refusal)]), cache, now=lambda: NOW
    ).analyze(request(), ledger())
    partial = OpenAIResponsesAdapter(
        enabled_settings(), FakeTransport([response(incomplete)]), cache, now=lambda: NOW
    ).analyze(request(), ledger())

    assert refused.status == AnalysisStatus.REFUSED
    assert refused.refusal == "cannot process"
    assert partial.status == AnalysisStatus.INCOMPLETE
    assert partial.incomplete_reason == "max_output_tokens"
    assert cache.get(request()) is None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"not-json", "openai.response_invalid"),
        (
            b'{"id":"r","model":"m","status":"completed","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}',
            "openai.output_text_missing",
        ),
        (
            b'{"id":"r","model":"m","status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"{}"}]}],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}',
            "openai.response_invalid",
        ),
    ],
)
def test_invalid_provider_envelopes_or_structured_outputs_fail_safely(
    body: bytes, code: str
) -> None:
    with pytest.raises(OpenAIResponsesError) as captured:
        parse_responses_result(body, request(), created_at=NOW)

    assert captured.value.code == code
