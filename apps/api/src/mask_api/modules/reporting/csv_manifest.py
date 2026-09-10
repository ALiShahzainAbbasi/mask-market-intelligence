"""Render the CSV source manifest (stdlib `csv` only, no new dependency)."""

from __future__ import annotations

import csv
import io

from mask_api.modules.reporting.contracts import ReportPackage

_HEADER = (
    "source_id",
    "name",
    "access",
    "cost_class",
    "operational_status",
    "methods",
    "attempt_outcome",
    "attempt_detail",
    "requests_used",
    "cache_hits",
)


def render_source_manifest_csv(report: ReportPackage) -> str:
    attempts_by_source = {item.source_id: item for item in report.source_attempts}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    for source in report.source_inventory:
        attempt = attempts_by_source.get(source.source_id)
        writer.writerow(
            (
                source.source_id,
                source.name,
                source.access,
                source.cost_class,
                source.operational_status,
                ";".join(method.value for method in source.methods),
                attempt.outcome if attempt else "",
                attempt.detail or "" if attempt else "",
                attempt.requests_used if attempt else "",
                attempt.cache_hits if attempt else "",
            )
        )
    return buffer.getvalue()
