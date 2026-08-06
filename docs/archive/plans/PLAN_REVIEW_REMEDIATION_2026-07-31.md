# Remediation plan, adversarial review of 2026-07-31

Subject: the nine findings in `docs/ADVERSARIAL_REVIEW_2026-07-31.md`.
Nothing here commits anything. Gate D is a user check-off before the first `git add`.
Findings 1 to 4 are docs and gate the pending commit; 5 to 9 are code nits on a follow-up branch.

## 0. Baseline (main at ea74647, 2026-07-31, before any edit)

| Check | Command | Result |
|---|---|---|
| Tests | `uv run pytest` | 323 passed, 3 skipped, 1 pre-existing warning |
| Lint | `uv run ruff check .` | clean |
| Tree | `git status --short` | `M docs/DATA_SOURCES.md`, 2 untracked review docs |
| p90 | `uv run etl transform --input data/load_2022.csv … --input data/load_2026.csv --season winter` | `threshold_mwh = 385832.584`, 270 days, 4 windows incl. 2026-01-24 to 2026-02-03 |
| Finding 1 integral | see A3 | 4,530,391.30625 MWh over 11 complete days |
| Finding 2 | `generating_energy_mwh(12000, 200, 0.70)` | 4.69245 MWh; at 12,249 m³, 4.789818 MWh |

## 1. Ground rules

1. No `git commit`, `merge`, or `push` before Gate D.
2. Stage by explicit path only; local scratch directories must not enter the index.
3. `docs/HANDOFF.md` and `RESUME_LOG.md` are gitignored and stay that way.
4. `data/*.csv` is gitignored, so any number derived from it carries the file-header provenance values.
5. Uncommitted text is corrected in place; committed text gets a dated append pointer. Everything above `docs/DATA_SOURCES.md:243` is committed.
6. Branch first: cut `review-remediation-2026-07-31` from ea74647 before the Gate D commit.
7. `docs/ADVERSARIAL_REVIEW_2026-07-31.md` is committed verbatim; disposition is recorded in section 7, not by editing the review.

## Gate A: documentation fixes (findings 1, 2, 4)

### A1. Finding 1: replace the derived event energy with the measured one

`docs/ARCHITECTURE_REVIEW_2026-07-31.md`, section D4, lines 233–245. 4,244,163 = 385,833 × 11, a lower bound, not the event. Measured: 4,530,391 MWh, share 0.71%. Recompute rather than relabel; the measurement exists. Replace lines 233–245 with:

```markdown
### D4. The scale sanity check the document never performs

Against the project's own measured p90 of **385,833 MWh/day**:

| Quantity | MWh | Denominator | Share |
|---|---|---|---|
| Nameplate 60,000 MWh | 60,000 | one p90 winter day (385,833 MWh) | **15.5%** |
| Usable after floor + 80% budget | 32,160 | one p90 winter day (385,833 MWh) | **8.3%** |
| Usable after floor + 80% budget | 32,160 | the 11-day Jan–Feb 2026 event (4,530,391 MWh) | **0.71%** |

The event figure is the **measured** integral over 2026-01-24 → 2026-02-03 through the same
local-day rollup that produced the p90 — eleven complete days, 24.0 local hours and 288
five-minute intervals each (`gridstatus.ISONE().get_load()`, `gridstatus==0.36.0`, retrieved
2026-07-30T18:31:23Z). It is **not** p90 × 11. That product, 4,244,163 MWh, is a lower bound,
because every day inside a window sits at or above the threshold by construction. The command
is in `docs/FACT_CHECK_REPORT.md` → "Multi-day stress events".

One caveat on the window: its last day, 2026-02-03, totals 385,833.412 MWh against a
threshold of 385,832.584 and clears it by 0.83 MWh. Drop that day and the event reads ten
days and 4,144,558 MWh, moving the share 0.71% → 0.78%. The argument rests on the order of
magnitude, which does not move.

And 4,320 MW is roughly 22% of ISO-NE's winter peak — a single asset larger than any
storage facility in the interconnection. Neither figure is discussed. The architecture
should not be able to run a scenario this size without printing that ratio.
```

