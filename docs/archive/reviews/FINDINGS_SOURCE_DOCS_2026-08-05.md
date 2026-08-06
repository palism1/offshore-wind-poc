# Source document review, 2026-08-05

Point-in-time record. Read as evidence, not as current state.

Source folder: `~/Downloads/GridStress Explorer`. The three `.docx` files are Google Docs
exports. Google Docs tabs export as `Title`-styled paragraphs, so the tab list survives the
export and is readable.

## 1. Tab structure

| Document | Tabs | Last change |
|---|---|---|
| Overview Document | 8 | Aug 5, 2026 08:46 |
| Scaling Document | 0 (single tab) | Jun 28, 2026 |
| Software Architecture Document | 11 | Aug 4, 2026 22:03 |

Overview tabs: Technical Brief, Definitions and Key Concepts, Regulatory Policies,
Assumptions, Variables & Inputs, Constraints & Rules, Metrics, Success Criteria.

Software Architecture tabs, with their status marks:

- ✅ 1-Scenario Config, 2-Data Pipeline, 3-Stress Event Detection, 4-Simulation
  Initialization, 5-Storage Dispatch Engine, 6-Grid Simulation Engine, 7-Scenario
  Metrics Engine
- ⏳ Global Asmts & Rules, Global Interf. Contract, Gloval Data Governance (title typo
  in the source)
- 🪦 Archived

The two spreadsheets: `Contacts.xlsx` has two tabs, People and Government.
`Resources/Datasets.xlsx` has one tab, Sheet1.

## 2. Changes since the 2026-07-30 snapshot

Compared against `docs/source/2026-07-30_Software_Architecture_Documentation.md`.
Refreshed exports are stored as `docs/source/2026-08-04_Software_Architecture_Documentation.md`
and `docs/source/2026-08-05_Overview_Document.md`.

**Status marks are new.** Components 1 to 7 are marked done. The three Global tabs are
marked in progress. These marks did not exist on Jul 30.

**Every data contract lost its `Type` column.** The Jul 30 tables carried
`Field | Required | Type | Unit | Description`. The current tables carry
`Field | Unit | Description`. Components 3 to 7 also lost the `Required` column.

**Component 2, data pipeline.**

| Jul 30 | Aug 4 |
|---|---|
| `wind_mwh` | split into `observed_wind_mwh` and `scaled_wind_mwh` |
| `demand_percentile` | renamed `load_percentile`, redefined as "pre-processed 5-winters percentile of daily load" |
| `wind_forecast_frac` | removed |

The five winters, 2021/2022 through 2025/2026, are now named explicitly, and each winter
runs the extract, transform and validate sequence independently.

**Component 3, stress event detection.** Timestamps became dates.
`event_start_timestamp` and `event_end_timestamp` became `event_start_date` and a derived
`event_end_date`. Removed: `first_hour_index`, `last_hour_index`, `peak_daily_load`,
`percentile_threshold`. `event_id` and `winter_id` are now defined as hash values.

**Component 4, simulation initialization.** `simulation_id` removed. `current_timestamp`
became `current_date`. `state_of_charge` became `available_charge`. `current_hour_index`
now states the Eastern Time zone, which is the first time zone commitment anywhere in the
architecture document.

**Component 5, storage dispatch engine.** `dispatched_capacity` became `charge_dispatched`.
The total dispatch rule changed:

- Archived tab: `Discharge(t) = Discharge_peak(t) + Discharge_smooth(t)`
- Component 5, current: `TotalDischarge(t) = Discharge_peak(t) OR Discharge_smooth(t)`

The change from a sum to an exclusive choice changes the dispatch result. It does not match
`src/owr/dispatch.py`, which sums the two allocations.

**Component 7, scenario metrics engine.** The heading "Capacity Margin Improvement" became
"Capacity Margin Deficit Reduction", and a new formula appeared above the old one.

## 3. The metric change: Capacity Margin Improvement to Capacity Margin Deficit Reduction

The rename is applied in **one** place: the Component 7 heading. Five places still carry the
old name.

