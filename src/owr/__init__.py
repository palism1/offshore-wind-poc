"""Offshore Wind Reserve — scenario simulation engine (Phase 3).

Pure-Python, no I/O in the core, so the whole engine runs and is tested without a
database or any external API. Public surface:

    from owr import Config, StorageAsset, DayProfile, simulate
"""

from owr.config import Config
from owr.models import (
    DailyResult,
    DayProfile,
    HourlyResult,
    PeakWindow,
    StorageAsset,
    StressWindow,
    WrapConvention,
)
from owr.simulator import SimulationResult, simulate

__all__ = [
    "Config",
    "StorageAsset",
    "DayProfile",
    "StressWindow",
    "PeakWindow",
    "WrapConvention",
    "HourlyResult",
    "DailyResult",
    "SimulationResult",
    "simulate",
]