Folded in beyond the number: per-row denominator column (old header was wrong for row 3), row-3 label fixed to match, and the 2026-02-03 margin (a planning find, not in the review; it closes the next attack on the same number). Check while editing: 60000/385833 = 15.55%, 32160/385833 = 8.34%, 32160/4530391 = 0.7099%, 32160/4144558 = 0.776%.

### A2. Finding 2: pair 4.69 MWh with 12,000 m³

`docs/DATA_SOURCES.md`, consequence 2, lines 275–279, uncommitted, correct in place. Replace the last sentence with:

```markdown
   At the published **12,000 m³** working volume the shallow variant is **4.69 MWh** at
   200 m / η=0.70; at the **12,249 m³** the 28.60 m inner diameter implies geometrically it
   is **4.79 MWh**. Both sit inside the 4.5–5.0 MWh band already recorded above, so the
   249 m³ discrepancy between the published and geometric volumes changes nothing
   downstream.
```

Verify:

```
uv run python -c "from owr.storage_physics import generating_energy_mwh as e; \
  print(e(volume_m3=12000.0, head_m=200.0, efficiency=0.70), \
        e(volume_m3=12249.0, head_m=200.0, efficiency=0.70))"
```

Expected: `4.692450... 4.789818...`.

### A3. Record the measured event energy in a tracked file

`docs/FACT_CHECK_REPORT.md`, after the "Four multi-day events…" paragraph (~line 415). `docs/HANDOFF.md` is gitignored, so the reproduce command lives here. Insert:

````markdown
**Event energy, measured 2026-07-31.** The 11-day event integrates to **4,530,391 MWh**
across its eleven complete days (24.0 local hours and 288 five-minute intervals each). This
is the measured integral, **not** p90 × 11; that product, 4,244,163 MWh, is a lower bound,
since every day in a window sits at or above the threshold by construction. The window's
last day clears the threshold by 0.83 MWh (385,833.412 against 385,832.584), so a ten-day
reading of the same event at 4,144,558 MWh is one rounding away — worth stating wherever the
eleven-day figure is published.

Reproduce (the `data/*.csv` pulls are local-only per `.gitignore`; each file carries its
provenance banner in the header):

```
uv run etl transform --input data/load_2022.csv --input data/load_2023.csv \
  --input data/load_2024.csv --input data/load_2025.csv --input data/load_2026.csv \
  --season winter --out /tmp/daily_all.csv

python3 -c "import csv; rows=[r for r in csv.DictReader(open('/tmp/daily_all.csv')) \
  if '2026-01-24' <= r['date'] <= '2026-02-03']; \
  print(len(rows), sum(float(r['load_mwh']) for r in rows))"
```

Expected: `threshold_mwh = 385832.584`, `population_days = 270`, the four-window list above,
then `11 4530391.30625`.
````

Write the command block as a single triple-backtick fence inside ordinary markdown; check the rendered file.

### A4. Finding 4: dated pointers at the contradicted sites

Four sites. Scope: claims about what Fraunhofer publishes get a pointer; ordinary uses of the 0.5–1.0 m modeling geometry do not.

**A4a, `docs/DATA_SOURCES.md:31`** (reference-table StEnSea row). Append in the cell after "…see [4] for the theoretical shallow-water variant":

```
**Superseded 2026-07-31** — the Tenerife slide deck (see "2026-07-31: published sphere
geometry found" below) publishes 34.0 m OD / 28.60 m ID / 2.7 m wall / 12,000 m³ /
21 MWh / **70–80%** for the 1:1 design. Read the figures in this cell as the
iee.fraunhofer.de landing-page summary; the slide deck is the primary geometry source
```

