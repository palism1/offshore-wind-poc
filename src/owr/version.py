"""Shared provenance helper: the short git sha stamped on every run.

Moved out of ``owr.api.app`` so the simulator CLI (``owr.cli``) can tag its output
with the same code_version the API uses, without importing anything from the API
layer (which would pull fastapi onto the engine's runtime path).
"""

from __future__ import annotations

import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def code_version() -> str:
    """Short git sha of the engine, tagged onto every run for provenance."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return sha or "unknown"
    except Exception:
        return "unknown"
