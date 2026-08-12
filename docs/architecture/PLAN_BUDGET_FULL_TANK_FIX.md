# Implementation plan: the full-tank zero-budget fix

Written 2026-08-10. Follow-on to `docs/architecture/PLAN_EVENT_RELATIVE_RECHARGE.md`
(Sections 7, 9, 12/D11, 12/D15, 15/R3). Scope: one defect, four source files, no new
architecture. Baseline to hold: **820 passed, 4 skipped**, ruff clean (measured
2026-08-10 on the current working tree).

Abbreviation: SoC means state of charge.

---

## 1. The fix in one paragraph

`budget.daily_budget`'s second term takes a **recharge opportunity**, a forward estimate of
the wind the schedule routes to storage. Phase 6 of the recharge plan replaced that input
with `recharge.charge_forward(...).charged_mwh`, which is the charge a tank can **accept**
after the headroom clamp. The two quantities are not the same. Feeding the accepted quantity
into the opportunity term puts the SoC into both terms of the minimum, so a full reserve
forecasts zero further recharge and the whole budget floors at 0.0. The fix restores the
opportunity basis: a new `recharge.recharge_opportunity_mwh(days, day_schedules)` sums
`charge_request_mw` over the horizon, takes no starting SoC and no `StorageAsset`, and feeds
`expected_recharge_mwh`. `budget.py`'s formula does not change. `sweep.py`, `sweep_cli.py`
and `api/app.py` do not change.

---

## 2. Root cause, with evidence

### 2.1 The contract was written down, then changed without notice

The function this plan's predecessor deleted stated the contract in its own docstring
(`git show e358231 -- src/owr/simulator.py`, `_surplus_wind_recharge_mwh`):

> "Applies no SoC or power clamp: this is a forecast of opportunity for
> `budget.daily_budget`'s recharge term, not a dispatch."

The recharge plan's D11 argued that `budget.py` needed no change, because `daily_budget`
"already takes `expected_recharge_mwh` from its caller and fixes no recharge definition".
That is true of the **routing rule**. It is not true of the **clamp basis**. Phase 6 changed
both and recorded only one. R3 named the residual risk as a conservative under-statement. R3
did not fire as an under-statement. It fired as a hard zero.

### 2.2 The source document calls the quantity an opportunity

`docs/source/2026-08-05_Software_Architecture_Documentation.md`, Component 5:

> "Estimate Future Recharge Opportunities. Estimate available recharge throughout the
> remaining forecast horizon."

An opportunity is a property of the wind resource and the schedule. It is not a property of
the tank's present fill. `metrics.recharge_opportunity_mw` already reads the source that way:
on every charging hour it returns `wind[h]` with no SoC clamp and no power clamp.

### 2.3 The defect is an absorbing state, not a start condition

Measured on `examples/real_winter_stress_2026.csv`, `--storage-mwh 60000 --power-mw 5000`,
default efficiency:

