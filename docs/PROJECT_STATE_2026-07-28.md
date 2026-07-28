# Project State — 2026-07-28

Ordered from what will not change to what is moving fastest. Read top-down to know
what is safe to build on; read bottom-up to know what to argue about this week.

Inputs: the repo at `main`, `docs/FINDINGS_REVIEW_2026-07-24.md`, `docs/FACT_CHECK_REPORT.md`,
and the Discord sync through 2026-07-27 (metric revision, storage pivot).

---

## Tier 1 — Settled. Build on these without hedging.

**The software foundation is technology-agnostic and complete through Phase 4.**

| Phase | State |
|---|---|
| 0 Repo scaffold (uv, Python 3.12, ruff, pytest, docker-compose) | Done |
| 1 PostgreSQL 16 + TimescaleDB schema, 3 migrations | Done, not yet run live |
| 2 ETL extract skeleton (`gridstatus` → `raw.*`, provenance, CLI) | Skeleton done, fixture-tested |
| 3 Simulation engine (MPC rolling-window dispatch) | Done, tested |
| 4 FastAPI backend + in-memory and Postgres repositories | Done, tested |
| 6 CI (GitHub Actions: ruff + pytest) | Done |

`66 passed, 3 skipped`, ruff clean.

**Storage is modeled as a generic long-duration asset** — power MW, energy MWh,
round-trip efficiency, `soc_floor`, `strategic_reserve`. This is the decision that
matters most right now. The storage pivot in Tier 5 changes numbers the engine reads
from config; it does not fork a line of engine code. StEnSea, LAES, sand-battery
hybrid, or a mixed portfolio all run through the same `stress_finder → initial_soc →
budget → dispatch → soc_engine → metrics` loop. The pivot is a parameter and copy
problem, not a rewrite.

**Provenance as a product feature.** Every `raw.*` row carries source, retrieved_at,
source_query, dataset_version; every run is stamped with the engine git SHA. Independent
of which storage technology wins.

**Externally verified, primary-sourced** (see `FACT_CHECK_REPORT.md`): FERC Order 2023 /
2023-A scope and lineage; the ISO-NE transitional cluster study (26 requests, 21 storage,
~8 GW, completing August 2026); ISO-NE's storage-specific compliance path; transmission
permitting at 8+ years against 2–3 year data center builds; ISO-NE record peaks
(28,130 MW summer 2006, 22,818 MW winter 2004); subsea pumped hydro as a real technology
category.

**Winter wind exceeds summer wind in New England, every year 2022–2026.** Verified
against Report B's per-year table (575>345, 455>205, 503>281, 584>356, 725>467). The
*ratio* is disputed in Tier 3. The *direction* is not, and the direction is what the
strategic-reserve argument actually needs.

**Rolling-horizon dispatch is textbook model predictive control.** The architecture is
conventional and defensible. Name it MPC in front of a technical audience.

---

## Tier 2 — Decided. Needs paperwork, not thought.

**Reserve split: 20% floor + 10% strategic reserve = 30% protected.** Team decision
2026-07-17, encoded in `config.py`, tested, merged.

**Scope is NEMA / Boston zone 4008.** Settled de facto — the repo, both report subtitles,
and the CSV all say NEMA, and someone produced 17,395 hours of NEMA data to build the
reports. Needs a one-line ratification so it stops being re-litigated.

**Canonical wind dataset.** Also settled de facto by those same reports (NEMA 4008 hourly,
2022–2026, 2023 flagged anomalous). On the board as open; it is really just unrecorded.

**`docs/HANDOFF.md` is stale in four places** — says reserve floor 33% (it is 20+10),
says 35 tests (66), says CI not started (it is running), says Phase 2 blocked on
credentials (see below). Documentation fix only.

**Phase 2 may not be blocked at all.** The board says ETL extract is Blocked on ISO-NE
Web Services credentials, but 17,395 hours of NEMA load, wind and LMP for 2022–2026
already exist. Either credentials exist or the data came through public `gridstatus`
endpoints. Asking whoever ran the analysis is the cheapest unblock available and it has
been outstanding since 2026-07-24.

---

## Tier 3 — Open decisions with a clear recommendation. Each blocks code.