**A4b, `docs/DATA_SOURCES.md:184–191`** (efficiency bullet, the recorded reason for calling η=0.70 conservative). Append after the `Source:` line, indented inside the bullet:

```markdown
  **Superseded 2026-07-31 — the reason, not the conclusion.** Fraunhofer publishes a
  **70–80%** band for the 1:1 design, not a single 80% figure: Ernst, Tenerife 2024-11-21,
  slide "StEnSea – Technical data (scale 1:1)", recorded in full below. 0.70 is therefore
  the bottom of the published band rather than a value below a single published figure.
  The choice of 0.70 stands and is now better supported. The sentence "Fraunhofer publishes
  a **single 80%** figure" does not stand.
```

**A4c, `docs/DATA_SOURCES.md:192–197`** (energy-scaling bullet, "4.5–5.0 MWh (0.5–1.0 m wall)"). A planning find, fourth statement of the same geometry. Append:

```markdown
  **Wall band superseded 2026-07-31:** the published 1:1 wall is **2.7 m**, not 0.5–1.0 m
  (see below). The 0.5–1.0 m pair is retained as the project's *modeling* geometry because
  its 11,494–12,770 m³ internal volume brackets the published 12,000 m³, so the 4.5–5.0 MWh
  result is unaffected. No wall thickness is published for a 200 m-rated sphere, which is
  why the modeling pair has not been replaced.
```

**A4d, `tests/test_storage_physics.py`**, comments only. Do not touch a constant, assertion, or test name; the review verified those numbers. After the constant block at lines 30–36:

```python
# Updated 2026-07-31 (docs/DATA_SOURCES.md, "published sphere geometry found"): the
# *published* 1:1 spec is 34.0 m OD / 28.60 m ID / 2.7 m wall / 12,000 m3 / 21 MWh /
# 70-80% efficiency (Ernst, Tenerife 2024-11-21). The 30 m OD + 0.5-1.0 m wall pair
# used below is the project's MODELING geometry, not the published spec. It is kept
# deliberately: its 11,494-12,770 m3 internal volume brackets the published 12,000 m3,
# so the energy results hold while the wall thickness does not, and no wall thickness
# is published for a 200 m-rated sphere to replace it with. FRAUNHOFER_EFFICIENCY =
# 0.80 is the top of the published 70-80% band, not a single published value.
```

Replace the line-57 header with:

```python
# --- Fraunhofer headline-number validation (load-bearing) ------------------
# What these pin: that the model recovers Fraunhofer's published 20 MWh inside their
# published 600-800 m depth band. What they do NOT pin: the wall thickness, which the
# 2026-07-31 note above records as superseded.
```

## Gate B: finding 3, the source PDF

**Resolved 2026-08-01 via path 1.** The reviewed PDF (download timestamp 2026-07-30 21:05 matching the review header, 35-page page tree) was found in `~/Downloads` and copied to `docs/source/2026-07-30_Software_Architecture_Documentation.pdf`. Remaining steps:

1. `git check-ignore -v docs/source/2026-07-30_Software_Architecture_Documentation.pdf` must print nothing.
2. Spot-check three cheap, hard-to-coincide claims: 35 pages; the parameter register under "no implicit assumptions shall be made" is `@` placeholders (B1); default scenario 3,000 units / 60,000 MWh / 4,320 MW / 200 transmission (B3) and two "Step 6" headings, first empty (B1, R14). Any miss: stop and report; a mismatched artifact is worse than none.
3. Edit `docs/ARCHITECTURE_REVIEW_2026-07-31.md` lines 2–3 to:

```markdown
Reviewed 2026-07-31. Source artifact: `docs/source/2026-07-30_Software_Architecture_Documentation.pdf`
(35 pages, "Software Architecture Documentation", downloaded 2026-07-30 21:05, stored
verbatim and unedited per the convention set in commit 6c6c3bf).
```

(Path 2, DRAFT marker with findings marked unverifiable, is no longer needed.)

