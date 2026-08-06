# PLAN — Review fixes F1 to F8

Date: 2026-08-06. Branch: `worktree-review-fixes`. Base commit: `74baf44`.

Source of the work: `docs/FINDINGS_2026-08-06_SYSTEM_REVIEW.md`. The reviewer
reproduced every finding. This plan does not re-argue the defects. It fixes them
in the finding's own order, one phase per finding, one commit per phase.

New source document folded in: `Metric_Thresholds_v1.1.pdf`, "Metric Thresholds &
Operating Ranges", 2026-08-05, winter only. It sources two constants that
`config.py` still labels team choices, and it confirms the floor rule that F1
breaks. It changes no finding and no fix order.

## 1. Scope

In scope: F1 to F8, the two design decisions below, the tests that prove them,
and the documents whose numbers move.

Out of scope, named so nobody adds them:

- The four metrics the new document defines (CMDR, SWE, FOP, RCM). They need
  per-event, winter-only wiring and oil and gas series. They get their own plan.
- A Pydantic sum check in `api/schemas.py`. The finding scopes F4 to `models.py`,
  and `create_run` already maps `ValueError` to HTTP 422.
- The `recharge_sufficiency_ratio` unit basis. It compares terminal input energy
  against terminal output energy and stays as it is. Its printed values move
  because its input moves.
- Any change to `Config.default_efficiency` (stays 1.0) or to the reserve
  fractions (stay 0.20 and 0.10).

## 2. Design decision D1 — efficiency is round trip, and the engine splits it

**Decision.** `StorageAsset.efficiency`, `Config.default_efficiency`, the
`--efficiency` flag and the API `efficiency` field all keep the round-trip
meaning. The engine applies `sqrt(efficiency)` on each leg. A new property
`StorageAsset.one_way_efficiency` computes the split, and the state equation and
both clamps read that property.

**Why.** Three reasons, in order.

1. The sourced figure stays usable as printed. `DEMO.md` and
   `docs/FINDINGS_STENSEA_PAPER_2026-08-02.md` cite 0.72 from Dick et al. Table 1
   as a full-cycle (round-trip) number. After this change `--efficiency 0.72`
   realizes a 0.72 round trip. Under the one-way relabel an operator must type
   0.8485 to get the published figure, and typing 0.72 silently models 0.5184.
2. No wire contract breaks. The flag name, the API field name, the JSON report
   key, the CSV comment line in `sweep_cli` and the `app.scenario.efficiency`
   column all keep their names and their meaning. Only the internal arithmetic
   changes.
3. The relation is already modeled and tested. `storage_physics.round_trip_from_one_way`
   is the square, `one_way_from_round_trip` is the square root, and
   `docs/FINDINGS_STENSEA_PAPER_2026-08-02.md` section 3 recommends the symmetric
   split as a modeling convention. This decision adopts that convention in the
   engine instead of asking every operator to apply it by hand.

**No behavior change at the default.** `sqrt(1.0) == 1.0`, so every default run
and every test at efficiency 1.0 keeps its numbers.

**Files this decision touches** (exact edits in Phase 1): `src/owr/models.py`,
`src/owr/soc_engine.py`, `src/owr/simulator.py`, `src/owr/initial_soc.py`,
`src/owr/config.py`, `src/owr/cli.py`, `src/owr/sweep_cli.py`,
`src/owr/api/schemas.py`, `tests/test_models.py` (new), `tests/test_soc_engine.py`,
`DEMO.md`, `README.md`, `docs/DATA_SOURCES.md`,
`docs/FINDINGS_STENSEA_PAPER_2026-08-02.md` (one supersession line).

## 3. Design decision D2 — surplus-wind charging leaves `net_load_mw`

**Decision.** `net_load_mw = gross_load - discharge`. Charge from surplus wind is
recorded in the `charge` column only. The baseline peak stays the worst hour of
gross load. Wind is netted out of neither series.

**Why.** Five reasons.

1. The metric compares two worlds that must differ by storage alone. The baseline
   never counts the charging draw, so the reserve side must not count it either.
   The current code adds it on one side only, which is what makes severity
   reduction go negative.
2. Surplus wind is wind above the load the grid must serve in that hour, by the
   construction of `surplus_wind` in `simulator.py`. The grid never supplies it.
   Adding it to grid load counts energy the grid does not deliver.
3. The persisted schema already carries this definition.
   `db/migrations/001_init.sql:129` documents `net_load` as "gross load minus
   discharge". Option D2 makes the engine agree with the column comment. No
   migration is needed.
