"""Tests for src/owr/sweep_chart.py (docs/PLAN_SCENARIO_SWEEP.md section 6.2).

Cases 1 to 3 need matplotlib installed (skipped without the ``viz`` extra).
Cases 4 to 6 need no matplotlib: ``render_sweep_chart`` validates before it
imports (rule 1).
"""

from __future__ import annotations

import pandas as pd
import pytest

from owr.sweep import SWEEP_FRAME_COLUMNS
from owr.sweep_chart import ChartDependencyError, render_sweep_chart


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "storage_mwh": [5000.0, 10000.0, 20000.0],
            "power_mw": [4320.0, 4320.0, 4320.0],
            "duration_hours": [1.16, 2.31, 4.63],
            "severity_reduction": [0.0009, 0.0018, 0.0035],
            "baseline_peak_mw": [15000.0, 15000.0, 15000.0],
            "reserve_peak_mw": [14987.0, 14973.0, 14947.0],
            "energy_discharged_mwh": [3394.0, 6788.0, 13577.0],
            "energy_charged_mwh": [0.0, 0.0, 0.0],
            "final_soc_mwh": [1606.0, 3212.0, 6423.0],
            "equivalent_full_cycles": [0.679, 0.679, 0.679],
        },
        columns=list(SWEEP_FRAME_COLUMNS),
    )


def test_renders_png(tmp_path):
    pytest.importorskip("matplotlib")
    path = tmp_path / "chart.png"
    render_sweep_chart(
        _frame(), path=str(path), title="t", subtitle="s", footer="f"
    )
    assert path.exists()
    assert path.stat().st_size > 1024
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_renders_svg(tmp_path):
    pytest.importorskip("matplotlib")
    path = tmp_path / "chart.svg"
    render_sweep_chart(
        _frame(), path=str(path), title="t", subtitle="s", footer="f"
    )
    text = path.read_text()
    assert "<svg" in text


def test_footer_text_reaches_svg_output(tmp_path):
    pytest.importorskip("matplotlib")
    path = tmp_path / "chart.svg"
    footer = "engine deadbeef, generated 2026-08-05, sizes 5,000 to 20,000 MWh"
    render_sweep_chart(
        _frame(), path=str(path), title="t", subtitle="s", footer=footer
    )
    text = path.read_text()
    assert "deadbeef" in text


def test_rejects_empty_frame():
    empty = pd.DataFrame(columns=list(SWEEP_FRAME_COLUMNS))
    with pytest.raises(ValueError):
        render_sweep_chart(empty, path="unused.png", title="t", subtitle="s", footer="f")


def test_rejects_frame_missing_severity_reduction():
    frame = _frame().drop(columns=["severity_reduction"])
    with pytest.raises(ValueError):
        render_sweep_chart(frame, path="unused.png", title="t", subtitle="s", footer="f")


def test_chart_dependency_error_is_value_error():
    assert issubclass(ChartDependencyError, ValueError)
