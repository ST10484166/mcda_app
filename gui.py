"""CustomTkinter GUI for MCDA tool: tabs, tables, charts."""

from __future__ import annotations
import os
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from typing import Optional, List, Callable

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from models import Scenario, Criterion, Threshold, build_default_scenario
from calculations import MCDAEngine, MCDAResult
from history import UndoManager
from file_manager import ProjectFile, export_to_excel, export_to_pdf
import plotting

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

COLOR_A = "#4A5E2E"
COLOR_B = "#C9A84C"
COLOR_WARN = "#B94A48"
COLOR_OK = "#4A5E2E"
AUTOSAVE_DIR = os.path.join(os.path.expanduser("~"), ".mcda_tool")


# =========================================================================
# SMALL REUSABLE DIALOGS
# =========================================================================

class NotesDialog(ctk.CTkToplevel):
    """Popup editor for a criterion's Option A / Option B justification notes."""

    def __init__(self, master, criterion: Criterion, on_save: Callable[[], None]):
        super().__init__(master)
        self.title(f"Notes - {criterion.name}")
        self.geometry("480x420")
        self.criterion = criterion
        self.on_save = on_save
        self.grab_set()

        ctk.CTkLabel(self, text=f"Notes for: {criterion.name}",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(12, 6))

        ctk.CTkLabel(self, text="Option A justification:").pack(anchor="w", padx=16)
        self.txt_a = ctk.CTkTextbox(self, height=140)
        self.txt_a.pack(fill="x", padx=16, pady=(2, 10))
        self.txt_a.insert("1.0", criterion.notes_a)

        ctk.CTkLabel(self, text="Option B justification:").pack(anchor="w", padx=16)
        self.txt_b = ctk.CTkTextbox(self, height=140)
        self.txt_b.pack(fill="x", padx=16, pady=(2, 10))
        self.txt_b.insert("1.0", criterion.notes_b)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="Save", command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="gray40",
                      command=self.destroy).pack(side="left", padx=6)

    def _save(self):
        self.criterion.notes_a = self.txt_a.get("1.0", "end-1c")
        self.criterion.notes_b = self.txt_b.get("1.0", "end-1c")
        self.on_save()
        self.destroy()


class BulkWeightsDialog(ctk.CTkToplevel):
    """Edit multiple weights at once; unspecified weights auto-scale to sum to 100%."""

    def __init__(self, master, scenario: Scenario, on_apply: Callable[[], None]):
        super().__init__(master)
        self.title("Bulk Edit Weights")
        self.geometry("640x480")
        self.scenario = scenario
        self.on_apply = on_apply
        self.grab_set()

        ctk.CTkLabel(self, text="Edit multiple weights (leave blank to auto-scale)",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 6))

        self.container = ctk.CTkScrollableFrame(self)
        self.container.pack(fill="both", expand=True, padx=12, pady=6)

        self.entries = []  # list of (criterion, tk.StringVar)
        for i, c in enumerate(self.scenario.criteria, start=1):
            row = ctk.CTkFrame(self.container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            idx = ctk.CTkLabel(row, text=f"{i}.", width=28)
            idx.pack(side="left", padx=(4, 6))
            name = ctk.CTkLabel(row, text=c.name)
            name.pack(side="left", padx=(0, 8))
            var = tk.StringVar(value=self._fmt(c.weight))
            ent = ctk.CTkEntry(row, width=100, textvariable=var)
            ent.pack(side="right", padx=6)
            self.entries.append((c, var))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)
        ctk.CTkButton(btn_frame, text="Apply & Normalize", command=self._apply,
                      fg_color=COLOR_B, hover_color="#a88a3e", width=160).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy, width=120).pack(side="left", padx=6)

    @staticmethod
    def _fmt(v: float) -> str:
        return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)

    def _parse(self, text: str) -> Optional[float]:
        try:
            if text.strip() == "":
                return None
            return float(text)
        except Exception:
            return None

    def _apply(self):

        # Read specified weights (None means unspecified)
        specified = {}
        unspecified = []
        for c, var in self.entries:
            val = self._parse(var.get())
            if val is None:
                unspecified.append(c)
            else:
                specified[c.id] = max(0.0, min(100.0, val))

        spec_sum = sum(specified.values())
        if spec_sum > 100.0 + 1e-9:
            messagebox.showwarning("Invalid weights", "Specified weights sum to more than 100%.")
            return

        remaining = round(100.0 - spec_sum, 10)

        # Sum current weights of unspecified to preserve relative proportions
        others_current = sum(c.weight for c in unspecified)
        new_weights = {}
        if unspecified:
            if others_current > 0:
                factor = remaining / others_current
                for c in unspecified:
                    new_weights[c.id] = round(c.weight * factor, 2)
            else:
                # distribute equally
                equal = round(remaining / len(unspecified), 2)
                for c in unspecified:
                    new_weights[c.id] = equal

        # Apply specified weights
        for c in self.scenario.criteria:
            if c.id in specified:
                c.weight = round(specified[c.id], 2)
            elif c.id in new_weights:
                c.weight = new_weights[c.id]

        # Correct rounding drift
        drift = round(100.0 - sum(c.weight for c in self.scenario.criteria), 2)
        if self.scenario.criteria:
            self.scenario.criteria[-1].weight = round(self.scenario.criteria[-1].weight + drift, 2)

        self.on_apply()
        self.destroy()


