# MCDA Decision Tool

A template for building Multi-Criteria Decision Analysis (MCDA) tools—GUI applications for comparing two options using weighted scoring.

## What is MCDA?

MCDA helps you make structured decisions by:
- Defining criteria that matter for your decision
- Scoring how well each option performs on each criterion (1–10)
- Weighting criteria by importance
- Computing an overall recommendation

You can also set deal-breaker thresholds (e.g., *must be affordable*) that can exclude an option entirely.

## Why use this template?

You have a specific decision to make (study abroad, buy a house, change jobs, etc.) and want a structured, documented way to evaluate your options. This template gives you:
- A desktop GUI to edit criteria, weights, scores, and thresholds—no code changes required
- Sensitivity analysis to see which criteria matter most
- Multiple scenarios (optimistic, pessimistic, etc.)
- Export to Excel or PDF for sharing

## Getting Started

**Install:**
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Run:**
```bash
python main.py
```

Requires Python 3.9+. On Linux, you may need `sudo apt-get install python3-tk`.

## Customizing Your Decision

1. **Edit `models.py`** — Replace the default criteria with your own in the `build_default_scenario()` function.
2. **Adjust `plotting.py`** — Change `COLOR_A` and `COLOR_B` to your preferred colors.
3. **Run and use** — Add criteria, scores, weights, thresholds, and scenarios through the GUI. Save and export as needed.

## Project Structure

| File | Purpose |
|---|---|
| `models.py` | Data classes: `Criterion`, `Threshold`, `Scenario` + JSON serialization. |
| `calculations.py` | MCDA scoring, feasibility checks, sensitivity analysis. |
| `gui.py` | CustomTkinter UI: tabs, tables, charts. |
| `plotting.py` | Matplotlib chart builders. |
| `file_manager.py` | Save/load projects, export Excel/PDF. |
| `history.py` | Undo/redo. |
| `main.py` | Entry point. |

### Autosave
The full project autosaves every 30 seconds and on close to
`~/.mcda_tool/autosave_mcda.json`. On startup you'll be offered the chance
to restore it.

## 5. Extending to more than two options

The model is built around a generic `Criterion` (id/name/weight) plus
per-option scores. To add Option C in the future, the cleanest path is to
extend `Criterion` to hold a `scores: Dict[str, float]` keyed by an option
id instead of fixed `score_a`/`score_b` fields, and generalize
`MCDAEngine.compute()` to loop over an `options: List[str]` list rather
than hardcoding A/B. The GUI tables would then render one score column and
one weighted column per option. This refactor is intentionally isolated to
`models.py` + `calculations.py` — the plotting and file-export modules
already iterate rather than hardcode two series where practical, so the
GUI is the main place that would need new columns.
