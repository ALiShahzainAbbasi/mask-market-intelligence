"""Aggregate every real Phase 3 data source (Phase 3-lite M1/M2/M4/M9-
proxy, M3 workflow, M5 competitors [as far as complete], M7 buyer-
accessibility raw evidence, and the pain-point meta-categories) into one
real master JSON, for building the comprehensive 14-market comparative
Technical + Founder report pair. Performs no new real data collection --
pure aggregation of already-real, already-verified sources on disk.

Usage:
    uv run python scripts/aggregate_phase3_master.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "outputs/runs/phase3_deep_dive/phase3_master.json"


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    lite = _load(ROOT / "outputs/runs/phase3_deep_dive/phase3_results.json")
    m3_pattern = str(ROOT / "outputs/runs/phase3_m3_workflow_*/phase3_m3_results.json")
    m3_files = sorted(glob.glob(m3_pattern))
    m3 = _load(Path(m3_files[-1])) if m3_files else []
    m5_path = ROOT / "outputs/runs/phase3_m5_competitors/phase3_m5_results.json"
    m5 = _load(m5_path) if m5_path.is_file() else {"results": []}
    pain = _load(ROOT / "outputs/runs/phase3_deep_dive/pain_point_categories.json")

    lite_by_naics = {r["naics"]: r for r in lite["results"]}  # type: ignore[index]
    m3_by_naics = {r["naics"]: r for r in m3}  # type: ignore[union-attr]
    m5_by_naics = {r["naics"]: r for r in m5["results"]}  # type: ignore[index]

    m7_summaries: dict[int, dict[str, object]] = {}
    for f in sorted(glob.glob(str(ROOT / "outputs/runs/phase3_m7/*.json"))):
        d = _load(Path(f))
        naics = d["naics"]  # type: ignore[index]
        companies = d.get("sampled_companies", [])  # type: ignore[union-attr]
        n = len(companies)
        with_phone = sum(1 for c in companies if c.get("has_phone"))
        with_form = sum(1 for c in companies if c.get("has_contact_form"))
        with_name = sum(1 for c in companies if c.get("named_individual"))
        meta = d.get("meta_ad_library", {})  # type: ignore[union-attr]
        fb = d.get("facebook_presence", [])  # type: ignore[union-attr]
        fb_active = sum(1 for c in fb if c.get("has_facebook_page"))
        m7_summaries[naics] = {  # type: ignore[index]
            "companies_sampled": n,
            "phone_coverage": f"{with_phone}/{n}",
            "contact_form_coverage": f"{with_form}/{n}",
            "named_individual_coverage": f"{with_name}/{n}",
            "meta_ads_query": meta.get("query_used"),
            "meta_ads_approx_active": meta.get("approx_active_ads"),
            "meta_ads_distinct_advertisers": meta.get("distinct_advertisers_observed", []),
            "facebook_checked": len(fb),
            "facebook_active": fb_active,
        }

    master = []
    for naics, lite_r in lite_by_naics.items():
        m3_r = m3_by_naics.get(naics, {})
        m5_r = m5_by_naics.get(naics, {"status": "PENDING"})
        m7_r = m7_summaries.get(naics, {})
        master.append(
            {
                "naics": naics,
                "label": lite_r["label"],
                "m1_light": lite_r["components"]["m1_light"],
                "composite_score_0_10": lite_r["composite_score_0_10"],
                "observed_weight_0_1": lite_r["observed_weight_0_1"],
                "m2_light": lite_r["component_detail"]["m2_light"],
                "m4_light": lite_r["component_detail"]["m4_light"],
                "m9_light_proxy": lite_r["component_detail"]["m9_light"],
                "m3_workflow": {
                    "status": m3_r.get("status", "NOT_ATTEMPTED"),
                    "onet_soc_code": m3_r.get("onet_soc_code"),
                    "occupation_title": m3_r.get("occupation_title"),
                    "grounded_documents": m3_r.get("grounded_documents"),
                    "total_task_statements": m3_r.get("total_task_statements"),
                },
                "m5_competitors": {
                    "status": m5_r.get("status"),
                    "score": m5_r.get("score"),
                    "distinct_real_competitors": m5_r.get("distinct_real_competitors", []),
                    "real_competitor_weaknesses": m5_r.get("real_competitor_weaknesses", {}),
                },
                "m7_buyer_accessibility": m7_r,
            }
        )

    master.sort(key=lambda r: float(r["composite_score_0_10"] or 0), reverse=True)  # type: ignore[arg-type]

    output = {
        "generated_from": {
            "phase3_lite": "outputs/runs/phase3_deep_dive/phase3_results.json",
            "m3_workflow": m3_files[-1] if m3_files else None,
            "m5_competitors": str(m5_path),
            "m7_evidence": "outputs/runs/phase3_m7/*.json",
            "pain_categories": "outputs/runs/phase3_deep_dive/pain_point_categories.json",
        },
        "m5_completion": f"{len(m5_by_naics)}/14",
        "markets": master,
        "pain_point_categories": pain["categories"],  # type: ignore[index]
        "pain_total_mentions": pain["total_mentions"],  # type: ignore[index]
    }
    OUT_PATH.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"M5 completion: {len(m5_by_naics)}/14")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
