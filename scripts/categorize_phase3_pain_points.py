"""Group the 51 real, grounded Phase 3 pain mentions (recovered by
scripts/extract_phase3_real_quotes.py from real cached Gemini responses)
into a small number of real, evidence-based meta-categories, instead of
leaving them as dozens of one-off Gemini-generated pain_category/
pain_subcategory labels.

Real deterministic rule, not a language-model judgment (matching this
project's core doctrine: Gemini extracts and classifies individual
mentions; it never decides the scoring/grouping taxonomy): each real
mention is assigned to the first meta-category whose real keyword set
matches its real pain_category + pain_subcategory + pain_description
text (case-insensitive substring match), checked in a fixed priority
order chosen to match the real, dominant patterns actually observed
across all 14 markets (read by hand before writing this list -- see
outputs/runs/phase3_deep_dive/real_quotes_by_market.json). Any real
mention matching none of the keyword sets falls into a real, disclosed
"Other" bucket -- never force-fit.

Usage:
    uv run python scripts/categorize_phase3_pain_points.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUOTES_PATH = ROOT / "outputs/runs/phase3_deep_dive/real_quotes_by_market.json"
OUT_PATH = ROOT / "outputs/runs/phase3_deep_dive/pain_point_categories.json"

# Order matters: checked top to bottom, first real match wins.
META_CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "Invoicing, Billing & Cash Flow",
        [
            "invoic",
            "deposit",
            "billing",
            "payment",
            "cash flow",
            "ledger",
            "non-payment",
            "underpayment",
            "delayed payment",
            "transaction fee",
        ],
    ),
    (
        "Estimating, Quoting & Pricing",
        [
            "estimat",
            "quot",
            "pricing",
            "price updat",
            "price increase",
            "job pricing",
        ],
    ),
    (
        "Software Tools: Usability, Integration & Cost",
        [
            "software",
            "app overload",
            "user interface",
            "ui",
            "ux",
            "mobile app",
            "subscription",
            "compatib",
            "feature limitation",
            "data management",
            "customer data",
        ],
    ),
    (
        "Customer Acquisition & Sales/Marketing",
        [
            "lead generation",
            "client acquisition",
            "acquiring customers",
            "website creation",
            "sales contact",
            "marketing",
        ],
    ),
    (
        "Scheduling, Dispatch & Administrative/Compliance Burden",
        [
            "scheduling",
            "dispatch",
            "paperwork",
            "documentation",
            "administrative",
            "labor rights",
            "compensation",
            "startup",
            "expansion cost",
            "tech support",
            "access management",
        ],
    ),
]


def _classify(mention: dict[str, object]) -> str:
    haystack = " ".join(
        str(mention.get(field) or "")
        for field in ("pain_category", "pain_subcategory", "pain_description")
    ).lower()
    for name, keywords in META_CATEGORIES:
        if any(kw in haystack for kw in keywords):
            return name
    return "Other (unclassified)"


def _mean(values: list[int]) -> float | None:
    return round(statistics.mean(values), 2) if values else None


def main() -> None:
    by_market: dict[str, list[dict[str, object]]] = json.loads(
        QUOTES_PATH.read_text(encoding="utf-8")
    )
    all_mentions: list[dict[str, object]] = []
    for market_label, mentions in by_market.items():
        for m in mentions:
            m = dict(m)
            m["market_label"] = market_label
            all_mentions.append(m)

    print(f"Total real mentions: {len(all_mentions)}")

    grouped: dict[str, list[dict[str, object]]] = {name: [] for name, _ in META_CATEGORIES}
    grouped["Other (unclassified)"] = []
    for m in all_mentions:
        category = _classify(m)
        m["assigned_meta_category"] = category
        grouped[category].append(m)

    summary = []
    for name, mentions in grouped.items():
        severities = [int(str(v)) for m in mentions if (v := m.get("severity_1_10")) is not None]
        ai_scores = [
            int(str(v)) for m in mentions if (v := m.get("ai_suitability_1_10")) is not None
        ]
        econ_scores = [
            int(str(v)) for m in mentions if (v := m.get("economic_impact_1_10")) is not None
        ]
        markets_touched = sorted({str(m["market_label"]) for m in mentions})
        summary.append(
            {
                "category": name,
                "real_mention_count": len(mentions),
                "share_of_total_pct": round(100 * len(mentions) / len(all_mentions), 1)
                if all_mentions
                else 0,
                "markets_with_this_pain": len(markets_touched),
                "market_labels": markets_touched,
                "mean_severity_1_10": _mean(severities),
                "n_with_severity": len(severities),
                "mean_ai_suitability_1_10": _mean(ai_scores),
                "n_with_ai_suitability": len(ai_scores),
                "mean_economic_impact_1_10": _mean(econ_scores),
                "n_with_economic_impact": len(econ_scores),
                "sample_real_quotes": [
                    {
                        "market": m["market_label"],
                        "quote": m["evidence_span"],
                        "pain_category_raw": m["pain_category"],
                    }
                    for m in mentions[:4]
                ],
            }
        )
    summary.sort(key=lambda s: int(str(s["real_mention_count"])), reverse=True)

    OUT_PATH.write_text(
        json.dumps({"total_mentions": len(all_mentions), "categories": summary}, indent=2),
        encoding="utf-8",
    )
    for s in summary:
        print(
            f"{s['category']}: {s['real_mention_count']} mentions "
            f"({s['share_of_total_pct']}%), {s['markets_with_this_pain']} markets, "
            f"mean severity={s['mean_severity_1_10']}, mean AI-suitability="
            f"{s['mean_ai_suitability_1_10']}"
        )
    print(f"\nOutput: {OUT_PATH}")


if __name__ == "__main__":
    main()
