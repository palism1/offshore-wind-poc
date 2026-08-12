# Fact-Check Report — 2026-07-16

Verification pass against the three source documents
(Overview, Scaling, Software Architecture Model, converted from Downloads on 2026-07-16).

## Verified

- **FERC Order No. 2023 / 2023-A scope.** Order 2023 (issued July 28, 2023, docket RM22-14) reforms generator interconnection with annual cluster studies, readiness deposits, and a first-ready first-served process; Order 2023-A is the rehearing/clarification order. The Overview's "reliable, efficient, transparent, timely, and fair" phrasing matches FERC's own language, and the lineage to Orders 2003/2006/845 is correct.
  Sources: https://www.ferc.gov/explainer-interconnection-final-rule , https://www.ferc.gov/explainer-interconnection-final-rule-2023-A
- **ISO-NE first (transitional) cluster study.** Confirmed: 26 interconnection requests, 21 battery storage, 2 solar, 3 wind, most located in Massachusetts, ~8 GW combined summer rated capacity, largest project SouthCoast Wind 1 (1,200 MW), expected completion **August 2026**.
  Sources: https://www.utilitydive.com/news/iso-ne-launches-cluster-study-of-26-battery-wind-and-solar-projec/803333/ , https://isonewswire.com/2025/10/20/iso-ne-begins-interconnection-transitional-cluster-study/ , https://www.renewableenergyworld.com/power-grid/transmission/iso-new-england-begins-its-first-interconnection-cluster-study-for-26-projects/
  ~~Caveat: the exact "August 6, 2026" date and the per-state breakdown (2 CT / 2 ME / 2 VT / 1 NH / 0 RI) were not independently confirmed; cite "August 2026" in slides unless the ISO filing is checked directly.~~ **RESOLVED 2026-07-30 — both confirmed. See the 2026-07-30 addendum.**
- **ISO-NE storage-specific Order 2023 compliance path.** Confirmed: ISO-NE is pursuing an alternative compliance pathway for storage interconnection, aiming to avoid a "control technology" requirement.
  Source: https://www.rtoinsider.com/58863-iso-ne-order-2023-compliance-storage/ , https://www.iso-ne.com/committees/key-projects/order-no-2023-key-project
- **Transmission vs data center timelines (Scaling doc).** Supported: transmission permitting alone averages ~6.5 years and often exceeds 10 (total development commonly 8+ years); data centers build in 18 to 30 months (2 to 3 years including planning is fair).
  Sources: https://cleanpower.org/wp-content/uploads/gateway/2024/04/ACP-Pass-Permitting-Reform_Fact-Sheet.pdf , https://www.niskanencenter.org/contextualizing-electric-transmission-permitting-data-from-2010-to-2020/ , https://broadstaffglobal.com/data-center-construction-timeline
- **"Seafloor wind energy reserves" is a real technology category.** Subsea pumped hydro storage exists as demonstrated concepts: Fraunhofer StEnSea (hollow concrete spheres at 600 to 800 m depth, pump-turbine uses water column pressure, explicitly designed to pair with offshore wind) and Ocean Grazer's Ocean Battery (seabed reservoir plus flexible bladder). This legitimizes the project premise and reconciles "pumped hydro" wording with offshore co-location.
  Sources: https://www.iee.fraunhofer.de/en/topics/stensea.html , https://en.wikipedia.org/wiki/Stored_Energy_at_Sea , https://www.esig.energy/deep-sea-pumped-storage/
- **ISO-NE record demand context.** All-time summer peak 28,130 MW (Aug 2, 2006); all-time winter peak 22,818 MW (Jan 15, 2004); summer 2025 peak 26,586 MW (June 24). Useful anchors for the severity percentile feature.
  Sources: https://www.iso-ne.com/about/key-stats/electricity-use , https://isonewswire.com/2025/10/23/summer-2025-recap-reliability-maintained-as-grid-sees-highest-peak-in-over-a-decade/

## Unverifiable (pending data work)

- **Seasonal denominators 561,878 MWh (summer) and 434,214 MWh (winter)** in `DemandPercentile(d)`. Dimensionally plausible as peak-day total energy: they imply daily average demand of 23.4 GW and 18.1 GW against record hourly peaks of 28.1 GW and 22.8 GW. No published source states these numbers. Action: derive them from ISO-NE hourly load history during ETL validation, record the exact query and date range, and store them as data-derived constants rather than magic numbers.
- **"Grid operators already use 10-20 tools" (Scaling doc).** No citable source found. Treat as anecdote; caveat it on any slide or drop it.

## Internal Inconsistencies (raise with team; do not silently fix)

