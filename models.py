"""Data models for MCDA: Criterion, Threshold, Scenario + JSON serialization."""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


def _new_id() -> str:
    """Generate a short unique ID for tracking rows."""
    return uuid.uuid4().hex[:12]


@dataclass
class Criterion:
    """One criterion: weight (%), scores for each option (1-10), and notes."""

    id: str = field(default_factory=_new_id)
    name: str = "New Criterion"
    weight: float = 0.0          # percentage points; all criteria should sum to 100
    score_a: float = 5.0         # 1-10
    score_b: float = 5.0         # 1-10
    notes_a: str = ""
    notes_b: str = ""

    def weighted_a(self) -> float:
        """Weighted score for Option A: (Weight / 100) × Score."""
        return (self.weight / 100.0) * self.score_a

    def weighted_b(self) -> float:
        """Weighted score for Option B: (Weight / 100) × Score."""
        return (self.weight / 100.0) * self.score_b

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Criterion":
        return Criterion(
            id=d.get("id", _new_id()),
            name=d.get("name", "Criterion"),
            weight=float(d.get("weight", 0.0)),
            score_a=float(d.get("score_a", 5.0)),
            score_b=float(d.get("score_b", 5.0)),
            notes_a=d.get("notes_a", ""),
            notes_b=d.get("notes_b", ""),
        )


@dataclass
class Threshold:
    """A critical / deal-breaker requirement (feasibility gate).

    `pass_a` / `pass_b` are booleans: True means the requirement is
    currently satisfied for that option. If ANY threshold is not passed
    for an option, that option is treated as infeasible regardless of
    its weighted MCDA score - the gate is checked before, and overrides,
    the normal score comparison.
    """

    id: str = field(default_factory=_new_id)
    name: str = "New Threshold"
    pass_a: bool = True
    pass_b: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Threshold":
        return Threshold(
            id=d.get("id", _new_id()),
            name=d.get("name", "Threshold"),
            pass_a=bool(d.get("pass_a", True)),
            pass_b=bool(d.get("pass_b", True)),
            notes=d.get("notes", ""),
        )


@dataclass
class Scenario:
    """A named, fully self-contained snapshot of the decision model
    (its own criteria, weights, scores and thresholds). Scenarios such
    as 'Optimistic' / 'Expected' / 'Worst Case' can be saved and switched
    between instantly."""

    name: str = "Expected"
    option_a_label: str = "Option A - Study Abroad"
    option_b_label: str = "Option B - Stay & Reapply"
    criteria: List[Criterion] = field(default_factory=list)
    thresholds: List[Threshold] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "option_a_label": self.option_a_label,
            "option_b_label": self.option_b_label,
            "criteria": [c.to_dict() for c in self.criteria],
            "thresholds": [t.to_dict() for t in self.thresholds],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Scenario":
        return Scenario(
            name=d.get("name", "Scenario"),
            option_a_label=d.get("option_a_label", "Option A"),
            option_b_label=d.get("option_b_label", "Option B"),
            criteria=[Criterion.from_dict(c) for c in d.get("criteria", [])],
            thresholds=[Threshold.from_dict(t) for t in d.get("thresholds", [])],
        )


# 2 Default criteria names for the "Expected" scenario, in order of appearance.
DEFAULT_CRITERIA_NAMES = [
    "Quality of life",
    "Personal fulfillment",
]


def build_default_scenario() -> Scenario:
    """Create the default 'Expected' scenario: the 2 standard criteria
    with equal weights (auto-normalized to sum exactly to 100%) and three
    example critical thresholds relevant to a study-abroad decision."""
    n = len(DEFAULT_CRITERIA_NAMES)
    equal_weight = round(100.0 / n, 2)
    criteria = [
        Criterion(name=nm, weight=equal_weight, score_a=5.0, score_b=5.0)
        for nm in DEFAULT_CRITERIA_NAMES
    ]
    # Correct rounding drift so weights sum to exactly 100.
    drift = round(100.0 - sum(c.weight for c in criteria), 2)
    criteria[-1].weight = round(criteria[-1].weight + drift, 2)

    thresholds = [
        Threshold(
            name="Funding secured (if needed)",
            pass_a=True, pass_b=True,
            notes="Loan / bursary / family funding confirmed and legally committed.",
        ),
        Threshold(
            name="Visa approved",
            pass_a=True, pass_b=True,
            notes="visa granted (typically only applicable to Option A).",
        ),
        Threshold(
            name="Loan repayment is affordable",
            pass_a=True, pass_b=True,
            notes="Projected repayments fit a realistic income.",
        ),
    ]
    return Scenario(name="Expected", criteria=criteria, thresholds=thresholds)
