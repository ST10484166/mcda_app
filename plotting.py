"""Matplotlib chart builders for MCDA results."""

from __future__ import annotations
from typing import List, Tuple, Optional
import numpy as np
import matplotlib.pyplot as plt

from models import Scenario
from calculations import MCDAResult

COLOR_A = "#4A5E2E"   # Option A
COLOR_B = "#C9A84C"   # Option B


def totals_bar_chart(scenario: Scenario, result: MCDAResult) -> plt.Figure:
    """Horizontal bar chart comparing the two options' total scores."""
    fig, ax = plt.subplots(figsize=(5.2, 3.2), dpi=100)
    labels = [scenario.option_a_label, scenario.option_b_label]
    values = [result.total_a, result.total_b]
    colors = [COLOR_A, COLOR_B]
    bars = ax.barh(labels, values, color=colors)
    ax.set_xlim(0, 10)
    ax.set_xlabel("Weighted Total Score (out of 10)")
    ax.set_title("Total Score Comparison")
    for bar, v in zip(bars, values):
        ax.text(v + 0.15, bar.get_y() + bar.get_height() / 2, f"{v:.2f}",
                 va="center", fontsize=9)
    fig.tight_layout()
    plt.close(fig)
    return fig


def radar_chart(scenario: Scenario) -> plt.Figure:
    """Radar / spider chart comparing raw (unweighted) scores across every
    criterion, so the shape of each option's profile is visible at a glance."""
    criteria = scenario.criteria
    n = len(criteria)
    if n == 0:
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.text(0.5, 0.5, "No criteria", ha="center")
        plt.close(fig)
        return fig

    labels = [c.name for c in criteria]
    scores_a = [c.score_a for c in criteria]
    scores_b = [c.score_b for c in criteria]

    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    scores_a = scores_a + scores_a[:1]
    scores_b = scores_b + scores_b[:1]
    angles = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(6.2, 6.2), subplot_kw=dict(polar=True), dpi=100)
    ax.plot(angles, scores_a, color=COLOR_A, linewidth=2, label=scenario.option_a_label)
    ax.fill(angles, scores_a, color=COLOR_A, alpha=0.15)
    ax.plot(angles, scores_b, color=COLOR_B, linewidth=2, label=scenario.option_b_label)
    ax.fill(angles, scores_b, color=COLOR_B, alpha=0.15)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(0, 10)
    ax.set_title("Score Profile by Criterion", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.12), fontsize=8)
    fig.tight_layout()
    plt.close(fig)
    return fig


def contribution_bar_chart(scenario: Scenario) -> plt.Figure:
    """Grouped horizontal bar chart: each criterion's weighted contribution
    to Option A vs Option B."""
    names = [c.name for c in scenario.criteria]
    wa = [c.weighted_a() for c in scenario.criteria]
    wb = [c.weighted_b() for c in scenario.criteria]

    y = np.arange(len(names))
    bar_h = 0.38

    fig, ax = plt.subplots(figsize=(6.4, max(3.2, 0.36 * max(1, len(names)))), dpi=100)
    ax.barh(y - bar_h / 2, wa, bar_h, color=COLOR_A, label=scenario.option_a_label)
    ax.barh(y + bar_h / 2, wb, bar_h, color=COLOR_B, label=scenario.option_b_label)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Weighted contribution")
    ax.set_title("Criterion Contribution to Each Option")
    ax.legend(fontsize=8)
    fig.tight_layout()
    plt.close(fig)
    return fig


def weight_pie_chart(scenario: Scenario) -> plt.Figure:
    """Pie chart of the current weight distribution across criteria."""
    names = [c.name for c in scenario.criteria]
    weights = [max(0.0, c.weight) for c in scenario.criteria]
    fig, ax = plt.subplots(figsize=(5.8, 5.8), dpi=100)
    if not names or sum(weights) <= 0:
        ax.text(0.5, 0.5, "No weights set", ha="center")
        plt.close(fig)
        return fig
    cmap = plt.get_cmap("Greens")
    n = max(1, len(names) - 1)
    colors = [cmap(0.3 + 0.6 * i / n) for i in range(len(names))]
    ax.pie(weights, labels=names, autopct="%1.0f%%", textprops={"fontsize": 7},
           colors=colors, startangle=90)
    ax.set_title("Weight Distribution")
    fig.tight_layout()
    plt.close(fig)
    return fig


def tornado_chart(rankings: List[Tuple[str, Optional[float]]]) -> plt.Figure:
    """Tornado-style bar chart of criteria influence ranking.
    `rankings`: list of (criterion_name, breakeven_distance), most
    influential (smallest distance) first."""
    filtered = [(n, d) for n, d in rankings if d is not None]
    if not filtered:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No breakeven point found in range for any criterion",
                 ha="center", wrap=True)
        plt.close(fig)
        return fig
    names = [n for n, _ in filtered][::-1]
    dists = [d for _, d in filtered][::-1]
    fig, ax = plt.subplots(figsize=(6.4, max(3.2, 0.36 * max(1, len(names)))), dpi=100)
    ax.barh(names, dists, color=COLOR_A)
    ax.set_xlabel("Weight-point change needed to flip decision\n(smaller = more influential)")
    ax.set_title("Criteria Influence Ranking")
    fig.tight_layout()
    plt.close(fig)
    return fig