def ask_text(master, title: str, prompt: str, initial: str = "") -> Optional[str]:
    return simpledialog.askstring(title, prompt, initialvalue=initial, parent=master)


# =========================================================================
# Tab 1: CRITERIA MATRIX
# =========================================================================

class CriteriaMatrixTab(ctk.CTkFrame):
    """Editable criteria table: Criterion | Weight% | Score A | Score B |
    Weighted A | Weighted B | Notes | Delete."""

    def __init__(self, master, app: "MCDAApp"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._row_widgets = []  # keep references to entries per criterion id

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))

        self.weight_sum_label = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.weight_sum_label.pack(side="left", padx=(0, 16))

        ctk.CTkButton(top, text="+ Add Criterion", command=self._add_criterion,
                      width=140).pack(side="left", padx=4)
        ctk.CTkButton(top, text="Bulk Edit Weights", command=self._bulk_edit,
                  width=160).pack(side="left", padx=4)
        ctk.CTkButton(top, text="Normalize Weights to 100%", command=self._normalize,
                      width=190, fg_color=COLOR_B, hover_color="#a88a3e",
                      text_color="black").pack(side="left", padx=4)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._apply_filter())
        search_entry = ctk.CTkEntry(top, placeholder_text="Search / filter criteria...",
                                     textvariable=self.search_var, width=220)
        search_entry.pack(side="right", padx=4)

        # Header row (add numbering column)
        header = ctk.CTkFrame(self, fg_color="gray20")
        header.pack(fill="x", padx=10)
        cols = [("#", 1), ("Criterion", 3), ("Weight %", 1), ("A Score", 1), ("B Score", 1),
                ("Weighted A", 1), ("Weighted B", 1), ("Notes", 1), ("", 1)]
        for i, (text, weight) in enumerate(cols):
            header.grid_columnconfigure(i, weight=weight)
            ctk.CTkLabel(header, text=text, font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=i, sticky="w", padx=6, pady=6)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for i in range(len(cols)):
            self.scroll.grid_columnconfigure(i, weight=[1, 3, 1, 1, 1, 1, 1, 1, 1][i])

        self.refresh()

    # -- data mutation helpers --------------------------------------------------

    def _add_criterion(self):
        self.app.push_undo()
        self.app.scenario.criteria.append(Criterion(name="New Criterion", weight=0.0))
        self.app.on_model_changed(rebuild_table=True)

    def _delete_criterion(self, criterion_id: str):
        c = next((c for c in self.app.scenario.criteria if c.id == criterion_id), None)
        if c and messagebox.askyesno("Delete criterion", f"Delete '{c.name}'?"):
            self.app.push_undo()
            self.app.scenario.criteria = [
                x for x in self.app.scenario.criteria if x.id != criterion_id]
            self.app.on_model_changed(rebuild_table=True)

    def _normalize(self):
        self.app.push_undo()
        MCDAEngine.normalize_weights(self.app.scenario)
        self.app.on_model_changed(rebuild_table=True)

    def _apply_filter(self):
        query = self.search_var.get().strip().lower()
        for row in self._row_widgets:
            visible = query in row["criterion"].name.lower()
            for w in row.get("widgets", []):
                if visible:
                    w.grid()
                else:
                    w.grid_remove()

    def _bulk_edit(self):
        def apply_cb():
            self.app.push_undo()
            self.app.on_model_changed(rebuild_table=True)

        BulkWeightsDialog(self, self.app.scenario, on_apply=apply_cb)

    # -- (re)building the visual table (again...) -------------------------------------------

    def refresh(self):
        """Fully rebuild the table rows from the current scenario."""
        for w in self.scroll.winfo_children():
            w.destroy()
        self._row_widgets = []

        for r, c in enumerate(self.app.scenario.criteria):
            self._build_row(r, c)

        self._update_weight_sum_label()

    def _build_row(self, r: int, c: Criterion):
        # Place cells directly in the scroll grid so columns align with header
        idx_label = ctk.CTkLabel(self.scroll, text=str(r + 1))
        idx_label.grid(row=r, column=0, sticky="w", padx=6, pady=2)

        name_var = tk.StringVar(value=c.name)
        weight_var = tk.StringVar(value=self._fmt(c.weight))
        score_a_var = tk.StringVar(value=self._fmt(c.score_a))
        score_b_var = tk.StringVar(value=self._fmt(c.score_b))

        name_entry = ctk.CTkEntry(self.scroll, textvariable=name_var)
        name_entry.grid(row=r, column=1, sticky="ew", padx=4, pady=2)

        weight_entry = ctk.CTkEntry(self.scroll, textvariable=weight_var, width=70)
        weight_entry.grid(row=r, column=2, sticky="w", padx=4, pady=2)

        score_a_entry = ctk.CTkEntry(self.scroll, textvariable=score_a_var, width=60)
        score_a_entry.grid(row=r, column=3, sticky="w", padx=4, pady=2)

        score_b_entry = ctk.CTkEntry(self.scroll, textvariable=score_b_var, width=60)
        score_b_entry.grid(row=r, column=4, sticky="w", padx=4, pady=2)

        weighted_a_label = ctk.CTkLabel(self.scroll, text=self._fmt(c.weighted_a()))
        weighted_a_label.grid(row=r, column=5, sticky="w", padx=4, pady=2)
        weighted_b_label = ctk.CTkLabel(self.scroll, text=self._fmt(c.weighted_b()))
        weighted_b_label.grid(row=r, column=6, sticky="w", padx=4, pady=2)

        notes_btn = ctk.CTkButton(self.scroll, text="Notes", width=60,
                                   command=lambda: self._open_notes(c))
        notes_btn.grid(row=r, column=7, padx=4, pady=2)

        del_btn = ctk.CTkButton(self.scroll, text="X", width=32, fg_color=COLOR_WARN,
                                 hover_color="#8a3634",
                                 command=lambda cid=c.id: self._delete_criterion(cid))
        del_btn.grid(row=r, column=8, padx=4, pady=2)

        def commit(*_):
            self.app.push_undo()
            c.name = name_var.get() or c.name
            c.weight = self._parse_float(weight_var.get(), c.weight, 0, 100)
            c.score_a = self._parse_float(score_a_var.get(), c.score_a, 1, 10)
            c.score_b = self._parse_float(score_b_var.get(), c.score_b, 1, 10)
            weight_var.set(self._fmt(c.weight))
            score_a_var.set(self._fmt(c.score_a))
            score_b_var.set(self._fmt(c.score_b))
            weighted_a_label.configure(text=self._fmt(c.weighted_a()))
            weighted_b_label.configure(text=self._fmt(c.weighted_b()))
            self._update_weight_sum_label()
            self.app.on_model_changed(rebuild_table=False)

        for widget in (name_entry, weight_entry, score_a_entry, score_b_entry):
            widget.bind("<FocusOut>", commit)
            widget.bind("<Return>", commit)

        self._row_widgets.append({
            "widgets": [idx_label, name_entry, weight_entry, score_a_entry, score_b_entry,
                        weighted_a_label, weighted_b_label, notes_btn, del_btn],
            "criterion": c,
        })

    # -- utilities ----------------------------------------------------------

    @staticmethod
    def _fmt(v: float) -> str:
        return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)

    @staticmethod
    def _parse_float(text: str, fallback: float, lo: float, hi: float) -> float:
        try:
            v = float(text)
        except (TypeError, ValueError):
            messagebox.showwarning("Invalid input", f"'{text}' is not a number. Reverting.")
            return fallback
        return max(lo, min(hi, v))

    def _open_notes(self, c: Criterion):
        NotesDialog(self, c, on_save=lambda: self.app.on_model_changed(rebuild_table=False))

    def _update_weight_sum_label(self):
        total = MCDAEngine.weight_sum(self.app.scenario)
        valid = MCDAEngine.weights_valid(self.app.scenario)
        color = COLOR_OK if valid else COLOR_WARN
        suffix = "" if valid else "  \u26A0 Must total 100% before final calculation"
        self.weight_sum_label.configure(
            text=f"Total weight: {total:.2f}%{suffix}", text_color=color)