**Round-trip efficiency default: 0.85 or 1.0?** `config.py` still ships 1.0. Report B
computed every charging gap at 0.85. At 1.0 the engine understates required charging
energy by 17.6%.

This one has been upgraded by the pivot. Efficiency was a constant to pin down; it is now
the primary axis on which the storage candidates differ — StEnSea 0.80 (Fraunhofer's own
published figure), LAES + thermal 0.50–0.70, thermal-only ~0.35. Efficiency needs to
become a first-class scenario input that the comparison turns on, not a default someone
picks once.

**One canonical stress-event definition.** Three artifacts, three segmentations of the
same January 2025 activity. The dates corroborate; the counts and durations do not,
because each used a different threshold and merge rule. Report B's construction
(12+ hours above threshold = stress day, 2+ consecutive = event) is conventional.
Recommend adopting it. Blocks `stress_finder.py` and every case study.

**Is charged wind priced at opportunity cost?** Report A found zero hours of negative net
load — no curtailment, no surplus. So every MWh diverted to storage must be replaced by
another generator at that hour's price. Report B's "18 of 19 events have zero charging
gap" answers whether enough wind was physically generated, which is the weaker question.
The arbitrage case survives (charge cheap, discharge into a $443/MWh event) but it has to
be scored. This is the single largest correctness gap in the model and it is a
`dispatch.py` / `metrics.py` change.

**Reserve usage rules** — when the 10% and the 20% may each be drawn. On the board,
unresolved since 2026-07-18. Until decided the engine treats the sum as one floor, which
is a safe but conservative reading.

**2023 anomaly handling.** Both reports flag 2023 wind as anomalously low and both say
"treat with caution" without saying what that means. Recommend an explicit `exclude_years`
scenario parameter so the choice lands in run provenance instead of a footnote.

---

## Tier 4 — Changed this week. Absorbable, but the code has not caught up.

**Framing moved to fuel adequacy.** This resolves PLAN.md open question #6, which had
been blocking the executive summary. The old "load-forecasting uncertainty" framing was
never supported by the ISO-NE 21-day page we cite — that page is a generator fuel-supply
adequacy report. Fuel adequacy is the framing the citation actually supports. Mitchell
picked the defensible one.

**The metric set was revised.** MVP v1.0 is now:

| Metric | Code status |
|---|---|
| Capacity Margin Improvement | Partial — `metrics.capacity_margin` exists; the *improvement* delta vs. baseline does not |
| Stress Window Effectiveness | Partial — `metrics.severity_reduction` is close; needs renaming to the agreed formula |
| Fuel-Fired Generation Offset | Not built |
| Recharge Capacity Mismatch | Partial — `budget.recharge_sufficiency_ratio` is the same quantity inverted |
| Estimated Capital Costs | Not built; no capex formula owner assigned |
| Scenario Robustness Score (composite of the first four) | Not built |

`metrics.py` is 27 lines and covers roughly a third of the new spec. The formulas live in
a Google Doc; they need to land in the repo with unit tests quoting them, per existing
convention.

Two things to confirm rather than assume: whether **Scenario Robustness Score replaces
"Decision Confidence"** (listed in Overview v2 as tracked and "still needs to be defined"),
and who owns the **capex/payback formula** — Mitchell offered it to the channel and nobody
took it. Thresholds went to Alexander and are still undefined, which blocks any pass/fail
colouring in the eventual UI.

**Investment vs. operational scope.** PLAN.md open question #7 asked whether the tool
judges operational value or investment feasibility, since every metric was operational.
Adding Estimated Capital Costs answers it: investment is in scope. The claim and the
metric now agree.

**CLI is MVP v1.0; UI is v1.1+.** Phase 5 moves from HELD to explicitly deferred. There is
an ETL CLI (`src/owr/etl/cli.py`) but no *simulator* CLI. That is the critical path to a
demoable v1.0 and it is a small, well-scoped piece of work over a finished engine.

**DHS as a secondary user.** No code impact by Mitchell's own statement. The resource-adequacy
and regional-redundancy argument is defensible and needs no new evidence. The adversarial-deterrence
and underwater-surveillance points are labelled speculation by their own author and must not enter
a technical document or deck without a primary source.

---

