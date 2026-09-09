"""Deterministic grounding gate for completed structured analysis."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

from pydantic import JsonValue, ValidationError

from mask_api.modules.analysis.contracts import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
)
from mask_api.modules.analysis.grounding_contracts import (
    GroundingDisposition,
    GroundingIssue,
    GroundingIssueCode,
    GroundingIssueSeverity,
    GroundingReport,
    HighImpactClaim,
    HighImpactKind,
    HighImpactVerification,
    HighImpactVerificationRequest,
    InjectionSignal,
    VerificationDecision,
)
from mask_api.modules.analysis.ports import HighImpactVerifier
from mask_api.modules.analysis.schemas import (
    ClusterNamingOutput,
    CommercialPainOutput,
    CompetitorOutput,
    GeneralEvidenceOutput,
    InterviewFindingType,
    InterviewOutput,
    PersonaOutput,
    PricingStatus,
    RelevanceOutput,
    SearchIntentOutput,
    output_model_for,
)
from mask_api.modules.evidence.domain import EvidencePersona
from mask_api.research_runner.budgets import BudgetLedger
from mask_api.research_runner.contracts import MethodId

GROUNDING_VERSION = "grounding-v1"
# An operational review-priority threshold only; it is not a score or formula input.
SEVERE_PAIN_REVIEW_THRESHOLD = 8

_NUMBER = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[kKmMbB]|%)?(?![A-Za-z0-9_])"
)
_INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\bignore\s+(?:(?:all|any|the|your)\s+)?(?:previous|prior|above|system|developer)\s+instructions?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_spoofing",
        re.compile(r"(?:^|\n)\s*(?:system|developer|assistant)\s*:", re.IGNORECASE),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"\b(?:reveal|print|show|return|expose)\b.{0,60}"
            r"\b(?:api[ _-]?key|password|secret|token|system prompt)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "tool_activation",
        re.compile(
            r"\b(?:call|use|invoke|run)\s+(?:(?:the|a)\s+)?(?:tool|browser|shell|terminal|powershell|cmd)\b",
            re.IGNORECASE,
        ),
    ),
)


class GroundingError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("analysis grounding could not be completed safely")


@dataclass(frozen=True)
class _SpanBinding:
    path: str
    span: str | None
    required: bool = True


@dataclass(frozen=True)
class _NumericBinding:
    path: str
    expected: tuple[Decimal, ...]
    evidence_spans: tuple[str, ...]


def validate_grounding(
    request: AnalysisRequest,
    result: AnalysisResult,
    *,
    verifications: tuple[HighImpactVerification, ...] = (),
) -> GroundingReport:
    """Validate one completed result without network, retries, repair, or scoring."""

    issues: list[GroundingIssue] = []
    if result.request_cache_key != request.cache_key:
        issues.append(
            _issue(
                GroundingIssueCode.ANALYSIS_REQUEST_MISMATCH,
                GroundingIssueSeverity.BLOCKING,
                "/",
                "analysis result does not belong to this request",
            )
        )
    if result.status != AnalysisStatus.COMPLETED or result.structured_output is None:
        issues.append(
            _issue(
                GroundingIssueCode.ANALYSIS_NOT_COMPLETED,
                GroundingIssueSeverity.BLOCKING,
                "/",
                "only completed structured analysis can enter grounding",
            )
        )
        return _report(request, None, issues=issues, verifications=verifications)

    try:
        validated = output_model_for(request.schema_id).model_validate(result.structured_output)
    except ValidationError:
        issues.append(
            _issue(
                GroundingIssueCode.STRUCTURED_OUTPUT_INVALID,
                GroundingIssueSeverity.BLOCKING,
                "/",
                "structured output no longer matches its registered schema",
            )
        )
        return _report(request, None, issues=issues, verifications=verifications)

    preserved = cast(dict[str, JsonValue], validated.model_dump(mode="json"))
    spans = _span_bindings(validated)
    issues.extend(_validate_exact_spans(request.source_text, spans))

    numeric_bindings = _numeric_bindings(validated, request.source_text)
    issues.extend(_validate_numeric_bindings(numeric_bindings))

    injection_signals = _detect_prompt_injection(request.source_text)
    issues.extend(
        _issue(
            GroundingIssueCode.PROMPT_INJECTION_SIGNAL,
            GroundingIssueSeverity.REVIEW,
            "/source_text",
            f"untrusted source matched injection rule {signal.rule_id}",
        )
        for signal in injection_signals
    )

    claims = _high_impact_claims(request, validated)
    issues.extend(_verification_issues(claims, verifications))
    contradictions = _contradiction_paths(validated)
    return _report(
        request,
        preserved,
        issues=issues,
        claims=claims,
        verifications=verifications,
        contradictions=contradictions,
        injection_signals=injection_signals,
    )


class GroundingService:
    """Coordinates an optional independent second pass after deterministic checks."""

    def __init__(self, verifier: HighImpactVerifier | None = None) -> None:
        self._verifier = verifier

    def validate(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
        *,
        ledger: BudgetLedger | None = None,
    ) -> GroundingReport:
        initial = validate_grounding(request, result)
        if self._verifier is None or not initial.high_impact_claims:
            return initial
        if (
            any(issue.severity == GroundingIssueSeverity.BLOCKING for issue in initial.issues)
            or initial.injection_signals
        ):
            return initial
        if ledger is None:
            raise GroundingError("grounding.verifier_budget_missing")
        verification_request = HighImpactVerificationRequest(
            analysis_cache_key=request.cache_key,
            normalized_document_sha256=request.normalized_document_sha256,
            source_text=request.source_text,
            claims=initial.high_impact_claims,
        )
        verified = self._verifier.verify(verification_request, ledger)
        return validate_grounding(request, result, verifications=verified)


def _report(
    request: AnalysisRequest,
    output: dict[str, JsonValue] | None,
    *,
    issues: list[GroundingIssue],
    claims: tuple[HighImpactClaim, ...] = (),
    verifications: tuple[HighImpactVerification, ...] = (),
    contradictions: tuple[str, ...] = (),
    injection_signals: tuple[InjectionSignal, ...] = (),
) -> GroundingReport:
    has_blocker = any(issue.severity == GroundingIssueSeverity.BLOCKING for issue in issues)
    if has_blocker:
        disposition = GroundingDisposition.REJECTED
    elif issues:
        disposition = GroundingDisposition.NEEDS_REVIEW
    else:
        disposition = GroundingDisposition.ACCEPTED
    canonical = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    accepted = disposition == GroundingDisposition.ACCEPTED
    return GroundingReport(
        grounding_version=GROUNDING_VERSION,
        analysis_cache_key=request.cache_key,
        normalized_document_sha256=request.normalized_document_sha256,
        structured_output_sha256=digest,
        disposition=disposition,
        eligible_for_scoring_input=accepted,
        preserved_output=output,
        scoring_input=output if accepted else None,
        issues=tuple(issues),
        high_impact_claims=claims,
        verifications=verifications,
        contradiction_paths=contradictions,
        injection_signals=injection_signals,
    )


def _issue(
    code: GroundingIssueCode,
    severity: GroundingIssueSeverity,
    path: str,
    detail: str,
) -> GroundingIssue:
    return GroundingIssue(code=code, severity=severity, json_path=path, detail=detail)


def _validate_exact_spans(source: str, bindings: tuple[_SpanBinding, ...]) -> list[GroundingIssue]:
    issues: list[GroundingIssue] = []
    for binding in bindings:
        if binding.span is None:
            if binding.required:
                issues.append(
                    _issue(
                        GroundingIssueCode.EVIDENCE_SPAN_MISSING,
                        GroundingIssueSeverity.BLOCKING,
                        binding.path,
                        "material extracted value requires an evidence span",
                    )
                )
            continue
        if not binding.span or binding.span not in source:
            issues.append(
                _issue(
                    GroundingIssueCode.EVIDENCE_SPAN_NOT_EXACT,
                    GroundingIssueSeverity.BLOCKING,
                    binding.path,
                    "evidence span is not an exact source substring",
                )
            )
    return issues


def _validate_numeric_bindings(bindings: tuple[_NumericBinding, ...]) -> list[GroundingIssue]:
    issues: list[GroundingIssue] = []
    for binding in bindings:
        observed: set[Decimal] = set()
        for span in binding.evidence_spans:
            observed.update(_numbers(span))
        missing = tuple(value for value in binding.expected if value not in observed)
        if missing:
            issues.append(
                _issue(
                    GroundingIssueCode.NUMERIC_CLAIM_UNGROUNDED,
                    GroundingIssueSeverity.BLOCKING,
                    binding.path,
                    "one or more proposed numeric values are absent from the linked evidence",
                )
            )
    return issues


def _span_bindings(output: object) -> tuple[_SpanBinding, ...]:
    bindings: list[_SpanBinding] = []
    if isinstance(output, RelevanceOutput):
        bindings.extend(
            _SpanBinding(f"/evidence_spans/{index}", span)
            for index, span in enumerate(output.evidence_spans)
        )
    elif isinstance(output, PersonaOutput):
        bindings.append(
            _SpanBinding(
                "/evidence_span",
                output.evidence_span,
                required=output.persona != EvidencePersona.UNKNOWN,
            )
        )
    elif isinstance(output, CommercialPainOutput):
        for index, pain_record in enumerate(output.records):
            bindings.append(
                _SpanBinding(f"/records/{index}/evidence_span", pain_record.evidence_span)
            )
            for value_index, value in enumerate(pain_record.financial_value_mentioned):
                bindings.append(
                    _SpanBinding(
                        f"/records/{index}/financial_value_mentioned/{value_index}/evidence_span",
                        value.evidence_span,
                    )
                )
    elif isinstance(output, GeneralEvidenceOutput):
        bindings.extend(
            _SpanBinding(f"/records/{index}/evidence_span", record.evidence_span)
            for index, record in enumerate(output.records)
        )
    elif isinstance(output, CompetitorOutput):
        for index, competitor_record in enumerate(output.records):
            bindings.extend(
                _SpanBinding(f"/records/{index}/evidence_spans/{span_index}", span)
                for span_index, span in enumerate(competitor_record.evidence_spans)
            )
            bindings.append(
                _SpanBinding(
                    f"/records/{index}/pricing/evidence_span",
                    competitor_record.pricing.evidence_span,
                    required=competitor_record.pricing.status != PricingStatus.UNKNOWN,
                )
            )
    elif isinstance(output, InterviewOutput):
        bindings.extend(
            _SpanBinding(f"/findings/{index}/evidence_span", finding.evidence_span)
            for index, finding in enumerate(output.findings)
        )
    return tuple(bindings)


def _numeric_bindings(output: object, source: str) -> tuple[_NumericBinding, ...]:
    bindings: list[_NumericBinding] = []
    if isinstance(output, RelevanceOutput):
        span_set = output.evidence_spans
        for index, reason in enumerate(output.reasons):
            values = _numbers(reason)
            if values:
                bindings.append(_NumericBinding(f"/reasons/{index}", values, span_set))
    elif isinstance(output, CommercialPainOutput):
        for index, pain_record in enumerate(output.records):
            for path, text in (
                ("pain_description", pain_record.pain_description),
                ("existing_workaround", pain_record.existing_workaround),
            ):
                values = _numbers(text or "")
                if values:
                    bindings.append(
                        _NumericBinding(
                            f"/records/{index}/{path}", values, (pain_record.evidence_span,)
                        )
                    )
            for value_index, value in enumerate(pain_record.financial_value_mentioned):
                bindings.append(
                    _NumericBinding(
                        f"/records/{index}/financial_value_mentioned/{value_index}/amount",
                        (Decimal(str(value.amount)),),
                        (value.evidence_span,),
                    )
                )
    elif isinstance(output, GeneralEvidenceOutput):
        for index, evidence_record in enumerate(output.records):
            values = _numbers(evidence_record.claim)
            if values:
                bindings.append(
                    _NumericBinding(
                        f"/records/{index}/claim", values, (evidence_record.evidence_span,)
                    )
                )
    elif isinstance(output, CompetitorOutput):
        for index, competitor_record in enumerate(output.records):
            if competitor_record.pricing.amount is not None:
                evidence = (
                    (competitor_record.pricing.evidence_span,)
                    if competitor_record.pricing.evidence_span is not None
                    else ()
                )
                bindings.append(
                    _NumericBinding(
                        f"/records/{index}/pricing/amount",
                        (Decimal(str(competitor_record.pricing.amount)),),
                        evidence,
                    )
                )
    elif isinstance(output, InterviewOutput):
        for index, finding in enumerate(output.findings):
            values = _numbers(finding.claim)
            if values:
                bindings.append(
                    _NumericBinding(f"/findings/{index}/claim", values, (finding.evidence_span,))
                )
    elif isinstance(output, ClusterNamingOutput):
        values = _numbers(output.description)
        if values:
            bindings.append(_NumericBinding("/description", values, (source,)))
    elif isinstance(output, SearchIntentOutput):
        for index, intent_record in enumerate(output.records):
            values = _numbers(intent_record.keyword)
            if values:
                bindings.append(_NumericBinding(f"/records/{index}/keyword", values, (source,)))
    return tuple(bindings)


def _numbers(text: str) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for match in _NUMBER.finditer(text):
        token = match.group(0).replace(",", "")
        suffix = token[-1:].casefold()
        multiplier = Decimal(1)
        if suffix in {"k", "m", "b", "%"}:
            token = token[:-1]
            multiplier = {
                "k": Decimal(1_000),
                "m": Decimal(1_000_000),
                "b": Decimal(1_000_000_000),
                "%": Decimal(1),
            }[suffix]
        try:
            value = Decimal(token) * multiplier
        except InvalidOperation:
            continue
        if value not in values:
            values.append(value)
    return tuple(values)


def _high_impact_claims(request: AnalysisRequest, output: object) -> tuple[HighImpactClaim, ...]:
    candidates: list[tuple[HighImpactKind, str, JsonValue, tuple[str, ...]]] = []
    if isinstance(output, CommercialPainOutput):
        for index, pain_record in enumerate(output.records):
            for value_index, value in enumerate(pain_record.financial_value_mentioned):
                candidates.append(
                    (
                        HighImpactKind.FINANCIAL_VALUE,
                        f"/records/{index}/financial_value_mentioned/{value_index}/amount",
                        value.amount,
                        (value.evidence_span,),
                    )
                )
            if pain_record.purchase_intent_0_4 is not None and pain_record.purchase_intent_0_4 >= 3:
                candidates.append(
                    (
                        HighImpactKind.HIGH_PURCHASE_INTENT,
                        f"/records/{index}/purchase_intent_0_4",
                        pain_record.purchase_intent_0_4,
                        (pain_record.evidence_span,),
                    )
                )
            if pain_record.severity_1_10 is not None and (
                pain_record.severity_1_10 >= SEVERE_PAIN_REVIEW_THRESHOLD
            ):
                candidates.append(
                    (
                        HighImpactKind.SEVERE_PAIN,
                        f"/records/{index}/severity_1_10",
                        pain_record.severity_1_10,
                        (pain_record.evidence_span,),
                    )
                )
    elif isinstance(output, CompetitorOutput):
        for index, competitor_record in enumerate(output.records):
            if competitor_record.pricing.status != PricingStatus.UNKNOWN:
                candidates.append(
                    (
                        HighImpactKind.COMPETITOR_PRICING,
                        f"/records/{index}/pricing",
                        cast(JsonValue, competitor_record.pricing.model_dump(mode="json")),
                        tuple(
                            span
                            for span in (
                                competitor_record.pricing.evidence_span,
                                *competitor_record.evidence_spans,
                            )
                            if span is not None
                        ),
                    )
                )
    elif isinstance(output, InterviewOutput):
        for index, finding in enumerate(output.findings):
            if finding.finding_type == InterviewFindingType.CONTRADICTION:
                candidates.append(
                    (
                        HighImpactKind.INTERVIEW_CONTRADICTION,
                        f"/findings/{index}",
                        cast(JsonValue, finding.model_dump(mode="json")),
                        (finding.evidence_span,),
                    )
                )
    elif isinstance(output, GeneralEvidenceOutput):
        for index, evidence_record in enumerate(output.records):
            if evidence_record.methodology_id == MethodId.M3 and _numbers(evidence_record.claim):
                candidates.append(
                    (
                        HighImpactKind.WORKFLOW_ECONOMICS,
                        f"/records/{index}/claim",
                        evidence_record.claim,
                        (evidence_record.evidence_span,),
                    )
                )
    claims = [
        HighImpactClaim(
            claim_id=_claim_id(request.cache_key, kind, path, value, spans),
            kind=kind,
            json_path=path,
            proposed_value=value,
            evidence_spans=spans,
        )
        for kind, path, value, spans in candidates
    ]
    return tuple(claims)


def _claim_id(
    cache_key: str,
    kind: HighImpactKind,
    path: str,
    value: JsonValue,
    spans: tuple[str, ...],
) -> str:
    payload = json.dumps(
        [cache_key, kind.value, path, value, spans],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verification_issues(
    claims: tuple[HighImpactClaim, ...],
    verifications: tuple[HighImpactVerification, ...],
) -> list[GroundingIssue]:
    issues: list[GroundingIssue] = []
    by_id = {claim.claim_id: claim for claim in claims}
    seen: set[str] = set()
    valid: dict[str, HighImpactVerification] = {}
    for provided in verifications:
        if provided.claim_id not in by_id or provided.claim_id in seen:
            issues.append(
                _issue(
                    GroundingIssueCode.VERIFICATION_UNEXPECTED,
                    GroundingIssueSeverity.BLOCKING,
                    "/verifications",
                    "verification is duplicated or does not match a detected claim",
                )
            )
            continue
        seen.add(provided.claim_id)
        valid[provided.claim_id] = provided
    for claim in claims:
        matched = valid.get(claim.claim_id)
        if matched is None:
            issues.append(
                _issue(
                    GroundingIssueCode.HIGH_IMPACT_UNVERIFIED,
                    GroundingIssueSeverity.REVIEW,
                    claim.json_path,
                    "high-impact claim requires an independent second pass",
                )
            )
        elif matched.decision == VerificationDecision.AMBIGUOUS:
            issues.append(
                _issue(
                    GroundingIssueCode.HIGH_IMPACT_AMBIGUOUS,
                    GroundingIssueSeverity.REVIEW,
                    claim.json_path,
                    "independent verification was ambiguous",
                )
            )
        elif matched.decision == VerificationDecision.UNSUPPORTED:
            issues.append(
                _issue(
                    GroundingIssueCode.HIGH_IMPACT_UNSUPPORTED,
                    GroundingIssueSeverity.BLOCKING,
                    claim.json_path,
                    "independent verification did not support the claim",
                )
            )
    return issues


def _contradiction_paths(output: object) -> tuple[str, ...]:
    paths: list[str] = []
    if isinstance(output, GeneralEvidenceOutput):
        paths.extend(
            f"/records/{index}"
            for index, record in enumerate(output.records)
            if record.polarity.value == "contradictory"
        )
    elif isinstance(output, InterviewOutput):
        paths.extend(
            f"/findings/{index}"
            for index, finding in enumerate(output.findings)
            if finding.finding_type == InterviewFindingType.CONTRADICTION
        )
    return tuple(paths)


def _detect_prompt_injection(source: str) -> tuple[InjectionSignal, ...]:
    signals: list[InjectionSignal] = []
    for rule_id, pattern in _INJECTION_RULES:
        for match in pattern.finditer(source):
            start, end = match.span()
            excerpt_start = max(0, start - 40)
            excerpt_end = min(len(source), end + 40)
            excerpt = source[excerpt_start:excerpt_end].replace("\x00", "")[:240].strip()
            if excerpt:
                signals.append(
                    InjectionSignal(
                        rule_id=rule_id,
                        start=start,
                        end=end,
                        excerpt=excerpt,
                    )
                )
            if len(signals) == 20:
                return tuple(signals)
    return tuple(signals)
