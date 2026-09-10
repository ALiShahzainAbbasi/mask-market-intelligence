"""Render a self-contained, static HTML market research report.

No template engine or external asset is used -- plain string composition
with `html.escape` on every interpolated value, since report content can
ultimately include evidence text pulled from public web sources (A17.5),
which must never be trusted to be safe markup.
"""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape

from mask_api.modules.reporting.contracts import MethodReportEntry, ReportPackage

_STYLE = """
body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; }
body { padding: 0 1rem; color: #1a1a1a; }
h1, h2, h3 { color: #111; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; font-size: 0.9rem; }
th { background: #f2f2f2; }
.tag { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 0.3rem; font-size: 0.8rem; }
.tag-complete, .tag-eligible_to_advance { background: #d4f4dd; }
.tag-provisional, .tag-not_ready { background: #fff3cd; }
.tag-unknown, .tag-missing, .tag-does_not_meet_gate { background: #f0f0f0; }
.tag-blocked, .tag-confirmed { background: #f8d7da; }
.tag-suspected, .tag-founder_review_required { background: #ffe5b4; }
pre { background: #f7f7f7; padding: 0.75rem; overflow-x: auto; font-size: 0.8rem; }
.summary { background: #eef4ff; padding: 1rem; border-radius: 0.4rem; }
"""


def _tag(value: str) -> str:
    escaped = escape(value)
    return f'<span class="tag tag-{escaped}">{escaped}</span>'


def render_html_report(report: ReportPackage) -> str:
    sections = [
        _header(report),
        _executive_summary(report),
        _scorecard(report),
        _gates(report),
        _vetoes(report),
        _method_detail(report),
        _source_inventory(report),
        _source_attempts(report),
        _evidence_appendix(report),
    ]
    body = "\n".join(sections)
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(report.market_name)} — Market Research Report</title>"
        f"<style>{_STYLE}</style></head><body>\n{body}\n</body></html>\n"
    )


def _header(report: ReportPackage) -> str:
    return (
        f"<h1>{escape(report.market_name)}</h1>"
        f"<p><strong>Market ID:</strong> {escape(report.market_id)} &middot; "
        f"<strong>Formula version:</strong> {escape(report.formula_version)} &middot; "
        f"<strong>Generated:</strong> {escape(report.generated_at.isoformat())} &middot; "
        f"<strong>Snapshot:</strong> {escape(report.snapshot.snapshot_id[:16])}&hellip;</p>"
    )


def _executive_summary(report: ReportPackage) -> str:
    action = escape(report.next_recommended_action)
    return (
        "<h2>Executive Summary</h2>"
        f'<div class="summary"><p>{escape(report.executive_summary)}</p>'
        f"<p><strong>Recommended next action:</strong> {action}</p></div>"
    )


def _scorecard(report: ReportPackage) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(item.method_id.value)}</td>"
        f"<td>{_decimal_or_dash(item.raw_score)}</td>"
        f"<td>{_confidence_cell(item)}</td>"
        f"<td>{_decimal_or_dash(item.risk_adjusted_score)}</td>"
        f"<td>{_tag(item.completeness.value)}</td>"
        "</tr>"
        for item in report.methods
    )
    research = report.snapshot.automated_research_score
    final_status = escape(report.snapshot.final_validated_score.status.value)
    return (
        "<h2>M1&ndash;M10 Scorecard</h2>"
        "<table><thead><tr><th>Method</th><th>Raw score</th><th>Confidence</th>"
        "<th>Risk-adjusted</th><th>Completeness</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<p><strong>Automated Research Score:</strong> {_decimal_or_dash(research.score)} "
        f"(observed methodology weight {_percent(research.observed_weight)}) &mdash; "
        "provisional, never the approved final score.</p>"
        f"<p><strong>Final Validated Score:</strong> {final_status}</p>"
    )


def _confidence_cell(item: MethodReportEntry) -> str:
    if item.confidence is None or item.confidence.label is None:
        return "unknown"
    return f"{item.confidence.numeric_confidence:.1f} {_tag(item.confidence.label.value)}"