## Tier 5 — Actively unstable. Do not build against these numbers.

### The siting failure is real

600–800 m depth requires roughly 35 miles offshore, which pushes wind → storage → mainland
to 155–215 miles of transmission against the 35–42 miles originally assumed. The "close to
load centers" claim is dead and Mitchell is right to drop it, along with the transmission
capacity claim. Flat seafloor area for thousands of units is a second, independent
constraint.

### Three numbers driving the pivot are wrong, and correcting them changes the conclusion

**1. `FINDINGS_REVIEW_2026-07-24.md` I-1 says the corrected NEMA reserve is "8–13 spheres."
That is wrong by a factor of about 50.** It treated Keith's "1 GWh StEnSea product" as one
sphere. Fraunhofer's published full-scale unit is **20 MWh** per 30 m sphere at 600–800 m,
efficiency 0.80. A 1 GWh product is a *park* of ~50 spheres.

Corrected: 8,400–12,600 MWh ÷ 20 MWh = **420–630 full-scale spheres**. I wrote that line;
it is the number described in that document as "the difference between implausible and a
procurement conversation," so it needs correcting before either report leaves the team.

**2. Mitchell's 6,000-unit figure inherits the ISO-NE / NEMA scale error.** It is sized
against the 40,000–60,000 MWh target, which `FINDINGS_REVIEW` I-1 already established is
full-ISO-NE, roughly 5× too large for a NEMA study. The per-unit arithmetic is sound —
40,000 ÷ 6,000 ≈ 6.7 MWh, consistent with a 20 MWh sphere at one-third depth. The target
is what is inflated.

At the corrected NEMA target of 8,400–12,600 MWh and ~5.7–6.7 MWh per reduced-depth unit:
**roughly 1,300–2,200 units**, not 6,000.

That is still a lot of concrete. It is not obviously fatal, and it is 3–4× less bad than
the number currently driving "our original idea falls apart." The pivot may still be
correct; it should be decided against the right number.

**3. "One-third depth" is not a demonstrated StEnSea variant.** Fraunhofer's 1:3 prototype
is one-third *diameter* (10 m, 0.5–1 MWh) deployed at **full depth, 500–700 m**. Nobody has
built a shallow-water sphere. Energy scales with the pressure head, so a 200 m unit is a new
engineering case, not a scaled-down version of a tested one.

### The Provincetown site claim needs verification before it anchors anything

"~200 m just off Provincetown, deepest in New England" does not match published
bathymetry. Wilkinson Basin reaches ~275 m but sits centrally in the Gulf of Maine, far
from Provincetown. Stellwagen Basin in Massachusetts Bay is closer to ~100 m. Somebody
should pull the USGS Massachusetts Bay bathymetry model and put an actual depth-vs-distance
curve behind the site before it becomes the plan.

### Sand battery comparison

Mitchell's read is right and the arithmetic holds: thermal storage returning electricity
through a steam cycle lands near 35%, so it is a heat product, not an electricity product.
LAES with thermal integration at 50–70% is the serious alternative. The comparison to make
explicit is efficiency loss against transmission loss — at what transmission distance does
StEnSea's 0.80 stop beating LAES sited closer in? That is a one-afternoon calculation and
it would settle the storage question with a number instead of a debate.

---

## What I would do next, in order

1. **Ask where the 17,395 hours of NEMA data came from.** One message. May unblock Phase 2
   today. Outstanding for four days.
2. **Correct the sphere-count error** in `FINDINGS_REVIEW` and re-run the sizing at 20 MWh
   per unit before the pivot decision is made on the wrong number.
3. **Land Tier 3 decisions 1–3** (efficiency 0.85 and promoted to a comparison axis,
   Report B's stress definition, opportunity-cost charging). Cheap to decide, everything
   waits on them.
4. **Run the efficiency-vs-transmission-distance calculation.** It turns the storage pivot
   from an argument into a number.
5. **Build the simulator CLI.** Critical path to a demoable v1.0 over a finished engine.
6. **Get the metric formulas out of the Google Doc and into `metrics.py`** with tests, once
   thresholds and the capex owner exist.

Steps 1, 2 and 4 do not depend on the storage pivot resolving. Neither does any Tier 1 work.