## Gate C: verification before staging

All must pass before Gate D is offered.

| # | Command | Expected |
|---|---|---|
| C1 | `uv run pytest` | 323 passed, 3 skipped |
| C2 | `uv run ruff check .` | clean |
| C3 | A3's two commands | `385832.584`, 270 days, four windows, `11 4530391.30625` |
| C4 | A2's one-liner | `4.692450… 4.789818…` |
| C5 | `grep -rn "4,244,163\|0\.76%" docs/` | only the review's historical mentions and the lower-bound explanations from A1/A3 |
| C6 | `grep -rn "4\.79 MWh" docs/DATA_SOURCES.md` | only the 12,249 m³ sentence |
| C7 | `grep -c "2026-07-31" docs/DATA_SOURCES.md` | ≥ 4 |
| C8 | `git status --short` | intended paths only; no local scratch or gitignored files |
| C9 | `git diff` + open each untracked file | read every change before staging |

## Gate D: user check-off

Present and stop: the C9 diff, the C8 untracked list, the staging command, the commit message. Then three separate yeses: commit, merge to main, push (origin/main is six commits behind).

```
git checkout -b review-remediation-2026-07-31
git add docs/DATA_SOURCES.md \
        docs/FACT_CHECK_REPORT.md \
        docs/ARCHITECTURE_REVIEW_2026-07-31.md \
        docs/ADVERSARIAL_REVIEW_2026-07-31.md \
        docs/PLAN_REVIEW_REMEDIATION_2026-07-31.md \
        docs/source/2026-07-30_Software_Architecture_Documentation.pdf \
        tests/test_storage_physics.py
```

Commit message draft (no co-author trailer, no tool names):

```
Correct the event-energy figure and pointer the superseded sphere geometry

The architecture review reported the 11-day Jan-Feb 2026 event as 4,244,163 MWh,
the p90 threshold times eleven days, a lower bound by construction. The measured
integral over 2026-01-24 to 2026-02-03 through the same local-day rollup is
4,530,391 MWh; the usable-storage share is 0.71%, not 0.76%. The conclusion is
unchanged. The measurement and reproduce command are in the fact-check report,
since the raw pulls stay local. The window's last day clears the threshold by
0.83 MWh, so a ten-day reading is one rounding away; stated wherever the figure
appears.

Fraunhofer's Tenerife deck publishes 34.0 m OD, 28.60 m ID, 2.7 m wall, 12,000 m3,
21 MWh, 70-80% efficiency. Three earlier sites still carried "30 m OD, 20 MWh, a
single 80% figure" and now carry dated pointers, including the 2026-07-28
correction that justified calling 0.70 conservative: 0.70 is the bottom of a
published band, not a value below a single figure. The 0.5-1.0 m modeling wall is
kept and labeled as modeling geometry; its volume brackets the published 12,000 m3
and no wall thickness is published for a 200 m-rated sphere.

At the published 12,000 m3 the shallow variant is 4.69 MWh, not 4.79; 4.79 is the
12,249 m3 geometric volume. Both sit inside the recorded 4.5-5.0 MWh band.
```

## Follow-up branch: code nits (findings 5–9)

Branch `etl-nits-2026-07-31`, cut after the Gate D commit. Independent of the docs commit; each item revertible alone.

### F5: `etl transform` rejects a multi-zone pool

`src/owr/etl/cli.py`, `_run_transform` (lines 144–182). `read_rows_csv` guarantees `row["zone"]` for the `load` dataset. Track zones and raise before `daily_loads_from_readings`, so the misleading duplicate-instant message can never fire first:

```python
zones: dict[str, str] = {}  # zone -> first input path that supplied it
...
for row in rows:
    zones.setdefault(row["zone"], path)
    readings.append(_reading_from_row(row, path))

if len(zones) > 1:
    listed = ", ".join(f"{z} ({p})" for z, p in sorted(zones.items()))
    raise ValueError(
        f"inputs mix {len(zones)} zones: {listed}. Pool one zone at a time — a "
        "threshold over two zones is neither zone's threshold."
    )
```

