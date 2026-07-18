"""Provenance stamping for ``raw.*`` rows.

"Provenance is a product feature" (docs/HANDOFF.md key design decision #4, and the
db/migrations/001_init.sql header): every raw row must be traceable to the exact
input that produced it. The schema encodes this as four columns on every table:

    source           who/what produced the row (e.g. 'gridstatus.isone.load')
    retrieved_at     when we pulled it (tz-aware UTC)
    source_query     the exact query issued, human-readable and reproducible
    dataset_version  the provider/library version the pull was made against

A single ``Provenance`` instance is stamped once per extract batch and copied onto
every row in that batch, so all rows from one pull share one audit record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Provenance:
    """Audit record copied onto every row of a single extract batch.

    source
        Stable identifier for the producer, e.g. ``'gridstatus.isone.load'``.
        Doubles as the ``source`` component of the idempotency key, so re-running
        the same logical extract overwrites rather than duplicates.
    source_query
        The exact, reproducible query issued to the provider, e.g.
        ``"gridstatus.ISONE().get_load(start=2026-01-01, end=2026-01-02)"``.
    dataset_version
        The provider/library version the pull was made against, e.g.
        ``'gridstatus==0.30.1'``. Never a literal buried in code — it is captured
        from the live library at pull time (see extract.gridstatus_version).
    retrieved_at
        tz-aware UTC timestamp of the pull. Defaults, via :meth:`stamp`, to "now".
    """

    source: str
    source_query: str
    dataset_version: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.source_query:
            raise ValueError("source_query is required")
        if not self.dataset_version:
            raise ValueError("dataset_version is required")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware (UTC)")

    @classmethod
    def stamp(
        cls,
        source: str,
        source_query: str,
        dataset_version: str,
        *,
        retrieved_at: datetime | None = None,
    ) -> Provenance:
        """Create a Provenance for a batch, defaulting ``retrieved_at`` to now (UTC)."""
        return cls(
            source=source,
            source_query=source_query,
            dataset_version=dataset_version,
            retrieved_at=retrieved_at or datetime.now(UTC),
        )

    def as_columns(self) -> dict[str, object]:
        """The four provenance columns, ready to merge into a row dict."""
        return {
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "source_query": self.source_query,
            "dataset_version": self.dataset_version,
        }
