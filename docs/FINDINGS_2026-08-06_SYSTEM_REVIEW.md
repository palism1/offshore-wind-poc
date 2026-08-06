# System review findings, 2026-08-06

Full-system adversarial review, dependency-ordered from `models.py` up to docs.
All 596 tests pass and ruff is clean, so every finding below comes from targeted
reproduction, not from the suite. Status: awaiting triage. No fixes applied.

## Blocking

### F1. Critical. Depth 1. `src/owr/soc_engine.py:29-35` (`clamp_discharge`), with `src/owr/budget.py:40-46`

Defect: `clamp_discharge` treats tank energy above the floor as deliverable
energy, but `next_soc` removes `discharge / eff` from the tank. The engine
discharges below the protected reserve floor when efficiency is below
`energy_budget_fraction` (0.80).

Failure scenario: `soc=40, min_soc=30, eff=0.8, request 50` returns discharge
10; the next SoC is 27.5, below the floor. The shipped demo command (`DEMO.md`
Act 4, `--efficiency 0.72` on `examples/real_winter_stress_2026.csv`) drives
SoC to 17,971.4 MWh against an 18,000 MWh floor.

Evidence: both repros ran with `uv run python`; the demo run reports
`lowest soc: 17971.38`, `violated: True`. The 80% budget rule masks the bug at
eff >= 0.8, which is why eff=1.0 tests never catch it.

Fix: in `clamp_discharge`, cap deliverable energy at
`(soc - min_soc_mwh) * efficiency`. Audit `daily_budget`, which also feeds tank
basis `usable_energy` in as if it were terminal MWh.

Urgent: the demo runs 2026-08-07 morning and Act 4 exercises this path. The
Act 4 expected numbers in `DEMO.md` come from the defective run and move when
this is fixed.

### F2. Major. Depth 0. `src/owr/config.py:43-51`, `src/owr/soc_engine.py:17-21`, `src/owr/cli.py:201-208`

Defect: the parameter is labeled round-trip efficiency everywhere, but the
state equation applies it on each leg, so the effective round-trip efficiency
is `eff ** 2`.

Failure scenario: an operator passes `--efficiency 0.72` (Dick et al.
round-trip figure, per `DEMO.md`); the model then charges at 0.72 and
discharges at 0.72, an effective round trip of 0.518, which overstates losses
by 28%.

Evidence: PLAUSIBLE by arithmetic. 1 MWh wind stores 0.72 MWh (`charge * eff`);
that tank energy delivers `0.72 * 0.72 = 0.5184` MWh at the terminals.
`storage_physics.round_trip_from_one_way` documents exactly this square
relation. The `config.py` note "understates required charging energy by 17.6%"
(`1/0.85`) matches one-leg application and contradicts the equation two lines
above it.

Fix: decide the semantics once. Either apply `sqrt(eff)` per leg and keep the
round-trip label, or relabel the flag and Config field one-way. Fix this before
F1: the F1 clamp formula depends on which number `eff` is.

### F3. Major. Depth 2. `src/owr/simulator.py:186-199`

Defect: charge drawn from surplus wind is added to `net_load_mw` and therefore
to `reserve_peak_mw`, but surplus wind is by construction the wind above net
load, which the grid never supplies; the baseline peak ignores wind entirely.

Failure scenario: flat load 100 MW, one hour with 500 MW wind, storage with
headroom. Baseline peak 100 MW, reserve peak 500 MW, severity reduction -4.0.
Storage strictly helps, the metric says it made the peak five times worse.
`sweep` inherits this and `metrics.severity_reduction` does not clamp, so a
windy profile produces a sweep chart where bigger storage looks worse.

Evidence: repro ran; output `baseline peak 100.0, reserve peak 500.0, severity
reduction -4.0`.

Fix: pick one accounting. Either net wind out of both baseline and net load,
or exclude surplus-wind charging from `net_load_mw` (record it in `charge`
only). Document the choice in the `hourly_frame` field map.

### F4. Major. Depth 0 origin, depth 3 exposure. `src/owr/models.py:41-47` (`StorageAsset.__post_init__`), `src/owr/api/schemas.py:26-27`

Defect: `StorageAsset` does not validate `soc_floor_frac` or
`strategic_reserve_frac` at all, and the API path never builds a `Config`, so
the only sum check in the codebase (`config.py:155-157`) is bypassed.

