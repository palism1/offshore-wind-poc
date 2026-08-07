# Job Board

synced 2026-08-06T22:00:00.000Z

## In Progress

- [Update project documentation to current direction — Mitchell](https://discord.com/channels/1527018571912446132/1527871831623729313) [Docs] — Owner: _unassigned_
- [Import price analysis — Alexander](https://discord.com/channels/1527018571912446132/1527871615864541184) [Data] — Owner: _unassigned_
- [Wind forecast accuracy vs real-time observations — Alexander](https://discord.com/channels/1527018571912446132/1527871527528431697) [Modeling] — Owner: _unassigned_
- [Winter and summer load profile analysis — Alexander](https://discord.com/channels/1527018571912446132/1527871300888953012) [Data] — Owner: _unassigned_

## Open

- [Decide usage rules for the 10% reserve and 20% floor — Unclaimed](https://discord.com/channels/1527018571912446132/1527873559421128885) [Planning] — Owner: _unassigned_
- [Decide storage naming for external comms — Mitchell](https://discord.com/channels/1527018571912446132/1527873329137057852) [Planning, Docs] — Owner: _unassigned_
- [Decide the canonical wind dataset — Team](https://discord.com/channels/1527018571912446132/1527872272860446791) [Planning, Modeling] — Owner: _unassigned_

## Blocked

- [Build ETL extract, raw ISO-NE load ingestion — Mikko](https://discord.com/channels/1527018571912446132/1527870917152211024) [Software] — Owner: _unassigned_ — `src/owr/etl/extract.py` and its tests ship, but the live ISO-NE pull stays unverified: ISO-NE Web Services credentials are still not provisioned, so the extract skeleton runs against fixtures only.

## Done

- [Merge the reserve-split branch to main - Mikko](https://discord.com/channels/1527018571912446132/1527869913895669934) [Software] — Owner: _unassigned_
- [Adopt pandas/numpy at the four DataFrame boundaries — Mikko](docs/archive/plans/PLAN_PANDAS_ADOPTION.md) [Software] — Owner: Mikko — 2026-08-05, 360 passed / 3 skipped, ruff clean
- [Implement metrics.py toward Architecture Component 7 — Mikko](docs/archive/plans/PLAN_METRICS_COMPONENT7.md) [Software] — Owner: Mikko — 2026-08-05, 459 passed / 3 skipped, ruff clean
- [Add the EIA-930 oil and gas hourly generation extractor — Mikko](docs/archive/plans/PLAN_EIA_OIL_GAS.md) [Software] — Owner: Mikko — 2026-08-05, 505 passed / 4 skipped, ruff clean
- [Build the scenario sweep chart (`sweep` CLI) — Mikko](docs/archive/plans/PLAN_SCENARIO_SWEEP.md) [Software] — Owner: Mikko — 2026-08-05, 552 passed / 4 skipped with the `viz` extra (548 passed / 8 skipped without it), ruff clean
- [Sync the code to the 2026-08-05 Architecture export — Mikko](docs/archive/plans/PLAN_ARCH_0805_SYNC.md) [Software] — Owner: Mikko — 2026-08-05, 572 passed / 4 skipped, ruff clean
- [Build ETL transform, daily aggregation and denominators — Mikko](https://discord.com/channels/1527018571912446132/1527871203434299665) [Validation, Software] — Owner: kKomi — 2026-08-05, `src/owr/etl/transform.py` and `tests/test_etl_transform.py` both ship
- [Fix review findings F1 to F8 (efficiency semantics, discharge floor, net-load accounting, reserve validation, charging rule, annotation wording) — Mikko](docs/archive/plans/PLAN_REVIEW_FIXES.md) [Software] — Owner: Mikko — 2026-08-06, 622 passed / 4 skipped, ruff clean
- Week 4B spec sync, all phases (SWE/CMDR metrics, robustness scoring, hour-ending 1-24, wind multiplier, pooled ETL percentile, integer percentile comparison, auto-increment ids, efficiency default 0.7225, daily_budget two-term minimum) [Software] — Owner: Mikko — branch `week4b-spec-sync`, 738 passed / 4 skipped, ruff clean. DEMO.md re-rehearsed against real output through Phase 9.