`ValueError` matches the existing exit-2 usage-error contract. Tests in `tests/test_etl_cli_transform.py`: overlapping-timestamp two-zone (exit 2, names zones and paths, no "duplicate absolute instant"); disjoint two-zone (exit 2, the silent-pooling case); same-zone (exit 0, unchanged output).

### F6: warn when an excluded day sits next to a stressed day

`src/owr/etl/transform.py`, `find_windows_per_winter` (lines 69–85). Use `warnings.warn`, keeping the module pure and the docstring's "gaps are not fatal here" contract. Inside the per-winter loop, after `result[label]`:

```python
incomplete = sorted(d.date for d in days if not d.complete)
if incomplete:
    stressed = {d.date for d in ordered if d.load_mwh >= threshold_mwh}
    adjacent = sorted(
        d for d in incomplete
        if d - timedelta(days=1) in stressed or d + timedelta(days=1) in stressed
    )
    if adjacent:
        warnings.warn(
            f"{label}: {len(adjacent)} incomplete day(s) adjacent to a stressed day "
            f"({', '.join(d.isoformat() for d in adjacent)}). A window there may be "
            "split or dropped; backfill those days and rerun before publishing.",
            UserWarning,
            stacklevel=2,
        )
```

Get right: `>=` to match `find_stress_windows_at_threshold`; compute inside the per-winter loop so summer days never trigger; an incomplete day is never itself stressed (its total is understated), the warning is about complete neighbours. Add `import warnings`, `from datetime import date, timedelta`; extend the docstring with the false-negative direction. Tests in `tests/test_etl_transform.py`: adjacent incomplete day warns and windows are unchanged; no stressed neighbour, no warning; different winter, no warning; no incomplete days, no warning.

**Acceptance criterion, measured on the shipped CSVs:** the only in-winter incomplete day is 2024-01-31 (23.83 h); neighbours 357,946 and 340,089 MWh, both under threshold. The warning must NOT fire on the shipped data and C3's output must stay byte-identical. If it fires, the predicate is wrong.

### F7: document `DayProfile`'s 24-hour assumption

`src/owr/models.py:15`, comment only (latent: stress windows are Dec–Feb, DST is Mar/Nov):

```python
# Winter-only assumption, made explicit 2026-07-31. `owr.etl.daily` correctly produces
# 23- and 25-hour local days across DST transitions (local_day_hours), and DayProfile
# rejects them. That is safe only while the study window is Dec 1 - Feb 28/29, which
# contains no transition. Shoulder-season or full-year data reaches DayProfile through
# `scenario_input.read_day_profiles` and `api.app`, and both would raise there. Fix by
# carrying per-day hour counts, not by loosening this check.
HOURS_PER_DAY = 24
```

Optional: a test pinning that a 23-value `hourly_load_mw` raises `ValueError`.

### F8: document the divergent `severity_reduction` guards

Three implementations, not two: `metrics.py:22–27` raises on `baseline_peak_mw <= 0`; `cli.py:419–425` returns 0.0; `api/app.py:56–59` returns 0.0 then delegates. Documentation only; `tests/test_metrics.py:24` pins the raise. Add to the `metrics.py` docstring:

```
Raises on a non-positive baseline: with no baseline peak there is no fraction to
report, and returning 0.0 would read as "the reserve did not help", which is a
different claim. The two report paths that must not abort a run —
``owr.cli._severity_reduction`` and ``owr.api.app._severity_reduction`` — guard the
input themselves and return 0.0. The divergence is deliberate as of 2026-07-31: this
function is the strict one, the report paths degrade. Changing either side without
the other reintroduces the inconsistency.
```

Extend the `cli.py:419` comment and add the matching one at `app.py:56`.

### F9: EIA extractor operational edges