4. It gives the metric a provable floor. `discharge >= 0`, so
   `reserve_peak_mw <= baseline_peak_mw` always, so severity reduction is never
   negative. The alternative (net wind out of both series) can drive the baseline
   peak to zero or below on a windy profile, and `metrics.severity_reduction`
   raises `ValueError` there.
5. It keeps dispatched energy separable, which the new source document requires.
   CMDR, SWE and FOP all consume `capacity_dispatched(t)` per stressed hour.
   Under D2, `capacity_dispatched(t) == discharge(t) == gross_load - net_load`,
   and `charge` stays a clean separate column. The alternative mixes wind and
   charging into `net_load` and forces a second accounting change later.

**Accepted limitation.** A charging hour consumes transmission and conversion
capacity that this model does not represent. The engine has no transmission model
(`transmission_limit_mw` is unread), so the limitation predates this change.

**Where the field map changes** (exact edits in Phase 4):
`SimulationResult.reserve_peak_mw` comment and the `hourly_frame` docstring table
in `src/owr/simulator.py`, plus the `metrics.net_load` docstring, which keeps its
formula and defines `charge_mw` as grid-supplied charge.

## 4. Phases

Every phase ends with the full suite and the linter green:

```
uv run pytest
uv run ruff check .
```

Every phase ends with one commit on `worktree-review-fixes`. Do not push.

### Phase 1 — F2, efficiency semantics and the new source document (about 90 min)

Goal: one meaning for `efficiency` across the whole system, plus the two config
constants the new document sources.

**`src/owr/models.py`**

1. Add `import math`.
2. Add the property to `StorageAsset`:

```python
@property
def one_way_efficiency(self) -> float:
    """Per-leg efficiency: ``sqrt(efficiency)``."""
```

   The docstring must state: `efficiency` is round trip; the engine charges and
   discharges once per cycle, so each leg carries the square root; the symmetric
   split is the convention recorded in
   `docs/FINDINGS_STENSEA_PAPER_2026-08-02.md` section 3;
   `storage_physics.one_way_from_round_trip` is the same formula, and `models`
   does not import it because `models` is the lowest layer and takes no
   intra-package import.
3. Extend the `efficiency` attribute docstring: round trip at the terminals, and
   the engine applies `one_way_efficiency` on each leg.

**`src/owr/soc_engine.py`**

4. Rename the fourth parameter of `next_soc` to `one_way_efficiency`. The formula
   body does not change. The rename is the guard: a call site that passes a
   round-trip value is now visible at the call. The rename breaks three tests in
   `tests/test_soc_engine.py` that pass `efficiency=` by keyword:
   `test_state_equation_lossless` (lines 13 and 14), `test_state_equation_lossy`
   (lines 19 to 21) and `test_negative_flows_rejected` (line 27). Step 16 updates
   all three. No asserted value changes.
5. Update the module docstring. State the equation in one-way terms, and state
   that callers pass `asset.one_way_efficiency`.
6. In `clamp_charge`, replace `asset.efficiency` with `asset.one_way_efficiency`
   and update the inline comment.

**`src/owr/simulator.py`** (lines 182 and 190) and **`src/owr/initial_soc.py`**
(line 30)

7. Change all three calls to `next_soc(..., one_way_efficiency=asset.one_way_efficiency)`.

**`src/owr/config.py`**

8. Rewrite the `default_efficiency` docstring paragraph. State: round trip; the
   engine splits it symmetrically, so `sqrt(eff)` applies per leg; 1.0 is still
   the default and still an open team question; Dick et al. Table 1 gives 0.72
   full cycle and that number is entered directly, never pre-squared.
9. Rewrite the `default_soc_floor_frac / default_strategic_reserve_frac`
   paragraph. Keep the 2026-07-17 team decision sentence. Add: the **combined**
   0.30 is now sourced by `docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf`,
   Winter Data Anchors table, rows "Protected Reserve 30% of Total Capacity" and
   "Max Available Charge 70% of Total Capacity". State that the source fixes the
   total and not the 20/10 split, and that the split stays a team choice. State
   the document's internal discrepancy: its RCM derivation writes "Protected
   reserve floor = 20% of Total Capacity (cannot discharge below)" while its
   anchor table writes 30%; this repo reads 20% floor plus 10% strategic reserve
   equal to 30% protected.

**`src/owr/cli.py`** (line 205) and **`src/owr/sweep_cli.py`** (line 150)

