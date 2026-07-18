"""Phase 2 — ETL pipeline (extract / transform / validate).

Maps to docs/PLAN.md "Phase 2 — ETL pipeline". This package is the boundary
between external data providers (ISO-NE / EIA via the ``gridstatus`` library) and
the ``raw.*`` landing tables from db/migrations/001_init.sql.

Design rules encoded here, mirroring the rest of the repo:

* **Skeleton is testable offline.** The only code that touches the network or a
  credentialed provider lives behind a small ``Source`` protocol and imports
  ``gridstatus`` lazily, so the transform-to-rows logic, the idempotent upsert
  keying and the provenance stamping are all unit-tested with fixtures — no
  network, no credentials, no ``gridstatus``/``pandas`` install required.
* **Provenance is a product feature.** Every row written to ``raw.*`` carries
  (source, retrieved_at, source_query, dataset_version); see ``provenance.py``.
* **Idempotent upserts keyed on (source, ts[, zone]).** See ``extract.py`` —
  re-running an extract over the same window overwrites, never duplicates.

Only the ``extract`` step is implemented in this phase. ``transform`` and
``validate`` are scaffolded in ``cli.py`` so they slot in without reshaping the
CLI (docs/PLAN.md Phase 2 step 3: ``etl extract | transform | validate``).
"""

from owr.etl.provenance import Provenance

__all__ = ["Provenance"]
