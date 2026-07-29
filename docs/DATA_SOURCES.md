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

## Reference sources (inform design, not ingested)

| Source | URL | Role |
|---|---|---|
| StEnSea seafloor storage specs (Fraunhofer) | https://www.iee.fraunhofer.de/en/topics/stensea.html | Storage-asset parameters (power MW, energy MWh, efficiency 0.75–0.80); note only a 1:10 unit built, 1:3 planned — model the full-scale 1:1 *design*, and see [4] for the theoretical shallow-water variant |
| EIA New England dashboard | https://www.eia.gov/dashboard/newengland/electricity | Demand/price context, sanity-checking ingested values |
| gridstatus library | https://github.com/gridstatus/gridstatus | ETL wrapper over ISO-NE + EIA (pragmatic extract layer) |
| NOAA NCEI Bathymetric Data Viewer | https://www.ncei.noaa.gov/maps/bathymetry/ | Interactive seafloor-depth map (GEBCO, coastal relief, multibeam layers); draw the Gulf of Maine depth-vs-distance curve for a candidate StEnSea site |
| GEBCO gridded global bathymetry | https://www.gebco.net/data_and_products/gridded_bathymetry_data/ | Downloadable depth grid behind most viewers; use for a numeric depth profile |
| CCOM/UNH Western Gulf of Maine bathymetry & backscatter | https://www.ccom.unh.edu/research/research-projects/wgom-bathymetry-backscatter | High-resolution multibeam survey of the western Gulf of Maine (the water nearest Cape Cod / Provincetown) |
| Jordan Basin deep-water study (NOAA) | https://repository.library.noaa.gov/view/noaa/53045/noaa_53045_DS1.pdf | Primary-source depths for the Gulf's deep basins (Wilkinson/Jordan ~275 m, Georges 379 m) |

Additional diagram/imagery references live in `DIAGRAM_REFERENCES.md`; claim-verification
sources live in `FACT_CHECK_REPORT.md`. This file is for ingest and data provenance only.

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
   study loses its first month, including December cold snaps. Mar/Jun/Jul are the optional
   summer extension (Mitchell: "March 1st to August 31st [is] up to you, we don't need to
   check summer until later versions") — keep them, do not gate v1.0 on them.

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
| Months | January, February, March, June, July — **plus December, added by Mitchell's 2026-07-28 scope; see open decision 3** |
| Years | 2022–2026 (December files are 2021–2025) |
| Wind generation | ISO-NE Daily Generation by Fuel Type ("i do not know if its same with the EIA data") — **superseded 2026-07-28 by EIA hourly `electricity/rto/fuel-type-data`; the ISO-NE daily report stays as the reconciliation reference** |
| Study window | **Dec 1 – Feb 28/29, winters 2021/22 → 2025/26** (Mitchell, MVP v1.0). Mar–Aug optional, deferred past v1.0 |

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

- **Round-trip efficiency ≈ 0.75–0.80** (recommend 0.75). Efficiency is governed by the
  pump-turbine and motor-generator, not the head, so the shallow variant keeps the
  full-scale band. Source: Fraunhofer StEnSea (0.75–0.80 published).
- **Energy per sphere scales ~linearly with depth (pressure head).** A 20 MWh unit at
  ~700 m falls to ~5.7 MWh at ~200 m (≈200/700). This matches the 5.7–6.7 MWh/unit figure
  in `PROJECT_STATE_2026-07-28.md` Tier 5.

A specific candidate depth still needs a depth-vs-distance point from the bathymetry viewers
in the reference table above before it anchors a siting scenario.

### Mitchell's 2026-07-28 spec for the shallow variant, and its arithmetic

Supplied as "interpolated from the other prototypes", explicitly open to revision:

| Parameter | Mitchell's value | Check |
|---|---|---|
| Power | 1.67 MW (33.33% of 5 MW) | consistent with `5 MW × 200/600` **only at η≈0.814**, not at 0.70 |
| Energy capacity | 20 MWh | **inconsistent** with 30 m + 200 m; that geometry yields 4.5–5.5 MWh |
| Outer diameter | 30 m | Fraunhofer full-scale figure |
| Efficiency | 0.70 | adopted; supersedes the 0.75 recommended above and Report B's 0.85 |
| Hydraulic head | 200 m | shallow-variant target |
| Flow rate | ~1.02 m³/s | this is the **5 MW / 600 m / η≈0.81** flow, carried over unscaled |

Using `P = ρ·g·Q·h·η` with ρ=1025 kg/m³, g=9.81 m/s²:

- **Power / flow / efficiency cannot all hold.** Q=1.02, h=200, η=0.70 → **1.436 MW**.
  For 1.67 MW at η=0.70, **Q = 1.186 m³/s**. Recommend keeping 1.67 MW and restating
  Q ≈ **1.19 m³/s**.
- **Energy / geometry cannot both hold.** 20 MWh at h=200, η=0.70 needs **~51,100 m³** of
  working volume — a **~46 m** sphere. A 30 m sphere is 14,137 m³ gross (~11,500–12,100 m³
  internal at a 0.75–1.0 m wall) → **4.5–5.5 MWh** at 200 m. The same 30 m sphere at
  600–800 m and η=0.80 gives 15–21 MWh, which is the source of the 20 MWh figure.
- **Consequence.** Duration is 12 h if 20 MWh/1.67 MW holds, ~3 h at the geometry-consistent
  ~5 MWh. Sphere count for a 40,000–60,000 MWh system reserve moves from ~2,000–3,000 to
  **~8,000–12,000**.

Resolution: fix two of {outer diameter, head, energy per sphere} and let the third follow.
Pending Mitchell's choice, the modeling default is 30 m + 200 m + ~5 MWh + 1.67 MW.

One further point for `config.py`: `P = ρ·g·Q·h·η` is the **generating** form. Pumping is
`P = ρ·g·Q·h / η`. Whether 0.70 is the round-trip figure (→ ~0.837 each way) or the one-way
turbine figure (→ ~0.49 round-trip) must be stated before it becomes `default_efficiency`.
