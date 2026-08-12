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
- [Event-relative wind routing and recharge — Mikko](docs/architecture/PLAN_EVENT_RELATIVE_RECHARGE.md) [Software] — Owner: Mikko — 2026-08-11, 829 passed / 4 skipped, ruff clean. New `OperatingSchedule`/`DaySchedule`/`DispatchWindow` (`models.py`, `schedule.py`) classify every hour as non-event, pre-charge, or active (off-peak/ramp-up/peak/ramp-down/) and drive `simulator`, `recharge`/`initial_soc`, `dispatch` and `metrics` from one shared classification; the three disagreeing surplus-wind rules are deleted. `default_peak_window_wrap` flips to `stop_at_midnight`; new `default_ramp_hours` (`[TWEAK]`, 1). **Resolved** (`docs/architecture/PLAN_BUDGET_FULL_TANK_FIX.md`): the follow-on found during implementation — `recharge.charge_forward`'s SoC-clamped forecast fed into `budget.daily_budget`'s recharge term, which put the state of charge into both terms of the minimum and floored the budget at zero for every remaining day at a full start — is fixed. The recharge term is a horizon **opportunity**, not the charge a tank could accept: new `recharge.recharge_opportunity_mwh` sums `charge_request_mw` over the remaining horizon with no starting SoC and no `StorageAsset`, so no state of charge can enter it. `simulator.py`'s call site now feeds that function into `daily_budget`; `budget.py`'s formula is unchanged. `sweep` now reports a real, rising severity-reduction curve at its fully-charged default start; see `tests/test_simulator.py::test_total_discharge_does_not_fall_as_starting_soc_rises` and `tests/test_sweep.py::test_sweep_severity_reduction_is_positive_at_the_full_start` for the pinned behavior. `recharge_cycle_basis` (D15's day-set mismatch between the two terms) stays open, at a raised priority: the mismatch was invisible before this fix, because a full-start multi-event span produced all-zero budgets everywhere; it is visible now, in shipped budget values. Follow-on: hour `state` / day `mode` are CLI-only (Section 16 of the plan); an API/Postgres consumer needs migration 004 on `app.run_result_hourly`/`app.run_result_daily` to see them.
- Delete `Config.energy_budget_fraction` [Software] — Owner: Mikko — 2026-08-11, 832 passed / 4 skipped, ruff clean. The "80% energy budget rule" is gone from the engine: `next_need` in `simulator.simulate` now passes the full `usable_energy` at day close, not 80% of it, so the protected reserve floor is the only remaining limit on a day's discharge. No simulation dynamics move — `budget.daily_budget` never read the field, so severity reduction, budgets, discharge, charge and equivalent full cycles are unchanged (confirmed against the `real_winter_stress_2026.csv` demo run: 0.8% severity reduction, 63,420 MWh discharged, 73,861 MWh charged, all matching DEMO.md). The one moved figure is `DailyResult.recharge_sufficiency_ratio`: a day now needs 1.25 times the old recharge to report 1.0. The `--energy-budget-fraction` CLI flag and the `energy budget` config-block line are removed; a saved command that still passes the flag now exits 2, an intended break.