Failure scenario: `POST /scenarios` with `soc_floor_frac=0.9,
strategic_reserve_frac=0.9` returns 201; the run returns `status: succeeded`
with `severity_reduction: 0.0` because `min_soc_mwh` (1,800) exceeds
`total_mwh` (1,000) and nothing can ever discharge. A negative fraction is
also accepted and yields a negative floor.

Evidence: both repros ran; the API round trip returned 201/201/200 with silent
zero output.

Fix: validate `0 <= each fraction` and
`soc_floor_frac + strategic_reserve_frac < 1` in
`StorageAsset.__post_init__`, mirroring `Config`. The CLI path already rejects
this via `Config`, so only `models.py` needs the change.

## Nits

### F5. Minor. Depth 2. `src/owr/initial_soc.py:26-31`

Pre-event charging counts the full wind series as chargeable and ignores
lead-day load; in-window charging takes only surplus above net load. The two
paths disagree, so `soc_at_window_start` is optimistic. The docstring states
the rule, so this is a documented inconsistency, not a hidden one. PLAUSIBLE
by inspection. Fix: apply the simulator's surplus rule in `charge_from_wind`.

### F6. Minor. Depth 3. `src/owr/api/app.py:103`

The decision-package annotation states "above its protected floor"
unconditionally. With F1 live, a persisted package can state a falsehood.
Fix: compare `final_soc` with `min_soc_mwh` and word the sentence from the
result.

### F7. Minor. Depth 4. Test gaps tied to F1 and F3

`tests/test_soc_engine.py` exercises `clamp_discharge` only at efficiency 1.0;
`tests/test_simulator.py` builds every asset at `efficiency=1.0`; no test
asserts SoC never crosses the floor, and no test covers a charging hour's
effect on `reserve_peak_mw`. Fix: add a floor-invariant property test at eff
in {0.5, 0.72} and a surplus-wind charging test, written against the spec
after F1 to F3 are decided.

### F8. Minor. Depth 4. `docs/BOARD.md`

The live sections (In Progress, Open, Blocked) carry `synced 2026-07-24` while
the Done list records merges through 2026-08-05; the ETL transform item sits
in In Progress and in Done at once. Fix: resync the board. `README.md`
(596 passed, 4 skipped) and `HANDOFF.md` (600 passed with a live database)
both match measured reality.

## Fix order

1. F2, decide efficiency semantics (`config.py`, `soc_engine.py` docstrings,
   CLI help). Everything downstream depends on what the number means.
2. F4, `StorageAsset` fraction validation in `models.py` (depth 0,
   independent, no downstream effect on F1 to F3).
3. F1, `clamp_discharge` and the `daily_budget` basis in `soc_engine.py` /
   `budget.py`, using the F2 decision.
4. F3, net-load accounting in `simulator.py`, then `sweep.py` and both CLI
   reports inherit the corrected peaks.
5. F5, `initial_soc.py` surplus rule.
6. F6, annotation wording in `api/app.py`.
7. F7 tests with each fix; regenerate the `DEMO.md` Act 4 table last, since
   F1 to F3 all move its numbers.

Before the demo on 2026-08-07, the cheap mitigation is a `DEMO.md` footnote on
Act 4, since fixes F1 to F3 change every rehearsed number and a same-day engine
change risks the demo itself.

## Checked and found sound

- `stress_finder.py`: threshold math, gap splitting by calendar date,
  empty-input paths, `with_peak_hourly_load` immutability. Tests mirror the
  spec.
- `peak_window.py`: wrap conventions, tie-break to earliest start, look-ahead
  adjacency check.
- `dispatch.py`: budget and power-cap guarantees hold (`sum == budget`
  unclipped, per-hour clip exact); the flat-day zero-dispatch edge is the only
  oddity and it is bounded.
- `storage_physics.py`: dimensional check of every formula; pump/turbine
  asymmetry correct.
- `etl/daily.py`: DST handling is correct (UTC-converted midnights, 23/24/25
  expected hours, naive and duplicate timestamps rejected).
- `etl/seasons.py`, `etl/transform.py`: season boundaries, pooled threshold,
  per-winter grouping that cannot merge across Feb/Dec.
- `scenario_input.py`: NaN and infinity rejection, duplicate hours, 24-row
  completeness, date adjacency, derived percentile rule.
- `etl/credentials.py` and `extract.py` call sites: the key is never bound,
  returned, or interpolated; redaction is secondary as documented.
- `api/pg_store.py` against `db/migrations/`: persisted shape, recomputed
  window properties, idempotent `save_run`; no schema drift against
  `schemas.py` found.
- `config.py` validation, `sweep.py` spec validation, `version.py`,
  `api/store.py`.
