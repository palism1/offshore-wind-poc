# Adversarial review, 2026-07-31

Scope: work merged at ea74647 (storage physics, peak-window finder, EFC metric, p90 stress pipeline, EIA extractor, `etl transform`), the uncommitted `docs/DATA_SOURCES.md` edits, and the untracked `docs/ARCHITECTURE_REVIEW_2026-07-31.md`. Method: full suite (323 passed, 3 skipped), independent recomputation of the p90 pipeline from the shipped CSVs without importing `owr`, hand recomputation of every physics number in the docs.

## Findings, ranked

**1. Derived event energy reported as measured (major, uncommitted).** `docs/ARCHITECTURE_REVIEW_2026-07-31.md:241` states the Jan–Feb 2026 event as 4,244,163 MWh. That is exactly 385,833 × 11: threshold times days, a lower bound. Measured integral from `data/load_2026.csv`, 2026-01-24 to 2026-02-03, same local-day rollup: 4,530,391 MWh. Usable-storage share 0.71%, not 0.76%. Conclusion survives; labeling does not.

**2. 4.79 MWh paired with the wrong volume (minor, blocking in context).** `docs/DATA_SOURCES.md:277`: 1025 × 9.81 × 12,000 × 200 × 0.70 / 3.6e9 = 4.69 MWh at the published 12,000 m³. 4.79 MWh belongs to the 12,249 m³ geometric volume of the 28.60 m inner sphere. Both inside the 4.49–5.00 band; one-line relabel.

**3. Source PDF not in the repo (major).** The architecture review names "Software Architecture Documentation.pdf, 35 pages, downloaded 2026-07-30", but `docs/source/` holds only the Overview PDF. Commit 6c6c3bf set the store-the-artifact convention. Until it lands, all B-series findings are unverifiable from the repo.

**4. New geometry section contradicts three un-pointered sites (major for one).** `docs/DATA_SOURCES.md:247-297` establishes 34 m OD / 28.60 m ID / 2.7 m wall / 21 MWh / published 70–80% band. Still standing without pointers:
- `docs/DATA_SOURCES.md:31`: "30 m OD, 20 MWh, 5–7 MW, 80% round-trip".
- `docs/DATA_SOURCES.md:184-191`: "Fraunhofer publishes a single 80% figure", itself a 2026-07-28 correction the new source contradicts (Tenerife slide: 70–80%), and the recorded justification for η=0.70. Worst of the three.
- `tests/test_storage_physics.py:30-36` and the line-57 header still present 30 m OD + 0.5–1.0 m wall as Fraunhofer spec; the doc says that wall is 3–5× too thin.
Fix: one dated append pointer at each site.

**5. `etl transform` ignores the zone column (nit, code).** `src/owr/etl/cli.py:185-196` reads only `ts`, `load_mw`, `interval_minutes`. Overlapping two-zone inputs fail with a misleading "duplicate absolute instant"; disjoint ones silently pool into one threshold. Fix: assert a single zone.

**6. An incomplete day inside a real event deletes or shortens it (nit, code).** `find_windows_per_winter` (`src/owr/etl/transform.py:83`) drops incomplete days; adjacency then splits the run, so a 3-day event with a bad-meter middle day vanishes at `min_window_days=2`. Fix: warn when an excluded day is date-adjacent to a stressed day.

**7. `DayProfile` hard-codes 24 hours (nit, latent).** `src/owr/models.py:76` rejects the 23/25-hour days `owr.etl.daily` correctly produces around DST. Latent while stress windows are Dec–Feb. Fix: document the winter-only assumption.

**8. Divergent `severity_reduction` guards (nit).** `src/owr/metrics.py:26` raises on `baseline_peak_mw <= 0`; `src/owr/cli.py:423` returns 0.0. Duplication documented, divergence not.

**9. EIA extractor edges (nit).** One NaN hour aborts a pull with no skip path (`src/owr/etl/extract.py:334`). End-exclusivity of `gridstatus get_dataset` is unverifiable offline; the idempotent upsert bounds the damage to one boundary hour.

## Verified correct — do not re-litigate

- p90 pipeline, exact: winter p90 385,832.584 MWh over 270 complete days (median 345,417, min 279,576, max 430,209); summer 413,476 over 393 days; 324,043 intervals; four windows incl. the 11-day event. Matches CLI output and `docs/FACT_CHECK_REPORT.md:392`. All six DST days integrate to exactly 23.0/25.0 hours.
- Storage physics, exact: head recovery 700.90/778.71 m, shallow band 4.4946–4.9936 MWh, 1.436 MW at Q=1.02, Q=1.1863 for 1.67 MW, pump/turbine ratio 1/η². The head-band test survives the efficiency-convention ambiguity: if 0.80 is round-trip, the band shifts to 627–697 m, still inside 600–800.
- Concrete-ratio scale invariance, exact: 2,401 kg/m³, 268 vs 270 m³ for the 1:3 unit, 51,146 m³ for 20 MWh at 200 m/0.70, 34,785 m³ shell both ways, ratio 1.0000.
- EFC wiring: `cli.py:445` delegates to `metrics.equivalent_full_cycles`; the divide-by-efficiency variant is gone.
- `local_day_hours` UTC-conversion rationale is real Python behavior; the fix is correct.

Remediation plan: `docs/PLAN_REVIEW_REMEDIATION_2026-07-31.md`.
