# Findings Review — 2026-07-24

Review of the Discord sync (Keith Trnka mentor feedback, Mitchell on MVP scope and DHS)
against three new analysis artifacts:

| Artifact | Short name here |
|---|---|
| `jtbd_driven_grid_project_overview.txt` | Overview v2 |
| `NE_Wind_Reserve_Findings_v2.pdf` | Report A |
| `NE_Stage1_Stage2_Findings.pdf` | Report B |
| `daily_stress_events.csv` | CSV |

Verdicts follow the source-verification procedure. Inconsistencies are
surfaced for a team decision, not silently reconciled.

---

## Headline

**Report A and Report B are measuring two different power systems.** Report A's
Finding 6 and its entire storage-sizing recommendation are computed on
**full ISO-NE** load; everything else in both reports is **NEMA/Boston zone 4008**.
Carrying Report A's sizing number into the simulator would oversize the reserve by
roughly **5×**. Nothing else in this review matters as much.

---

## Internal Inconsistencies

### I-1 — Stress threshold differs 4.8× between reports (BLOCKING)

- Report A, Finding 6: 90th-percentile threshold **16,750 MWh**; three January 2025
  events with peak loads 18,758 / 18,109 / 19,378 MWh.
- Report B, header + Stage 1: 90th-percentile threshold **3,504 MWh**; highest peak
  load anywhere in the dataset **5,492 MWh**.

Both claim NEMA/Boston. They cannot both be NEMA.

**Resolution (high confidence):** Report A Finding 6 is full ISO-NE, not NEMA.
Evidence:

1. 3,504 / 16,750 = **20.9%**, and NEMA is ≈20% of ISO-NE system load.
2. ISO-NE system winter peak runs ~19–20 GW — matching Report A's 18,758–19,378.
   NEMA winter peak runs ~3.8–4.0 GW — matching Report B.
3. Report A's *own* Finding 4 table lists 2022 summer peak as **5,090 MWh**, which
   is exactly Report B's Event 01 peak of **5,090 MWh**. So Report A Finding 4 is
   NEMA while Report A Finding 6 is ISO-NE. Report A is internally mixed.

**Consequence.** Report A's "Implications" section inherits the wrong scale:

| Quantity | Report A (ISO-NE) | Corrected (NEMA 4008) |
|---|---|---|
| Threshold | 16,750 MWh | 3,504 MWh |
| 5% target, per stressed hour | 838 MWh | **175 MWh** |
| Total reserve, 7-day event | 40,000–60,000 MWh | **~8,400–12,600 MWh** |

This reframes Keith's question directly. Against a **1 GWh StEnSea unit**, the
corrected NEMA figure is roughly **8–13 spheres**, not 40–60. That is the difference
between "implausible" and "a procurement conversation."

**Needs a decision:** is the study scope NEMA/Boston (4008) or ISO-NE system-wide?
The repo, both report subtitles, and the CSV all say NEMA. Recommend ratifying NEMA
and reissuing Report A Finding 6 + Implications at NEMA scale.

### I-2 — Three sources, three different event sets

Same underlying January 2025 activity, three different segmentations:

| Source | Jan 2025 events | Winter multi-day events, full period |
|---|---|---|
| Report A | 3 (Jan 5–10, Jan 13–17, Jan 20–26) | "recurring across 2022–2024" |
| Report B | 1 (Event 10, Jan 21–22) | 3 total, none before 2025 |
| CSV | 3 (W09 Jan 6–9, W10 Jan 16, W11 Jan 21–24) | 6 |

The **dates corroborate each other** — all three see early-Jan, mid-Jan and late-Jan
clusters. The **durations and counts do not**, because each used a different
threshold and a different day-merging rule.

Sharpest case: **CSV W17 spans Jan 24 – Feb 10 2026 as one 18-day event.** Report B
splits that same window into Event 17 (Jan 25–31, 7d) and Event 18 (Feb 8–9, 2d) with
a 7-day quiet gap between them. An 18-day "event" is an artifact of a loose merge
rule, not a real 18-day grid emergency. It should not be used for storage sizing.

Also note Report A's claim that multi-day January events recur "across 2022, 2023 and
2024" is **contradicted by Report B's own table**, which lists zero winter events
before January 2025. Under Report B's stricter threshold the recurrence claim does not
hold. Under the CSV's looser one it partly does (W06 in Feb 2023). Do not put the
recurrence claim in a deliverable until one threshold is agreed.