| Location | Text | Action |
|---|---|---|
| Architecture, Component 7, data contract | field `capacity_magin_improvement` | rename to `capacity_margin_deficit_reduction`; also fixes the `magin` typo |
| Overview, Technical Brief tab | "Reliability: Capacity Margin Improvement" | rename |
| Overview, Variables & Inputs tab, Dependent | "Capacity Margin Improvement" | rename |
| Overview, Metrics tab | "CMI Score: (0, ≤0MW; 50, =75; 100, ≥150)" | rename, and decide whether the score band still applies |
| Overview, Metrics tab, robustness thresholds | "Capacity Margin Improvement:" | rename |

The Archived tab also carries the old name. Leave it. It is history.

### The two formulas conflict

Component 7 now holds both of these, one after the other, under the new heading:

1. `ΔCM(t) = max(0, CM_with_storage(t) − CM_without_storage(t))`
2. `∑(net_load_dispatch(t) − net_load_observed(t)) / ∑ net_load_observed(t) × 100`

Formula 1 is a deficit reduction in MW, floored at zero, per hour. Formula 2 is the old
percentage change in net load, and it is the formula the Overview document still labels
"Capacity Margin Improvement". The two are different quantities in different units.

The Overview Metrics tab scores CMI in MW (`50, =75; 100, ≥150`), which fits formula 1 and
not formula 2. This needs one decision before Component 7 can be built.

**Open question for the team: which formula is the Capacity Margin Deficit Reduction, and is
the old percentage formula retired or kept as a second metric?**

## 4. Redacted text

The `@` placeholders across all tabs are the open engineering decisions. Per direction on
2026-08-05, ignore them for this week. The three ⏳ Global tabs are almost entirely `@`.

## 5. Library direction from the team

Received 2026-08-02.

- Core required: pandas, NumPy
- Required: Pydantic, pytest, pathlib, logging, typing, dataclass, psycopg, Typer
- Optional: Rich, Matplotlib, Plotly, mypy, Ruff
- Suggestion: use `dataclass` to group the variables that track system and world state

Current repository state against that list:

| Library | Status |
|---|---|
| pandas, NumPy | Not a dependency. `pyproject.toml` declares `dependencies = []`. |
| Pydantic | In use, `src/owr/api/schemas.py`. Not used outside the API layer. |
| pytest, Ruff | In use, dev group. |
| pathlib, logging, typing, dataclass | Standard library. `dataclass` is already the pattern in 10 modules, including `models.py` and `config.py`. |
| psycopg | In use, `src/owr/api/pg_store.py`, optional extra. |
| Typer | Not used. Both CLIs use `argparse`. |
| Rich, Matplotlib, Plotly, mypy | Not used. |

### The conflict to settle before any pandas work starts

the repo map states: "Engine core stays pure. No I/O, no DB imports below the CLI and API
layers." `pyproject.toml` states the engine is "intentionally pure-Python with no
third-party runtime deps so it stays fully testable offline". A pandas rewrite of the engine
core contradicts both.

A split that keeps both commitments:

| Layer | Files | pandas fit |
|---|---|---|
| ETL | `etl/daily.py`, `etl/transform.py`, `etl/rows_csv.py`, `etl/extract.py` | Strong. These are table operations on CSV rows, and `extract.py` already receives a pandas `DataFrame` from `gridstatus` and immediately converts it away. |
| Scenario input | `scenario_input.py` | Strong. It is a CSV reader with per-column validation. |
| Engine core | `stress_finder.py`, `budget.py`, `dispatch.py`, `soc_engine.py`, `metrics.py`, `simulator.py` | Weak. These are scalar and per-hour operations on dataclasses. pandas adds a dependency and removes type safety without removing code. |
| Percentile | `stress_finder.py` lines 16 to 17 | Direct. The module hand-rolls linear interpolation to match NumPy's default without depending on NumPy. Adding NumPy deletes that code. |

Recommendation: adopt pandas and NumPy in the ETL and scenario-input layers, and at the
`stress_finder` percentile. Keep the per-hour engine on dataclasses. Take that split to the
team rather than assuming it.
