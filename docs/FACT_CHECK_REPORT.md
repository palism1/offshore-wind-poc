# Fact-Check Report — 2026-07-16

Verification pass against the three source documents
(Overview, Scaling, Software Architecture Model, converted from Downloads on 2026-07-16).

## Verified

- **FERC Order No. 2023 / 2023-A scope.** Order 2023 (issued July 28, 2023, docket RM22-14) reforms generator interconnection with annual cluster studies, readiness deposits, and a first-ready first-served process; Order 2023-A is the rehearing/clarification order. The Overview's "reliable, efficient, transparent, timely, and fair" phrasing matches FERC's own language, and the lineage to Orders 2003/2006/845 is correct.
  Sources: https://www.ferc.gov/explainer-interconnection-final-rule , https://www.ferc.gov/explainer-interconnection-final-rule-2023-A
- **ISO-NE first (transitional) cluster study.** Confirmed: 26 interconnection requests, 21 battery storage, 2 solar, 3 wind, most located in Massachusetts, ~8 GW combined summer rated capacity, largest project SouthCoast Wind 1 (1,200 MW), expected completion **August 2026**.
  Sources: https://www.utilitydive.com/news/iso-ne-launches-cluster-study-of-26-battery-wind-and-solar-projec/803333/ , https://isonewswire.com/2025/10/20/iso-ne-begins-interconnection-transitional-cluster-study/ , https://www.renewableenergyworld.com/power-grid/transmission/iso-new-england-begins-its-first-interconnection-cluster-study-for-26-projects/
  Caveat: the exact "August 6, 2026" date and the per-state breakdown (2 CT / 2 ME / 2 VT / 1 NH / 0 RI) were not independently confirmed; cite "August 2026" in slides unless the ISO filing is checked directly.
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