# =========================================================================
# Tab 2: CRITICAL THRESHOLDS (feasibility gate. Big words for Elmo)
# =========================================================================

class ThresholdsTab(ctk.CTkFrame):
    """Deal-breaker editor: each threshold gates an option's feasibility
    independent of its weighted MCDA score."""

    def __init__(self, master, app: "MCDAApp"):
        super().__init__(master, fg_color="transparent")
        self.app = app

        intro = ctk.CTkLabel(
            self,
            text=("Define deal-breakers below (e.g. 'Funding secured', 'Visa approved'). "
                  "If ANY required threshold fails for an option, that option is marked "
                  "infeasible regardless of its weighted score. Holds one accountable to objective choice."),
            wraplength=760, justify="left")
        intro.pack(anchor="w", padx=14, pady=(12, 6))

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(top, text="+ Add Threshold", command=self._add_threshold,
                      width=160).pack(side="left")

        header = ctk.CTkFrame(self, fg_color="gray20")
        header.pack(fill="x", padx=10)
        cols = [("Threshold", 3), ("Option A", 1), ("Option B", 1), ("Notes", 3), ("", 1)]
        for i, (text, w) in enumerate(cols):
            header.grid_columnconfigure(i, weight=w)
            ctk.CTkLabel(header, text=text, font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=i, sticky="w", padx=6, pady=6)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=6)

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13, weight="bold"),
                                          wraplength=760, justify="left")
        self.status_label.pack(anchor="w", padx=14, pady=(4, 12))

        self.refresh()

    def _add_threshold(self):
        self.app.push_undo()
        self.app.scenario.thresholds.append(Threshold(name="New Threshold"))
        self.app.on_model_changed(rebuild_table=False)
        self.refresh()

    def _delete_threshold(self, tid: str):
        t = next((t for t in self.app.scenario.thresholds if t.id == tid), None)
        if t and messagebox.askyesno("Delete threshold", f"Delete '{t.name}'?"):
            self.app.push_undo()
            self.app.scenario.thresholds = [
                x for x in self.app.scenario.thresholds if x.id != tid]
            self.app.on_model_changed(rebuild_table=False)
            self.refresh()

    def refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        for i in range(5):
            self.scroll.grid_columnconfigure(i, weight=[3, 1, 1, 3, 1][i])

        for r, t in enumerate(self.app.scenario.thresholds):
            self._build_row(r, t)

        self._update_status()

    def _build_row(self, r: int, t: Threshold):
        row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row.grid(row=r, column=0, columnspan=5, sticky="ew", pady=2)
        for i, w in enumerate([3, 1, 1, 3, 1]):
            row.grid_columnconfigure(i, weight=w)

        name_var = tk.StringVar(value=t.name)
        name_entry = ctk.CTkEntry(row, textvariable=name_var)
        name_entry.grid(row=0, column=0, sticky="ew", padx=4)

        a_var = tk.StringVar(value="Yes" if t.pass_a else "No")
        a_menu = ctk.CTkOptionMenu(row, values=["Yes", "No"], variable=a_var, width=80,
                                    command=lambda v: commit())
        a_menu.grid(row=0, column=1, padx=4)

        b_var = tk.StringVar(value="Yes" if t.pass_b else "No")
        b_menu = ctk.CTkOptionMenu(row, values=["Yes", "No"], variable=b_var, width=80,
                                    command=lambda v: commit())
        b_menu.grid(row=0, column=2, padx=4)

        notes_var = tk.StringVar(value=t.notes)
        notes_entry = ctk.CTkEntry(row, textvariable=notes_var)
        notes_entry.grid(row=0, column=3, sticky="ew", padx=4)

        del_btn = ctk.CTkButton(row, text="X", width=32, fg_color=COLOR_WARN,
                                 hover_color="#8a3634",
                                 command=lambda tid=t.id: self._delete_threshold(tid))
        del_btn.grid(row=0, column=4, padx=4)

        def commit(*_):
            self.app.push_undo()
            t.name = name_var.get() or t.name
            t.pass_a = (a_var.get() == "Yes")
            t.pass_b = (b_var.get() == "Yes")
            t.notes = notes_var.get()
            self.app.on_model_changed(rebuild_table=False)
            self._update_status()

        name_entry.bind("<FocusOut>", commit)
        name_entry.bind("<Return>", commit)
        notes_entry.bind("<FocusOut>", commit)
        notes_entry.bind("<Return>", commit)

    def _update_status(self):
        feas = MCDAEngine.check_feasibility(self.app.scenario)
        lines = []
        if feas.option_a_feasible and feas.option_b_feasible:
            lines.append("\u2713 Both options currently pass all critical thresholds.")
            color = COLOR_OK
        else:
            color = COLOR_WARN
            if not feas.option_a_feasible:
                lines.append(f"\u2717 Option A is INFEASIBLE - failed: {', '.join(feas.failed_a)}")
            if not feas.option_b_feasible:
                lines.append(f"\u2717 Option B is INFEASIBLE - failed: {', '.join(feas.failed_b)}")
        self.status_label.configure(text="\n".join(lines), text_color=color)


