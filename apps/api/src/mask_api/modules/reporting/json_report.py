"""Render the machine-readable JSON report (report.json)."""

from __future__ import annotations

import json

from mask_api.modules.reporting.contracts import ReportPackage


def render_json_report(report: ReportPackage) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
