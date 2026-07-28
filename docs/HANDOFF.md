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

Verified at the start of this session, commit `7c18531`: `uv run pytest` gave 66 passed, 3
skipped; `uv run ruff check .` passed; working tree clean; 0 commits unpushed.

Verified after this session's simulator CLI work, uncommitted on top of `7c18531`:

| Check | Command | Result |
|---|---|---|
| Test suite | `uv run pytest` | **151 passed, 3 skipped** (skips are Docker-gated Postgres tests) |
| Lint | `uv run ruff check .` | **All checks passed** |
| Working tree | `git status --short` | uncommitted (see "What is in flight") |

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

**Simulator CLI built, uncommitted.** The working tree carries the new `src/owr/cli.py`,
`src/owr/scenario_input.py`, `src/owr/version.py`, `src/owr/__main__.py`,
`examples/make_synthetic_winter_stress.py` + its generated CSV, the `Config` additions in
`src/owr/config.py`, the `code_version()` move out of `src/owr/api/app.py`, and their tests.
Verified: 151 passed, 3 skipped; ruff clean. Nothing is committed yet — review and commit
is the next action.

**Not yet posted:** a Discord project update drafted at
`2026-07-28_project_update.md` (repo root, gitignored) plus a short message body for the
channel. Mikko posts it; it corrects a teammate's number so it should go out under his name.

## Next step

Review and commit the simulator CLI (see "What is in flight"), then pick up the remaining
checklist below.

Notes for whoever picks it up:
- `src/owr/etl/cli.py` is the **ETL** CLI. The simulator CLI (`src/owr/cli.py`) is separate.
- `docs/PLAN_SIMULATOR_CLI.md` is the plan this was built against, including the CSV format,
  the argument surface, and the four open team questions the CLI surfaces as flags with
  labeled defaults rather than resolving.
- The CSV day-profile format the CLI reads is provisional — no ETL export matches it yet
  (see `src/owr/scenario_input.py` module docstring).

Remaining checklist from `docs/PROJECT_STATE_2026-07-28.md`, in order:
1. ~~Data-provenance question~~ — raised in the Discord draft, awaiting a reply.
2. ~~Correct the sphere count~~ — done, commit `08ef67a`.
3. Tier 3 decisions — raised with recommendations, blocked on the team.
4. ~~Efficiency-vs-transmission-distance calculation~~ — done, commit `1e4a241`.
5. ~~Simulator CLI~~ — built this session, uncommitted.
6. Metric formulas into `metrics.py` — blocked on the formulas and thresholds.

## Open questions and decisions not yet made

**Blocked on the team, each blocks code:**

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
6. **Does "Scenario Robustness Score" replace "Decision Confidence"?** Unconfirmed.
7. **Who owns the capex/payback formula?** Offered to the channel 2026-07-23, unclaimed.
   Thresholds assigned to Alexander, still undefined.

**Blocked on an answer from Alexander:**

8. **Where did the 17,395 hours of NEMA load/wind/LMP data come from?** The board says Phase 2
   ETL is blocked on ISO-NE Web Services credentials, but that data exists. If it came through
   public `gridstatus` endpoints, Phase 2 unblocks immediately. Open since 2026-07-24 and the
   cheapest unblock available.

**Assumptions that may be wrong:**

- The `STORAGE_SITING_TRADEOFF.md` calculation takes LAES round-trip efficiency of 0.50–0.70
  from Mitchell's Discord post. Not checked against a primary source. Do that before it
  drives a decision.
- Seasonal denominators (561,878 MWh summer / 434,214 MWh winter) remain underivable from
  available artifacts. Do not hard-code; derive during ETL and store in `features.constants`
  with the query.
- The ~200 m depth claimed off Provincetown does not match published bathymetry. Needs a
  depth-vs-distance curve from the USGS Massachusetts Bay model before that site anchors
  anything.

## How to run it

```bash
cd ~/Desktop/offshore-wind-poc
uv sync --group dev                                    # .venv, Python 3.12 + dev tools
uv run pytest                                          # 151 passed, 3 skipped
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
