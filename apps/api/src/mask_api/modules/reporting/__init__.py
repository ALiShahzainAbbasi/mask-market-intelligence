"""Compose the v1 market research report: JSON, HTML, and a CSV source manifest."""

from mask_api.modules.reporting.builder import (
    ReportBuildError,
    build_executive_summary,
    build_report_package,
    recommend_next_action,
)
from mask_api.modules.reporting.contracts import (
    MethodReportEntry,
    ReportPackage,
    SourceAttemptOutcome,
    SourceInventoryEntry,
)
from mask_api.modules.reporting.csv_manifest import render_source_manifest_csv
from mask_api.modules.reporting.html_report import render_html_report
from mask_api.modules.reporting.json_report import render_json_report

__all__ = [
    "MethodReportEntry",
    "ReportBuildError",
    "ReportPackage",
    "SourceAttemptOutcome",
    "SourceInventoryEntry",
    "build_executive_summary",
    "build_report_package",
    "recommend_next_action",
    "render_html_report",
    "render_json_report",
    "render_source_manifest_csv",
]
