from enum import StrEnum


class MarketStage(StrEnum):
    BROAD_SCREEN = "broad_screen"
    DEEP_RESEARCH = "deep_research"
    LIVE_VALIDATION = "live_validation"
    FINALIST = "finalist"
    SELECTED = "selected"
    REJECTED = "rejected"


class MarketStatus(StrEnum):
    ACTIVE = "active"
    HOLD = "hold"
    ARCHIVED = "archived"


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    RETIRED = "retired"


class ResearchPlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"