# =========================================================================
# Tab 3: RESULTS & CHARTS
# =========================================================================

class ResultsTab(ctk.CTkFrame):
    """Summary numbers + the four required charts (totals bar, radar,
    contribution bar, weight pie)."""

    def __init__(self, master, app: "MCDAApp"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._canvases: List[FigureCanvasTkAgg] = []

        self.summary_frame = ctk.CTkFrame(self)
        self.summary_frame.pack(fill="x", padx=10, pady=10)

        self.warn_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13, weight="bold"),
                                        wraplength=900, justify="left")
        self.warn_label.pack(anchor="w", padx=14)

        ctk.CTkButton(self, text="\u21bb Refresh Charts", command=self.refresh,
                      width=160).pack(anchor="e", padx=14, pady=(4, 0))

        self.charts_tabview = ctk.CTkTabview(self)
        self.charts_tabview.pack(fill="both", expand=True, padx=10, pady=10)
        for name in ["Totals", "Radar Profile", "Contribution", "Weight Distribution"]:
            self.charts_tabview.add(name)

        self.refresh()

    def refresh(self):
        scenario = self.app.scenario
        result = MCDAEngine.compute(scenario)
        self._render_summary(result)
        self._render_charts(scenario, result)

    def _render_summary(self, result: MCDAResult):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        s = self.app.scenario

        valid = MCDAEngine.weights_valid(s)
        if not valid:
            self.warn_label.configure(
                text=f"\u26A0 Weights currently total {MCDAEngine.weight_sum(s):.2f}%. "
                     "Final calculation is blocked until weights sum to 100% "
                     "(use 'Normalize Weights to 100%' on the Criteria Matrix tab).",
                text_color=COLOR_WARN)
        elif result.feasibility.any_gate_active:
            msgs = []
            if result.feasibility.failed_a:
                msgs.append(f"Option A blocked by: {', '.join(result.feasibility.failed_a)}")
            if result.feasibility.failed_b:
                msgs.append(f"Option B blocked by: {', '.join(result.feasibility.failed_b)}")
            self.warn_label.configure(text="\u26A0 " + "  |  ".join(msgs), text_color=COLOR_WARN)
        else:
            self.warn_label.configure(text="")

        grid = ctk.CTkFrame(self.summary_frame, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=10)
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        def stat(col, title, value, color=None):
            box = ctk.CTkFrame(grid, corner_radius=10)
            box.grid(row=0, column=col, sticky="ew", padx=6)
            ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=12)).pack(pady=(10, 2))
            ctk.CTkLabel(box, text=value, font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=color).pack(pady=(0, 10))

        stat(0, s.option_a_label, f"{result.total_a:.2f} / 10", COLOR_A)
        stat(1, s.option_b_label, f"{result.total_b:.2f} / 10", COLOR_B)
        stat(2, "Difference", f"{result.difference:+.2f}  ({result.pct_difference:.1f}%)")

        if not valid:
            rec_text, rec_color = "Blocked (fix weights)", COLOR_WARN
        elif result.recommended is None:
            rec_text, rec_color = "No feasible / tied option", COLOR_WARN
        else:
            label = s.option_a_label if result.recommended == "A" else s.option_b_label
            rec_text, rec_color = label, (COLOR_A if result.recommended == "A" else COLOR_B)
        stat(3, f"Recommended  |  {result.confidence_label}", rec_text, rec_color)

    def _render_charts(self, scenario: Scenario, result: MCDAResult):
        for canvas in self._canvases:
            canvas.get_tk_widget().destroy()
        self._canvases = []

        specs = [
            ("Totals", plotting.totals_bar_chart(scenario, result)),
            ("Radar Profile", plotting.radar_chart(scenario)),
            ("Contribution", plotting.contribution_bar_chart(scenario)),
            ("Weight Distribution", plotting.weight_pie_chart(scenario)),
        ]
        for tab_name, fig in specs:
            container = self.charts_tabview.tab(tab_name)
            canvas = FigureCanvasTkAgg(fig, master=container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)
            self._canvases.append(canvas)

    def current_figures(self):
        """Return fresh Figure objects (for PDF export) without touching the
        embedded canvases."""
        scenario = self.app.scenario
        result = MCDAEngine.compute(scenario)
        return [
            plotting.totals_bar_chart(scenario, result),
            plotting.radar_chart(scenario),
            plotting.contribution_bar_chart(scenario),
            plotting.weight_pie_chart(scenario),
        ]


