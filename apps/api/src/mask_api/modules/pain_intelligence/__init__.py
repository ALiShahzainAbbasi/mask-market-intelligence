"""Grounded, duplicate-safe, deterministic M2 pain intelligence."""

from mask_api.modules.pain_intelligence.contracts import (
    ClusteringConfiguration,
    M2Result,
    M2Status,
    PainMention,
)
from mask_api.modules.pain_intelligence.ingestion import mentions_from_grounding
from mask_api.modules.pain_intelligence.service import PainIntelligenceService

__all__ = [
    "ClusteringConfiguration",
    "M2Result",
    "M2Status",
    "PainIntelligenceService",
    "PainMention",
    "mentions_from_grounding",
]