1. **Storage technology naming.** Architecture doc Step 1 says "Pumped Hydro Storage"; Overview assumptions say "Batteries are co-located with offshore wind"; the project summary says "seafloor wind energy reserves." Likely intent is subsea pumped hydro (StEnSea-like). Software resolution: model a generic long-duration storage asset with configurable power, energy capacity, and efficiency, so the choice of label is a UI/copy decision, not a code fork.
2. **Efficiency contradiction.** Overview assumes 100% round-trip efficiency, but the Architecture doc's state equation is `soc(t+1) = soc(t) + charge(t)·eff − discharge(t)/eff`. Resolution: implement efficiency as a parameter defaulting to 1.0 for the POC; the formula then satisfies both documents.
3. **Reserve definitions.** ~~The Architecture doc uses `soc_floor` plus `strategic_reserve` as separate percentages, but elsewhere states a "constant reserve of 33% total capacity" and `soc_now >= .33 soc_total + strategic_reserve`. One canonical definition is needed before coding.~~ **RESOLVED 2026-07-17 (team):** the protected reserve is a 20% floor plus a separate 10% reserve of total storage (30% protected, 70% for regular operations). Encoded as the engine defaults (`soc_floor_frac=0.20`, `strategic_reserve_frac=0.10`). STILL OPEN: the usage rules for when the 10% reserve and 20% floor may each be drawn down; until decided, the engine treats their sum as one protected floor.
4. **Document structure defects.** The Architecture doc has two different "Step 6" sections, Step 5 trails off mid-sentence, and Step 6 is blank. Step numbering also diverges from the outline (the outline has no user-confirmation step; the steps list has one as Step 4).
5. **Empty specification sections.** Overview's Constraints, Metrics, Required Inputs, and Success Criteria are blank. The software plan cannot define acceptance criteria until these exist; proposed drafts are in PLAN.md as team questions.
6. **Wording nit.** "Electrical net generation of operating the offshore wind is zero" appears to mean parasitic/station losses are zero, i.e. all gross wind generation is deliverable. Suggest rewording.

## Best-Practice Notes

