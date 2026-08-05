# Data Sources — Canonical Ingest Registry — 2026-07-22

Single source of record for every dataset the tool ingests, plus the reference and
onboarding sources behind the design. Provenance is a product goal (every result must
trace to its inputs), so a source does not enter the ETL until it has a row here with a
URL, format, cadence, auth requirement, and the engine/metric it feeds.

Seeded from Mitchell's 2026-07-15 Discord source drop and the URLs already scattered
across `DIAGRAM_REFERENCES.md`, `FACT_CHECK_REPORT.md`, `PLAN.md`, and `HANDOFF.md`.

Legend: **Status** — `confirmed` (agreed ingest input) · `candidate` (pending a team
decision, see Open decisions below) · `reference` (informs design, not ingested).

## Ingest sources (ETL inputs)

| Source | URL | Format | Cadence | Auth | Feeds | Status |
|---|---|---|---|---|---|---|
| ISO-NE Web Services API v1.1 | https://webservices.iso-ne.com/docs/v1.1/ | REST/JSON | hourly | ISO-NE credentials | Hourly system load + LMP; primary API path (also wraps via `gridstatus`) | confirmed |
| ISO-NE hourly real-time system demand | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/dmnd-rt-hourly-sys | CSV | hourly | public download | Load profiles, stress-window finder, daily-load denominators | candidate — see [1] |
| ISO-NE hourly wholesale load cost | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/whlsecost-hourly-system | CSV | hourly | public download | Cost-vs-gas / residual-load-cost metric | confirmed |
| ISO-NE hourly wholesale load cost, **New England system-wide** | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/whlsecost-hourly-system (`locationId=4000`) | CSV | hourly | public download | **Canonical** load/LMP series — Alexander's 2026-07-28 spec, see [3] | confirmed — see [3] |
| ISO-NE hourly wholesale load cost, NEMA/Boston | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/whlsecost-hourly-system (`locationId=4008`) | CSV | hourly | public download | The 17,395-hour NEMA series; now the eastern-MA sub-region view, not the study basis | superseded by 4000 — see [3] |
| ISO-NE Daily Generation by Fuel Type | https://www.iso-ne.com/isoexpress/web/reports/operations/-/tree/daily-gen-fuel-type | CSV | **daily** | public download | Reconciliation reference for the EIA hourly wind series (was Alexander's 2026-07-28 wind choice) | superseded for charging — see [2] |
| EIA API v2 (opendata) | https://www.eia.gov/opendata/browser/ | REST/JSON | varies | EIA API key | Generation + capacity context (also wraps via `gridstatus`) | confirmed |
| EIA hourly generation by fuel type (RTO) | https://www.eia.gov/opendata/browser/electricity/rto/fuel-type-data | REST/JSON | hourly | **EIA API key (free, required)** | **Canonical hourly wind series** for storage charging — Mitchell's 2026-07-28 choice; ISO-NE respondent, `WND` fuel type | confirmed — see [2] |
| EIA hourly generation by fuel type (RTO) — oil and gas | https://www.eia.gov/opendata/browser/electricity/rto/fuel-type-data | REST/JSON | hourly | **EIA API key (free, required)** | Hourly petroleum (`OIL`) and natural gas (`NG`) net generation, respondent `ISNE`; lands in `raw.hourly_fuel_gen`; feeds the Fuel-Fired Generation Offset metric | extractor shipped; live pull unverified, key pending |

## Reference sources (inform design, not ingested)

