# Fact-Check Report — 2026-07-16

Produced by the source-verification procedure against the three source documents
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
3. **Reserve definitions.** The Architecture doc uses `soc_floor` plus `strategic_reserve` as separate percentages, but elsewhere states a "constant reserve of 33% total capacity" and `soc_now >= .33 soc_total + strategic_reserve`. One canonical definition is needed before coding.
4. **Document structure defects.** The Architecture doc has two different "Step 6" sections, Step 5 trails off mid-sentence, and Step 6 is blank. Step numbering also diverges from the outline (the outline has no user-confirmation step; the steps list has one as Step 4).
5. **Empty specification sections.** Overview's Constraints, Metrics, Required Inputs, and Success Criteria are blank. The software plan cannot define acceptance criteria until these exist; proposed drafts are in PLAN.md as team questions.
6. **Wording nit.** "Electrical net generation of operating the offshore wind is zero" appears to mean parasitic/station losses are zero, i.e. all gross wind generation is deliverable. Suggest rewording.

## Best-Practice Notes

- **Rolling-horizon dispatch (the doc's daily 7-day-forecast loop) is textbook model predictive control.** Literature standard: optimize over the horizon, execute only the current step, re-optimize with updated state. The receding horizon inherently absorbs small forecast errors. The doc's design is sound; name it MPC in the deck for credibility.
  Sources: https://doi.org/10.3390/electronics11010101 , https://www.sciencedirect.com/science/article/abs/pii/S0142061522005853
- **Data access.** ISO-NE Web Services API v1.1 (https://webservices.iso-ne.com/docs/v1.1/) is the primary source for hourly load and LMP; EIA API v2 for generation/capacity. The open-source `gridstatus` Python library wraps both with a consistent interface and is the pragmatic ETL choice. https://github.com/gridstatus/gridstatus
- **Reference architecture.** VPP-Sim (open-source virtual power plant framework) validates the intended stack: FastAPI backend, TimescaleDB (PostgreSQL extension) for time series, a separate optimization/dispatch module reading forecasts from the DB. https://www.researchgate.net/publication/397208596
- **Provenance (an explicit project goal).** Standard pattern: land raw API payloads immutably, transform in versioned steps, tag every simulation result with input dataset versions and code version. This directly serves the "auditable results" requirement.
