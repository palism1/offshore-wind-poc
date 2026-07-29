# HANDOFF — Offshore Wind Reserve Scenario Tool
Updated: 2026-07-28

Read this first when resuming in a fresh session.

## Where things stand

Phases 0–4 and CI are complete and tested. The engine, the FastAPI layer, the Postgres
repository, the ETL extract skeleton, and the simulator CLI all work; nothing in the code
is half-finished. This session built the **simulator CLI**: a terminal entry point
(`simulate`, also runnable as `python -m owr`) that reads a day-profile CSV and drives the
engine loop end to end. It is the demoable v1.0 the team decided on 2026-07-23.

## What this project is

A proof-of-concept scenario tool for the **Software & Infrastructure Lead** role. Question
under test: can long-duration storage charged from offshore wind reduce the severity of
multi-day winter grid stress events on NEMA/Boston, versus sending wind straight to the
grid. Data science and forecast modeling belong to a separate Data & Modeling Lead.

Framing as of 2026-07-27 is **winter fuel adequacy**, not load-forecast uncertainty. The
ISO-NE 21-day page we cite is a generator fuel-supply report and supports the former only.

## What works, verified

This session opened at commit `7c18531` with 66 passed, 3 skipped. The simulator CLI added
86 tests. Verified at `17bdb9c`, the current tip of `main`:

| Check | Command | Result |
|---|---|---|
| Test suite | `uv run pytest` | **152 passed, 3 skipped** (skips are Docker-gated Postgres tests) |
| Lint | `uv run ruff check .` | **All checks passed** |
| Working tree | `git status --short` | clean |
| Remote sync | `git log origin/main..HEAD` | 0 unpushed |
| Branches | `git branch -a` | `main` only, local and remote |

| Phase | Scope | State |
|---|---|---|
| 0 | Repo scaffold (uv, Python 3.12, ruff, pytest, docker-compose) | Done |
| 1 | PostgreSQL 16 + TimescaleDB schema, 3 migrations | Written, **never run against a live DB** |
| 2 | ETL extract via `gridstatus` → `raw.*`, provenance, CLI | Skeleton done, **fixture-tested only** |
| 3 | Simulation engine (MPC rolling-window dispatch) | Done, tested |
| 3.5 | Simulator CLI (`simulate` / `python -m owr`), reads a day-profile CSV and drives the engine loop end to end | Done, tested — MVP v1.0 |
| 4 | FastAPI backend, in-memory + Postgres repositories | Done, tested (in-memory path) |
| 5 | Frontend | Deferred post-v1.0 by team decision |
| 6 | CI (GitHub Actions: ruff + pytest) | Done, running |

## History rewrite — read before touching git

On 2026-07-28 the entire history was rewritten with `git filter-repo` and force-pushed.
Every commit SHA changed. Consequences:

- **Any clone or fork made before 2026-07-28 has diverged.** Re-clone; do not merge.
- The three merged PRs (#1, #2, #3) still read as merged but their commit links are dead.
- The three merged branches (`reserve-default-split`, `worktree-ci-workflow`,
  `worktree-postgres-repo`) were deleted from the remote. Only `main` exists.
- A pre-rewrite backup lives at `offshore-wind-poc-BACKUP-20260728-112028.bundle` in the
  repo root. It is gitignored and **must never be committed** — it contains the history
  that was removed. The rewrite is verified on the remote, so the bundle is safe to delete.
- `.gitignore` no longer lists local tooling directories. Those moved to
  `~/.config/git/ignore` (`core.excludesFile`).

## What is in flight

**Nothing.** The working tree is clean, everything is on `origin/main`, and `main` is the
only branch — local and remote. Verified this session: **152 passed, 3 skipped**, ruff clean.

The simulator CLI landed in three commits: `160eebb` (the CLI), `ad14298` (NEMA series
provenance), `17bdb9c` (canonical ISO Express URL). The Discord project update was posted.

## Next step

**Phase 2 ETL, now unblocked.** Point the extract at the public ISO Express CSV endpoint —
`/transform/csv/whlsecost/hourly?month=YYYYMM&locationId=4008` — and run it for real. The
credential wait that blocked this phase does not apply to this dataset; see open question 8
below and `docs/DATA_SOURCES.md` [3]. This is the only substantial work not waiting on
someone else.

Two things to settle while doing it, both recorded in `DATA_SOURCES.md` [3]: the file count
is 24 where five months across five years would be 25, and the 17,395-hour total agrees with
24 files only to within daylight-saving adjustments. Neither is alarming; both should be
resolved before the series anchors a published number.

After that, the CLI's CSV reader and the ETL output need to meet. The reader's day-profile
format is provisional and nothing in the schema matches it yet, so either the ETL grows a
CSV export in that shape or the reader learns the ETL's shape. That is a design call, not a
mechanical one.

Notes for whoever picks it up:
- `src/owr/etl/cli.py` is the **ETL** CLI. The simulator CLI (`src/owr/cli.py`) is separate.
- `docs/PLAN_SIMULATOR_CLI.md` is the plan this was built against, including the CSV format,
  the argument surface, and the four open team questions the CLI surfaces as flags with
  labeled defaults rather than resolving.
- The CSV day-profile format the CLI reads is provisional — no ETL export matches it yet
  (see `src/owr/scenario_input.py` module docstring).

Remaining checklist from `docs/PROJECT_STATE_2026-07-28.md`, in order:
1. ~~Data-provenance question~~ — answered by Alexander 2026-07-28; see open question 8.
2. ~~Correct the sphere count~~ — done, commit `08ef67a`.
3. Tier 3 decisions — raised with recommendations, blocked on the team.
4. ~~Efficiency-vs-transmission-distance calculation~~ — done, commit `1e4a241`.
5. ~~Simulator CLI~~ — done, commit `160eebb`.
6. Metric formulas into `metrics.py` — blocked on the formulas and thresholds.
7. **Phase 2 ETL against the public endpoint** — unblocked 2026-07-28, next.

## Open questions and decisions not yet made

**Blocked on the team, each blocks code.** Mitchell volunteered on 2026-07-28 to take 1–3
and raised the impact-target question himself, which is the threshold half of 7. Nothing is
decided yet; these move from "unowned" to "with Mitchell", no further.

1. ~~**Round-trip efficiency default.**~~ **RESOLVED 2026-07-28 by Mitchell: 0.70.** See the
   third-reply block below. `config.py` still ships 1.0 — flipping the default to 0.70 is a
   pending one-line code change. The 0.85 that had been recommended here was never a StEnSea
   figure: it is Report B Finding 2.2's assumption (`NE_Stage1_Stage2_Findings.pdf`), which
   computed every charging gap at 85% round-trip. Mitchell is right that no StEnSea prototype
   claims above 0.80. Efficiency still becomes a first-class scenario input — it is the axis
   the candidate technologies differ on (StEnSea 0.70–0.80, LAES 0.50–0.70, thermal ~0.35).
2. ~~**One canonical stress-event definition.**~~ **RESOLVED 2026-07-28 by Mitchell.** A stress
   event is a run of **2+ consecutive days** (minimum stress window is a user parameter) whose
   **daily total demand** sits above the **historical 90th-percentile** threshold. There is no
   hours-above-an-hourly-threshold criterion in event identification. Report B's "12+ hours
   above threshold = stress day" rule is **retired**. Details and the code delta below.
3. **Is charged wind priced at opportunity cost?** Report A found zero hours of negative net
   load, so no free wind exists. Recommend yes. Largest correctness gap in the model.
4. **Reserve usage rules** — when the 10% strategic reserve and the 20% floor may each be
   drawn. Open since 2026-07-18. Engine currently treats the sum as one protected floor.
5. **Cycle count per year.** Identified 2026-07-28 as the variable the storage siting
   trade-off turns on, and completely unspecified. At ~10 cycles/yr capex dominates; at
   ~200 the efficiency case returns. Should become a scenario input.

   Mitchell read this on 2026-07-28 as the lifecycle payback question — whether the capex
   amortizes against fuel saved. That is one of the two things the number decides. The other
   is the siting trade-off, where the same figure decides whether the near-shore efficiency
   argument holds. Both halves need the answer; whoever supplies it should know it is
   answering two questions.
6. **Does "Scenario Robustness Score" replace "Decision Confidence"?** Unconfirmed.
7. **Who owns the capex/payback formula?** Offered to the channel 2026-07-23, unclaimed.
   Thresholds assigned to Alexander, still undefined. Mitchell raised the impact-target
   question unprompted on 2026-07-28 and was offered the thresholds; unconfirmed.

   Any payback on fuel savings needs a price, and the engine carries no prices at all. This
   makes 7 downstream of 3 — until charged wind is priced or explicitly not priced, a fuel
   saving cannot be computed as net.

**Answered, 2026-07-28:**

8. ~~**Where did the 17,395 hours of NEMA load/wind/LMP data come from?**~~ Alexander answered:
   the public ISO Express portal, no credentials and no API key. Files are
   `whlsecost_hourly_4008_YYYYMM.csv` (location 4008 = NEMA/Boston), 24 monthly CSVs covering
   January/February/March/June/July across 2022–2026. Full record in `docs/DATA_SOURCES.md` [3].
   **Phase 2 ETL is unblocked** — point the extract at the public CSV endpoint. Two loose ends
   noted there: the file count is 24 where five months across five years would be 25, and the
   hour count agrees with 24 files only to within daylight-saving adjustments.

**Clarifications received, 2026-07-28 (Mitchell's second reply):**

These correct standing assumptions in `PROJECT_STATE_2026-07-28.md` and
`FINDINGS_REVIEW_2026-07-24.md`. Recorded here as the living register; the source docs
carry dated pointers back to this block rather than being rewritten.

- **Scope is all of New England (ISO-NE system), not NEMA/Boston 4008.** This reverses the
  Tier 2 "Scope is NEMA" ratification and the I-1 recommendation to reissue at NEMA scale.
  Mitchell's reason is data availability — the offshore-wind and regional picture does not
  hold together on a single load zone — while noting the storage itself only really benefits
  eastern Massachusetts. Consequences, none yet actioned:
  - The I-1 "5× oversize" is no longer an error to correct but the intended scale. The
    system-wide reserve target is Report A Finding 6's **~40,000–60,000 MWh**, i.e. roughly
    **2,000–3,000 full-scale (20 MWh) spheres**, not the NEMA 420–630. NEMA becomes the
    "where it lands" sub-region, not the sizing basis.
  - The 17,395-hour series is `locationId=4008` (NEMA). A New England study needs
    `locationId=4000` (system-wide) from the **same public ISO Express endpoint**
    (`DATA_SOURCES.md` [3]) — a re-pull, not a new data source or new credentials. The
    stress-event set, the $443/MWh pricing, and the seasonal wind ratio all need recomputing
    at 4000 before they anchor a system-scale claim.
- **The shallow StEnSea unit is a deliberately theoretical variant, not a claim about a
  built product.** Mitchell proposed it knowing no shallow-water sphere exists; the physics
  is sound and the task is to *set* an achievable efficiency, not to find a demonstrated one.
  This retires the Tier 5 "not a demonstrated variant" objection as a blocker. Guidance for
  the scenario input: round-trip efficiency is set by the pump-turbine and motor-generator,
  not by the head, so the shallow variant keeps Fraunhofer's **0.75–0.80** band; recommend
  **0.75** as the conservative default. What the shallower head costs is *energy per sphere*,
  which scales ~linearly with depth: a 20 MWh unit at ~700 m becomes ~5.7 MWh at ~200 m
  (≈200/700), consistent with the 5.7–6.7 MWh/unit already used in `PROJECT_STATE` Tier 5.
- **The "200 m off Provincetown" line was a landmark reference, not a claim of 200 m water
  200 m from shore.** Provincetown is the nearest named place to a Gulf of Maine location a
  bathymetry map showed at ≥200 m. This is consistent with published bathymetry: the Gulf of
  Maine's deep basins all exceed 250 m (Wilkinson ~275 m, Jordan ~275 m, Georges 379 m, the
  deepest), but they sit tens of miles offshore, separated by central highs of 90–150 m; the
  nearest 200 m+ feature to Provincetown is **Wilkinson Basin**, roughly 50+ nmi to the
  NE/E, while Stellwagen Basin immediately north of the Cape is only ~80–100 m. So the depth
  exists and the landmark is roughly right; what still needs pinning is the **depth-vs-
  distance curve** for a specific candidate point, because even Wilkinson's ~275 m is well
  short of StEnSea's native 600–800 m — which is exactly why the shallow variant is needed.
  Bathymetry map sources added to `DATA_SOURCES.md` so the team shares one reference.
- **Opportunity-cost charging (decision 3 / I-4) — charging model now specified by Mitchell.**
  New England has no excess wind capacity, so net load is never negative and there is never
  surplus/curtailed wind to charge from for free. Report A's "zero hours of negative net load"
  is therefore expected, not a puzzle. The charging model Mitchell specified on 2026-07-28:
  1. **Charge storage from wind, timed to the highest-wind-speed hours** in the pre-event
     window (turbine output rises steeply with wind speed, so this captures the most energy
     for the least backfill). This is what the engine's `priority_wind_weight` (0.3 in the
     `Priority = 0.7·Demand + 0.3·WindForecast` term, `config.py`) already biases toward.
  2. **Backfill the load that the diverted wind was serving with LNG, pre-event, while gas is
     still unconstrained.** Physically: wind → storage, LNG → load. Economically this is the
     opportunity cost I-4 flagged, and it is now named — the marginal generator at charge time
     is LNG, so charging is priced at the pre-event LNG cost, not zero.
  3. **Discharge storage during the reliability event, when gas is constrained** (the fuel-
     adequacy thesis). The value credited is event-time: displacing constrained/expensive
     generation, e.g. the $443/MWh Event 17 price.
  So decision 3 resolves **yes, charged wind carries an opportunity cost**, and the mechanism
  is temporal arbitrage of *gas availability* — burn LNG when unconstrained, discharge stored
  wind when it is not. This gives the **Fuel-Fired Generation Offset** metric its meaning:
  add fuel-fired MWh pre-event, offset (more expensive, constrained) fuel-fired MWh during
  the event; the net is what the asset is worth. This is Mitchell's feedback on the report,
  not an open question routed to Alexander — the modeling default is settled. What is still
  needed is the *prices* (pre-event LNG cost and event-time value), and those come straight
  from the load-cost data now being pulled: the `whlsecost-hourly-system` report Alexander is
  sourcing carries the wholesale/LMP series. So this is a data-wiring task into `dispatch.py`
  / `metrics.py`, not a decision anyone still owes (keeps 7 downstream of 3 as data, not as a
  pending call).