**Needs a decision:** one canonical stress definition — threshold percentile, hours
per day qualifying a stress day, and maximum gap for merging days into one event.
Everything downstream (`stress_finder.py`, sizing, case studies) depends on it.

### I-3 — Round-trip efficiency: analysis says 0.85, engine says 1.0

Report B Finding 2.2 computes every charging gap at **85% round-trip efficiency**.
Overview v2 and `src/owr/config.py` use **`default_efficiency: float = 1.0`**.

The engine at 1.0 understates required charging energy by **17.6%** relative to the
analysis that produced the "zero charging gap" result. These two artifacts cannot be
compared until they agree.

**Recommend:** move the engine default to 0.85, keep 1.0 as an explicit
idealized-case override. This retires FACT_CHECK inconsistency #2 with a real number
instead of a reconciliation.

### I-4 — "Zero charging gap" ignores the opportunity cost Report A identifies

This is the most substantive modeling gap, and the two reports contradict each other
inside a single study.

Report A, Finding 3, is unambiguous:

> Hours where net load < 0: **0** — no oversupply, no curtailment needed.
> "every MWh of wind generated is genuinely reducing grid stress. There is no surplus
> disposal problem. This means storage would be charged from wind that would otherwise
> flow directly to the grid — the simulation's core tradeoff."

Report B, Finding 2.2, then concludes **18 of 19 events have zero charging gap** by
counting the full 7-day pre-event wind total as available for charging.

**There is no free wind.** Every MWh diverted into storage during the pre-event window
raises net load in that window and must be replaced by another generator at that hour's
price. Report B's zero-gap result answers "was enough wind physically generated?" — a
much weaker question than "could it be diverted without creating new stress?"

The strategic-reserve case still stands, because the arbitrage is real: charge at
pre-event prices, discharge into a $443/MWh event. But it must be *scored*, not
assumed free. Report B's headline currently reads as though charging is costless.

**Recommend:** the dispatch model charges wind at an explicit opportunity cost (the
hourly LMP at charge time), and the economic score reports net value, not gross
avoided cost. This is a `dispatch.py` / `metrics.py` change, and it is the difference
between a defensible result and one a reviewer dismantles.

### I-5 — "Winter wind is 80% higher" does not reproduce

Report A headlines **568 / 315 MWh-hr = 1.80×**. Report B's per-year table averages to
winter **568.3** (matches) but summer **330.8**, giving **1.72×**, not 1.80×.

Reconcilable: hour-weighting rather than year-averaging, with 2026 summer only
partially present, pulls the summer mean down toward 315. Excluding 2026 entirely gives
296.8. So 315 sits inside the plausible range.

Verdict: **reconcilable but underdocumented.** The 80% figure is the foundation of the
whole strategic-reserve argument and it is the number an ISO-NE audience will check
first. State the weighting explicitly or quote 1.72× from the per-year table.

Separately: Overview v2's claim that winter exceeds summer wind **every year 2022–2026**
is **Verified** against Report B's table (575>345, 455>205, 503>281, 584>356, 725>467).

### I-6 — HANDOFF.md is stale on the reserve floor

`docs/HANDOFF.md` still says "reserve floor 33%". **The code is already correct** —
`config.py` has `default_soc_floor_frac 0.20` + `default_strategic_reserve_frac 0.10`,
matching the team decision in commit `d6690f1`. Documentation fix only, no code change.

Still genuinely open, and correctly labeled as such in the config docstring: **when the
10% reserve and the 20% floor may each be drawn down.** This is the board item
"Decide usage rules for the 10% reserve and 20% floor" and it remains unresolved.

### I-7 — The 2023 anomaly has no handling path

Both reports flag 2023 as anomalously low wind (454.6 MWh/hr winter) and both say
"treat with caution." Neither says what that means operationally.

**Recommend:** an explicit `exclude_years` scenario parameter rather than an informal
caveat, so a run either includes 2023 or does not, and the choice is recorded in the
run's provenance.

---

## Unverifiable / Still Open

- **Seasonal denominators** (561,878 MWh summer / 434,214 MWh winter) remain
  underivable from these artifacts — the CSV totals are stress-event sums, not
  seasonal totals. Still blocked per HANDOFF; do not hard-code.
- **"Decision Confidence"** is listed in Overview v2 as a tracked metric and is
  explicitly "(still needs to be defined)." It blocks completion of `metrics.py`.
- **Keith's market-misalignment questions** (what prevents a 1 GWh StEnSea build
  today; is there incentive misalignment vs multi-day reliability) cannot be answered
  by the current engine, which has no market or revenue model. See Decisions below.

