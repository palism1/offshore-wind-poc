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
| ISO-NE hourly wholesale load cost, NEMA/Boston | https://www.iso-ne.com/isoexpress/web/reports/load-and-demand/-/tree/whlsecost-hourly-system (`locationId=4008`) | CSV | hourly | public download | The 17,395-hour NEMA load/LMP series already in use | confirmed — see [3] |
| EIA API v2 (opendata) | https://www.eia.gov/opendata/browser/ | REST/JSON | varies | EIA API key | Generation + capacity context (also wraps via `gridstatus`) | confirmed |
| EIA hourly generation by fuel type (RTO) | https://www.eia.gov/opendata/browser/electricity/rto/fuel-type-data | REST/JSON | hourly | EIA API key | Generation mix; wind-generation input to storage charge | candidate — see [2] |

## Reference sources (inform design, not ingested)

| Source | URL | Role |
|---|---|---|
| StEnSea seafloor storage specs (Fraunhofer) | https://www.iee.fraunhofer.de/en/topics/stensea.html | Storage-asset parameters (power MW, energy MWh, efficiency); note only a 1:10 unit built, 1:3 planned — model the full-scale 1:1 *design* |
| EIA New England dashboard | https://www.eia.gov/dashboard/newengland/electricity | Demand/price context, sanity-checking ingested values |
| gridstatus library | https://github.com/gridstatus/gridstatus | ETL wrapper over ISO-NE + EIA (pragmatic extract layer) |

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

These two `candidate` rows are blocked on team calls already tracked in
`PLAN.md` → "Open questions for the team":

1. **Canonical load dataset** — ISO-NE real-time system demand CSV vs. the Web Services
   API load feed. Both cover all-NE hourly demand; pick one as the schema's load source.
   (PLAN.md open question 5 / storage of denominators.)
2. **Canonical wind dataset** — EIA hourly generation-by-fuel-type (system-wide wind) vs.
   a dedicated offshore-wind proxy/forecast. Determines the charge-side input to storage.
   (PLAN.md open question 5.)

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
