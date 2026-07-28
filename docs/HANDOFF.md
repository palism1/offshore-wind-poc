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

1. **Round-trip efficiency default.** `config.py` ships 1.0; Report B computed everything at
   0.85. At 1.0 the engine understates required charging energy by 17.6%. Recommend 0.85.
   The storage pivot upgrades this — efficiency is now the axis the candidate technologies
   differ on (StEnSea 0.80, LAES 0.50–0.70, thermal ~0.35), so it should become a
   first-class scenario input.
2. **One canonical stress-event definition.** Three artifacts use three different thresholds
   and merge rules on the same January 2025 activity. Recommend Report B's rule (12+ hours
   above threshold = stress day, 2+ consecutive = event). Blocks `stress_finder`.
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

**Assumptions that may be wrong:**

- The `STORAGE_SITING_TRADEOFF.md` calculation takes LAES round-trip efficiency of 0.50–0.70
  from Mitchell's Discord post. Not checked against a primary source. Do that before it
  drives a decision.
- Seasonal denominators (561,878 MWh summer / 434,214 MWh winter) remain underivable from
  available artifacts. Do not hard-code; derive during ETL and store in `features.constants`
  with the query.
- The ~200 m depth claimed off Provincetown does not match published bathymetry. Needs a
  depth-vs-distance curve from the USGS Massachusetts Bay model before that site anchors
  anything. Mitchell said on 2026-07-28 that he has adjustment specs for a shallower StEnSea
  system and will send them. He was asked for depth and round-trip efficiency together,
  since those are the two fields a siting scenario needs. Not yet received, and his estimate
  is not a primary source — it still needs checking against published bathymetry under
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
