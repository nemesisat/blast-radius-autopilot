"""The Data Necromancer — autonomous metadata investigation & knowledge
resurrection engine for DataHub.

Resurrects the dead (undocumented assets) and exposes the zombies (metadata that
has silently gone wrong), writing evidence-backed conclusions back to the graph.
"""

from .evidence import Evidence
from .investigator import (
    Contradiction,
    Investigation,
    detect_contradictions,
    evidence_footer,
    investigate,
)
from .health import Health, HealthResult, classify, coverage, leaderboard

__version__ = "0.1.0"

__all__ = [
    "Evidence",
    "investigate",
    "detect_contradictions",
    "evidence_footer",
    "Investigation",
    "Contradiction",
    "classify",
    "Health",
    "HealthResult",
    "leaderboard",
    "coverage",
]