# =========================================================================
# Tab 4: SENSITIVITY ANALYSIS
# =========================================================================

class SensitivityTab(ctk.CTkFrame):
    """Live weight sliders (preview only - do not mutate the scenario until
    'Apply' is pressed), plus breakeven / influence-ranking analysis."""

    def __init__(self, master, app: "MCDAApp"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._sliders = []
        self._canvas: Optional[FigureCanvasTkAgg] = None

        intro = ctk.CTkLabel(
            self,
            text=("Drag a slider to preview the effect of changing that criterion's weight "
                  "(other weights rescale proportionally to keep the total at 100%). "
                  "Nothing is saved until you click 'Apply this weight to scenario'."),
            wraplength=900, justify="left")
        intro.pack(anchor="w", padx=14, pady=(10, 6))

        # TODO: add a "reset all sliders" button, clicker to manually enter numbers instead of slider dependence
        self.preview_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.preview_label.pack(anchor="w", padx=14, pady=(0, 6))

        self.scroll = ctk.CTkScrollableFrame(self, height=260)
        self.scroll.pack(fill="x", padx=10, pady=6)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkButton(bottom, text="Analyze Breakeven & Influence Ranking",
                      command=self.run_influence_analysis).pack(anchor="w", pady=(0, 6))

        self.influence_text = ctk.CTkTextbox(bottom, height=140)
        self.influence_text.pack(fill="x", pady=(0, 6))

        self.chart_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        self.chart_frame.pack(fill="both", expand=True)

        self.refresh()

    def refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._sliders = []
        scenario = self.app.scenario

        for c in scenario.criteria:
            row = ctk.CTkFrame(self.scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=c.name, width=220, anchor="w").pack(side="left", padx=4)
            val_label = ctk.CTkLabel(row, text=f"{c.weight:.1f}%", width=60)
            val_label.pack(side="right", padx=4)
            slider = ctk.CTkSlider(row, from_=0, to=100,
                                    command=lambda v, cid=c.id, lbl=val_label:
                                    self._on_slide(cid, v, lbl))
            slider.set(c.weight)
            slider.pack(side="left", fill="x", expand=True, padx=8)
            apply_btn = ctk.CTkButton(row, text="Apply", width=60,
                                       command=lambda cid=c.id, s=slider: self._apply(cid, s.get()))
            apply_btn.pack(side="right", padx=4)
            self._sliders.append((c.id, slider, val_label))

        self._update_preview_label()

    def _on_slide(self, criterion_id: str, new_weight: float, val_label: ctk.CTkLabel):
        val_label.configure(text=f"{new_weight:.1f}%")
        ta, tb = MCDAEngine.recompute_with_weight_override(
            self.app.scenario, criterion_id, new_weight)
        s = self.app.scenario
        leader = s.option_a_label if ta >= tb else s.option_b_label
        self.preview_label.configure(
            text=f"Preview -> {s.option_a_label}: {ta:.2f}   |   "
                 f"{s.option_b_label}: {tb:.2f}   |   Leading: {leader}")

    def _apply(self, criterion_id: str, new_weight: float):
        self.app.push_undo()
        scenario = self.app.scenario
        target = next((c for c in scenario.criteria if c.id == criterion_id), None)
        if target is None:
            return
        others = [c for c in scenario.criteria if c.id != criterion_id]
        others_sum = sum(c.weight for c in others)
        remaining = 100.0 - new_weight
        if others_sum > 0:
            factor = remaining / others_sum
            for c in others:
                c.weight = round(c.weight * factor, 2)
        target.weight = round(new_weight, 2)
        self.app.on_model_changed(rebuild_table=True)

    def _update_preview_label(self):
        result = MCDAEngine.compute(self.app.scenario)
        s = self.app.scenario
        self.preview_label.configure(
            text=f"Current -> {s.option_a_label}: {result.total_a:.2f}   |   "
                 f"{s.option_b_label}: {result.total_b:.2f}   |   "
                 f"Recommended: {result.recommended or 'tie'}")

    def run_influence_analysis(self):
        scenario = self.app.scenario
        rankings = MCDAEngine.influence_ranking(scenario)

        self.influence_text.delete("1.0", "end")
        self.influence_text.insert("end", "Criteria ranked by decision influence "
                                            "(smallest weight-change to flip = most influential):\n\n")
        for i, (name, dist) in enumerate(rankings, start=1):
            if dist is None:
                self.influence_text.insert("end", f"{i}. {name}: never flips the decision (0-100% range)\n")
            else:
                self.influence_text.insert("end", f"{i}. {name}: flips decision after a "
                                                     f"{dist:.1f} weight-point change\n")

        for w in self.chart_frame.winfo_children():
            w.destroy()
        fig = plotting.tornado_chart(rankings)
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvas = canvas


# =========================================================================
# Tab 5: SCENARIO MANAGEMENT
# =========================================================================

class ScenariosTab(ctk.CTkFrame):
    """Save / load / delete named scenarios (Optimistic, Expected, Worst
    Case, or any custom name)."""

    def __init__(self, master, app: "MCDAApp"):
        super().__init__(master, fg_color="transparent")
        self.app = app

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 6))
        self.name_entry = ctk.CTkEntry(top, placeholder_text="New scenario name...", width=240)
        self.name_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(top, text="Save Current As New Scenario",
                      command=self._save_as_new).pack(side="left", padx=4)
        ctk.CTkButton(top, text="Duplicate Active Scenario",
                      command=self._duplicate).pack(side="left", padx=4)

        io_frame = ctk.CTkFrame(self, fg_color="transparent")
        io_frame.pack(fill="x", padx=14, pady=4)
        ctk.CTkButton(io_frame, text="Save Project (.json)",
                      command=self.app.save_project_as).pack(side="left", padx=4)
        ctk.CTkButton(io_frame, text="Open Project (.json)",
                      command=self.app.open_project).pack(side="left", padx=4)
        ctk.CTkButton(io_frame, text="Export Excel (.xlsx)",
                      command=self.app.export_excel).pack(side="left", padx=4)
        ctk.CTkButton(io_frame, text="Export PDF Report",
                      command=self.app.export_pdf).pack(side="left", padx=4)

        ctk.CTkLabel(self, text="Saved Scenarios", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=14, pady=(14, 4))
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.refresh()

    def _save_as_new(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showinfo("Scenario name required", "Please type a name for this scenario.")
            return
        import copy
        new_scn = copy.deepcopy(self.app.scenario)
        new_scn.name = name
        self.app.project.add_scenario(new_scn)
        self.app.scenario = new_scn
        self.name_entry.delete(0, "end")
        self.app.on_model_changed(rebuild_table=True, switch_scenario=True)
        self.refresh()

    def _duplicate(self):
        import copy
        base = self.app.scenario
        new_scn = copy.deepcopy(base)
        new_scn.name = f"{base.name} (copy)"
        self.app.project.add_scenario(new_scn)
        self.app.scenario = new_scn
        self.app.on_model_changed(rebuild_table=True, switch_scenario=True)
        self.refresh()

    def _load(self, name: str):
        for s in self.app.project.scenarios:
            if s.name == name:
                self.app.scenario = s
                self.app.project.active_scenario_name = name
                self.app.on_model_changed(rebuild_table=True, switch_scenario=True)
                self.refresh()
                return

    def _delete(self, name: str):
        if len(self.app.project.scenarios) <= 1:
            messagebox.showwarning("Cannot delete", "At least one scenario must remain.")
            return
        if messagebox.askyesno("Delete scenario", f"Delete scenario '{name}'?"):
            self.app.project.delete_scenario(name)
            self.app.scenario = self.app.project.get_active()
            self.app.on_model_changed(rebuild_table=True, switch_scenario=True)
            self.refresh()

    def refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        for s in self.app.project.scenarios:
            row = ctk.CTkFrame(self.scroll)
            row.pack(fill="x", pady=4)
            is_active = (s.name == self.app.scenario.name)
            marker = "\u25CF  " if is_active else "    "
            ctk.CTkLabel(row, text=f"{marker}{s.name}",
                         font=ctk.CTkFont(weight="bold" if is_active else "normal")).pack(
                side="left", padx=10, pady=8)
            ctk.CTkButton(row, text="Load", width=70,
                          command=lambda n=s.name: self._load(n)).pack(side="right", padx=6)
            ctk.CTkButton(row, text="Delete", width=70, fg_color=COLOR_WARN,
                          hover_color="#8a3634",
                          command=lambda n=s.name: self._delete(n)).pack(side="right", padx=6)


# =========================================================================
# MAIN APPLICATION WINDOW
# =========================================================================

class MCDAApp(ctk.CTk):
    """Top-level application window: owns the ProjectFile (all scenarios),
    the currently active Scenario, the undo/redo manager, and wires up the
    menu bar + five tabs."""

    def __init__(self):
        super().__init__()
        self.title("Decision Support Tool - Study Abroad vs Reapply (MCDA)")
        self.geometry("1240x820")
        self.minsize(1000, 700)

        self.project = ProjectFile(scenarios=[build_default_scenario()])
        self.scenario: Scenario = self.project.get_active()
        self.undo_manager = UndoManager()
        self.current_path: Optional[str] = None
        self._dirty = False

        self._build_menu()

        self.tabview = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=8, pady=8)
        for name in ["Criteria Matrix", "Critical Thresholds", "Results & Charts",
                     "Sensitivity Analysis", "Scenarios"]:
            self.tabview.add(name)

        self.criteria_tab = CriteriaMatrixTab(self.tabview.tab("Criteria Matrix"), self)
        self.criteria_tab.pack(fill="both", expand=True)

        self.thresholds_tab = ThresholdsTab(self.tabview.tab("Critical Thresholds"), self)
        self.thresholds_tab.pack(fill="both", expand=True)

        self.results_tab = ResultsTab(self.tabview.tab("Results & Charts"), self)
        self.results_tab.pack(fill="both", expand=True)

        self.sensitivity_tab = SensitivityTab(self.tabview.tab("Sensitivity Analysis"), self)
        self.sensitivity_tab.pack(fill="both", expand=True)

        self.scenarios_tab = ScenariosTab(self.tabview.tab("Scenarios"), self)
        self.scenarios_tab.pack(fill="both", expand=True)

        self._try_load_autosave()
        self._schedule_autosave()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # MENU BAR
    # ------------------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Project", command=self.new_project)
        file_menu.add_command(label="Open Project...", command=self.open_project)
        file_menu.add_command(label="Save Project", command=self.save_project)
        file_menu.add_command(label="Save Project As...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export Excel (.xlsx)...", command=self.export_excel)
        file_menu.add_command(label="Export PDF Report...", command=self.export_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        menubar.add_cascade(label="Edit", menu=edit_menu)
        self.bind_all("<Control-z>", lambda e: self.undo())
        self.bind_all("<Control-y>", lambda e: self.redo())

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Dark / Light Mode", command=self._toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        self.configure(menu=menubar)

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        ctk.set_appearance_mode("Light" if current == "Dark" else "Dark")

    # ------------------------------------------------------------------
    # UNDO/REDO
    # ------------------------------------------------------------------

    def push_undo(self):
        self.undo_manager.push(self.scenario)
        self._dirty = True

    def undo(self):
        restored = self.undo_manager.undo(self.scenario)
        if restored is not None:
            self.project.add_scenario(restored) if False else None
            # replace scenario object in-place within project's list
            idx = next((i for i, s in enumerate(self.project.scenarios)
                        if s.name == self.scenario.name), None)
            self.scenario = restored
            if idx is not None:
                self.project.scenarios[idx] = restored
            self.on_model_changed(rebuild_table=True)

    def redo(self):
        restored = self.undo_manager.redo(self.scenario)
        if restored is not None:
            idx = next((i for i, s in enumerate(self.project.scenarios)
                        if s.name == self.scenario.name), None)
            self.scenario = restored
            if idx is not None:
                self.project.scenarios[idx] = restored
            self.on_model_changed(rebuild_table=True)

    # ------------------------------------------------------------------
    # CHANGE PROPAGATION
    # ------------------------------------------------------------------

    def on_model_changed(self, rebuild_table: bool = False, switch_scenario: bool = False):
        """Central refresh hook called after ANY edit. Keeps every tab in
        sync with the (single, shared) active Scenario object."""
        self._dirty = True
        if rebuild_table or switch_scenario:
            self.criteria_tab.refresh()
            self.thresholds_tab.refresh()
            self.sensitivity_tab.refresh()
        else:
            self.criteria_tab._update_weight_sum_label()
            self.thresholds_tab._update_status()

        # Results/Sensitivity summaries are cheap - keep them live too.
        self.results_tab.refresh()
        if not rebuild_table:
            self.sensitivity_tab._update_preview_label()

    def _on_tab_changed(self):
        selected = self.tabview.get()
        if selected == "Results & Charts":
            self.results_tab.refresh()
        elif selected == "Sensitivity Analysis":
            self.sensitivity_tab.refresh()
        elif selected == "Scenarios":
            self.scenarios_tab.refresh()

    # ------------------------------------------------------------------
    # FILE OPERATIONS (new, open, save, export)
    # ------------------------------------------------------------------

    def new_project(self):
        if messagebox.askyesno("New Project", "Discard current project and start fresh?"):
            self.project = ProjectFile(scenarios=[build_default_scenario()])
            self.scenario = self.project.get_active()
            self.current_path = None
            self.undo_manager.clear()
            self.on_model_changed(rebuild_table=True, switch_scenario=True)

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            self.project = ProjectFile.load(path)
            self.scenario = self.project.get_active()
            self.current_path = path
            self.undo_manager.clear()
            self.on_model_changed(rebuild_table=True, switch_scenario=True)
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def save_project(self):
        if self.current_path:
            self.project.save(self.current_path)
            self._dirty = False
            messagebox.showinfo("Saved", f"Project saved to {self.current_path}")
        else:
            self.save_project_as()

    def save_project_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                             filetypes=[("JSON files", "*.json")])
        if not path:
            return
        self.project.save(path)
        self.current_path = path
        self._dirty = False
        messagebox.showinfo("Saved", f"Project saved to {path}")

    def export_excel(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                             filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return
        try:
            result = MCDAEngine.compute(self.scenario)
            export_to_excel(self.scenario, result, path)
            messagebox.showinfo("Exported", f"Excel file saved to {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def export_pdf(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                             filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            result = MCDAEngine.compute(self.scenario)
            tmp_dir = os.path.join(AUTOSAVE_DIR, "tmp_charts")
            os.makedirs(tmp_dir, exist_ok=True)
            img_paths = []
            for i, fig in enumerate(self.results_tab.current_figures()):
                p = os.path.join(tmp_dir, f"chart_{i}.png")
                fig.savefig(p, dpi=140)
                img_paths.append(p)
            export_to_pdf(self.scenario, result, img_paths, path)
            messagebox.showinfo("Exported", f"PDF report saved to {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    # ------------------------------------------------------------------
    # AUTOSAVE (periodic, and on-close)
    # ------------------------------------------------------------------

    def _try_load_autosave(self):
        path = os.path.join(AUTOSAVE_DIR, "autosave_mcda.json")
        if os.path.exists(path):
            if messagebox.askyesno("Restore autosave",
                                    "A previous autosaved session was found. Restore it?"):
                try:
                    self.project = ProjectFile.load(path)
                    self.scenario = self.project.get_active()
                    self.on_model_changed(rebuild_table=True, switch_scenario=True)
                except Exception:
                    pass

    def _schedule_autosave(self):
        if not self.winfo_exists():
            return
        try:
            self.project.autosave(AUTOSAVE_DIR)
        except Exception:
            pass
        try:
            self.after(30_000, self._schedule_autosave)  # every 30 seconds
        except tk.TclError:
            pass

    def _on_close(self):
        try:
            self.project.autosave(AUTOSAVE_DIR)
        except Exception:
            pass
        self.destroy()