| Source | URL | Role |
|---|---|---|
| StEnSea seafloor storage specs (Fraunhofer) | https://www.iee.fraunhofer.de/en/topics/stensea.html | Storage-asset parameters. Full-scale 1:1 **design**: 30 m OD, 20 MWh, **5–7 MW**, **80%** round-trip, 600–800 m. Built/planned units are smaller and less efficient — 1:10 (3 m, 100 m, 40%) and 1:3 (10 m, 500–700 m, 60%). Model the 1:1 design; see [4] for the theoretical shallow-water variant |
| EIA New England dashboard | https://www.eia.gov/dashboard/newengland/electricity | Demand/price context, sanity-checking ingested values |
| gridstatus library | https://github.com/gridstatus/gridstatus | ETL wrapper over ISO-NE + EIA (pragmatic extract layer) |
| NOAA NCEI Bathymetric Data Viewer | https://www.ncei.noaa.gov/maps/bathymetry/ | Interactive seafloor-depth map (GEBCO, coastal relief, multibeam layers); draw the Gulf of Maine depth-vs-distance curve for a candidate StEnSea site |
| GEBCO gridded global bathymetry | https://www.gebco.net/data_and_products/gridded_bathymetry_data/ | Downloadable depth grid behind most viewers; use for a numeric depth profile |
| CCOM/UNH Western Gulf of Maine bathymetry & backscatter | https://www.ccom.unh.edu/research/research-projects/wgom-bathymetry-backscatter | High-resolution multibeam survey of the western Gulf of Maine (the water nearest Cape Cod / Provincetown) |
| Jordan Basin deep-water study (NOAA) | https://repository.library.noaa.gov/view/noaa/53045/noaa_53045_DS1.pdf | Primary-source depths for the Gulf's deep basins (Wilkinson/Jordan ~275 m, Georges 379 m) |

Additional diagram/imagery references live in `DIAGRAM_REFERENCES.md`; claim-verification
sources live in `FACT_CHECK_REPORT.md`. This file is for ingest and data provenance only.

## Percentile computation change — 2026-08-05