---

## Best-Practice Note

Report B's "12 or more hours above threshold = a stress day" plus "2+ consecutive
stress days = an event" is a reasonable and conventional construction. The problem is
only that Report A and the CSV each used something different. Standard practice in
resource-adequacy work is to fix the event definition once, publish it, and hold it
constant across every downstream artifact. Do that before Stage 3.

---

## Discord items — what changes and what does not

### Mitchell: CLI is MVP v1.0, UI is v1.1+

Changes the plan. Phase 5 (React/Vite frontend) moves from **HELD** to **explicitly
deferred post-v1.0**. The deliverable for v1.0 is a terminal-runnable scenario tool.

The repo has the engine and a FastAPI layer but **no simulator CLI** — `src/owr/etl/`
exists, there is no `cli.py`. This is a new, well-scoped work item and it is now the
critical path to a demoable v1.0.

### Mitchell: DHS as a potential end user

**No code impact, by Mitchell's own statement** ("I don't think the simulator needs to
be designed for DHS"). Positioning material only.

Flagging one thing for the fact-check gate: the adversarial-deterrence and underwater-
surveillance points are speculation, and Mitchell labels them as such ("no evidence
yet," "morally grey"). They must not enter a technical document, slide deck, or the
Overview without a primary source. The defensible DHS argument is the resource-adequacy
and regional-redundancy one, which needs no speculation.

### Keith: the narrative has a logic jump

Correct, and the fix is now available in the data. Keith's point is that "keep the
lights on in a storm" does not lead a knowledgeable reader to "therefore build a
simulator."

The bridge is **I-1 corrected to NEMA scale**: a 7-day NEMA event needs ~8,400–12,600
MWh of reserve, which is ~8–13 StEnSea spheres, and Event 17 (Jan 25–31 2026) priced
that energy at **$443/MWh**. That is a specific, checkable claim that motivates
simulation — the sizing and the policy both sit in a range wide enough that you cannot
eyeball the answer.

His two suggested second questions are good and both point at **market and incentive
misalignment**, which the current engine cannot address. Recommend answering them in
prose in the Overview, and keeping a market model out of v1.0 scope.

His multi-audience suggestion (one overview for a general/HYS audience, one for
ISO-NE) maps directly onto the existing board item "Update project documentation to
current direction — Mitchell."

### Possible unblock on Phase 2 (worth chasing immediately)

HANDOFF says Phase 2 ETL is **BLOCKED on ISO-NE Web Services credentials**. But
somebody just produced **17,395 hours** of NEMA hourly load, wind and LMP data covering
2022–2026 to build these reports.

Either credentials now exist, or the data came through `gridstatus`/public endpoints
that do not need them. Either way **Phase 2 may no longer be blocked**, and the board's
"Build ETL extract, raw ISO-NE load ingestion" item may be wrong. Ask whoever ran the
analysis where the data came from — this is the cheapest possible unblock.

---

## Decisions needed from the team

Ordered by how much is blocked behind them.

1. **Scope: NEMA/Boston (4008) or full ISO-NE?** Blocks all sizing. Recommend NEMA,
   then reissue Report A Finding 6 and Implications at NEMA scale.
2. **One canonical stress-event definition** — percentile, hours/day, merge gap.
   Blocks `stress_finder.py` and every case study. Recommend Report B's rule.
3. **Round-trip efficiency default: 0.85 or 1.0?** Recommend 0.85 (I-3).
4. **Is wind charged at opportunity cost?** Recommend yes (I-4). Biggest single
   correctness question in the model.
5. **Reserve usage rules** — when may the 10% and the 20% each be drawn? Already on
   the board, still open.
6. **Canonical wind dataset** — already on the board, and these reports appear to
   settle it de facto (NEMA 4008 hourly, 2022–2026, 2023 flagged). Ratify and record.
7. **Define "Decision Confidence"** — blocks `metrics.py`.
8. **Storage naming for external comms** — already on the board, unchanged, copy-only.

## Recommended next steps

1. Get the answer to the Phase 2 data-provenance question above. It may unblock ETL
   today.
2. Land decisions 1–4. They are cheap to make and everything else waits on them.
3. Build the **v1.0 scenario CLI** over the existing engine — now the critical path.
4. Correct Report A Finding 6 and Implications to NEMA scale before either report is
   shown outside the team.
5. Add CI (`ruff check` + `pytest`), still absent, still cheap.