| `--start-soc-mwh` | Discharged (MWh) | Per-day budgets (MWh) |
|---|---|---|
| 60000 (default) | 0.0 | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| 59000 | 107.0 | `[107, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| 55000 | 534.8 | `[535, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| 45000 | 1604.3 | `[1604, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| 30000 | 2557.2 | `[927, 1290, 340, 0, 0, 0, 0, 0, 0, 0, 0]` |

Off-peak charging refills the tank within one to three days at every starting SoC. The budget
then reaches 0.0 and never recovers, because a full tank forecasts no further recharge and a
zero budget produces no discharge to open headroom. A different starting SoC postpones the
failure. It does not remove it.

### 2.4 The defect inverts a physical invariant

Total discharge against starting SoC, same file and asset, current code:

```
0.00:5,227  0.10:4,936  0.25:4,596  0.30:4,039  0.40:3,547  0.50:2,557
0.60:2,039  0.70:1,861  0.80:1,283  0.90:642    0.95:321    1.00:0
```

The model delivers less energy the more energy it holds. Under the fix the same ladder rises
from 59,898 MWh to 71,596 MWh and is non-decreasing at every step. Section 6 turns this into
a test.

### 2.5 Why the chosen fix is not the old bug in new clothes

Three separate claims, each checkable:

1. **Nothing the engine *does* becomes SoC-unaware.** The hour loop still calls
   `soc_engine.clamp_charge` against the live SoC. `initial_soc.charge_from_wind` still uses
   the SoC-clamped `recharge.charge_forward`. Only the **planning signal** stops carrying a
   constraint that the other term of the minimum already carries.
2. **The load-netting surplus rule does not come back.** `recharge_opportunity_mwh` calls
   `charge_request_mw`, which reads the hour's `HourState` and the hour's wind. It never
   reads load and never reads discharge. The expression that
   `tests/test_schedule.py::test_guard_surplus_wind_rule_does_not_reappear_in_code` counts,
   `max(0.0, wind - max(0.0, load - discharge))`, does not appear in the new code. That guard
   protects against the **load-netting** rule, not against SoC independence; do not read it as
   forbidding this change.
3. **The state variable must not gate the decision that changes it.** `available_charge_mwh`
   is the SoC-aware term and it stays. Putting the SoC into the second term as well makes
   `daily_budget` a decreasing function of stored energy over part of its range, which
   Section 2.4 measures.

---

## 3. The change, file by file

### 3.1 `src/owr/recharge.py`

Add one private helper and one public function. Place the helper above `charge_forward` and
call it from both functions, so the two alignment checks live once.

```python
def _require_aligned(
    days: Sequence[DayProfile], day_schedules: Sequence[DaySchedule]
) -> None:
    if len(days) != len(day_schedules):
        raise ValueError(
            f"days (len {len(days)}) and day_schedules (len {len(day_schedules)}) must match"
        )
    for day, day_schedule in zip(days, day_schedules, strict=True):
        if day.date != day_schedule.date:
            raise ValueError(
                f"date mismatch: day {day.date} vs day_schedule {day_schedule.date}"
            )


def recharge_opportunity_mwh(
    days: Sequence[DayProfile], day_schedules: Sequence[DaySchedule]
) -> float:
    _require_aligned(days, day_schedules)
    total = 0.0
    for day, day_schedule in zip(days, day_schedules, strict=True):
        wind = day.hourly_wind_mw if day.hourly_wind_mw else (0.0,) * HOURS_PER_DAY
        for hour in range(HOURS_PER_DAY):
            total += charge_request_mw(wind[hour], day_schedule.hours[hour])
    return total
```

Keep the two error messages byte-identical to today's, so no existing test message drifts.

The docstring must state five facts:

1. This is the recharge term of `budget.daily_budget`, Component 5's "available recharge
   throughout the remaining forecast horizon".
2. It is an opportunity, not a dispatch. It takes no starting SoC and no `StorageAsset`, so
   no state of charge can enter it.
3. On a charging hour its per-hour value equals `metrics.recharge_opportunity_mw`'s value for
   the same hour, so the budget term and the reported metric share one definition.
4. A caller must not clamp it by headroom. Name the consequence: the budget falls as stored
   energy rises, and a full reserve floors the whole minimum at 0.0.
5. It applies no power clamp either. Say that the team question stays open, and reference
   Section 4 item 5 of this plan.

Change two sentences that this fix makes wrong:

- `ChargeForecast.charged_mwh`'s inline comment: add that no budget term reads it, and that a
  future caller must not wire it into one. Name this plan.
- `charge_forward`'s docstring: the sentence "any budget term it feeds is therefore
  conservative (R3)" is no longer true, because it feeds no budget term. Restate it: the
  forecast serves `initial_soc` only, where the headroom clamp is correct.

Keep `ChargeForecast` with both fields. `charged_mwh` loses its only production reader, and
removing it would mean deleting the dataclass, changing `charge_forward`'s return type and
editing five tests. The field is honest content of a forecast, and the churn is larger than
the field costs.

### 3.2 `src/owr/simulator.py`

In the per-day loop, replace the `charge_forward` call and the budget call with:

```python
        if day_schedule.mode is DayMode.ACTIVE_EVENT:
            day_budget = budget_mod.daily_budget(
                available_charge_mwh=usable_energy(soc, asset),
                remaining_stress_days=remaining_cycles,
                expected_recharge_mwh=recharge_mod.recharge_opportunity_mwh(
                    remaining_days, day_schedules[i:]
                ),
                remaining_cycles=remaining_cycles,
            )
        else:
            day_budget = 0.0
```

Keep the `recharge_mod` import; the hour loop still calls `charge_request_mw`. Update the
comment block above `remaining_days`: state that the numerator is the horizon opportunity,
that it carries no SoC, and that D15's day-set mismatch stands. Two side effects belong in
the module docstring, one sentence each. The per-hour clamp and state update leave the
forecast, so the per-hour work drops while the loop shape stays O(n^2 * 24) and R2 is
unchanged. R3 no longer applies, because the budget term no longer forecasts a SoC
trajectory.

### 3.3 `src/owr/budget.py`

Docstring only. The formula does not change. Add to `daily_budget`:

> `expected_recharge_mwh` is a recharge **opportunity** over the remaining horizon, not the
> charge a tank could accept. The caller must not clamp it by headroom. `available_charge_mwh`
> is the only term that carries the state of charge. A headroom-clamped recharge term makes
> this function return less as the reserve holds more, and a full reserve then returns 0.0 for
> every remaining day. See `docs/architecture/PLAN_BUDGET_FULL_TANK_FIX.md`.

Do not rename the parameter. The call site now names the source function, which reads clearly,
and a rename would edit seven call sites in `tests/test_budget.py` for no added guarantee.

### 3.4 `src/owr/cli.py` and `src/owr/sweep_cli.py`, text only

No flag changes, no default changes, no behavior changes.

`src/owr/cli.py`, the `recharge_cycle_basis` open-question note: see Section 7.

**The stale wind claim lives in three places, not one.** The sentence "At 1.0 the shipped
profiles still charge 0.0 MWh: ISO-NE system-wide wind almost never exceeds system load. A
multiplier near 5 is what makes surplus wind appear" becomes false at all three. Measured
after the fix, the default `simulate` run on `examples/synthetic_winter_stress.csv` charges
13,380 MWh at multiplier 1.0. Correct every occurrence, or `--help` keeps telling an operator
something false:

| Location | Lines (about) |
|---|---|
| `src/owr/cli.py`, the `wind_multiplier_range` open-question note | 147 to 158 |
| `src/owr/cli.py`, the `--wind-multiplier` argparse `help=` string | 347 to 353 |
| `src/owr/sweep_cli.py`, the `--wind-multiplier` argparse `help=` string | 160 to 163 |

Replace the claim with this fact: event-relative recharge routes all pre-charge and off-peak
wind to storage, so charging is non-zero at the identity multiplier, and the multiplier scales
an existing quantity rather than creating one. Keep the `[OPEN: wind_multiplier_range]` tag and
the source reference in both help strings.

### 3.5 Files that do not change

| File | Reason |
|---|---|
| `src/owr/sweep.py` | Starting every point full is correct and now works. See Section 4 item 3 |
| `src/owr/sweep_cli.py` | No new flag. See Section 4 item 3. Its `--wind-multiplier` help text does change; see Section 3.4 |
| `src/owr/api/app.py` | `storage_start_mwh` is a required scenario field. There is no default to change |
| `src/owr/schedule.py`, `dispatch.py`, `metrics.py`, `soc_engine.py`, `initial_soc.py` | The defect is in one budget input. None of these produces it. `initial_soc.py` gets one docstring correction for a claim that is already false; see Section 8 |

---

## 4. Options rejected

1. **Exempt a fully-charged start from the recharge term.** It puts a cliff in the budget
   between `soc == total_mwh` and `soc == total_mwh - epsilon`. It also fails the measurement
   in Section 2.3: the budget reaches zero from day 4 at a 50 percent start, where no
   exemption applies.
2. **Change the CLI, API or sweep default starting SoC.** Section 2.3 shows this postpones the
   failure by one to three days and does not remove it. The API has no default to change. A
   reserve that is full when a forecast event starts is the right pre-positioning assumption,
   and moving it to work around a formula defect would hide the defect.
3. **Give `sweep` a starting-SoC option.** Not needed after the fix; measured, the default
   `uv run sweep --input examples/real_winter_stress_2026.csv --power-mw 2000` returns a rising
   curve (0.246 percent, 0.493 percent, then 0.759 percent from 20,000 MWh up). The option is
   also ill-defined for a sweep: one absolute MWh value is a different fill fraction at each
   ladder size, which breaks the comparability rule `sweep.py`'s docstring records
   ("every sweep point starts full", `PLAN_SCENARIO_SWEEP.md` section 4.3 rule 5). A fraction
   flag would be a new design decision, not a bug fix.
4. **Make the forecast discharge-aware.** The budget depends on the forecast and the forecast
   would depend on the budget. Resolving that needs a fixed point, and it is unnecessary once
   the term is opportunity-basis.
5. **Power-clamp the opportunity term** with `min(request, asset.power_mw)`. Rejected as an
   unneeded asset dependency in a resource estimate, and because the deleted precedent and
   `metrics.recharge_opportunity_mw` both apply no power clamp.

   The evidence axis is the storage-to-wind ratio, not the wind multiplier. A large tank with
   small power and high wind is where the two variants separate. Measured over nine
   configurations of (`total_mwh`, `power_mw`, wind), starting full, on a 3-day active-event
   fixture:

   | Configuration | Budget per day, unclamped | Budget per day, clamped | Discharged |
   |---|---|---|---|
   | 2,000 / 200 / 5,000 | 447, 670, 1,270 | 447, 670, 1,270 | 2,116.7 both |
   | 20,000 / 200 / 5,000 | 4,467, 6,500, 13,000 | 3,800, 3,800, 3,800 | 3,000.0 both |
   | 200,000 / 2,000 / 5,000 | 44,667, 65,000, 95,000 | 38,000 each day | 30,000.0 both |
   | 500,000 / 100 / 50,000 | 111,667, 167,400, 334,800 | 1,900 each day | 1,500.0 both |

   **Delivered discharge is identical in all nine, including the extremes.** The reason is
   structural, not a fixture accident: `dispatch.allocate_discharge` clips every hour at
   `power_mw`, so a budget above `power_mw` times the dispatch-hour count cannot be delivered.
   `soc_engine.clamp_charge` and `clamp_discharge` hold every physical limit regardless of what
   the budget forecasts.

   One honest limit. The reported `DailyResult.budget` does differ, so an operator reading the
   JSON report can see a budget that the asset could never deliver in one day. That is a
   reporting wart, not a behavior defect. Record both the choice and the wart in the
   `recharge_cycle_basis` note (Section 7 item 2).

---

## 5. Existing tests that change

Measured: an emulation of this fix run against the current suite gives **3 failed, 817 passed,
4 skipped**. Those three are exactly the tests that pin the defect.

| Test | Change |
|---|---|
| `tests/test_cli.py::test_reserve_peak_equals_baseline_without_surplus_wind_at_default_start` | Rename to `test_positive_severity_reduction_at_the_default_full_start`. Assert `severity_reduction > 0` and `energy_discharged_mwh > 0`. Measured value 0.0551. Replace the whole comment: the recharge plan predicted this inversion, and the opportunity basis delivers it |
| `tests/test_api.py::test_run_with_no_surplus_wind_discharges_nothing` | Rename to `test_run_with_no_wind_discharges_nothing` and change the fixture from `wind_mw=500.0` to `wind_mw=0.0`. Measured: 0.0 wind still gives `severity_reduction == 0` and all-zero budgets; 500.0 wind now gives 0.062. The intent survives, the mechanism is now "no recharge opportunity", never "no headroom" |
| `tests/test_sweep_cli.py::test_reference_point_real_and_synthetic` | Replace the four `approx(0.0)` pins with `> 0`. Add one pin that carries signal: real at multiplier 15 discharges more than real at multiplier 1 (104,314.8 MWh against 80,826.4 MWh), because severity reduction saturates on that file at 0.007587 while discharge does not. Rewrite the comment |

Comment-only updates. These tests keep passing, but their stated reasons become wrong, and a
reader who trusts them will build the next fixture around a constraint that no longer exists.

| File | What to correct |
|---|---|
| `tests/test_simulator.py` | `_stress_day`'s comment (about line 41) and `test_budget_rises_with_more_wind_on_active_event_days`'s comment (about line 229). Both say the fixture must avoid a full tank because the forecast is SoC-clamped |
| `tests/test_sweep.py` | `_stress_day`'s comment (about line 36), which calls a 0.0 severity reduction on that fixture intentional |
| `tests/test_cli.py` | `test_reserve_peak_below_baseline_and_positive_severity_reduction`'s comment (about line 333). Keep the fixture; correct the reason |
| `tests/test_api.py` | `test_full_run_flow`'s comment (about line 76). Keep the fixture; correct the reason |
| `tests/test_budget.py` | `test_daily_budget_is_zero_when_recharge_is_zero`: keep the test, add one line saying a zero here means no recharge opportunity in the horizon, never no headroom |

---

## 6. New tests

### 6.1 `tests/test_recharge.py`

1. `test_recharge_opportunity_sums_charge_requests`: one pre-charge day, wind 50.0 MW for 24
   hours, returns 1200.0. No efficiency factor applies; the value is routed energy, not stored
   energy.
2. `test_recharge_opportunity_skips_dispatch_and_non_event_hours`: an active-event day counts
   its off-peak hours only; a non-event day returns 0.0.
3. `test_recharge_opportunity_negative_wind_floors_at_zero`: D13 parity with
   `charge_request_mw`.
4. `test_recharge_opportunity_length_and_date_mismatch_raise`: both `ValueError` paths.
5. `test_guard_recharge_opportunity_takes_no_soc_and_no_asset`: assert
   `set(inspect.signature(recharge_opportunity_mwh).parameters) == {"days", "day_schedules"}`.

   **State the limit of this guard in its own docstring.** It constrains one function's
   signature and nothing else. It cannot see the call site, so it would not catch a future edit
   in `simulator.py` that goes back to `recharge_mod.charge_forward(...).charged_mwh`, which is
   exactly how the defect entered (commit `e358231`, Phase 9). Test 7 is the guard for that
   mistake, because it is behavioral and reads the simulator's output. Name test 7 in this
   test's docstring, and name this test in test 7's docstring, so a reader finds the pair.

### 6.2 `tests/test_simulator.py`

6. `test_full_tank_start_discharges_on_an_active_event`: existing `_stress_day` fixture,
   `_active_event_schedule`, `starting_soc=asset.total_mwh`. Assert total discharge is
   positive and `reserve_peak_mw < baseline_peak_mw`. Measured: 8,550.0 MWh discharged,
   reserve peak 11,525.0 against baseline 12,000.0.
7. `test_total_discharge_does_not_fall_as_starting_soc_rises`: same fixture, starting SoC
   fractions `(0.0, 0.2, 0.33, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)` of `total_mwh`. Assert the
   total-discharge sequence is non-decreasing. Measured under the fix: `0.0, 2975.0, 4275.0,
   5208.3, 6541.7, 7500.0, 8500.0, 8550.0, 8550.0`. Under current code the same sequence
   falls. This is the regression guard for the whole defect class, and the only test that
   watches the `simulator.py` call site. State both facts in the docstring and name test 5.
8. `test_two_window_span_pins_the_d15_day_set_mismatch`: the M1 test that the recharge plan
   specified in its Section 13.2 and did not deliver. See Section 7 below for the fixture and
   the assertion. Write it now, because this fix changes the exact expression it asserts.

### 6.3 `tests/test_sweep.py`

9. `test_sweep_severity_reduction_is_positive_at_the_full_start`: `run_sweep` over the
   existing 3-day fixture at sizes `(5000, 10000, 20000, 40000)`, power 2000 MW. Assert every
   point has `severity_reduction > 0` and that the values do not fall as size rises. Measured:
   0.015509, 0.031019, 0.062037, 0.124074. This is the test that proves the sweep deliverable
   is alive at its own default start.

---

## 7. D15 and `recharge_cycle_basis`

**Do not resolve D15 here.** Resolving it means choosing whether a cycle is a stress event or
a span day, and no source answers that. This fix leaves the mismatch unchanged in character
and changes two things about it.

First, the wording. D15 describes the numerator as "the recharge forecast", which now means
the horizon opportunity sum, not the SoC-clamped accepted charge. Correct that phrase in
`cli.py`'s `recharge_cycle_basis` note and in `simulator.py`'s comment.

Second, the urgency. Before this fix a multi-event span that started full produced all-zero
budgets, so the mismatch could not appear in any output. It appears now. Measured on an 8-day
two-window fixture (two 2-day windows, a 2-day gap, a 2-day tail, wind 150 MW, asset 20,000
MWh / 2,000 MW / efficiency 1.0 / floor 0.33, starting full):

```
modes:   [active, active, pre_charge, pre_charge, active, active, non_event, non_event]
budgets: [1675.0, 1739.3,        0.0,        0.0, 1425.0,  950.0,       0.0,       0.0]
```

Day 5's budget is 950.0 MWh because the numerator credits that day's 19 off-peak hours
(2,850 MWh) and nothing from the two trailing non-event days, while the divisor still counts
all three remaining days. An event-day basis would divide by one and give 2,850 MWh. The
mismatch costs a factor of three on that day, and it is now visible in shipped output.

Add to the `recharge_cycle_basis` note in `cli.py`, in this order:

1. The recharge term is an opportunity over the remaining horizon. It carries no state of
   charge, by construction: `recharge.recharge_opportunity_mwh` takes no SoC and no asset.
2. It applies no power clamp. On a large tank with small charge power the term can exceed what
   the asset could absorb, the minimum degenerates to its first term, and the reported daily
   budget can exceed what one day could deliver. Delivered energy is unaffected, because
   `dispatch.allocate_discharge` clips each hour at `power_mw` (Section 4 item 5). Whether to
   cap the term at the charge power stays open.
3. The D15 day-set mismatch is now observable in budget values, so the cycle basis needs a team
   answer sooner than it did.

**Test 8 (M1).** Build the 8-day fixture above. Assert every non-active day has
`budget == 0.0`. For each active day, recompute the budget from the two documented inputs and
assert equality:

```python
def soc_at_start_of(i: int) -> float:
    return starting_soc if i == 0 else result.daily[i - 1].hourly[-1].soc


for i, day_result in enumerate(result.daily):
    if day_schedules[i].mode is not DayMode.ACTIVE_EVENT:
        assert day_result.budget == 0.0
        continue
    soc = soc_at_start_of(i)
    remaining = len(span) - i     # D15: counts gap days and the second event's days
    expected = budget.daily_budget(
        available_charge_mwh=usable_energy(soc, asset),
        remaining_stress_days=remaining,
        expected_recharge_mwh=recharge.recharge_opportunity_mwh(
            span[i:], day_schedules[i:]
        ),
        remaining_cycles=remaining,
    )
    assert day_result.budget == pytest.approx(expected)
```

Measured: this recomputation matches the reported budget on all four active days. Call
`budget.daily_budget` rather than restating its `min`. The mismatch lives in the two inputs,
so a future change to the cycle basis must edit this test, which is the point of writing it.

---

## 8. Documentation

`README.md` and `DEMO.md` were not regenerated when the recharge feature landed, which its
own Section 14 required. This fix moves the same numbers again. Regenerate once, after the
code change, and do not hand-edit any figure.

| File | What to correct |
|---|---|
| `DEMO.md` Acts 3, 4, 5 | Every pinned table, and the narrative claim that the identity wind multiplier gives 0.0 percent. Re-run the four commands at lines 59, 74, 116 and 143 and paste the real output |
| `README.md` about line 61 | The paragraph stating that pre-event charging finds no surplus at any starting SoC. Under event-relative recharge, pre-charge hours route all their wind to storage |
| `CLAUDE.md` `budget.py` row | "(priority x reserve, floor-limited)" predates the two-term minimum. Restate it |
| `src/owr/initial_soc.py`, about line 31 | The `wind_charge_source` paragraph claims this rule "returns the starting SoC unchanged on both example files under the identity wind multiplier", then contradicts itself four lines later. Delete the false clause. This one predates the fix; `initial_soc`'s behavior does not change here |
| `docs/BOARD.md` | Replace the "Follow-on found during implementation" block with the resolution: the recharge term is an opportunity, `recharge.recharge_opportunity_mwh` supplies it, and `recharge_cycle_basis` stays open with a raised priority |

---

## 9. Phase order and verification gate

Run `uv run pytest` and `uv run ruff check .` after each phase.

1. Add `_require_aligned` and `recharge_opportunity_mwh` to `src/owr/recharge.py`, plus the
   two docstring corrections. Add the five tests in Section 6.1. The rest of the suite stays
   green, because nothing calls the new function yet.
2. Change the budget call in `src/owr/simulator.py`. Expect exactly three failures, the three
   tests in Section 5's first table. Rewrite those three. Add tests 6, 7 and 9. Then run the
   two checks in Section 9.1 before you continue.
3. Add test 8 (M1), then update `budget.py`'s docstring, `cli.py`'s open-question notes and the
   three stale wind sentences in Section 3.4.
4. Correct the five comment-only test files in Section 5's second table.
5. Regenerate `DEMO.md`, then correct `README.md`, `CLAUDE.md`, `initial_soc.py`'s docstring and
   `docs/BOARD.md`, per Section 8.

### 9.1 Two checks at the end of phase 2

Run both by hand. Neither becomes a committed test; both confirm a claim this plan rests on.

1. **Re-measure the storage-to-wind ratio axis.** Run the small-storage and large-tank
   configurations of Section 4 item 5 with and without `min(request, asset.power_mw)` in
   `recharge_opportunity_mwh`. Confirm that delivered discharge stays identical, and that only
   the reported `DailyResult.budget` moves. If discharge differs anywhere, stop: Section 4
   item 5's rejection no longer holds and the team must choose the clamp.
2. **Re-measure the invariant ladder.** Run
   `simulate --input examples/real_winter_stress_2026.csv --storage-mwh 60000 --power-mw 5000`
   at starting SoC 0, 30,000, 45,000, 55,000, 59,000 and 60,000. Confirm total discharge does
   not fall as the starting SoC rises. Section 2.4 gives the pre-fix values that must invert.

**Done means all five hold:**

1. `uv run pytest` reports at least 820 passed with 4 skipped.
2. `uv run ruff check .` is clean.
3. `uv run simulate --input examples/real_winter_stress_2026.csv --storage-mwh 60000
   --power-mw 5000 --format json` reports non-zero `energy_charged_mwh` and non-zero
   `energy_discharged_mwh`. Measured under the emulated fix: 79,514.1 MWh charged, 71,596.4
   MWh discharged, severity reduction 0.007587.
4. `uv run sweep --input examples/real_winter_stress_2026.csv --power-mw 2000` reports a
   non-zero severity reduction at every one of its seven sizes, rising from about 0.25 percent
   at 5,000 MWh to about 0.76 percent from 20,000 MWh up.
5. `tests/test_schedule.py`'s two architectural guards still pass unchanged.

---

## 10. Risks and assumptions

| # | Item | Response |
|---|---|---|
| A1 | The measurements in this plan come from a runtime emulation of the fix, not from the fix itself. The emulation rebinds `owr.simulator.recharge_mod` and computes the opportunity sum exactly as Section 3.1 specifies | Treat every figure as an expected value to confirm, not as a proven one. Re-measure at phase 2 |
| R1 | Every shipped example changes its numbers again, in the same direction the recharge plan predicted | Section 8 regenerates the documents from real runs |
| R2 | The opportunity term has no power clamp, so on a large tank with small power the second term goes inert and the minimum degenerates to its first term. The axis is the storage-to-wind ratio, not the wind multiplier | Delivered discharge is identical to the power-clamped variant across nine configurations, because `dispatch.allocate_discharge` clips each hour at `power_mw` (Section 4 item 5). Only the reported budget differs. Re-checked at phase 2, Section 9.1 check 1, and recorded as an open choice in `recharge_cycle_basis` |
| R3 | `ChargeForecast.charged_mwh` keeps no production reader | Kept on purpose (Section 3.1). A warning comment names this plan, so a future caller does not wire it into a budget term |
| R4 | Test 7's monotonicity holds on three measured configurations and by argument, not by proof | If a new fixture breaks it, report the fixture rather than weakening the assertion. A break is the defect class this test exists to catch |
| R5 | D15 stays open and is now visible in output | Section 7 records the new evidence and raises the priority. No basis change here |
