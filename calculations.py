"""MCDA calculation engine: scoring, feasibility checks, sensitivity analysis."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional
import copy

from models import Scenario

WEIGHT_TOLERANCE = 0.01  # percentage points of slack allowed away from 100


@dataclass
class FeasibilityResult:
    """Outcome of running every Threshold (deal-breaker) against both options."""
    option_a_feasible: bool
    option_b_feasible: bool
    failed_a: List[str]
    failed_b: List[str]

    @property
    def any_gate_active(self) -> bool:
        return not self.option_a_feasible or not self.option_b_feasible


@dataclass
class MCDAResult:
    """Full result of one MCDA computation for a scenario."""
    total_a: float
    total_b: float
    difference: float           # total_a - total_b
    pct_difference: float       # symmetric percentage difference, always >= 0
    recommended: Optional[str]  # 'A', 'B', or None (tie / neither feasible)
    confidence_label: str
    feasibility: FeasibilityResult


class MCDAEngine:
    """Stateless helper: every method takes a Scenario and returns a result,
    never storing state itself, which makes it trivial to reuse across
    scenarios, sensitivity sweeps, and tests."""

    # ------------------------------------------------------------------
    # Weight validation
    # ------------------------------------------------------------------

    @staticmethod
    def weight_sum(scenario: Scenario) -> float:
        return round(sum(c.weight for c in scenario.criteria), 4)

    @staticmethod
    def weights_valid(scenario: Scenario) -> bool:
        return abs(MCDAEngine.weight_sum(scenario) - 100.0) <= WEIGHT_TOLERANCE

    @staticmethod
    def normalize_weights(scenario: Scenario) -> None:
        """Scale all weights proportionally so they sum to 100."""
        total = sum(c.weight for c in scenario.criteria)
        if not scenario.criteria:
            return
        if total <= 0:
            equal = 100.0 / len(scenario.criteria)
            for c in scenario.criteria:
                c.weight = round(equal, 2)
            return
        factor = 100.0 / total
        for c in scenario.criteria:
            c.weight = round(c.weight * factor, 2)
        # correct rounding drift on the last item so the sum is exact
        drift = round(100.0 - sum(c.weight for c in scenario.criteria), 2)
        scenario.criteria[-1].weight = round(scenario.criteria[-1].weight + drift, 2)

    # ------------------------------------------------------------------
    # Feasibility gate (critical thresholds / deal-breakers)
    # ------------------------------------------------------------------

    @staticmethod
    def check_feasibility(scenario: Scenario) -> FeasibilityResult:
        failed_a = [t.name for t in scenario.thresholds if not t.pass_a]
        failed_b = [t.name for t in scenario.thresholds if not t.pass_b]
        return FeasibilityResult(
            option_a_feasible=len(failed_a) == 0,
            option_b_feasible=len(failed_b) == 0,
            failed_a=failed_a,
            failed_b=failed_b,
        )

    # ------------------------------------------------------------------
    # Confidence labelling
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_label(pct_diff: float) -> str:
        pct = abs(pct_diff)
        if pct < 3:
            return "Too close to call"
        elif pct < 8:
            return "Slight advantage"
        elif pct < 15:
            return "Moderate advantage"
        else:
            return "Strong advantage"

    # ------------------------------------------------------------------
    # Main computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute(scenario: Scenario) -> MCDAResult:
        """Compute weighted totals and the final recommendation.

        The critical-threshold feasibility gate is applied FIRST: if one
        option fails a deal-breaker, it is recommended against regardless
        of its weighted score. If both fail, there is no feasible option.
        Only when both options clear the gate does the normal weighted
        score / confidence-band comparison decide the recommendation.
        """
        total_a = sum(c.weighted_a() for c in scenario.criteria)
        total_b = sum(c.weighted_b() for c in scenario.criteria)
        diff = total_a - total_b
        denom = (total_a + total_b) / 2.0
        pct_diff = 0.0 if denom == 0 else (abs(diff) / denom) * 100.0

        feas = MCDAEngine.check_feasibility(scenario)

        if feas.any_gate_active:
            if not feas.option_a_feasible and not feas.option_b_feasible:
                recommended = None
                confidence = "Neither option is currently feasible"
            elif not feas.option_a_feasible:
                recommended = "B"
                confidence = "Option A blocked by critical threshold(s)"
            else:
                recommended = "A"
                confidence = "Option B blocked by critical threshold(s)"
        else:
            if abs(diff) < 1e-9:
                recommended = None
            else:
                recommended = "A" if diff > 0 else "B"
            confidence = MCDAEngine._confidence_label(pct_diff)

        return MCDAResult(
            total_a=total_a,
            total_b=total_b,
            difference=diff,
            pct_difference=pct_diff,
            recommended=recommended,
            confidence_label=confidence,
            feasibility=feas,
        )

    # ------------------------------------------------------------------
    # Sensitivity analysis
    # ------------------------------------------------------------------

    @staticmethod
    def recompute_with_weight_override(scenario: Scenario, criterion_id: str,
                                        new_weight: float) -> Tuple[float, float]:
        """Return (total_a, total_b) as if `criterion_id`'s weight were set
        to `new_weight`, with every OTHER weight rescaled proportionally so
        the total still sums to 100. Never mutates the original scenario -
        used for "what if" slider previews and breakeven search."""
        temp = copy.deepcopy(scenario)
        target = next((c for c in temp.criteria if c.id == criterion_id), None)
        if target is None:
            result = MCDAEngine.compute(temp)
            return result.total_a, result.total_b

        new_weight = max(0.0, min(100.0, new_weight))
        others = [c for c in temp.criteria if c.id != criterion_id]
        others_current_sum = sum(c.weight for c in others)
        remaining = 100.0 - new_weight

        if others_current_sum > 0:
            factor = remaining / others_current_sum
            for c in others:
                c.weight = c.weight * factor
        elif others:
            equal = remaining / len(others)
            for c in others:
                c.weight = equal

        target.weight = new_weight
        result = MCDAEngine.compute(temp)
        return result.total_a, result.total_b

    @staticmethod
    def find_breakeven_weight(scenario: Scenario, criterion_id: str,
                               steps: int = 400) -> Optional[float]:
        """Scan a single criterion's weight from 0 to 100 (rescaling every
        other weight proportionally) and return the weight value at which
        the leading option flips, or None if it never flips across the
        whole 0-100 range."""
        prev_sign = None
        breakeven = None
        for i in range(steps + 1):
            w = 100.0 * i / steps
            ta, tb = MCDAEngine.recompute_with_weight_override(scenario, criterion_id, w)
            sign = 1 if ta >= tb else -1
            if prev_sign is not None and sign != prev_sign:
                breakeven = w
                break
            prev_sign = sign
        return breakeven

    @staticmethod
    def influence_ranking(scenario: Scenario) -> List[Tuple[str, Optional[float]]]:
        """Rank criteria by decision influence: the smaller the weight-point
        distance between a criterion's CURRENT weight and its breakeven
        weight, the more influential/fragile that criterion is (a small
        nudge is enough to flip the recommended option).

        Returns a list of (criterion_name, distance) sorted most -> least
        influential. `distance` is None if the decision never flips across
        the full 0-100 range for that criterion.
        """
        rankings = []
        for c in scenario.criteria:
            breakeven = MCDAEngine.find_breakeven_weight(scenario, c.id)
            distance = None if breakeven is None else abs(breakeven - c.weight)
            rankings.append((c.name, distance))

        def sort_key(item):
            _, dist = item
            return (dist is None, dist if dist is not None else 0.0)

        rankings.sort(key=sort_key)
        return rankings

    # ------------------------------------------------------------------
    # Contribution helper (for the "criterion contribution" bar chart)
    # ------------------------------------------------------------------

    @staticmethod
    def contributions(scenario: Scenario) -> List[Tuple[str, float, float]]:
        """Return list of (criterion_name, weighted_a, weighted_b)."""
        return [(c.name, c.weighted_a(), c.weighted_b()) for c in scenario.criteria]