10. Change both help strings to: `round-trip efficiency, applied as sqrt(eff) on
    each leg (default 1.0) [OPEN: round_trip_efficiency]`. Keep the
    `[OPEN: round_trip_efficiency]` marker for consistency with every other
    flag. No test reads the help string: the assertion at
    `tests/test_cli.py:107` reads the rendered summary table, which
    `cli.py:781-782` prints. Leave those two lines as they are.

**`src/owr/api/schemas.py`** (line 24)

11. Add a comment above the `efficiency` field: round trip at the terminals; the
    engine applies the square root on each leg. Do not change the field, the
    default or the constraints.

**Documents**

12. Copy `/Users/mikkopalis/Downloads/Metric_Thresholds_v1.1.pdf` to
    `docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf` and `git add` it.
13. `docs/DATA_SOURCES.md`: add one row to "Reference sources" for the document,
    and one dated subsection "## Metric thresholds document — 2026-08-05" that
    records, in this order: the two anchor rows this repo relies on; the reading
    (20 + 10 = 30, split unsourced); the internal 20/30 discrepancy; that the
    document's p90 rule corroborates `default_severity_percentile = 0.90`; that
    its 18,413 MWh/hr threshold is an **hourly** basis figure and therefore does
    not close the open daily-threshold question; that its "Maximum available
    capacity = 70% of Total Capacity" matches the denominator already implemented
    in `cli._build_report` as `total_mwh - min_soc_mwh`; and that CMDR, SWE, FOP
    and RCM are not implemented.
14. `docs/FINDINGS_STENSEA_PAPER_2026-08-02.md`: add one line under the title.
    "Superseded in part on 2026-08-06 by `docs/PLAN_REVIEW_FIXES.md` decision D1:
    the engine now splits the round-trip value itself, so `--efficiency 0.72` is
    correct and `sqrt(0.72)` must not be entered." Change nothing else in that
    file; it is a dated record.

**Tests**

15. New file `tests/test_models.py` (models.py has no test module today; this
    creates the mirror the conventions ask for):
    - `test_one_way_efficiency_is_the_square_root_of_round_trip`: at 0.72 and at
      0.5, `asset.one_way_efficiency == pytest.approx(math.sqrt(eff))`.
    - `test_one_way_efficiency_matches_storage_physics_converter`: equals
      `storage_physics.one_way_from_round_trip(eff)`. This is the drift guard for
      the duplicated formula.
    - `test_one_way_efficiency_is_one_at_the_lossless_default`.
16. `tests/test_soc_engine.py`:
    - Update the keyword in `test_state_equation_lossless`,
      `test_state_equation_lossy` and `test_negative_flows_rejected`. The
      asserted values do not change; the numbers those three pass (1.0 and 0.9)
      are read as one-way values.
    - New `test_round_trip_efficiency_is_realized_across_a_full_cycle`: build an
      asset at `total_mwh=1000, power_mw=1000, efficiency=0.72, soc_floor_frac=0.0,
      strategic_reserve_frac=0.0`, so no clamp binds. Start at SoC 0. Charge 100
      MWh at the terminals with `clamp_charge` and `next_soc`; the tank then holds
      `100 * asset.one_way_efficiency`. Take the discharge leg through `next_soc`
      alone: set `delivered = soc * asset.one_way_efficiency`, call
      `next_soc(soc, 0.0, delivered, asset.one_way_efficiency)`, and assert
      `delivered == pytest.approx(72.0)` and the returned SoC equals
      `pytest.approx(0.0)`.
    - **Do not call `clamp_discharge` in this test.** It still returns tank
      energy until Phase 3, so it would deliver 84.853 MWh and drive the SoC
      below zero, and the phase gate would fail at the Phase 1 commit. Phase 3
      step 6 covers the clamp. This test proves the state equation, which is what
      decision D1 changes.

Verify:

```
uv run pytest tests/test_models.py tests/test_soc_engine.py
uv run pytest
uv run ruff check .
```

Commit: `F2: efficiency is round trip and the engine splits it per leg`

### Phase 2 — F4, `StorageAsset` fraction validation (about 30 min)

Goal: the API path can no longer build an asset whose floor exceeds its capacity.

**`src/owr/models.py`**

1. In `StorageAsset.__post_init__`, after the efficiency check, mirror
   `config.py:155-157`:

```python
if self.soc_floor_frac < 0 or self.strategic_reserve_frac < 0:
    raise ValueError("soc_floor_frac and strategic_reserve_frac must be >= 0")
floor = self.soc_floor_frac + self.strategic_reserve_frac
if not 0.0 <= floor < 1.0:
    raise ValueError("soc_floor + strategic_reserve must be in [0, 1)")
```

   Keep the sum message identical to `Config`, so one rule reads the same in
   both places. The negative check is new; `Config` has none, and a negative
   fraction that a positive one offsets passes its sum rule. The CLI path builds
   both objects, so this check closes that gap on the CLI path too. The sum check
   also rejects `NaN`, because every comparison against `NaN` is false.