- **Rolling-horizon dispatch (the doc's daily 7-day-forecast loop) is textbook model predictive control.** Literature standard: optimize over the horizon, execute only the current step, re-optimize with updated state. The receding horizon inherently absorbs small forecast errors. The doc's design is sound; name it MPC in the deck for credibility.
  Sources: https://doi.org/10.3390/electronics11010101 , https://www.sciencedirect.com/science/article/abs/pii/S0142061522005853
- **Data access.** ISO-NE Web Services API v1.1 (https://webservices.iso-ne.com/docs/v1.1/) is the primary source for hourly load and LMP; EIA API v2 for generation/capacity. The open-source `gridstatus` Python library wraps both with a consistent interface and is the pragmatic ETL choice. https://github.com/gridstatus/gridstatus
- **Reference architecture.** VPP-Sim (open-source virtual power plant framework) validates the intended stack: FastAPI backend, TimescaleDB (PostgreSQL extension) for time series, a separate optimization/dispatch module reading forecasts from the DB. https://www.researchgate.net/publication/397208596
- **Provenance (an explicit project goal).** Standard pattern: land raw API payloads immutably, transform in versioned steps, tag every simulation result with input dataset versions and code version. This directly serves the "auditable results" requirement.

---

# Fact-Check Addendum — 2026-07-28 (Mitchell's third reply)

Every checkable claim in the 2026-07-28 record, verified against primary sources. The two
analysis PDFs were re-read directly (`pdftotext -layout`) rather than via our own summaries.

## Verified

- **StEnSea full-scale (1:1) design: 30 m outer diameter, 20 MWh, 5–7 MW, 80% round-trip
  efficiency, 600–800 m depth.** Fraunhofer IEE, primary.
  https://www.iee.fraunhofer.de/en/topics/stensea.html
- **StEnSea prototype efficiency series: 40% at 1:10 (3 m, 100 m depth) → 60% at 1:3 (10 m,
  500–700 m) → 80% at 1:1 (30 m, 600–800 m).** Same source. **Mitchell is correct that no
  StEnSea unit, including the full-scale design, exceeds 0.80.**
- **Report B computes charging gaps at 85% round-trip efficiency.** Verbatim, Finding 2.2:
  "the 7-day pre-event wind total was large enough to eliminate the charging gap entirely at
  a 5% load reduction target and 85% round-trip efficiency." Source: `NE_Stage1_Stage2_
  Findings.pdf`, Finding 2.2.
- **Report B's stress rule is the 12-hour one.** Verbatim: "A stress day is defined as any
  calendar day with 12 or more hours above the threshold; a multi-day event is two or more
  consecutive stress days." Threshold 3,504 MWh at p90, 1,740 of 17,395 stress hours (10.0%).
- **Report A: zero hours of negative net load.** "Hours where net load < 0: 0 — no oversupply,
  no curtailment needed." Supports the opportunity-cost charging model.
- **Event 17 (Jan 25–31, 2026) at $443/MWh is the highest-cost event in the dataset.** Report B.
- **Report A's 40,000–60,000 MWh reserve target.** Report A, Implications: 5% of the 16,750 MWh
  threshold = ~838 MWh per stressed hour. (Derivation is loose — see Internal Inconsistencies.)
- **ISO-NE all-time summer peak 28,130 MW (Aug 2, 2006); winter record 22,818 MW (Jan 15,
  2004).** https://www.iso-ne.com/about/key-stats/electricity-use
- **Gulf of Maine: three basins deeper than 200 m — Georges 379 m (deepest), Jordan and
  Wilkinson ~275 m each.** https://repository.library.noaa.gov/view/noaa/53045/noaa_53045_DS1.pdf
- **EIA `electricity/rto/fuel-type-data` is EIA-930 hourly generation by fuel type**, with
  `respondent=ISNE` and `fueltype=WND` as the ISO-NE wind series; an unkeyed request returns
  `API_KEY_MISSING` (tested 2026-07-28). https://www.eia.gov/opendata/documentation.php

## Internal math — verified by computation

ρ = 1025 kg/m³, g = 9.81 m/s², `P = ρ·g·Q·h·η`, `E = ρ·g·V·h·η`.

- Q=1.02 m³/s, h=200 m, η=0.70 → **1.436 MW** (not 1.67).
- 1.67 MW at h=200, η=0.70 → **Q = 1.186 m³/s**.
- 1.67 MW at Q=1.02, h=200 → **η = 0.814**; and 5 MW at h=600, η=0.814 → Q = 1.018 m³/s,
  confirming 1.02 is the unscaled full-scale flow.
- 20 MWh at h=200, η=0.70 → **51,146 m³**, a **46.1 m** sphere.
- 30 m sphere: 14,137 m³ gross; 11,494–12,770 m³ internal at 0.5–1.0 m wall → **4.5–5.0 MWh**
  at 200 m / 0.70.
- **Model validation:** the same geometry reproduces Fraunhofer's own 20 MWh at **701–779 m**
  for any wall thickness in 0.5–1.0 m — squarely inside their published 600–800 m band. The
  ~5 MWh at 200 m therefore rests on a model that independently recovers the manufacturer's
  headline figure.
- Sphere count for 40,000–60,000 MWh: **2,000–3,000** at 20 MWh/unit; **8,000–13,000** at the
  geometry-consistent 4.5–5.0 MWh/unit.
- Duration: 12.0 h at 20 MWh/1.67 MW; **~3.0 h** at 5 MWh/1.67 MW.
- Seasonal denominators as peak-*day* totals: 434,214 ÷ 24 = **18.1 GW**, 561,878 ÷ 24 =
  **23.4 GW** — ISO-NE system scale (vs NEMA's ~3.9 GW winter / ~5.5 GW summer peaks in
  Report B's own tables), so they did not need rescaling when scope went system-wide.

## Contradicted — corrections to our own documents

1. **"Fraunhofer publishes 0.75–0.80."** It publishes **0.80** for the full-scale design, a
   single figure. The 0.75 was our own conservative haircut presented as if sourced. Corrected
   in `DATA_SOURCES.md` [4] and the reference table. Consequence: the previously recommended
   0.85 sat **above the manufacturer's own best-case number** — Mitchell's objection is
   correct and the 0.85 recommendation was wrong on the primary source, not merely optimistic.
2. **"Full-scale rated power is 5 MW."** Fraunhofer states **5–7 MW**. Mitchell's "33.33% of
   5 MW" uses the bottom of the range, which is conservative and fine, but the range exists
   and the upper end would give 2.33 MW at 200 m.
3. **"Efficiency is governed by the pump-turbine and motor-generator, not the head, so the
   shallow variant keeps the full-scale band."** Overstated. Fraunhofer's own series falls
   40% → 60% → 80%, and that series **confounds machine scale with depth**, so it cannot be
   used to prove head-independence either way. The physics argument is plausible; it is not
   evidence. Mitchell's **0.70** sits between the built 1:3 figure (60%) and the full-scale
   design figure (80%) and is the better-supported choice.
4. **Report A's seasons are Jan–Mar (winter) and Jun–Jul (summer)** — both differ from
   Mitchell's 2026-07-28 definitions (Dec 1–Feb 28/29 and Jun 1–Sep 30). Report A's headline
   **"winter wind is 80% higher than summer" (568 vs 315 MWh/hr, 1.80×)** — which Report A
   itself calls "the single most important result for the strategic reserve concept" — is
   computed on months that are wrong in both directions: winter includes March (now excluded)
   and omits December (now included); summer omits August and September. **It must be
   recomputed before it anchors anything.**
5. **Both reports' p90 thresholds are hourly-basis, not daily-total basis.** Report B applies
   p90 "to hourly load data" (3,504 MWh); Report A's 16,750 MWh is likewise hourly (its peak
   loads of 18,758–19,378 MWh are hourly, and it counts "16 stress hours" in a day). Mitchell's
   definition thresholds **daily total demand**. **Neither existing threshold number carries
   over** — a new p90 must be computed over daily sums, roughly an order of magnitude larger.
   Anyone reusing 16,750 MWh under the new definition would be wrong by ~24×.

## Internal Inconsistencies (raise with team)

7. **Report A's 40–60 GWh sizing anchor does not reproduce from its own inputs.** 5% × 16,750
   = 837.5 MWh per stressed hour. Over the 7-day Event 3, at the 16 stress-hours/day Report A
   itself cites for Jan 21–22, that is ~94,000 MWh. The stated 40,000–60,000 MWh implies only
   **6.8–10.2 stressed hours/day**. Every sphere count in this project descends from that
   figure, so it needs a stated derivation before it anchors a published number.
8. **Report B's "summer dominates stress events" (16 of 19) excludes August**, the month of
   ISO-NE's all-time system peak (28,130 MW, Aug 2 2006). Its summer is Jun–Jul only. Both
   seasonal counts rest on two-month windows; under Mitchell's definitions winter gains
   December and summer gains August–September, and the 16:3 ratio is unresolved until then.

## Unverifiable

- **The shallow-water 200 m StEnSea variant.** No built or designed unit exists at that head;
  Mitchell states this openly. Efficiency 0.70 and ~5 MWh/sphere are design estimates,
  defensible by scaling but not sourced. Label as assumptions on any slide.
- **Whether 0.70 is the round-trip or one-way figure.** Not stated. Round-trip → ~0.837 each
  way; one-way turbine → ~0.49 round-trip. Blocks `config.py`.

---

# Fact-Check Addendum — 2026-07-30 (2026-07-27 Technical Brief + basin charts)

Verification pass over the 2026-07-27 "Future Grid-Stress Scenario Explorer" brief, its
Metrics V1.0 block, and three basin depth-profile charts. Externals checked against
ISO-NE, NOAA, and USGS. The metric formulas were reviewed twice — once directly, once
adversarially — and the second pass overturned five of the first pass's findings, which
are recorded below as withdrawn so they are not re-litigated.

## Verified

- **ISO-NE Transitional Cluster Study completes by August 6, 2026.** Not a projection — a
  tariff requirement. Study began 2025-10-11; interim results were released and developer
  responses closed 2026-07-07; final report early August. This **supersedes the 2026-07-16
  caveat** telling us to cite only "August 2026."
  https://isonewswire.com/2025/10/20/iso-ne-begins-interconnection-transitional-cluster-study/
- **Per-state breakdown of the 26 requests confirmed:** most in Massachusetts, two each in
  Connecticut, Maine, and Vermont, one in New Hampshire, none in Rhode Island. The exact
  Massachusetts count is not published anywhere located — do not state one.
- **21-Day Energy Assessment Forecast and Report.** The brief's name and causal story are
  ISO-NE's own: "two weeks in December 2017 and January 2018, which led the ISO to develop
  the 21-Day Energy Assessment Forecast and Report."
  https://www.iso-ne.com/about/what-we-do/21-day-forecast
- **Georges Basin 379 m; Jordan and Wilkinson ~275 m each.** Re-confirmed against the same
  NOAA source already cited in `DATA_SOURCES.md` [line 37].
- **Stress Window definition matches the implementation.** The brief's "peak daily total
  load above the 90th percentile" is what `src/owr/stress_finder.py:48` and
  `config.py:92` already do, on daily sums at p90.

## Contradicted

1. **"Murray Basin" does not appear to be a Gulf of Maine feature.** NOAA and USGS name
   three major basins — Wilkinson, Jordan, Georges — plus Grand Manan Basin and Emerald
   Basin. Bathymetric searches for "Murray Basin" return the Murray Basin in *Australia*.
   The chart's ~44°N feature is annotated with the Grand Manan Channel Sill, which is where
   **Grand Manan Basin** sits; the name may have drifted from the nearby **Murr Escarpment**,
   a submarine border fault paralleling the Maine coast. The feature must be pinned to a
   coordinate and a chart before it is named in any deliverable.
2. **Jordan Basin at 310 m contradicts the primary source.** NOAA puts Jordan and Wilkinson
   at ~275 m *each*. The comparative chart's 270/310 split makes Jordan 40 m deeper than
   Wilkinson when the source makes them equal. Wilkinson 270 vs 275 and Georges 380 vs 379
   are rounding and are fine.
3. **"S. Gulf Depression" at 42°N, 69.5°W may be Wilkinson Basin re-charted.** Wilkinson is
   the western-Gulf basin and its Geotechnical Test Area lies within the 260 m contour; the
   42°N/69.5°W point falls in its general area. The comparative chart plots the two as
   distinct basins at different depths (212 vs 270 m). If they are the same feature, the
   chart set double-counts one basin. **Resolve against the USGS Gulf of Maine 3-arc-second
   DEM** (sample depth at coordinates rather than argue from named features):
   https://pubs.usgs.gov/of/2011/1127/GOM03_v1_0faq.htm
4. **Winter defined as "December 1st and February 28th"** drops Feb 29. The recorded team
   definition is Dec 1 – Feb 28/29, and 2024 is inside the 2022–2026 data range.

## Unverifiable — and load-bearing

- **"For every year between 2022 and 2026, winter has consistently exhibited higher wind
  generation than summer."** No source in this project supports a *per-year* series; Report A
  gave one aggregate 1.80× ratio, computed on Jan–Mar vs Jun–Jul, which the 2026-07-28
  addendum [Contradicted #4] already found wrong in both directions against the settled
  season definitions. This sentence is the brief's central premise and must be recomputed
  from EIA-930 under Dec 1 – Feb 29 / Jun 1 – Sep 30 before it is repeated.

## Metric defects in V1.0 (ranked; all confirmed by adversarial review)

1. **Fuel-Fired Generation Offset is the wrong shape.** `oil+gas − (wind+dispatched)` has no
   time split, but `HANDOFF.md:271-275` records the team's settled meaning: fuel-fired MWh
   *pre-event* against fuel-fired MWh *during the event*. As written it also double-counts
   wind, since dispatched energy is stored wind.
2. **Stress Window Effectiveness and Fuel Offset Percentage are not bounded the way their
   [0, 100%] score tables assume, and they fail in this project's target scenario.** SWE's
   denominator (oil + gas + wind) excludes nuclear, hydro, and imports, so in a winter,
   low-wind, gas-constrained hour `capacity_dispatched` can exceed it and push SWE above
   100%, where no score is defined. Fuel Offset %'s numerator goes negative whenever
   `wind + dispatched > oil + gas`.
3. **The two percentage metrics divide by different wholes.** SWE uses `SUM(oil+gas+wind)`;
   Fuel Offset % uses `SUM(total_generation)`, which is undefined and evidently different.
   Both feed the same Robustness score.
4. **Scenario Robustness Score has no aggregation formula.** It lists four component
   thresholds and never states how they combine (average, weighted, minimum). It is the only
   metric in the document without a formula, and it stands in for a whole category.
5. **The Economics category runs on variables absent from the brief's own taxonomy.**
   `est_transmission_cost_per_mile`, `miles`, `est_storage_unit_cost`, `total_unit_count`,
   and `Solution_Lifetime` appear under neither Independent, Dependent, nor Constants. This
   compounds the already-recorded gap that the capex formula has no owner
   (`PROJECT_STATE_2026-07-28.md:137`, `HANDOFF.md:198`). Cost per EFC's units do resolve
   cleanly ($ ÷ (cycles/yr × yr) = $/cycle) — no defect there.
6. **The RCM chain is broken in two places.** `Average Recharge Mismatch` is defined and
   never used; `Recharge Capacity Mismatch` divides by `average_cycle_recharge_utilization`,
   which is defined nowhere and is probably the same quantity renamed. The average is also
   malformed: it sums over index `c` while the summand is indexed by `t`.
7. **Protected reserve is encoded twice, inconsistently.** `Protected Reserve = 30%`
   duplicates `Available Charge ≤ 70%`; `Protected Reserve Floor = 20%` duplicates
   `SoC ≥ 20%`; and a 30% protected reserve is incompatible with SoC reaching 20%. The
   settled encoding is Internal Inconsistency #3 above (20% floor + 10% strategic reserve),
   shipped as `config.py:90-91` and `models.py:37-38`. Keep the floor/reserve pair and drop
   the derived bounds.
8. **One metric slot carries three names** — "Storage Utilization" (category list),
   "Capacity Utilization" (dependent variable), and RCM (formula). None is reconciled.
9. **CMI carries a vestigial `× 100%`** — a no-op left from an earlier percentage draft,
   while its score bands are in MW.
10. **Variable misclassification.** Available Charge (defined as SoC − reserve), Net Load,
    and Peak Hour Triplet (`peak_window.py` output) are listed as *independent* but are all
    derived. Wind Generation Scale is listed as a *constant* but reads as the primary sweep
    variable. Unit Charge Rate has no Aggregate Charge Rate counterpart, breaking the
    otherwise consistent unit→aggregate naming pattern.
11. **Fuel-Fired Generation Offset (MWh) was superseded by Fuel Offset Percentage** per the
    brief's own changelog, but both formulas and the MWh-labelled score band survive.
12. **Regulatory Policies numbering skips 3 and 4.**

## Withdrawn on adversarial review (do not re-raise)

- "Comparing multiple storage technologies is outside scope" vs Alexander's Layer 1/2/3
  proposal is **not** a contradiction — Alexander explicitly said not to model the three
  layers, only to frame the simulation around them. This matches the existing design stance
  (Internal Inconsistency #1 above, `PLAN.md:10`): one generic storage asset, multi-technology
  framing kept in the narrative. The brief needs one sentence saying so.
- "Cost per Equivalent Full Cycle (New!)" is a changelog marker for this doc revision, not a
  novelty claim. EFC itself predates it in code; the blocker is that capex is unbuilt.
- Charge Rate / Unit Charge Rate and Rated / Aggregate Power Output are a deliberate
  generic→per-unit→aggregate hierarchy, not redundant terms.
- Energy arbitrage and Load shift are distinct industry mechanisms (price-driven vs
  demand-driven) that the brief's own V1.0/V1.1 split keeps on separate tracks.
- Excluding capital cost from the Robustness composite is justified by the brief's System
  Rules (reliability first, economics second).

## Open — needs a team decision

- Mitchell's question stands unanswered: **how the Provincetown hub is recharged.** The
  depth verdict is unchanged by the two new candidate sites — 231 m and 212 m are further
  below StEnSea's 600–800 m design depth than Georges Basin's 379 m, which was already
  recorded as insufficient.
- `HANDOFF.md:197` asked whether Scenario Robustness Score replaces Decision Confidence.
  The brief's category list pairs them directly. **Treat as answered: yes.**

## Assumptions and System Rules (added 2026-07-30, second pass)

The first pass of this addendum skipped the brief's Assumptions block and System Rules.
Reviewed here.

1. **"Total capacity is co-located with offshore wind" is unresolved against the siting
   work, and the answer changes the capex formula.** BOEM auctioned eight Gulf of Maine
   lease areas on 2024-10-29, off Maine, New Hampshire, and Massachusetts, 23–92 miles
   offshore in water too deep for fixed-bottom turbines (floating only). Storage in a Gulf
   of Maine basin could co-locate with those. But SouthCoast Wind (~26 nmi south of
   Martha's Vineyard) and Vineyard Wind (~14 mi south), the projects named in the cluster
   study, sit in southern New England waters — a different body of water from every basin
   on the depth charts. The assumption is true against one lease set and false against the
   other, and the brief does not say which. It also determines what `miles` measures in
   `Estimated Capital Costs`, a term that is currently undefined.
   https://www.boem.gov/renewable-energy/state-activities/maine/gulf-maine
2. **System Rules do not match the dispatch module.** "Reliability first, economics second,
   efficiency third" is encoded nowhere as an ordering. `dispatch.py:36-37` blends
   peak-shaving and smoothing at `peak_weight=0.5 / smooth_weight=0.5`, while the brief's
   own definition of *Strategic reserve dispatch* says to hold charge for declared
   reliability events "rather than daily peak-shaving." Spec and code disagree on the
   dispatch policy. Resolve before the metrics are implemented against either.
3. **"Temperature change does not affect total capacity, power output, or charge rate" is
   consistent with the implementation** — `storage_physics.py:18` fixes
   `RHO_SEAWATER_KG_M3 = 1025.0`. No action; noted as a verified spec/code agreement.
4. **"The peak of wind generation occurs in the winter" (Supporting Data)** is the third
   statement of the claim flagged under Unverifiable above. Same recomputation blocks it.
5. **"Redundancies in the system are preferred by grid planners"** is unsourced and stated
   as a determinant. Either cite it or relabel it as a design preference.
6. **The three assumption categories — Validating, Supporting Data, Determinants — are
   never defined.** Items appear to be sorted by whether the project tests them, rests on
   them, or fixes them, but nothing says so.
7. **"The risks of load-forecasting uncertainty can be mitigated by redistributing wind
   energy" (Validating)** is the one assumption the simulator cannot currently test: no
   forecast-error model exists in the engine. The MPC rolling horizon absorbs error
   implicitly (Best-Practice Notes above) but nothing injects or measures it.

## Not yet recorded anywhere

The brief itself does not exist in this repository — it arrived as pasted text. Following
the precedent set on 2026-07-28 for Alexander's data-source spec (keep the author's text
verbatim, keep our analysis in a separate document), the brief should be committed
verbatim as its own file so that this addendum has a stable referent and so no one's
wording is paraphrased into ours.

## Third pass — reading the actual PDF (2026-07-30)

The first two passes worked from text pasted into chat. The source document is now stored
verbatim at `docs/source/2026-07-27_Overview_Document.pdf` (20 pages, "Overview Document",
Last Updated Jul 27 2026). Reading it directly changes three findings and adds four.

### Corrections to this addendum

- **Wind Generation Scale is not miscategorised — the document answers itself.** It appears
  under **Required Inputs** (p.12), which is the operative input list. Listing it under
  Constants is the error, not the classification. Withdraw the earlier framing.
- **"Fuel-Fired Generation Offset (MWh) → Fuel Offset Percentage" is not in the document.**
  That changelog came from chat notes, not the brief. The PDF's **Success Criteria page is
  literally "TBD"** (p.20). The metric supersession is a team intent, not a written decision.
- **Scenario Robustness Score is emptier than reported.** Not only is there no aggregation
  formula — the four threshold values are blank in the document (p.18): each component is
  listed with a trailing colon and nothing after it.

### New findings

1. **"Reserve Power Output" is a Required Input that exists in no other list.** It appears on
   p.12 among the five required inputs and appears nowhere in Variables of Interest, nowhere
   in Constants, and in no metric formula. Either it is the same thing as Unit Power Output ×
   unit count, or it is a sixth quantity nobody has defined.
2. **"Location archetype: one of the project's four categories of storage siting" — the four
   categories are never enumerated anywhere in the document.** This is directly load-bearing
   for the current basin discussion: the siting debate (Provincetown hub, Murray Basin,
   S. Gulf Depression, co-location with which lease areas) has no defined taxonomy to slot
   candidates into.
3. **Wind Generation Scale is specified as "a scalar integer."** As written this forbids
   fractional scaling (1.5× wind), which is the natural sweep for a scenario explorer.
   Probably should read "scalar."
4. **Required Inputs contains two struck-through future options** — Grid Inflexibility and
   Natural gas inventory. Recorded so they are not mistaken for dropped requirements.

### Status of the 2026-07-16 "empty sections" finding

Internal Inconsistency #5 above flagged Constraints, Metrics, Required Inputs, and Success
Criteria as blank. Three of the four are now written. **Success Criteria remains TBD** and is
the last blank section in the document.

---

# Real p90 Daily Stress Thresholds — computed 2026-07-30

First computation from live ISO-NE data, replacing the invalidated report figures.
Source: `gridstatus.ISONE().get_load()` (credential-free public 5-minute system-load feed),
`gridstatus==0.36.0`, retrieved 2026-07-30T18:21Z. 324,043 five-minute intervals →
1,126 local calendar days (1,122 complete, 4 excluded as incomplete).

## Coverage limit — DATA DOES NOT REACH 2022

The credential-free feed's earliest record is **2023-06-30T20:00-04:00**. A 2022 pull
returns **0 rows**. So the usable population is **three winters** (2023/24, 2024/25,
2025/26 — 91/90/90 days), not the five the brief assumes. Anything claiming a
2022–2026 span must either be rescoped to 2023–2026 or wait on the credentialed
ISO-NE Web Services hourly feed. This is Phase A4 in `PLAN_EIA_EXTRACTOR.md`.

## Thresholds (p90 of daily total load, per season, pooled across years)

| Season | p90 threshold | Median | Min | Max | Population |
|---|---|---|---|---|---|
| Winter (Dec 1 – Feb 28/29) | **385,833 MWh/day** | 345,417 | 279,576 | 430,209 | 270 days |
| Summer (Jun 1 – Sep 30) | **413,476 MWh/day** | 320,220 | 227,491 | 491,457 | 393 days |

**Cross-check against the invalidated numbers.** 385,833 ÷ 24 = **16,076 MWh/hour**, within
4% of Report A's hourly p90 of 16,750 MWh. That independently confirms the 2026-07-28
finding: the old figures were hourly-basis, and the daily-basis threshold is ~24× larger.
The correct daily number is 385,833 MWh — **not** 16,750.

**Partial validation of the seasonal denominators.** The previously unverifiable
434,214 MWh (winter) sits just above our observed winter maximum of 430,209 MWh — consistent
with a peak-day total. The summer figure 561,878 MWh sits well above our observed summer
maximum of 491,457 MWh and is not corroborated.

## Multi-day stress events (winter p90, minimum window 2 days)

| Winter | Events | Detail |
|---|---|---|
| 2023/24 | 0 | none |
| 2024/25 | 1 | 2025-01-21 → 2025-01-23 (3 days) |
| 2025/26 | 3 | 2026-01-20 → 2026-01-21 (2 d); **2026-01-24 → 2026-02-03 (11 d)**; 2026-02-07 → 2026-02-09 (3 d) |

Four multi-day events across three winters. The **11-day January–February 2026 event** is
the dominant one and overlaps the event Report B priced at $443/MWh (Jan 25–31, 2026), the
highest-cost event in its dataset — independent corroboration from a separate source.

## Open spec question raised by these numbers — needs a team decision

**Summer's p90 daily total (413,476) is HIGHER than winter's (385,833)**, and the summer
maximum (491,457) exceeds the winter maximum (430,209). ISO-NE is summer-peaking; the
all-time system peak is 28,130 MW in August 2006.

The Stress Window definition says "peak daily total load sits above the 90th percentile"
without stating **the population the percentile is taken over**. The table above uses a
*per-season* population. If the p90 were pooled across all seasons instead, the threshold
would rise and the winter event count would fall — possibly to near zero, which would
invalidate the premise that winter stress is the thing to size storage against.

The project's framing is winter fuel adequacy, which argues for the per-season reading.
But this must be written into the definition rather than left implicit, and the choice
should be stated wherever the event list is published. **Raise with Mitchell.**

## Reproducing

Thresholds were computed through the tested `owr.etl.daily` / `owr.etl.transform` modules.
The `etl transform` CLI subcommand is **not yet wired** (it still prints "not implemented
yet"); this run drove the modules directly. Wiring it is the next implementation step.

---

# Fact-Check Addendum — 2026-08-11

Re-read pass. The source documents were re-fetched and diffed against the versions the
2026-07-16/07-28/07-30 passes above checked (`2026-07-27_Overview_Document.md` →
`2026-08-05_Overview_Document.md`; `2026-07-30_Software_Architecture_Documentation.md` →
`2026-08-04_Software_Architecture_Documentation.md` → `2026-08-05_Software_Architecture_Documentation.md`,
the latter two content-identical, differing only in markdown export escaping). External
facts already Verified above (FERC Order 2023/2023-A, StEnSea specs, ISO-NE record demand,
Gulf of Maine basin depths) are stable, sourced primary facts unlikely to move on a
three-week horizon and were not re-derived; this pass focuses on what changed in the source
documents themselves and one time-sensitive external claim.

## Verified

- **The source spec's own `usable_energy(t)` formula never included an energy-budget
  fraction.** `2026-08-05_Software_Architecture_Documentation.md`, Archived §Step 7:
  `usable_energy(t) = soc(t) - soc_floor - strategic_reserve`. No 80% (or any other)
  fraction multiplies this expression anywhere in the current source document. This
  directly supports the just-completed removal of `Config.energy_budget_fraction` from
  `src/owr/config.py` — the engine's `usable_energy(soc, asset)` now matches the source
  formula exactly, with the reserve floor as the only constraint.
- **Stress Window Effectiveness's denominator was corrected in the source between
  2026-07-27 and 2026-08-05, and the code already agrees with the corrected version.**
  Old (07-27): `SWE = capacity_dispatched(t) / (oil + gas + wind)`. New (08-05):
  `SWE = capacity_dispatched(t) / (oil + gas)` — wind dropped from the denominator. This
  resolves 2026-07-30 addendum Metric Defect #2/#3 (SWE could exceed 100% when
  `capacity_dispatched` exceeded a denominator that excluded nuclear/hydro/imports but
  included wind, and the two percentage metrics divided by different, inconsistent
  wholes). `src/owr/metrics.py:524-556` (`stress_window_effectiveness_fraction`) already
  implements `oil + gas` only, citing `docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf`
  directly. Source doc, Metric Thresholds PDF, and code now agree.
- **Recharge Capacity Mismatch's denominator variable was corrected to a name that is
  actually defined.** Old (07-27): divides by `average_cycle_recharge_utilization`
  (defined nowhere, per 07-30 addendum Internal Inconsistency #6 / Metric Defect #6). New
  (08-05): divides by `average_recharge_mismatch`, which the same document defines two
  lines above. `src/owr/metrics.py:334-352` (`average_recharge_mismatch_mwh`) and
  `:352-...` (`recharge_capacity_mismatch_fraction`) already use this corrected pairing.

## Contradicted — corrections to our own documents

- **The "80% energy budget rule" is absent from the source document as of 2026-08-04,
  three weeks before today's code removal.** `2026-07-30_Software_Architecture_Documentation.md`
  Archived §Step 7 (the version the 07-16 fact-check pass and the shipped
  `energy_budget_fraction` were both built against) contains: "Calculate what 80% of the
  total energy budget for the stress window ... Product of total energy budget times
  0.80" and "A simple average of 80% energy budget divided by number of days across the
  window." These bullets do **not** appear in `2026-08-04_Software_Architecture_Documentation.md`
  or `2026-08-05_Software_Architecture_Documentation.md` — the equivalent Step 7 section
  in both later revisions ends at the `usable_energy`/dispatch-window bullets with no 80%
  step at all. The source of truth dropped this rule before the codebase did; today's
  removal of `Config.energy_budget_fraction` (this session) brings the code in line with
  a change the architecture document had already made. `CLAUDE.md`'s `config.py` row
  still says "80% budget" (flagged stale in the prior session, deferred to the user) —
  this addendum adds a second, independent reason it needs updating: it no longer
  describes either the code or the current source document.

## Unverifiable — time-sensitive, re-check before citing

- **"26 interconnection requests" / "~8 GW combined capacity" for the ISO-NE Transitional
  Cluster Study may already be stale.** The Overview document's Regulatory Policies
  section (both 07-27 and 08-05 versions, unchanged) states 26 requests (21 storage, 2
  solar, 3 wind) completing by August 6, 2026 — this was independently confirmed in the
  2026-07-16 and 2026-07-30 passes above. Today is 2026-08-11, five days past that
  completion date. A web search found ISO-NE's **interim** results (released 2026-06-24,
  developer comment period closed 2026-07-07) cover **23 qualified projects representing
  ~4.8 GW** — three fewer projects and roughly 3.2 GW less capacity than the 26-request /
  ~8 GW figure our docs cite, per EPE Consulting's summary
  (https://epeconsulting.com/epe-intelligence/news/iso-nes-transitional-cluster-study-tc2-results-are-in-what-developers-need-to-know).
  No final report (due "early August 2026" per the same source) was found in search
  results as of this pass — it may not yet be published, or may not yet be indexed.
  **Action: check iso-ne.com directly for the final TC2 report before repeating "26
  requests" or "~8 GW" in any external-facing deliverable** — the number has already
  moved once between the queue-entry count and the interim study, and may move again in
  the final report.
- **Interim interconnection cost figures (~$3.2B total, ~$2.5B network upgrades) are new
  information, not yet in any project document, and sourced only from a secondary
  summary (EPE Consulting), not the ISO-NE filing itself.** Per this skill's own
  guidance, a secondary summary is not a source of record for a claim of this kind — if
  the team wants to cite interconnection cost figures, locate the underlying ISO-NE TC2
  interim/final report at iso-ne.com or the relevant filing before use.

## Internal inconsistencies — carried over, still open

- **`docs/architecture/architecture_overview.md` still states round-trip efficiency
  default as 1.00 ("100% efficient baseline"); the shipped default is 0.7225** (Week 4B,
  `src/owr/config.py:200`, `default_efficiency: float = 0.7225`). Same error appears in
  `docs/engineering_review.md`'s Planning Assumptions table ("Round-trip efficiency | 1.00
  | ..."). This was flagged as pre-existing, out-of-scope staleness during the
  `energy_budget_fraction` removal session (2026-08-11, earlier today) and is repeated
  here because it is a genuine code/doc inconsistency this skill's checklist is meant to
  catch, not because anything new was found. Not yet fixed.
- **Success Criteria is still "TBD"** in `2026-08-05_Overview_Document.md` (line 240),
  unchanged since the 2026-07-30 third-pass finding. No software acceptance criteria can
  be derived from the brief until this is written.

## Best-Practice Notes

- No new best-practice research this pass; the 2026-07-16 notes (MPC rolling horizon,
  ISO-NE/EIA API access via `gridstatus`, TimescaleDB reference architecture, provenance
  pattern) remain current and were not re-litigated.
