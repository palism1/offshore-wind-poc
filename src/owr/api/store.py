"""Repository interface + in-memory implementation.

The API depends only on the ``Repository`` protocol, so the PostgreSQL-backed store
(Phase 1 schema) can drop in later without touching the routes. The in-memory store
keeps the service runnable and testable with zero external services.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from owr.api.schemas import ScenarioCreate
from owr.simulator import SimulationResult


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ScenarioRecord:
    id: int
    inputs: ScenarioCreate
    created_at: datetime


@dataclass
class RunRecord:
    id: int
    scenario_id: int
    status: str
    code_version: str
    created_at: datetime
    result: SimulationResult | None = None
    stress_windows: list = field(default_factory=list)
    decision_package: dict | None = None


class Repository(Protocol):
    def add_scenario(self, inputs: ScenarioCreate) -> ScenarioRecord: ...
    def get_scenario(self, scenario_id: int) -> ScenarioRecord | None: ...
    def add_run(self, scenario_id: int, code_version: str) -> RunRecord: ...
    def get_run(self, run_id: int) -> RunRecord | None: ...

    def save_run(self, run: RunRecord) -> None:
        """Persist the current state of a run.

        Routes obtain a RunRecord from ``add_run`` and then mutate it in place
        (status, result, stress_windows, decision_package). The in-memory store
        holds the same object so those edits are visible for free; a persistent
        store returns detached rows, so callers must ``save_run`` after mutating
        for the changes to survive into a later request. Idempotent by run id.
        """
        ...


class InMemoryRepository:
    """Non-persistent store for the POC. Thread-safe enough for a single process."""

    def __init__(self) -> None:
        self._scenarios: dict[int, ScenarioRecord] = {}
        self._runs: dict[int, RunRecord] = {}
        self._scenario_seq = 0
        self._run_seq = 0
        self._lock = threading.Lock()

    def add_scenario(self, inputs: ScenarioCreate) -> ScenarioRecord:
        with self._lock:
            self._scenario_seq += 1
            rec = ScenarioRecord(id=self._scenario_seq, inputs=inputs, created_at=_now())
            self._scenarios[rec.id] = rec
            return rec

    def get_scenario(self, scenario_id: int) -> ScenarioRecord | None:
        return self._scenarios.get(scenario_id)

    def add_run(self, scenario_id: int, code_version: str) -> RunRecord:
        with self._lock:
            self._run_seq += 1
            rec = RunRecord(
                id=self._run_seq,
                scenario_id=scenario_id,
                status="pending",
                code_version=code_version,
                created_at=_now(),
            )
            self._runs[rec.id] = rec
            return rec

    def get_run(self, run_id: int) -> RunRecord | None:
        return self._runs.get(run_id)

    def save_run(self, run: RunRecord) -> None:
        # The stored object is already the one the route mutated; re-storing keeps
        # the contract explicit and matches the persistent store's semantics.
        with self._lock:
            self._runs[run.id] = run