`src/owr/etl/extract.py`.

(a) NaN aborts a whole pull (`wind_observations_from_records`, ~line 335). Keep fail-loud, make it actionable: collect non-finite timestamps, raise once with count and boundary timestamps:

```python
observations = []
bad: list[datetime] = []
for r in records:
    ts = _as_datetime(_first(r, _TS_KEYS))
    gen_mw = float(_first(r, _WIND_KEYS))
    if not math.isfinite(gen_mw):
        bad.append(ts)
        continue
    observations.append(WindObservation(ts=ts, gen_mw=gen_mw, horizon_days=horizon_days))

if bad:
    shown = ", ".join(t.isoformat() for t in bad[:5])
    more = f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""
    raise ValueError(
        f"{len(bad)} non-finite wind value(s), no rows written. "
        f"First ts={bad[0].isoformat()}, last ts={bad[-1].isoformat()}: {shown}{more}. "
        "Re-pull the surrounding window; the upsert is idempotent, so a narrower "
        "window can be re-run safely."
    )
```

`tests/test_etl_eia.py:154–159` matches `ts=2026-01-10T09:00:00`, still present; add one mixed good/NaN test asserting count and boundary timestamps.

(b) `get_dataset` end-exclusivity, unverifiable offline. Record as accepted risk in the `EiaWindSource` docstring (~line 470):

```
Accepted risk, recorded 2026-07-31: whether ``gridstatus.EIA().get_dataset(end=...)``
is end-exclusive is unverified — every test here uses a fake client, and no live pull
has run (the key is not provisioned). The ``Source`` protocol contract is ``[start,
end)``. If the provider is end-inclusive the pull gains one boundary hour, which the
idempotent upsert bounds to a duplicate-free extra row rather than corruption. First
live check: pull a two-day window and assert 48 rows, not 72.
```

Also `config.py:43`: "StEnSea 0.80" should read "StEnSea 0.70-0.80". Planning find, grouped here because it is `src/`.

### Follow-up verification

`uv run pytest` (323 + new tests), `uv run ruff check .`, and the C3 command byte-identical to the Gate C run. The last is the real acceptance test for F5 and F6.

## 7. Disposition record

| Finding | Severity | Disposition | Where |
|---|---|---|---|
| 1. Derived event energy reported as measured | major | | A1, A3 |
| 2. 4.79 MWh paired with 12,000 m³ | minor | | A2 |
| 3. Source PDF absent | major | resolved, path 1 (2026-08-01) | Gate B |
| 4. Un-pointered contradicted sites | major/minor | | A4a–d |
| 5. `etl transform` ignores `zone` | nit | | F5 |
| 6. Incomplete day deletes an event | nit | | F6 |
| 7. `DayProfile` hard-codes 24 hours | nit | | F7 |
| 8. Divergent `severity_reduction` guards | nit | | F8 |
| 9. EIA extractor edges | nit | | F9 |

Do-not-re-litigate list (no step may alter these): the p90 numbers (385,832.584 / 270 days / four windows), the physics band (4.4946–4.9936 MWh, head 700.90/778.71 m), the concrete-ratio argument, EFC wiring at `cli.py:445`, the `local_day_hours` fix. If a check moves one of these, stop and report.

## 8. Assumptions, risks, out of scope

Assumptions (each overridable): finding 1 is recomputed, not relabelled; the 0.5–1.0 m modeling wall stays (no published wall for a 200 m sphere; inventing a scaling law is the warned-against failure mode); the 4,530,391 figure is only reproducible with the local CSVs, mitigated by the recorded provenance values.

Risks: F6's warning must not change recorded output (guarded by the measured real-data check); F5 must not break the single-zone path (regression test); A3's nested fence must render (check the rendered file).

Out of scope: the fifteen R-series recommendations in the architecture review (rolling-horizon dispatch, LCOS, full-winter simulation, metric rebuilds). This plan only makes the record accurate.