`stress_finder.percentile_threshold` now calls `numpy.quantile` instead of a hand-rolled
linear-interpolation formula (`docs/PLAN_PANDAS_ADOPTION.md` phase 2). The two implementations
differ by at most about 1e-15 relative, measured over 20,000 random series. The set of days
classified as stressed is provably unchanged: 200,000 adversarial trials found zero stress-set
flips (full argument in `stress_finder.py`'s `percentile_threshold` docstring).

The recorded winter p90 threshold, **385,832.584 MWh/day** (see "Data pull complete" in
`docs/HANDOFF.md`), is unchanged at the three decimal places the CLI prints. A fresh
`etl transform` run over the same input reproduces the same figure.

## EIA-930 fuel series, what the numbers mean — 2026-08-05

- The pivoted column for oil is `Petroleum` and for gas is `Natural Gas`, never "Oil" and
  never "Gas" (`gridstatus/eia_constants.py:3-19`).
- **`0.0` means "zero output or not reported".** gridstatus pivots with `aggfunc="sum"`
  and pandas sums an all-null group to `0.0`, so a null EIA telemetry value arrives as a
  zero (`gridstatus/eia.py:950-955`; reproduced on pandas 2.3.3). ISO-NE petroleum output
  is legitimately `0.0` for most hours of the year, so the two cases cannot be told apart.
  Any metric built on these rows inherits that limit.
- **A missing hour is an absent row, not a NaN.** EIA omits an hour that has no row for
  the requested fuel, so a gap arrives as a shorter series. `extract.hourly_gaps` reports
  interior holes; edge truncation needs a row count against the window.
- A NaN in the requested fuel column means the pivot produced no such column, which is the
  signature of a renamed fuel upstream. The adapter raises on it.

## Onboarding / team resources

| Resource | URL |
|---|---|
| Shared Google Drive folder (team source-of-truth) | https://drive.google.com/drive/folders/103YgnT7wvcxI5h1MLTvnH_gRBueBZay4 |
| Power-industry + ISO-NE video overview (15 min) | https://vimeo.com/1159458723/0504f0666d |

## Auth needed before Phase 2 ETL

- **ISO-NE Web Services credentials** — https://webservices.iso-ne.com (also noted in `HANDOFF.md`).
  Not required for the NEMA/Boston series now in use; see [3]. Still wanted for the
  programmatic API path.
- **EIA API key** — https://api.eia.gov.
- The ISO Express CSV reports download without auth; API paths give the same data programmatically.
  Phase 2 ETL can start against the public CSV endpoint without waiting on either credential.

## Open decisions affecting sources

Tracked against `PLAN.md` → "Open questions for the team". Decision 2 closed 2026-07-28;
decisions 1 and 3 remain open.

1. **Canonical load dataset** — ISO-NE real-time system demand CSV vs. the Web Services
   API load feed. Both cover all-NE hourly demand; pick one as the schema's load source.
   (PLAN.md open question 5 / storage of denominators.)
2. ~~**Canonical wind dataset**~~ — **RESOLVED 2026-07-28 by Mitchell: EIA hourly
   `electricity/rto/fuel-type-data`.** Alexander had chosen ISO-NE Daily Generation by Fuel
   Type; Mitchell pointed at the EIA RTO hourly series instead, which settles the granularity
   flag — the charging model charges into the highest-wind-speed *hours* and a daily total
   cannot resolve that. Status of the two follow-ons:
   - **Granularity — closed.** EIA-930 hourly generation by fuel type, ISO-NE respondent,
     `WND` fuel type. Hourly, matching the load/LMP cadence.
   - **Auth — new.** The EIA v2 API requires a free registered API key; an unkeyed request
     returns `API_KEY_MISSING` (verified 2026-07-28). This is the project's first credentialed
     ingest source — the ISO Express CSVs need none. Register at
     https://www.eia.gov/opendata/register.php and keep the key out of the repo.
   - **Reconciliation — still open, now testable.** Alexander flagged he does not know whether
     ISO-NE and EIA agree. Both report the same ISO-NE wind fleet, so cross-check the EIA
     hourly series summed to daily against the ISO-NE daily report before either anchors a
     result. Keep the ISO-NE daily report as the reconciliation reference.
   (PLAN.md open question 5.)

3. **Winter months are missing from the current pull.** Mitchell set the MVP v1.0 scope on
   2026-07-28 as five winters — 2021/22 through 2025/26, **December 1 – February 28/29**.
   Alexander's spec pulls Jan/Feb/Mar/Jun/Jul across 2022–2026, which covers every Jan/Feb
   pair but **contains no December**. Five files are needed on the same endpoint and
   `locationId`: `whlsecost_hourly_4000_202112.csv`, `...202212.csv`, `...202312.csv`,
   `...202412.csv`, `...202512.csv`. A top-up, not a re-pull. Without them each winter in the
   study loses its first month, including December cold snaps.

   **Season definitions (Mitchell, 2026-07-28):** winter is **December 1 – February 28/29**,
   summer is **June 1 – September 30**. Summer is deferred past v1.0 ("we don't need to check
   summer until later versions"), so it gates nothing — but the pull is short there too:
   Alexander has **Jun/Jul only**, missing **August and September** in every year. That is ten
   more files when summer is picked up (`whlsecost_hourly_4000_YYYY08.csv` and `...YYYY09.csv`
   across 2022–2026). March belongs to neither season. Keep the March files, but they sit in
   no defined study window and must not be pooled into either seasonal denominator.

Until each is decided, treat the `candidate` source as provisional and do not hard-code it
as the canonical input.

## [3] Provenance of the 17,395-hour NEMA series

Answered by Alexander on 2026-07-28, closing a question open since 2026-07-24.

The series came entirely from the public ISO Express portal. No credentials, no API key,
and no account login at any point.

| Field | Value |
|---|---|
| Portal | ISO-NE ISO Express, hourly wholesale load cost |
| Report tree | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/whlsecost-hourly-system |
| CSV endpoint | `/transform/csv/whlsecost/hourly?month=YYYYMM&locationId=4008` |
| File pattern | `whlsecost_hourly_4008_YYYYMM.csv` |
| Location ID | 4008 (NEMA/Boston load zone); 4000 is New England system-wide |
| Months | January, February, March, June, July |
| Years | 2022–2026 |
| File count | 24 monthly CSVs |

One report tree serves the whole system and every zone; `locationId` selects which. Use the
tree URL above rather than the per-zone page — the zonal pages are views onto the same
report, and the ETL wants the parameterized endpoint anyway. Hourly history on this report
runs about seven years back, which comfortably covers 2022–2026.

**This unblocks Phase 2 ETL.** The board recorded Phase 2 as blocked on ISO-NE Web Services
credentials. For this dataset those credentials are not required, so the extract can be
pointed at the public CSV endpoint and run now.

Two things to check before the series anchors a result:

- Five months across five years is 25 files, and the count reported is 24. Identify the
  missing month before treating year coverage as uniform. July 2026 is the likely gap,
  being the current month.
- 24 monthly files over these months is roughly 17,400 hours, which agrees with the
  reported 17,395 to within the hours that daylight-saving transitions add and remove.
  The count is consistent; it is not by itself proof that no rows are missing.

**Scope update, 2026-07-28 — confirmed by both Mitchell and Alexander.** Study scope is all
of New England (ISO-NE system-wide), not NEMA/Boston. The 17,395-hour series above is
`locationId=4008` (NEMA). Alexander's 2026-07-28 spec for the system-wide pull, verbatim:

| Field | Value |
|---|---|
| Portal | ISO-NE ISO Express, hourly wholesale load cost |
| Report tree | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/whlsecost-hourly-system |
| CSV endpoint | `/transform/csv/whlsecost/hourly?month=YYYYMM&locationId=4000` |
| File pattern | `whlsecost_hourly_4000_YYYYMM.csv` |
| Location ID | **4000 (New England system-wide)**; 4008 is NEMA/Boston zone only |
| Months | January, February, March, June, July |
| Years | 2022–2026 |
| Scope | "We are using the entire NE and not NEMA/Boston" |
| Wind generation | ISO-NE Daily Generation by Fuel Type, https://www.iso-ne.com/isoexpress/web/reports/operations/-/tree/daily-gen-fuel-type ("i do not know if its same with the EIA data") |

**Confirmed as recorded, 2026-07-28 (Alexander).** The table above is Alexander's spec as
given and is not edited. Two rows were **later changed by Mitchell**, and those changes are
Mitchell's rather than Alexander's:

| Row | Alexander's spec | Superseded by Mitchell, 2026-07-28 | Why |
|---|---|---|---|
| Months | Jan, Feb, Mar, Jun, Jul (2022–2026) | **add December** (2021–2025) | Winter is defined as Dec 1 – Feb 28/29, so every winter in the study needs its December. Five extra files on the same endpoint and `locationId`: `whlsecost_hourly_4000_202112.csv` … `...202512.csv`. Nothing about the load/LMP pull itself changes |
| Wind generation | ISO-NE Daily Generation by Fuel Type | **EIA `electricity/rto/fuel-type-data`** (EIA-930 hourly, `respondent=ISNE`, `fueltype=WND`) | The ISO-NE report is **daily**; charging targets the highest-wind-speed *hours*, which a daily total cannot resolve. Alexander's own "i do not know if its same with the EIA data" is now directly testable — the ISO-NE daily report stays as the reconciliation reference, so it is still doing work. Note the EIA v2 API needs a free registered key; ISO Express needs none |

Everything else in Alexander's spec stands unchanged: portal, report tree, CSV endpoint, file
pattern, location ID, and the New England scope, which he confirmed independently of Mitchell.

**Season definitions (Mitchell, 2026-07-28):** winter = **Dec 1 – Feb 28/29**, five winters
2021/22 → 2025/26 for MVP v1.0. Summer = **Jun 1 – Sep 30**, deferred past v1.0 and short by
August and September in the current pull. March belongs to neither season.

Same report tree and endpoint as the NEMA pull — no new source, no credentials — only the
`locationId` changes, so the ETL should be parameterized on it and run both scopes from one
code path. The 4008 series stays useful as the eastern-Massachusetts sub-region where the
storage actually lands. Wind moves to the ISO-NE daily report; see open decision 2 for the
daily-vs-hourly and EIA-reconciliation flags. See `HANDOFF.md` → "Clarifications received,
2026-07-28".

## [4] Theoretical shallow-water StEnSea variant

Fraunhofer's built/planned units are full-depth (500–800 m). No shallow-water sphere exists;
the Gulf of Maine's deepest water (~275 m in the near basins, 379 m at Georges) does not
reach StEnSea's native depth, so Mitchell proposed a **theoretical shallower variant** for
this study. It is a design assumption, not a product spec. Physics for the scenario input:

- **Round-trip efficiency 0.70** (Mitchell, 2026-07-28). **Corrected 2026-07-28:** this
  section previously said "0.75–0.80 published, recommend 0.75" and attributed the band to
  Fraunhofer. Fraunhofer publishes a **single 80%** figure for the full-scale design; the
  0.75 was our own haircut presented as sourced. Their built/planned units run **lower** —
  40% at 1:10 and 60% at 1:3 — though that series confounds machine scale with depth, so it
  proves nothing about head-independence in either direction. 0.70 sits between the built 1:3
  figure and the 1:1 design figure and is the better-supported choice for a novel shallow
  variant. Source: https://www.iee.fraunhofer.de/en/topics/stensea.html
- **Energy per sphere scales ~linearly with depth (pressure head).** A 30 m sphere at 200 m
  and 0.70 gives **4.5–5.0 MWh** (0.5–1.0 m wall). Sanity check on the model: the same
  geometry reproduces Fraunhofer's own 20 MWh at **701–779 m**, inside their published
  600–800 m band, so the shallow figure rests on a model that recovers the manufacturer's
  headline number. Slightly below the 5.7–6.7 MWh/unit in `PROJECT_STATE_2026-07-28.md`
  Tier 5, which assumed 0.75–0.80 efficiency rather than 0.70.

A specific candidate depth still needs a depth-vs-distance point from the bathymetry viewers
in the reference table above before it anchors a siting scenario.

**2026-07-28: this model is now executable**, in `src/owr/storage_physics.py`. The
701–779 m depth band (recovering Fraunhofer's 20 MWh) and the 4.49–5.00 MWh shallow-variant
band above are pinned as tests in `tests/test_storage_physics.py`, not just prose. The
module takes efficiency as an explicit argument and ships no default, so it does not answer
the round-trip-vs-one-way question below — it only makes both readings computable.

### Mitchell's 2026-07-28 spec for the shallow variant, and its arithmetic

Supplied as "interpolated from the other prototypes", explicitly open to revision:

| Parameter | Mitchell's value | Check |
|---|---|---|
| Power | 1.67 MW (33.33% of 5 MW) | consistent with `5 MW × 200/600` **only at η≈0.814**, not at 0.70. Note Fraunhofer states **5–7 MW**; 5 is the conservative end |
| Energy capacity | 20 MWh | **inconsistent** with 30 m + 200 m; that geometry yields 4.5–5.0 MWh |
| Outer diameter | 30 m | Fraunhofer full-scale figure — verified |
| Efficiency | 0.70 | adopted. **Verified that Mitchell is right**: Fraunhofer's full-scale design is 80% and no unit exceeds it, so the previously recommended 0.85 was above the manufacturer's best case |
| Hydraulic head | 200 m | shallow-variant target |
| Flow rate | ~1.02 m³/s | this is the **5 MW / 600 m / η≈0.81** flow, carried over unscaled |

Using `P = ρ·g·Q·h·η` with ρ=1025 kg/m³, g=9.81 m/s²:

- **Power / flow / efficiency cannot all hold.** Q=1.02, h=200, η=0.70 → **1.436 MW**.
  For 1.67 MW at η=0.70, **Q = 1.186 m³/s**. Recommend keeping 1.67 MW and restating
  Q ≈ **1.19 m³/s**.
- **Energy / geometry cannot both hold.** 20 MWh at h=200, η=0.70 needs **~51,100 m³** of
  working volume — an internal diameter of **~46.05 m**, i.e. an **outer diameter of
  ~47.05 m** at a 0.5 m wall (every other diameter in this section is an outer diameter; this
  one was previously mislabeled the same way, corrected 2026-07-28). A 30 m sphere is
  14,137 m³ gross (11,494–12,770 m³ internal at a 0.5–1.0 m wall) → **4.5–5.0 MWh** at 200 m.
  **The model is validated against Fraunhofer:** the same geometry puts 20 MWh at
  **701–779 m** (η=0.80), inside their published 600–800 m band, for any wall thickness in
  0.5–1.0 m. So the 20 MWh figure is the full-depth rating and the ~5 MWh shallow figure
  comes from a model that independently recovers the manufacturer's own headline number.
- **Consequence.** Duration is 12 h if 20 MWh/1.67 MW holds, ~3 h at the geometry-consistent
  ~5 MWh. Sphere count for a 40,000–60,000 MWh system reserve moves from ~2,000–3,000 to
  **~8,000–13,000**. Both rest on Report A's 40–60 GWh target, whose own derivation is loose
  — see `FACT_CHECK_REPORT.md` addendum, internal inconsistency 7.

Resolution: fix two of {outer diameter, head, energy per sphere} and let the third follow.
Pending Mitchell's choice, the modeling default is 30 m + 200 m + ~5 MWh + 1.67 MW.

One further point for `config.py`: `P = ρ·g·Q·h·η` is the **generating** form. Pumping is
`P = ρ·g·Q·h / η`. Whether 0.70 is the round-trip figure (→ ~0.837 each way) or the one-way
turbine figure (→ ~0.49 round-trip) must be stated before it becomes `default_efficiency`.

### 2026-07-31: published sphere geometry found — the 0.5–1.0 m wall band is wrong

Source: Bernhard Ernst (Fraunhofer IEE), *StEnSea: Stored Energy in the Sea*, I Congreso de
Sistemas Eléctricos Aislados, Tenerife, 2024-11-21. Slide "StEnSea – Technical data (scale
1:1)", geometry credited to Hochtief, 2017.
<https://intranet.coiitf.es/images/stories/SEATF/05.%20Ernst%20Bernhard%20-%202024_11_21_Teneriffa_StEnSea_Fraunhofer_Ernst_small.pdf>
(read in full; the slide is a table plus an FE strain plot carrying the inner-diameter dimension)

Published 1:1 figures: concrete; turbine power 5 MW; discharge time 4.2 h; **discharge
capacity 21 MWh**; efficiency **70–80%**; diameter "ca. 30"; **wall thickness 2.7 m**;
**volume 12,000 m³**; pressure **70 bar / 700 m**; weight 20,000 t (> buoyancy). The FE
figure labels **inner diameter 28.60 m**, so "ca. 30 m" is the nominal/inner figure and the
**outer diameter is ~34.0 m**.

Two independent consistency checks on that geometry:

- π/6 × 28.60³ = 12,249 m³ against the published 12,000 m³ working volume.
- shell volume π/6 × (34.0³ − 28.60³) = 8,331 m³; against the published 20,000 t that implies
  **2,401 kg/m³**, i.e. reinforced concrete. The 2.7 m wall is load-bearing, not a typo.

The 1:3 unit corroborates: 9 m outer, 0.5 m wall → π/6 × 8³ = 268 m³ against a published
270 m³.

**Consequences.**

1. **The 0.5–1.0 m wall band used throughout this file and in `tests/test_storage_physics.py`
   is 3–5× too thin.** Real `t/D_outer` is **0.079** (1:1) and **0.056** (1:3); the assumed
   band is 0.017–0.033.
2. **Energy results survive by coincidence.** The model's 30 m-outer sphere at a 0.5–1.0 m
   wall gives 11,494–12,770 m³ internal, which brackets the true 12,000 m³ of a 34 m-outer
   sphere with a 2.7 m wall. Volume is right, geometry is not. At the published 12,000 m³ the
   shallow variant is **4.79 MWh** at 200 m / η=0.70, inside the 4.5–5.0 MWh band already
   recorded above.
3. **The "one big sphere uses less concrete" argument collapses.** With `t = k·D`, shell
   volume is `π/6·D³·[1 − (1−2k)³]` and internal volume is `π/6·D³·(1−2k)³`, so concrete per
   m³ of storage is `[1 − (1−2k)³]/(1−2k)³` — **independent of D**. At Fraunhofer's own
   k = 0.0794, both a single sphere sized for 51,146 m³ internal (46.1 m inner / 54.7 m outer
   / 4.35 m wall) and 4.18 Fraunhofer-geometry spheres come to **34,785 m³ of concrete**,
   ratio **1.0000**. The 38% saving claimed for a single 47 m sphere depends entirely on
   holding the wall at 0.5 m while the diameter grows 57%.
4. **η = 0.70 is confirmed conservative-but-published** — it is the bottom of Fraunhofer's own
   stated 70–80% band, not below it.
5. The headline capacity is **21 MWh**, not 20. The 20 MWh figure used in `[4]` and in the
   `config.py` default comes from the scale table on a later slide, which rounds. Either is
   defensible; state which.

**Open.** No wall thickness or pressure rating is published for a 200 m-rated sphere, and
70 bar / 700 m is the only rating point given. A shallow variant sees ~20 bar, so its wall
should be thinner than 2.7 m — but the scaling law between the two is not in this source and
should not be invented. Sizing the shallow variant's wall is the remaining blocker on any
concrete-volume or cost comparison.