2. Extend the `soc_floor_frac, strategic_reserve_frac` attribute docstring with
   the rule and with the source citation from Phase 1 step 9 (combined 30%
   sourced, split a team choice).

**Tests** in `tests/test_models.py`:

3. `test_negative_soc_floor_frac_rejected`.
4. `test_negative_strategic_reserve_frac_rejected`.
5. `test_fraction_sum_at_or_above_one_rejected`: 0.9 + 0.9, and 0.5 + 0.5.
6. `test_fraction_sum_just_below_one_accepted`: 0.6 + 0.39.
7. `test_default_fractions_still_build`: guards against an over-strict rule.

**Tests** in `tests/test_api.py`:

8. `test_run_with_an_impossible_floor_is_rejected_not_silently_zero`: POST a
   scenario with `soc_floor_frac=0.9` and `strategic_reserve_frac=0.9`, then POST
   a run. Assert the run POST returns 422 and that `GET /runs/{id}` reports
   status `failed`. This is the finding's own repro, inverted.

Verify:

```
uv run pytest tests/test_models.py tests/test_api.py
uv run pytest
uv run ruff check .
```

Commit: `F4: StorageAsset validates the reserve fractions`

### Phase 3 — F1 and F7a, deliverable energy and the floor invariant (about 90 min)

Goal: the engine never discharges below the protected floor at any efficiency.

Spec, stated once: `discharge` is energy at the terminals. Delivering it costs
`discharge / one_way_efficiency` out of the tank. Tank energy above the floor is
`soc - min_soc_mwh`. Deliverable energy is therefore
`(soc - min_soc_mwh) * one_way_efficiency`. The source rule is
`docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf`, RCM winter derivation:
"Protected reserve floor = 20% of Total Capacity (cannot discharge below)".

**`src/owr/soc_engine.py`**

1. Change `usable_energy` to return deliverable energy at the terminals:

```python
return max(0.0, soc - asset.min_soc_mwh) * asset.one_way_efficiency
```

   Rewrite its docstring around the spec above. State that the tank basis and the
   terminal basis coincide at efficiency 1.0, which is why the suite never caught
   this.
2. Leave `clamp_discharge`'s body unchanged. It already reads
   `min(requested, usable_energy(...), asset.power_mw)`, and step 1 makes all
   three terms terminal quantities. Add one docstring sentence naming the units.

**`src/owr/budget.py`**

3. `daily_budget`: keep the signature and the parameter name. Update the
   docstring to state that `usable_energy_mwh` is energy deliverable at the
   terminals, so the 80% rule caps a terminal-basis budget that `dispatch`
   allocates as hourly discharge. This is the audit the finding asks for; no code
   change is required once step 1 lands.

**`src/owr/models.py`**

4. Add a docstring to `DailyResult` naming the unit of each field, and state that
   `usable_energy` is the deliverable-at-terminals figure at the end of the day.
   The JSON key and the API field keep their names.

**`src/owr/cli.py`**

5. No code change. Confirm and leave `max_available = asset.total_mwh -
   asset.min_soc_mwh` on the tank basis: it is the recharge-capacity denominator
   (70% of total capacity), not a discharge quantity. Do not multiply it by the
   leg efficiency.

**Tests** in `tests/test_soc_engine.py`:

6. `test_clamp_discharge_caps_at_deliverable_energy_above_the_floor`: asset
   `total_mwh=100, power_mw=100, efficiency=0.64, soc_floor_frac=0.30,
   strategic_reserve_frac=0.0` (leg is exactly 0.8). Assert
   `clamp_discharge(40.0, 50.0, asset) == pytest.approx(8.0)` and that
   `next_soc(40.0, 0.0, 8.0, asset.one_way_efficiency) == pytest.approx(30.0)`.
   This is the finding's arithmetic repro.
7. `test_floor_invariant_holds_at_lossy_efficiency` (F7a). Parametrize
   `efficiency` over `(0.5, 0.72)` and, inside the test, loop `soc` over
   `(min_soc, min_soc + 1, half of total, total)` and `requested` over
   `(0.0, 1.0, total, 10 * total)`. Assert
   `next_soc(soc, 0.0, clamp_discharge(soc, requested, asset), asset.one_way_efficiency)
   >= asset.min_soc_mwh - 1e-9`. The docstring cites the source rule above. Use a
   tolerance because the round trip through a multiply and a divide is not exact
   in IEEE 754. Do not add an epsilon to production code.
