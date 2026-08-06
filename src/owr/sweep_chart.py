"""Matplotlib rendering of a sweep frame. Implements docs/archive/plans/PLAN_SCENARIO_SWEEP.md
section 4.4.

CLI layer, not engine core: Matplotlib is an optional dependency (the ``viz``
extra) and is imported inside ``_matplotlib``, never at module scope, so
``owr.sweep_cli`` can import this module unconditionally and cost nothing when
Matplotlib is absent. A missing dependency raises ``ChartDependencyError``
(subclass of ``ValueError``) at call time, with an install hint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from matplotlib.figure import Figure

CHART_FIGSIZE_INCHES: tuple[float, float] = (11.0, 7.5)
CHART_DPI: int = 150
CHART_TITLE_FONTSIZE: int = 17
CHART_SUBTITLE_FONTSIZE: int = 12
CHART_LABEL_FONTSIZE: int = 13
CHART_TICK_FONTSIZE: int = 12
CHART_ANNOTATION_FONTSIZE: int = 11
CHART_FOOTER_FONTSIZE: int = 8
CHART_LINE_WIDTH: float = 2.4
CHART_MARKER_SIZE: float = 8.0

_REQUIRED_COLUMNS = ("storage_mwh", "severity_reduction", "energy_discharged_mwh")


class ChartDependencyError(ValueError):
    """Matplotlib is absent. Subclasses ``ValueError`` so the CLI's own handler
    turns it into exit 2 with a message on stderr."""


def _matplotlib():
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from matplotlib.ticker import StrMethodFormatter
    except ImportError as exc:
        raise ChartDependencyError(
            "chart output needs matplotlib, an optional dependency. Install it "
            "with: uv sync --group dev --extra viz"
        ) from exc
    return Figure, FigureCanvasAgg, StrMethodFormatter


def render_sweep_chart(
    frame: pd.DataFrame,
    *,
    path: str,
    title: str,
    subtitle: str,
    footer: str,
) -> None:
    """Render the two-panel sweep chart to ``path``. The file extension picks
    PNG or SVG. Validates ``frame`` before importing Matplotlib (rule 1), so the
    two validation tests run without Matplotlib installed.
    """
    if frame.empty:
        raise ValueError("frame must not be empty")
    missing = [c for c in _REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing required column(s): {', '.join(missing)}")

    Figure, FigureCanvasAgg, StrMethodFormatter = _matplotlib()

    fig: Figure = Figure(figsize=CHART_FIGSIZE_INCHES, dpi=CHART_DPI)
    FigureCanvasAgg(fig)
    ax_top, ax_bottom = fig.subplots(2, 1, sharex=True)

    storage = frame["storage_mwh"]
    severity_pct = frame["severity_reduction"] * 100
    discharged = frame["energy_discharged_mwh"]

    ax_top.plot(
        storage, severity_pct, marker="o", linewidth=CHART_LINE_WIDTH,
        markersize=CHART_MARKER_SIZE,
    )
    ax_top.set_ylim(bottom=0)
    ax_top.grid(True, alpha=0.3)
    ax_top.set_ylabel("severity reduction (%)", fontsize=CHART_LABEL_FONTSIZE)
    ax_top.yaxis.set_major_formatter(StrMethodFormatter("{x:,.1f}"))
    ax_top.tick_params(labelsize=CHART_TICK_FONTSIZE)
    for x, y in zip(storage, severity_pct, strict=True):
        ax_top.annotate(
            f"{y:.2f}%", (x, y), textcoords="offset points", xytext=(0, 8),
            ha="center", fontsize=CHART_ANNOTATION_FONTSIZE,
        )

    ax_bottom.plot(
        storage, discharged, marker="o", linewidth=CHART_LINE_WIDTH,
        markersize=CHART_MARKER_SIZE,
    )
    ax_bottom.set_ylim(bottom=0)
    ax_bottom.grid(True, alpha=0.3)
    ax_bottom.set_xlabel("storage energy capacity (MWh)", fontsize=CHART_LABEL_FONTSIZE)
    ax_bottom.set_ylabel("energy discharged (MWh)", fontsize=CHART_LABEL_FONTSIZE)
    ax_bottom.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax_bottom.tick_params(labelsize=CHART_TICK_FONTSIZE)

    # Title near the top edge, subtitle a clear line below it: the plan's original
    # y=0.945 for the subtitle collided with a two-line wrapped title at this
    # figure size (verified visually, plan section 5 phase 3 step 3). y=0.985 /
    # 0.905 leaves a gap that reads clean at arm's length in both example charts.
    fig.suptitle(title, fontsize=CHART_TITLE_FONTSIZE, y=0.985)
    fig.text(0.5, 0.905, subtitle, ha="center", fontsize=CHART_SUBTITLE_FONTSIZE)
    fig.text(0.01, 0.01, footer, ha="left", va="bottom", fontsize=CHART_FOOTER_FONTSIZE)
    fig.tight_layout(rect=(0, 0.04, 1, 0.87))

    fig.savefig(path)