- **Alexander's actual 2026-07-28 input is the data-source spec, not the charging model.**
  He confirmed the New England scope independently ("We are using the entire NE and not
  NEMA/Boston") and gave the exact pull: `whlsecost` at `locationId=4000`, file pattern
  `whlsecost_hourly_4000_YYYYMM.csv`, months Jan/Feb/Mar/Jun/Jul, years 2022–2026 — the
  system-wide re-pull already anticipated, now specified. For wind he used **ISO-NE Daily
  Generation by Fuel Type** (`daily-gen-fuel-type`), not EIA, and flagged he does not know if
  it matches EIA. Two flags recorded in `DATA_SOURCES.md` open decision 2: that report is
  **daily** while charging needs hourly wind, and the ISO-NE-vs-EIA values are unreconciled.
  Full spec table in `DATA_SOURCES.md` [3].

**Clarifications received, 2026-07-28 (Mitchell's third reply):**

- **Sphere spec, interpolated from the other prototypes.** Mitchell supplied: power
  **1.67 MW** (33.33% of 5 MW), energy **20 MWh**, outer diameter **30 m**, efficiency
  **0.70**, hydraulic head **200 m**, flow rate **~1.02 m³/s**. Checked against
  `P = ρ·g·Q·h·η` (ρ=1025, g=9.81) — **three of the six numbers cannot hold at once.** Two
  independent inconsistencies:
  1. *Power vs. flow vs. efficiency.* At Q=1.02 m³/s, h=200 m, η=0.70 the formula gives
     **1.436 MW**, not 1.67. The 1.67 MW figure implies **η≈0.814**, which is the full-scale
     machine's efficiency, not the 0.70 being adopted — 1.02 m³/s is exactly the flow of a
     5 MW / 600 m / η≈0.81 machine, so it was carried over unchanged while power was scaled
     by the head ratio and efficiency was separately revised. Pick one:
     **1.67 MW → Q = 1.186 m³/s**, or **Q = 1.02 m³/s → 1.44 MW**. Recommend holding
     1.67 MW (the 5 MW × 200/600 scaling is the deliberate choice) and restating Q as
     **~1.19 m³/s**.
  2. *Energy vs. geometry.* 20 MWh at h=200 m, η=0.70 requires a working volume of
     **~51,100 m³** — a sphere of **~46 m** outer diameter. A 30 m sphere holds 14,137 m³
     gross (~11,500–12,100 m³ internal at a 0.75–1.0 m wall), which at 200 m and 0.70 yields
     **4.5–5.5 MWh**. The 20 MWh figure is the *full-depth* rating: the same 30 m sphere at
     600–800 m and η=0.80 gives 15–21 MWh, which is where Fraunhofer's 20 MWh comes from.
     Energy scales ~linearly with head, so keeping 30 m and 200 m forces **~5 MWh/sphere**,
     consistent with the 5.7–6.7 MWh/unit already in `PROJECT_STATE` Tier 5.
  This is not a rounding quarrel — it changes the asset's duration from **12 h**
  (20 MWh ÷ 1.67 MW) to **~3 h** (5 MWh ÷ 1.67 MW), and a 3-hour asset behaves very
  differently against a multi-day stress event than a 12-hour one. Resolve by choosing which
  two of {diameter, head, energy} are fixed and letting the third follow. Until Mitchell
  picks, the modeling default is 30 m + 200 m + ~5 MWh, and the **sphere count for a
  40,000–60,000 MWh system reserve rises from ~2,000–3,000 to ~8,000–12,000.**
- **Charge-rate formula confirmed:** `Power = ρ_seawater · g · Q · h · η`, or with everything
  else held constant `5 MW × (200/600)`. Adopted. One note for `dispatch.py`: that is the
  *generating* (discharge) form. Pumping is `P_pump = ρ·g·Q·h / η_pump`, so charge and
  discharge power are not the same number at the same flow. If 0.70 is the **round-trip**
  figure, the conventional split is √0.70 ≈ 0.837 each way; if it is the one-way turbine
  figure, round-trip is ~0.49. Which one 0.70 is needs saying before it lands in `config.py`.
- **"Report A" and "Report B"** are shorthand from `FINDINGS_REVIEW_2026-07-24.md`:
  Report A = `NE_Wind_Reserve_Findings_v2.pdf`, Report B = `NE_Stage1_Stage2_Findings.pdf`.
  The labels exist only because the two disagree with each other; they are not team documents.
- **Stress-event definition (decision 2) — resolved.** Event identification uses **daily
  total demand** against the **historical 90th percentile**, with a run of **2+ consecutive**
  such days (minimum window user-configurable) forming an event. Hourly counting plays no part
  in identification. The **implemented `stress_finder` already matches this exactly** — it
  thresholds daily energy against a percentile of the series and requires
  `min_stress_window_days` consecutive days. The only code delta is
  **`default_severity_percentile: 0.95 → 0.90`** in `config.py`, plus removing the "competing
  12-hour rule" language from that docstring and from decision 2. The 3-artifact
  disagreement is closed.
  - **New, separate step:** once events are identified, each day in the window gets a **peak
    load defined as a 3-hour period**. Nothing in the codebase does this yet — no 3-hour
    windowing exists in `stress_finder.py` or `metrics.py`. Two things still need saying:
    whether the 3-hour window is the maximum-load rolling 3 hours per day (assumed) and
    whether it drives dispatch or only reporting.
  - Open detail worth confirming: the 90th percentile is taken over **daily totals across the
    historical winter record** (all Dec–Feb days in the five-year set), not over hourly values
    and not per-winter. That is the reading being implemented.
- **MVP v1.0 data scope: five winters, 2021/22 through 2025/26, December 1 – February 28/29.**
  Summer is deferred past v1.0.
  - **Season definitions are now fixed:** **winter = Dec 1 – Feb 28/29**, **summer =
    Jun 1 – Sep 30**. March falls in neither and is a shoulder month — usable as data, but it
    belongs to no study window and must not be pooled into a seasonal denominator. This
    matters for the two seasonal denominators (561,878 MWh summer / 434,214 MWh winter) that
    `PLAN.md` says to derive during ETL: they now have month boundaries to derive against.
  - **This does not match Alexander's pull.** His spec is months Jan/Feb/Mar/Jun/Jul across
    2022–2026, which covers all five Jan/Feb pairs but **contains no December at all**. Five
    files are missing: `whlsecost_hourly_4000_202112.csv`, `...202212`, `...202312`,
    `...202412`, `...202512`. Same endpoint, same locationId — a five-file top-up, not a
    re-pull. Without them every winter in the study is missing its first month, and December
    carries real cold-snap events.
  - **Summer is short by two months per year, whenever it is picked up.** Jun 1 – Sep 30 needs
    August and September; Alexander has Jun/Jul only. Ten more files (`...YYYY08`, `...YYYY09`
    across 2022–2026). Not blocking — summer is post-v1.0 — but the current Jun/Jul files are
    half a season, not a season, and should not be described as summer coverage.
- **Hourly wind source: EIA `electricity/rto/fuel-type-data`** (EIA-930 hourly generation by
  fuel type; ISO-NE respondent, `WND` fuel type). This **resolves the daily-vs-hourly flag**
  raised against Alexander's ISO-NE `daily-gen-fuel-type` choice — charging needs hourly wind
  and this series provides it. Two practical notes: the EIA v2 API **requires a free API key**
  (verified — an unkeyed request returns `API_KEY_MISSING`), unlike the ISO Express CSV
  endpoint which needs none, so this is the project's first credentialed source; and the
  ISO-NE-vs-EIA reconciliation Alexander flagged is now directly testable, since both report
  the same ISO-NE wind fleet. Recorded in `DATA_SOURCES.md`.
- **Transmission.** Mitchell agrees tens of miles for a single hub is a materially smaller
  problem than 160–215 miles per individual wind farm, but transmission loss and cost still
  have to be modeled for any wind routed to the hub — the shorter distance reduces the term,
  it does not remove it. Depth-vs-distance curve agreed as needed (see the bathymetry bullet
  above); it is now wanted for the transmission case as well as the siting case.

**Assumptions that may be wrong:**

- The `STORAGE_SITING_TRADEOFF.md` calculation takes LAES round-trip efficiency of 0.50–0.70
  from Mitchell's Discord post. Not checked against a primary source. Do that before it
  drives a decision.
- Seasonal denominators (561,878 MWh summer / 434,214 MWh winter) remain underivable from
  available artifacts. Do not hard-code; derive during ETL and store in `features.constants`
  with the query. **Mitchell's 2026-07-28 season definitions (winter Dec 1 – Feb 28/29,
  summer Jun 1 – Sep 30) give the derivation its month boundaries** — the seasonal peak day
  is now selected from a defined candidate set instead of an assumed one. Per
  `FACT_CHECK_REPORT.md` these are **peak-day** total energies, not season totals:
  434,214 MWh ÷ 24 h = 18.1 GW and 561,878 ÷ 24 = 23.4 GW average across the day. Those are
  **ISO-NE system scale** (system winter peak ~19–20 GW, summer record ~28.1 GW), not NEMA
  (~3.8–4.0 GW). So they are consistent with the scope reversal to system-wide — one of the
  few figures that did not need rescaling. Still derive rather than hard-code.
- The shallow-StEnSea depth and efficiency Mitchell will send are a design estimate, not a
  primary source. The efficiency band above is defensible from Fraunhofer's full-scale figure
  but the specific candidate depth still needs checking against published bathymetry under
  convention #3.

## How to run it

```bash
cd ~/Desktop/offshore-wind-poc
uv sync --group dev                                    # .venv, Python 3.12 + dev tools
uv run pytest                                          # 152 passed, 3 skipped
uv run ruff check .                                    # All checks passed
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000                  # simulator CLI end to end
uv run --with uvicorn uvicorn owr.api.app:app --reload # API; OpenAPI docs at /docs
docker compose up -d db                                # Postgres 16 + TimescaleDB
uv run python -m owr.etl --help                        # ETL CLI (extract | transform | validate)
```

The API and engine run with **no database and no credentials** — the API uses an in-memory
store behind `owr.api.store.Repository`. Setting `OWR_DATABASE_URL` switches it to the
Postgres-backed store at runtime.

## Where everything is

| Thing | Location |
|---|---|
| Repo | `~/Desktop/offshore-wind-poc/` |
| GitHub | https://github.com/palism1/offshore-wind-poc (origin/main) |
| Phased plan | `docs/PLAN.md` |
| Simulator CLI implementation plan | `docs/PLAN_SIMULATOR_CLI.md` |
| Project state, ordered by stability | `docs/PROJECT_STATE_2026-07-28.md` |
| Storage siting trade-off calculation | `docs/STORAGE_SITING_TRADEOFF.md` |
| Findings review vs. the analysis reports | `docs/FINDINGS_REVIEW_2026-07-24.md` |
| Primary-source verification | `docs/FACT_CHECK_REPORT.md` |
| Data source registry | `docs/DATA_SOURCES.md` |
| Job board snapshot | `docs/BOARD.md` |
| Engine / API / ETL / simulator CLI | `src/owr/`, `src/owr/api/`, `src/owr/etl/`, `src/owr/cli.py` |
| Schema | `db/migrations/` |
| Resume log (LOCAL ONLY, gitignored) | `RESUME_LOG.md` |

## Repo conventions

1. `RESUME_LOG.md` is local-only and gitignored. Never commit it.
2. **No authoring metadata reaches the remote.** No co-author trailers, generator footers,
   tool names, or assistant-tooling paths in commits, PR bodies, issues, or tracked files.
   The 2026-07-28 rewrite existed to remove exactly that.
3. Verify before publishing. Every regulatory citation, grid statistic, formula and design
   constant needs a verdict — Verified, Contradicted, or Unverifiable — against a primary
   source before it reaches a slide, schema, plan, or code. Primary sources only: ISO-NE Web
   Services, EIA API v2, ferc.gov, BOEM, DOE/NREL/PNNL, Fraunhofer.
4. Surface disagreements between documents as a team decision; do not silently pick a side.
5. Design constants are labeled config values in `src/owr/config.py`, never magic numbers.
   Each docstring names the open team question it maps to.