8. `test_usable_energy_is_terminal_basis_and_matches_tank_basis_when_lossless`.

**Tests** in `tests/test_simulator.py`:

9. `test_soc_never_crosses_the_floor_at_lossy_efficiency`, parametrized over
   `(0.5, 0.72)`: run the existing three-day stress window fully charged and
   assert every hourly `soc >= asset.min_soc_mwh - 1e-6`, and the same for
   `final_soc`.

**Tests** in `tests/test_cli.py`:

10. `test_no_hourly_soc_below_min_soc_at_lossy_efficiency`: `_report(["--efficiency",
    "0.72"])`, then the same assertion as the existing eff-1.0 test at line 285.

Verify, including the finding's own demo repro:

```
uv run pytest tests/test_soc_engine.py tests/test_simulator.py tests/test_cli.py
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --start-soc-mwh 20000 --lead-days 1 \
  --efficiency 0.72 --format json > /tmp/f1.json
uv run python -c "import json;r=json.load(open('/tmp/f1.json'));s=[h['soc'] for d in r['daily'] for h in d['hourly']];print('lowest',min(s),'floor',r['summary']['min_soc_mwh'],'violated',min(s)<r['summary']['min_soc_mwh']-1e-6)"
uv run pytest
uv run ruff check .
```

The one-liner must print `violated False`. Before this phase it prints
`lowest 17971.38 ... violated True`.

Commit: `F1: cap discharge at deliverable energy above the reserve floor`

### Phase 4 — F3 and F7b, net-load accounting (about 60 min)

Goal: charging from surplus wind never raises the reported peak.

**`src/owr/simulator.py`**

1. Line 192: `net_load_mw = load[h] - discharge`. Add one comment naming D2 and
   the reason: surplus wind is wind above the load the grid must serve, so
   charging from it adds no grid load.
2. Update the `reserve_peak_mw` field comment on `SimulationResult`: worst hour of
   net load, where net load is gross load minus discharge.
3. Update the `hourly_frame` docstring field-map table. `net_load` maps to the
   architecture doc's `dispatched_net_load` and equals `gross_load - discharge`.
   Add one sentence: `charge` carries surplus-wind charging and never enters
   `net_load`, so `capacity_dispatched(t)` equals `discharge(t)` and equals
   `gross_load - net_load` for any later per-event metric.
4. Do not change `surplus_wind`, `clamp_charge`, the SoC updates or
   `capacity_margin`'s formula. `capacity_margin` follows `net_load_mw` and
   changes with it, which is correct: firm capacity does not serve a surplus-wind
   charge.

**`src/owr/metrics.py`**

5. `net_load`: keep the signature, the formula and the default. Extend the
   docstring: `charge_mw` is charge drawn **from the grid**; the simulator charges
   only from surplus wind and therefore passes no grid charge, so its `net_load`
   column is `gross - discharge`. This reconciles the two modules without a
   formula change. `tests/test_metrics.py:28` stays valid as written.

**Tests** in `tests/test_simulator.py`:

