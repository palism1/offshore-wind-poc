# HANDOFF — Offshore Wind Reserve Scenario Tool
Updated: 2026-07-28

Read this first when resuming in a fresh session.

## Where things stand

Phases 0–4 and CI are complete and tested. The engine, the FastAPI layer, the Postgres
repository, and the ETL extract skeleton all work; nothing in the code is half-finished.
The last session did no engine work — it rewrote the git history to remove authoring
metadata, then produced three analysis documents assessing the project against the team's
2026-07-27 storage pivot. The next unit of work is the **simulator CLI**, which does not
exist yet and is the critical path to a demoable v1.0.

## What this project is

A proof-of-concept scenario tool for the **Software & Infrastructure Lead** role. Question
under test: can long-duration storage charged from offshore wind reduce the severity of
multi-day winter grid stress events on NEMA/Boston, versus sending wind straight to the
grid. Data science and forecast modeling belong to a separate Data & Modeling Lead.

Framing as of 2026-07-27 is **winter fuel adequacy**, not load-forecast uncertainty. The
ISO-NE 21-day page we cite is a generator fuel-supply report and supports the former only.

## What works, verified

Run this session at commit `7c18531`:

| Check | Command | Result |
|---|---|---|
| Test suite | `uv run pytest` | **66 passed, 3 skipped** (skips are Docker-gated Postgres tests) |
| Lint | `uv run ruff check .` | **All checks passed** |
| Working tree | `git status --short` | clean |
| Remote sync | `git log origin/main..HEAD` | 0 unpushed |

| Phase | Scope | State |
|---|---|---|
| 0 | Repo scaffold (uv, Python 3.12, ruff, pytest, docker-compose) | Done |
| 1 | PostgreSQL 16 + TimescaleDB schema, 3 migrations | Written, **never run against a live DB** |
| 2 | ETL extract via `gridstatus` → `raw.*`, provenance, CLI | Skeleton done, **fixture-tested only** |
| 3 | Simulation engine (MPC rolling-window dispatch) | Done, tested |
| 4 | FastAPI backend, in-memory + Postgres repositories | Done, tested (in-memory path) |
| 5 | Frontend | Deferred post-v1.0 by team decision; CLI is MVP v1.0 |
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

**Nothing in code.** The working tree is clean and everything is pushed.

**Not yet posted:** a Discord project update drafted at
`2026-07-28_project_update.md` (repo root, gitignored) plus a short message body for the
channel. Mikko posts it; it corrects a teammate's number so it should go out under his name.

**Not yet started:** the simulator CLI. No branch, no files.

## Next step

Build the **simulator CLI** — a terminal entry point that runs a scenario end to end over
the existing engine and prints results. This is MVP v1.0 per the team's 2026-07-23 decision
(CLI first, UI at v1.1+).

Notes for whoever picks it up:
- `src/owr/etl/cli.py` exists and is the **ETL** CLI. The simulator CLI is separate.
- The engine loop it must drive is `stress_finder → initial_soc → [budget → dispatch →
  soc_engine] → metrics`, orchestrated by `src/owr/simulator.py`.
- The FastAPI routes in `src/owr/api/app.py` already sequence this correctly; read them
  before designing the CLI so the two stay consistent.
- This is code work, so it goes through the plan gate first per the SWE pipeline.

Remaining checklist from `docs/PROJECT_STATE_2026-07-28.md`, in order:
1. ~~Data-provenance question~~ — raised in the Discord draft, awaiting a reply.
2. ~~Correct the sphere count~~ — done, commit `08ef67a`.
3. Tier 3 decisions — raised with recommendations, blocked on the team.
4. ~~Efficiency-vs-transmission-distance calculation~~ — done, commit `1e4a241`.
5. **Simulator CLI** — next.
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
uv run pytest                                          # 66 passed, 3 skipped
uv run ruff check .                                    # All checks passed
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
| Project state, ordered by stability | `docs/PROJECT_STATE_2026-07-28.md` |
| Storage siting trade-off calculation | `docs/STORAGE_SITING_TRADEOFF.md` |
| Findings review vs. the analysis reports | `docs/FINDINGS_REVIEW_2026-07-24.md` |
| Primary-source verification | `docs/FACT_CHECK_REPORT.md` |
| Data source registry | `docs/DATA_SOURCES.md` |
| Job board snapshot | `docs/BOARD.md` |
| Engine / API / ETL | `src/owr/`, `src/owr/api/`, `src/owr/etl/` |
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