def _gates(report: ReportPackage) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(gate.gate_id.value)}</td>"
        f"<td>{_tag(gate.status.value)}</td>"
        f"<td>{_decimal_or_dash(gate.gate_score)}</td>"
        f"<td>{escape(', '.join(gate.unresolved_reasons) or '—')}</td>"
        "</tr>"
        for gate in report.snapshot.gates
    )
    return (
        "<h2>Gate Readiness</h2>"
        "<p>Eligibility only; a human records the actual "
        "advance/hold/reject/select decision.</p>"
        "<table><thead><tr><th>Gate</th><th>Status</th>"
        "<th>Gate score</th><th>Reasons</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _vetoes(report: ReportPackage) -> str:
    findings = report.snapshot.vetoes.findings
    if not findings:
        rows = '<tr><td colspan="3">No automatically detected veto signals.</td></tr>'
    else:
        rows = "".join(
            "<tr>"
            f"<td>{escape(item.veto_id.value)}</td>"
            f"<td>{_tag(item.status.value)}</td>"
            f"<td>{escape(item.trigger_detail)}</td>"
            "</tr>"
            for item in findings
        )
    not_evaluated = ", ".join(report.snapshot.vetoes.not_evaluated) or "none"
    return (
        "<h2>Red Flags / Vetoes</h2>"
        "<table><thead><tr><th>Veto</th><th>Status</th><th>Trigger</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<p><strong>Not automatically evaluated:</strong> {escape(not_evaluated)}</p>"
    )


def _method_detail(report: ReportPackage) -> str:
    sections = []
    for item in report.methods:
        detail_json = (
            json.dumps(item.detail, indent=2, sort_keys=True)
            if item.detail
            else "no detail supplied"
        )
        sections.append(
            f"<h3>{escape(item.method_id.value)} detail</h3><pre>{escape(detail_json)}</pre>"
        )
    return "<h2>Component Inputs &amp; Calculation Breakdown</h2>" + "".join(sections)


def _source_inventory(report: ReportPackage) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(item.source_id)}</td>"
        f"<td>{escape(item.name)}</td>"
        f"<td>{escape(item.access)}</td>"
        f"<td>{escape(item.cost_class)}</td>"
        f"<td>{escape(item.operational_status)}</td>"
        f"<td>{escape(', '.join(method.value for method in item.methods))}</td>"
        "</tr>"
        for item in report.source_inventory
    )
    return (
        "<h2>Source Inventory</h2>"
        "<table><thead><tr><th>Source</th><th>Name</th><th>Access</th><th>Cost</th>"
        "<th>Status</th><th>Methods</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _source_attempts(report: ReportPackage) -> str:
    if not report.source_attempts:
        return "<h2>Sources Attempted This Run</h2><p>No run-level source attempts recorded.</p>"
    rows = "".join(
        "<tr>"
        f"<td>{escape(item.source_id)}</td>"
        f'<td><span class="tag tag-{"complete" if item.outcome == "successful" else "unknown"}">'
        f"{escape(item.outcome)}</span></td>"
        f"<td>{escape(item.detail or '—')}</td>"
        f"<td>{item.requests_used}</td>"
        f"<td>{item.cache_hits}</td>"
        "</tr>"
        for item in report.source_attempts
    )
    return (
        "<h2>Sources Attempted This Run</h2>"
        "<table><thead><tr><th>Source</th><th>Outcome</th><th>Detail</th>"
        "<th>Requests</th><th>Cache hits</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _evidence_appendix(report: ReportPackage) -> str:
    references: list[str] = []
    for finding in report.snapshot.vetoes.findings:
        references.extend(finding.evidence_references)
    items = "".join(f"<li>{escape(reference)}</li>" for reference in sorted(set(references)))
    return (
        "<h2>Evidence Appendix (veto-linked references)</h2>"
        f"<ul>{items or '<li>No veto-linked evidence references in this snapshot.</li>'}</ul>"
        "<p>Per-method evidence references are embedded in each method's "
        "Component Inputs &amp; Calculation Breakdown section above.</p>"
    )


def _decimal_or_dash(value: Decimal | None) -> str:
    if value is None:
        return "&mdash;"
    return escape(f"{value:.2f}")


def _percent(value: Decimal) -> str:
    return escape(f"{(value * Decimal('100')):.0f}%")