6. `test_surplus_wind_charging_does_not_raise_the_reserve_peak` (F7b, the
   reviewer's repro, with a load bump added). One day: load 100 MW in every hour
   except 300 MW at hour 18; `hourly_wind_mw` 0 in every hour except 500 MW at
   hour 12. A flat load produces no dispatch at all (the known flat-day edge), so
   the bump is what makes the discharge leg real. Set `demand_percentile=0.95`,
   the starting SoC above the floor and below `total_mwh`, and `power_mw` at or
   above 500, so both a discharge and a charge can happen. Assert: hour 12 has
   `charge > 0`; hour 18 has `discharge > 0`; `baseline_peak_mw == 300.0`;
   `reserve_peak_mw <= baseline_peak_mw`; and at hour 12
   `net_load == pytest.approx(gross_load - discharge)`.
   Before this phase hour 12 reports a net load near 500 MW against a 300 MW
   baseline peak, which is a negative severity reduction.
7. `test_reserve_peak_never_exceeds_baseline_peak`: assert the invariant on the
   surplus-wind profile and on the existing three-day stress window.
8. `test_capacity_margin_follows_the_net_load_definition`: with
   `available_capacity_mw` set, assert
   `capacity_margin == pytest.approx(available - net_load)` in the charging hour.

Verify:

```
uv run pytest tests/test_simulator.py tests/test_metrics.py tests/test_sweep.py
uv run pytest
uv run ruff check .
```

`tests/test_sweep_cli.py::test_reference_point_real_and_synthetic` must stay green
without an edit. Both shipped profiles carry zero surplus-wind hours, so this
phase cannot move their numbers. If it does, stop and find the cause.

Commit: `F3: surplus-wind charging leaves net load and the reserve peak`

### Phase 5 — F5, one charging rule (about 60 min)

Goal: pre-event charging and in-window charging read the same wind.

**`src/owr/initial_soc.py`**

1. In `charge_from_wind`, take the day's load and charge from surplus only:

```python
load = day.hourly_load_mw
surplus = max(0.0, wind[hour] - max(0.0, load[hour]))
charge = clamp_charge(soc, surplus, asset)
```

   `DayProfile` always carries 24 load values, so no length guard is needed.
2. Rewrite the docstring. State the rule, state that it is now the simulator's
   rule with `discharge = 0` (no dispatch happens before the event), and name the
   open team question `wind_charge_source`: the shipped profiles carry ISO-NE
   system-wide wind, which serves load and is almost never surplus, so this rule
   returns the starting SoC unchanged on both example files. A dedicated
   offshore farm whose output goes to the reserve first is a different model that
   this engine does not assume.

**`src/owr/cli.py`**

3. Add a `wind_charge_source` entry to `_OPEN_QUESTIONS_STATIC` with
   `"flags": []`, following the shape of `recharge_opportunity_definition`. The
   note states the rule, the consequence on system-wide wind series, and the
   alternative dedicated-farm reading. Add the matching entry to the
   `open_questions` list in `_build_report` with
   `"value_used": "surplus wind above the hour's net load, charge and pre-charge alike"`.
   Do not add a flag and do not add a branch.

**Tests** in a new file `tests/test_initial_soc.py`. `initial_soc.py` has no test
module today; this creates the mirror the conventions ask for, as Phase 1 does for
`models.py`.

4. Move `test_initial_soc_charges_from_wind_before_event` out of
   `tests/test_simulator.py` into the new file, unchanged. Its lead day carries
   zero load, so it stays green under the new rule. Remove the now-unused
   `charge_from_wind` import from `tests/test_simulator.py`. Leave the import in
   `tests/test_cli.py`, which still uses it.
5. `test_charge_from_wind_ignores_wind_at_or_below_the_lead_day_load`: lead day
   with flat load 1000 and flat wind 800; assert the returned SoC equals the
   starting SoC.
6. `test_charge_from_wind_takes_only_the_surplus_above_load`: flat load 1000,
   flat wind 1200, power 100000, headroom large; assert the SoC rises by exactly
   `24 * 200 * asset.one_way_efficiency`.

**Tests** in `tests/test_cli.py`:

7. Replace `test_lead_days_strictly_increase_charge_in_order` with
   `test_lead_days_strictly_increase_charge_when_wind_exceeds_load`. Write a
   five-day CSV under `tmp_path` (`date,hour,load_mw,wind_mw`, 24 rows a day,
   load 100.0, wind 3000.0), then run the CLI with `--window all --lead-days N`
   for N in 1, 2, 3, `--storage-mwh 200000 --power-mw 2000 --start-soc-mwh 20000
   --format json`, and assert the three `soc_at_window_start_mwh` values strictly
   increase. `--window all` avoids any dependence on stress detection. Follow the
   `tmp_path` CSV pattern already at line 144.
8. `test_wind_charge_source_open_question_is_reported`: the id appears in
   `report["open_questions"]`.
9. Leave `test_lead_days_correctness_by_equality_against_charge_from_wind` and
   `test_window_all_lead_days_positive_path` as they are. Both compare the CLI
   against `charge_from_wind` directly, so both stay green and both stay
   meaningful.

Verify:

```
uv run pytest tests/test_initial_soc.py tests/test_simulator.py tests/test_cli.py
uv run pytest
uv run ruff check .
```

Commit: `F5: pre-event charging takes surplus wind only`

### Phase 6 — F6, an annotation that reads the result (about 30 min)

Goal: the decision package states the floor outcome it measured.

**`src/owr/api/app.py`**

1. In `_annotation`, build the asset from the scenario (`_asset(scenario)`) and
   read `min_soc_mwh`. The run succeeded, so the asset is valid by construction.
2. Choose the wording from the comparison, with a tolerance:

```python
above = res.final_soc >= asset.min_soc_mwh - 1e-6
position = "above" if above else "below"
```

   The sentence becomes: `The reserve ended at {final_soc:,.0f} MWh, {position}
   its protected floor of {min_soc_mwh:,.0f} MWh.`
3. Add `"min_soc_mwh": asset.min_soc_mwh` to `payload["summary"]`. It is additive;
   `pg_store` persists the payload as JSON and needs no migration.
4. The "below" branch is reachable without F1: a scenario whose
   `storage_start_mwh` sits under the floor can never discharge and ends under
   the floor. Say so in a comment so nobody deletes the branch as dead.

**Tests** in `tests/test_api.py`:

5. `test_annotation_states_the_floor_position_from_the_result`: the existing
   healthy scenario yields "above its protected floor of"; assert the payload
   carries `min_soc_mwh`.
6. `test_annotation_says_below_when_the_run_ends_under_the_floor`: scenario with
   `storage_total_mwh=1000`, `storage_start_mwh=100`, default fractions (floor
   300); assert the annotation contains "below its protected floor".

Verify:

```
uv run pytest tests/test_api.py
uv run pytest
uv run ruff check .
```

Commit: `F6: the decision package states the measured floor position`

### Phase 7 — F8, board resync and every number that moved (about 90 min)

Goal: the tracked documents match what the code now prints. Run first, write
second. Never predict a number.

1. Record the true suite result:

```
uv run pytest | tail -3
uv run ruff check .
```

2. Run the rehearsed demo commands and capture the output:

```
uv run simulate --input examples/synthetic_winter_stress.csv --list-windows
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --start-soc-mwh 20000 --lead-days 1
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --start-soc-mwh 20000 --lead-days 1 \
  --efficiency 0.72
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 2000 --chart sweep.png
```

3. Run the full-charge variant of Acts 3 and 4, because F5 removes the pre-event
   charge on this profile:

```
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1 --efficiency 0.72
```

4. Decision rule for `DEMO.md`, applied to the measured numbers. If the
   `--start-soc-mwh 20000` runs report a severity reduction that rounds to 0.0%,
   make the full-charge commands from step 3 the Act 3 and Act 4 commands, and
   keep one line in Act 3 that shows the pre-event charging block reporting no
   gain. Otherwise keep the rehearsed commands. Either way, rewrite both tables
   from the captured output.
5. `DEMO.md` edits: the Act 1 pass and skip counts; the Act 3 table and its two
   quirk bullets; the Act 4 table and its talking point (state that 0.72 is the
   round-trip figure, that the engine applies `sqrt(0.72) = 0.8485` per leg, and
   that the flag takes the published number directly); the Act 5 reference row;
   the rehearsal line at the top (date, branch, commit). Add one short paragraph
   to Act 3 that names `wind_charge_source`: ISO-NE system-wide wind never
   exceeds system load in this window, so the reserve sees no surplus to charge
   from, and the engine now says so instead of assuming a dedicated wind farm.
6. `README.md` edits: the pass and skip counts in the quick-start block; the
   expected-result paragraph under the real-scenario command (the 48,794 MWh
   figure is dead); the sweep expected number if step 2 moved it; and the
   model-constants paragraph, which gains one sentence stating that efficiency is
   round trip and that the engine splits it per leg.
7. `docs/BOARD.md` resync. Update the `synced` stamp to the real date and time of
   the edit. Move each live item that measured reality contradicts, and only
   those. The ETL transform item leaves In Progress: `src/owr/etl/transform.py`
   and `tests/test_etl_transform.py` both ship. The ETL extract item leaves
   Blocked only if `src/owr/etl/extract.py` and its tests ship; if the live pull
   is still unverified, keep the item and state that reason on the line. Add one
   Done line for this work, linked to `docs/PLAN_REVIEW_FIXES.md`, with the date
   and the measured test counts, matching the format of the other Done lines. Do
   not invent Discord links. Do not add a section.
8. `docs/FINDINGS_2026-08-06_SYSTEM_REVIEW.md`: change the status sentence at the
   top to name the resolution, one line: `Status: F1 to F8 fixed on
   worktree-review-fixes; see docs/PLAN_REVIEW_FIXES.md.` Change nothing else.
   The file is a dated record.
9. `HANDOFF.md` is untracked and exists only in the main checkout. Do not create
   it in this worktree. The coordinator updates it after the merge.

Verify:

```
uv run pytest
uv run ruff check .
git status --short
```

`git status` must show no unexpected file. `sweep.png` and `sweep.csv` are
ignored by `.gitignore`.

Commit: `F8: resync the board and regenerate every measured number`

## 5. Risks

**R1. F5 removes the demo's best number.** Both shipped profiles carry zero
surplus-wind hours, so `charge_from_wind` becomes an identity on them. `DEMO.md`
Act 3's "20,000 MWh -> 48,794 MWh over 1 lead day" and the same figure in
`README.md` both die. At `--start-soc-mwh 20000` against a 60,000 MWh asset with
an 18,000 MWh floor, only 2,000 MWh of tank sits above the floor, so Acts 3 and 4
shrink to almost nothing. Phase 7 step 3 and step 4 handle this with the
full-charge variant and an explicit decision rule. The `demo-fallback` tag still
points at the pre-fix rehearsal if demo morning goes wrong.

**R2. Telling a legitimate expectation update from a regression.** A number may
move only where one of these is true: efficiency is below 1.0 (F1, F2); the
profile has an hour with wind above load (F3, F5); or the reserve floor binds.
Everything else must hold still.

Canaries that must stay green with no edit, in every phase:

- `tests/test_sweep_cli.py::test_reference_point_real_and_synthetic` (0.010633
  and 0.25).
- `tests/test_cli.py::test_json_summary_matches_direct_simulate_call`,
  `::test_no_hourly_soc_below_min_soc`,
  `::test_reserve_peak_below_baseline_and_positive_severity_reduction`.
- `tests/test_metrics.py::test_recharge_opportunity_matches_simulator_at_scale_where_no_clamp_binds`.
- `tests/test_sweep.py::test_run_sweep_matches_direct_simulate_call_anti_fork_guard`.
- `tests/test_api.py` reserve-floor assertions at efficiency 1.0.

Expectation updates that are legitimate, and the only ones this plan authorizes:

- `tests/test_soc_engine.py::test_state_equation_lossless`,
  `::test_state_equation_lossy` and `::test_negative_flows_rejected`: the
  `next_soc` keyword rename only. No asserted value changes.
- `tests/test_simulator.py::test_initial_soc_charges_from_wind_before_event`:
  moved to `tests/test_initial_soc.py` in Phase 5, body unchanged.
- `tests/test_cli.py::test_lead_days_strictly_increase_charge_in_order`: replaced
  by a surplus-wind fixture, because the old fixture can no longer charge.
- `DEMO.md`, `README.md` and `docs/BOARD.md` numbers, in Phase 7 only, from
  captured output.

If any other assertion needs an edit, stop and report it. Treat it as a
regression until proven otherwise.

**R3. Floating point at the floor.** `(soc - min) * leg / leg` is not exact.
Assert with a tolerance (`1e-9` in unit tests, `1e-6` at MWh scale, matching the
existing suite). Do not add an epsilon to `soc_engine`.

**R4. The source document disagrees with itself.** Its anchor table says
protected reserve 30%; its RCM derivation says protected reserve floor 20%. The
citation must state this repo's reading (20 + 10 = 30) and the discrepancy, so
the next reader does not silently pick the other branch. The 18,413 MWh/hr
threshold is hourly basis and closes nothing about the daily rule.

**R5. F4 moves an API failure from silent to loud.** A scenario whose fractions
sum to 1.0 or more now fails at run time with HTTP 422 instead of returning
`succeeded` with `severity_reduction: 0.0`. `POST /scenarios` still returns 201,
by the scope decision in section 1. No shipped fixture uses such a pair; the
existing tests use 0.33 and 0.0.

**R6. Stored runs are not comparable across this change.** Three persisted
columns change meaning or value, and no migration marks the break:

- `app.scenario.efficiency` keeps its name and its round-trip meaning, but any
  run persisted before Phase 1 at an efficiency below 1.0 was computed with the
  leg applied twice (D1).
- `app.run_result_daily.usable_energy` moves from a tank basis to a terminal
  basis (F1). The two agree only at efficiency 1.0.
- `app.run_result_hourly.net_load` drops the charge term, so it changes on any
  hour that charged from surplus wind (D2). The column comment in
  `db/migrations/001_init.sql:129` already describes the new value.

No migration exists and none is planned. Compare old runs against new runs only
at efficiency 1.0 on a profile with no surplus-wind hour.

**R7. A binary file enters the repo.** `docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf`
is about 233 KB. Three source PDFs are already tracked, so this follows
precedent.

## 6. Order and dependencies

The finding's order holds and this plan follows it: F2, F4, F1, F3, F5, F6, F8.
One dependency is real and is the reason F2 leads: the F1 clamp formula multiplies
by the per-leg efficiency, which does not exist until D1 lands. F4 is independent
and sits second because it is the cheapest. F3, F5 and F6 do not depend on each
other. Phase 7 comes last because F1, F2 and F5 all move the published numbers.
