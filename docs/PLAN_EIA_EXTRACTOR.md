# Implementation Plan — EIA-930 Wind Extractor + Real p90 Daily Stress Thresholds
Date: 2026-07-30 · Branch: `storage-physics-peak-window` · Status: PLAN ONLY
Revision: 2 (2026-07-30, after adversarial review — see the revision note at the end)

Two work streams that share the Phase 2 ETL surface:

- **A.** An EIA-930 hourly ISO-NE wind-generation extractor, wired into `src/owr/etl/`,
  with the API key never reaching logs, stdout, provenance strings, or the database.
- **B.** Running the ISO-NE load pull for five winters and computing the **real** daily-basis
  p90 threshold and stress-window list, replacing the two hourly-basis published numbers
  (16,750 MWh / 3,504 MWh) that `docs/FACT_CHECK_REPORT.md` [Contradicted #5] found are wrong
  by ~24× under the settled definition.

B depends on one piece of A's infrastructure (CSV output from `extract`) and on a load-side
granularity fix (Phase A4). Order the phases as written.

---

## 0. Environment and ground truth

`uv` manages the venv; **there is no `pip`**. The `etl` extra is installed as of this session:

```bash
uv pip install -e '.[etl]'    # gridstatus 0.36.0, psycopg 3.3.4, pandas 2.3.3
```

> **Hazard:** `uv sync --group dev` (the command in `README.md` and CI) **prunes** the
> environment back to the dev group and will uninstall `gridstatus`. Use
> `uv sync --group dev --extra etl` locally, or re-run the `uv pip install` afterwards.
> CI installs the dev group only, so **every new test must pass without `gridstatus`,
> `pandas`, or `requests` importable.** Keep all provider imports lazy, exactly as
> `extract._import_gridstatus()` already does.

### Facts established by reading the installed library (not assumed)

| Fact | Where |
|---|---|
| `gridstatus.EIA(api_key=None)` reads `EIA_API_KEY` from the env itself and raises a **key-free** `ValueError` when absent | `gridstatus/eia.py:42-58` |
| `EIA.get_dataset(...)` sends the key in the **`X-Api-Key` header**, never in the URL or query params | `gridstatus/eia.py:184-186` |
| `EIA.list_routes()` / `list_facets()` send the key as a **query parameter** — an HTTP error from those would put the key in the exception message. **Never call them.** | `gridstatus/eia.py:78-90` |
| `electricity/rto/fuel-type-data` is supported, pivots fuel types into wide columns, and produces `Interval Start`, `Interval End`, `Respondent`, `Respondent Name`, and a title-cased `Wind` column | `gridstatus/eia.py:918-982`, `eia_constants.py:3-19` |
| gridstatus sets `Interval End = period` and `Interval Start = period − 1h` for EIA hourly | `gridstatus/eia.py:805-809` |
| `EIA.get_dataset` has **no retry or backoff** — a single `raise_for_status()` per page | `gridstatus/eia.py:92-98` |
| `ISONE().get_load()` hits the public `fiveminutesystemload` CSV — **5-minute** intervals, `Native Load`, tz-localized to `US/Eastern`, one HTTP request per local day, retried 3× | `gridstatus/isone.py:160-185`, `isone.py:972-996` |
| The hourly ISO-NE load feed (`ISONEAPI.get_load_hourly`) needs `ISONE_API_USERNAME`/`ISONE_API_PASSWORD` — **still blocked**, so 5-minute is the only credential-free path | `gridstatus/isone_api/isone_api.py:60-71, 369` |
| `raw.hourly_wind (ts, gen_mw, forecast_mw, horizon_days)`, PK `(source, ts, horizon_days)` — already exists | `db/migrations/001_init.sql:36-47` |
| `raw.hourly_load` is referenced only by `extract.py` and the SQL; nothing in `api/pg_store.py` touches `raw.*` | grep across `src/`, `tests/` |
| `find_stress_windows` has exactly two production callers: `cli.py:326` (input pre-validated for date contiguity by `scenario_input.py:214-221`) and `api/app.py:138` (input **not** validated for contiguity or ordering — `_day_profiles` passes the request body straight through) | grep across `src/` |
| No mypy in CI; ruff selects `E, F, I, UP, B`, line length 100 | `pyproject.toml:56-66`, `.github/workflows/ci.yml` |

---

## Decision 1 — use `gridstatus`, not a direct EIA v2 call

**Use `gridstatus.EIA().get_dataset("electricity/rto/fuel-type-data", ...)`.**

1. `gridstatus` is already this repo's declared provider boundary (`extract.py` module
   docstring, `docs/DATA_SOURCES.md` reference table, the `etl` extra). A second HTTP client
   would fork that boundary for no gain.
2. It puts the key in a **header**, not a query string. A direct `urllib` call written by hand
   is likely to end up with `?api_key=...` in a URL, which is the single most common way this
   key leaks (into exception messages, proxies, and shell history).
3. It handles the v2 API's 5000-row pagination and stable-sort requirement. A five-year hourly
   pull is ~44,000 rows = 9 pages; hand-rolling that is real work with a real off-by-one risk.
4. The repo has **no runtime dependencies by design**. A direct call needs either `requests`
   (already transitively present in the `etl` extra, but not declared) or stdlib `urllib` plus
   hand-written JSON paging. Using `gridstatus` keeps the dependency boundary exactly where
   `pyproject.toml` already draws it.

Costs accepted: gridstatus pivots fuel types into wide columns, so the wind value arrives under
`Wind` rather than `value`; it reinterprets `period` as `Interval End` (risk **R3**); and it
does no retry on EIA (risk **R13**).

---

## Decision 2 — no new `raw.*` table for wind; one small documentation migration

`raw.hourly_wind` already fits EIA-930 realized generation:

- EIA-930 `fuel-type-data` is genuinely hourly, so the table name is accurate (unlike the load
  side — see A4).
- It has no `zone` column, which is correct: EIA-930 is balancing-authority grain. The
  respondent (`ISNE`) is encoded in `source = "eia930.isne.wind"`, which is also the first
  component of the PK, so a future second respondent cannot collide.
- `gen_mw` carries realized generation; `forecast_mw` stays `NULL`.
- `horizon_days` is in the PK, so Postgres makes it implicitly `NOT NULL`. **Realized rows use
  `horizon_days = 0`** ("zero days ahead" = actual). This is a convention, not a schema
  requirement — write it down (Q6).

Migration **004** is therefore *recommended but not required*: it only documents the convention
and adds a cheap guard. The extractor must work against a database created from `001` alone.

---

## Phase A1 — credential handling and redaction

**New file: `src/owr/etl/credentials.py`** (named `credentials`, not `secrets`, to avoid
shadowing the stdlib `secrets` module).

```python
EIA_API_KEY_ENV = "EIA_API_KEY"
_MIN_REDACTABLE_LEN = 8          # never redact a trivially short value

class MissingCredentialError(RuntimeError): ...

def require_eia_api_key(getenv: Callable[[str], str | None] = os.environ.get) -> None:
    """Raise MissingCredentialError if the key is absent or blank. Returns nothing —
    the value is never returned, stored, or interpolated into the message."""

def redact_secrets(text: str, getenv: Callable[[str], str | None] = os.environ.get) -> str:
    """Replace every occurrence of the EIA_API_KEY value with '***REDACTED***'.
    No-op when the variable is unset, blank, or shorter than _MIN_REDACTABLE_LEN."""
```

Design points that must survive review:

- `require_eia_api_key` binds the value to a local that is never formatted into the error.
  The message names the **variable**, the registration URL, and the escape hatch:
  ```
  no EIA API key. Set $EIA_API_KEY (free registration:
  https://www.eia.gov/opendata/register.php). The wind dataset needs it even for
  --dry-run, because --dry-run still performs the provider pull.
  ```
  This mirrors the shape and tone of `cli.py:49-53`'s missing-DSN message.
- The `_MIN_REDACTABLE_LEN` guard matters: a developer with `EIA_API_KEY=a` set would otherwise
  see every letter `a` in every message replaced. Real EIA keys are 40 characters.
- `redact_secrets` is **defence in depth, not the primary mechanism.** The primary mechanism is
  that our own code never puts the key into a string. Redaction exists so a *provider* leak
  cannot reach stdout.

**Tests (`tests/test_etl_credentials.py`):**

| # | Case |
|---|---|
| 1 | key absent → `MissingCredentialError`, message contains `EIA_API_KEY` and the registration URL |
| 2 | key set to `""` and to `"   "` → same error |
| 3 | key present → returns `None`, raises nothing |
| 4 | the error message from (1) does not contain a sentinel value that *is* set under a different variable name (guards against a wildcard env dump) |
| 5 | `redact_secrets` replaces a 40-char sentinel, including multiple occurrences in one string |
| 6 | `redact_secrets` is a no-op when the variable is unset |
| 7 | `redact_secrets` is a no-op for a 1-char key (over-redaction guard) |
| 8 | `redact_secrets` leaves text without the key byte-identical |

---

## Phase A2 — the wind observation, dataset, adapter, and source

**Edit: `src/owr/etl/extract.py`.** Everything below follows the existing layering — pure
adapters above, one provider class at the boundary.

### Observation

```python
@dataclass(frozen=True)
class WindObservation:
    """One hourly realized wind-generation reading (EIA-930, ISO-NE respondent)."""
    ts: datetime
    gen_mw: float
    forecast_mw: float | None = None
    horizon_days: int = 0     # 0 = realized; >0 reserved for forecast rows (see Q6)
```

### Dataset

```python
def _wind_values(obs: WindObservation) -> dict[str, object]:
    return {"ts": obs.ts, "gen_mw": obs.gen_mw,
            "forecast_mw": obs.forecast_mw, "horizon_days": obs.horizon_days}

HOURLY_WIND = RawDataset(
    name="wind",
    table="raw.hourly_wind",
    value_columns=("ts", "gen_mw", "forecast_mw", "horizon_days"),
    conflict_key=("source", "ts", "horizon_days"),
    to_values=_wind_values,
)

DATASETS = {ds.name: ds for ds in (HOURLY_LOAD, HOURLY_LMP, HOURLY_WIND)}
```

`build_upsert_sql(HOURLY_WIND)` then yields `ON CONFLICT (source, ts, horizon_days) DO UPDATE
SET gen_mw = …, forecast_mw = …, retrieved_at = …, source_query = …, dataset_version = …`,
which is correct without touching the generic machinery. `--dataset` choices come from
`sorted(DATASETS)` in `cli.py:99`, so `wind` appears automatically.

### Record adapter (pure, no pandas)

```python
_WIND_KEYS = ("Wind", "gen_mw", "MW", "wind_mw")

def wind_observations_from_records(
    records: Iterable[dict[str, object]], *, horizon_days: int = 0
) -> list[WindObservation]:
```

- Timestamp via the existing `_first(r, _TS_KEYS)` → `"Interval Start"` matches gridstatus's
  output. Reuses `_as_datetime`, so a pandas-like `Timestamp` works.
- Value via `_first(r, _WIND_KEYS)`. `_first` already skips `None` and raises `KeyError` when
  no alias is present — keep that behaviour.
- **New guard:** reject non-finite values. `_handle_fuel_type_data` fills absent fuel columns
  with `np.nan`, and `float(nan)` succeeds, so without this a NaN lands in the database and
  silently poisons any seasonal ratio. Raise
  `ValueError(f"non-finite wind value at ts={ts.isoformat()}")`. This matches the repo's
  existing precedent in `scenario_input._parse_finite_float`.
- Fail-loud is deliberate: one bad hour aborts the pull. The operational escape hatch is the
  per-window chunking in B1, which localizes the failure and names the timestamp.

### Source

```python
EIA_FUEL_TYPE_DATASET = "electricity/rto/fuel-type-data"
EIA_ISONE_RESPONDENT = "ISNE"       # note: ISNE, not the ISO-NE zone label "ISONE"
EIA_WIND_FUEL_TYPE = "WND"

def _default_eia_client() -> Any:
    """gridstatus.EIA() — reads EIA_API_KEY from the environment itself, so this
    process never binds the key to a name. NEVER call .list_routes()/.list_facets()
    on the returned client: those pass the key as a URL query parameter
    (gridstatus/eia.py:84), so any HTTP error from them puts the key in the
    exception message. Enforced by a test canary, not just this comment."""
    return _import_gridstatus().EIA()

class EIAWindSource:
    source = "eia930.isne.wind"

    def __init__(self, *, respondent=EIA_ISONE_RESPONDENT, fuel_type=EIA_WIND_FUEL_TYPE,
                 client_factory=_default_eia_client, getenv=os.environ.get) -> None: ...
```

`get_observations(start, end)`:
1. `require_eia_api_key(self._getenv)` — **before** the client is built, so a missing key gives
   our message rather than gridstatus's.
2. `client = self._client_factory()`.
3. `frame = client.get_dataset(EIA_FUEL_TYPE_DATASET, start=start.isoformat(),
   end=end.isoformat(), frequency="hourly",
   facets={"respondent": self.respondent, "fueltype": self.fuel_type})`
   — `verbose` is left at its `False` default, deliberately: `verbose=True` logs the request
   params. (The params dict does not itself contain the key, which lives in the header, but
   leave the default alone regardless.)
4. `return list(wind_observations_from_records(frame.to_dict("records")))`.

Only `get_dataset` is ever called on the client. Nothing in `owr` may call `list_routes` or
`list_facets`.

`describe_query(start, end)` — the exact string that reaches stdout and the `source_query`
column:

```
gridstatus.EIA().get_dataset('electricity/rto/fuel-type-data', start=2021-12-01,
end=2022-03-01, frequency=hourly, facets={respondent=ISNE, fueltype=WND})
[api key read from $EIA_API_KEY; value not recorded]
```

**How auditability is preserved without the key.** The key is an authentication credential, not
a query parameter — it selects no data and changes no result. Anyone re-running this query with
*their own* registered key gets a byte-identical response. Recording the environment-variable
**name** tells an auditor exactly where the credential came from; recording the value would add
nothing reproducible and would put a live credential in every row of `raw.hourly_wind`.

`dataset_version()` returns `gridstatus_version()`, unchanged from the existing pattern. The EIA
route, facets, and frequency all live in `source_query`, so nothing is lost.

**No key is ever stored on the instance.** `self._getenv` is a callable, not a mapping; `vars()`
on the source therefore shows a function object, not a credential. `EIAWindSource` is a plain
class (like `ISONELoadSource`), not a dataclass — a dataclass would auto-generate a `__repr__`
that prints every field.

**Residual risk, acknowledged rather than designed away.** Two paths could still surface the key
in a developer's terminal, neither reachable through the shipped CLI:

- Enabling `urllib3` / `http.client` DEBUG wire logging prints request headers, which include
  `X-Api-Key`. Nothing in `owr` configures logging; this requires a deliberate opt-in.
- `pytest -l`, `--pdb`, or IPython `%debug` print frame locals. `EIAWindSource.get_observations`
  holds no key local by design, but a future edit that does, or driving `gridstatus.EIA`
  directly, would expose it.

These are operator-side, not defects in this design. Note them in the module docstring so the
next person does not think the property is stronger than it is.

### Factory

```python
if dataset_name == "wind":
    if zone not in ("ISONE", "ISNE"):
        raise ValueError(
            f"the wind dataset is EIA-930 balancing-authority data (respondent "
            f"{EIA_ISONE_RESPONDENT}) and has no load zone; got --zone {zone!r}. "
            f"Omit --zone or pass ISNE."
        )
    return EIAWindSource()
```

`cmd_extract` calls `source_factory(args.dataset, zone=args.zone)` and `--zone` defaults to
`"ISONE"`, so the default path works. The explicit rejection stops `--zone NEMA` from being
silently ignored. No signature changes anywhere, so the existing
`source_factory=lambda name, zone: source` test fakes keep working.

### Tests (`tests/test_etl_eia.py` — new file, no gridstatus import)

Fakes: `FakeFrame` (holds records, exposes `to_dict("records")`); `FakeEIAClient` (records
`get_dataset` call kwargs, returns a `FakeFrame`, **and defines `list_routes`/`list_facets` that
raise `AssertionError`**); `FakeWindSource`. Reuse `FakeTimestamp` from
`tests/test_etl_extract.py` by re-declaring it locally (the existing file does not export it).

Sentinel used throughout the leak group:
`SENTINEL = "SENTINELKEY0123456789abcdefghijklmnopqrst"` (40 chars).

Adapter:
1. gridstatus-shaped record (`Interval Start` + `Wind`) → `WindObservation` with
   `horizon_days == 0`, `forecast_mw is None`.
2. `MW` and `gen_mw` aliases accepted; `int` coerced to `float`.
3. pandas-like `Timestamp` accepted.
4. missing timestamp key → `KeyError`.
5. missing wind key → `KeyError`.
6. `float("nan")` → `ValueError`; `float("inf")` → `ValueError`; the message names the ts.
7. empty record list → `[]`.

Dataset / rows / SQL:
8. `"wind" in DATASETS`; `DATASETS["wind"] is HOURLY_WIND`.
9. `build_rows(HOURLY_WIND, …)` tuple order equals `HOURLY_WIND.columns`.
10. `build_upsert_sql(HOURLY_WIND)` contains `INSERT INTO raw.hourly_wind`,
    `ON CONFLICT (source, ts, horizon_days)`, `gen_mw = EXCLUDED.gen_mw`,
    `forecast_mw = EXCLUDED.forecast_mw`; does **not** contain `horizon_days = EXCLUDED.`,
    `ts = EXCLUDED.`, or `source = EXCLUDED.`.
11. placeholder count equals `len(HOURLY_WIND.columns)`.
12. `upsert_rows` through `FakeConn` writes one batch of the expected rows.

Source:
13. `source_for("wind")` → `EIAWindSource`, `source == "eia930.isne.wind"`.
14. `source_for("wind", zone="ISNE")` OK; `source_for("wind", zone="NEMA")` → `ValueError`
    naming ISNE.
15. `describe_query` contains the dataset path, `respondent=ISNE`, `fueltype=WND`,
    `frequency=hourly`, both ISO dates, and the literal text `$EIA_API_KEY`.
16. `describe_query` is deterministic across two calls with the same window.
17. `get_observations` with `FakeEIAClient` calls `get_dataset` with dataset
    `electricity/rto/fuel-type-data`, `frequency="hourly"`, and
    `facets == {"respondent": "ISNE", "fueltype": "WND"}`.
18. `get_observations` with `getenv` returning `None` raises `MissingCredentialError`
    **and the client factory was never called** (assert a call counter is 0).
19. **Query-param canary.** `FakeEIAClient.list_routes` / `.list_facets` raise
    `AssertionError("list_routes/list_facets send the API key as a URL query parameter; "
    "owr must never call them")`. Because `FakeEIAClient` is the client in every source test,
    any future code path that reaches those methods fails the suite. Assert directly that the
    fake raises, so the canary itself is covered and cannot rot into a no-op.

**Key-leak assertions — the load-bearing group.** Tests 20–21 use a local
`getenv = lambda name: SENTINEL if name == "EIA_API_KEY" else None`. Tests 22–25 go through the
real CLI and therefore use the real `os.environ.get`, so **each one must set or clear the
variable itself** — `redact_secrets` cannot redact a value it is not told to look for, and
without the setenv the redaction assertions pass vacuously.

20. `SENTINEL not in src.describe_query(start, end)`.
21. `SENTINEL not in repr(src)` and `SENTINEL not in str(vars(src))`.
22. `monkeypatch.setenv("EIA_API_KEY", SENTINEL)`; `extract(HOURLY_WIND, src, …)` → `SENTINEL`
    appears in **no** cell of **any** built row
    (`assert not any(SENTINEL in str(cell) for row in result.rows for cell in row)`), and in
    none of `provenance.source`, `.source_query`, `.dataset_version`.
23. `monkeypatch.setenv("EIA_API_KEY", SENTINEL)`;
    `cli.cmd_extract(dry_run=True, dataset="wind", source_factory=…)` → `SENTINEL` not in
    captured stdout.
24. `monkeypatch.setenv("EIA_API_KEY", SENTINEL)`; a source whose `get_observations` raises
    `RuntimeError(f"boom {SENTINEL}")` → `cmd_extract` returns non-zero, stdout contains
    `***REDACTED***`, and `SENTINEL` is not in stdout. Add the mirror case: with the variable
    **unset** (`monkeypatch.delenv`), the same raise prints the message unredacted — proving the
    redaction is driven by the env value and not by an unconditional string replace.
25. `monkeypatch.delenv("EIA_API_KEY", raising=False)`; `cmd_extract` for `--dataset wind`
    returns `2` with the actionable message (`EIA_API_KEY`, registration URL), no traceback.

End-to-end:
26. dry run over a fake source: `rows_built == n`, `rows_written == 0`, `dry_run is True`.
27. two extracts over the same window with a fixed `retrieved_at` build identical rows
    (idempotency by construction, mirroring the existing load test).

---

## Phase A3 — CLI wiring, redaction net, and `--out`

**Edit: `src/owr/etl/cli.py`.**

1. `_print_result` prints `redact_secrets(prov.source_query)` instead of the bare string.
2. Split `cmd_extract` into a thin wrapper plus `_run_extract`:
   ```python
   def cmd_extract(args, *, source_factory=source_for, connect=_default_connect) -> int:
       try:
           return _run_extract(args, source_factory=source_factory, connect=connect)
       except MissingCredentialError as exc:
           print(f"error: {exc}")
           return 2
       except Exception as exc:
           print(f"error: {type(exc).__name__}: {redact_secrets(str(exc))}")
           return 1
   ```
   Return code `2` for a missing credential mirrors the existing missing-DSN `2`. No `# noqa`
   is needed: ruff's selection (`E, F, I, UP, B`) does not include `BLE`.
   **Cost, accepted:** the broad `except` hides tracebacks for genuine bugs. The requirement
   ("the key must never appear in exception messages") makes a boundary catch the right trade;
   printing `type(exc).__name__` keeps the failure diagnosable.
3. New `--out PATH` argument on `extract`:
   ```
   --out PATH   also write the stamped rows to this CSV (same column order as the
                database insert). Independent of --dry-run; you still need either
                --dry-run or a DSN.
   ```
   Written before the DB branch, so `--dry-run --out data/raw_load.csv` is the no-database path
   that Phase B runs on.
4. `ExtractResult` gains `rows: tuple[tuple[object, ...], ...] = ()`, always populated by
   `extract()`. `rows_built` stays for compatibility and is always `len(rows)`. Document that
   the rows are retained so callers can serialize them.
   Memory note: 451 days × 288 intervals × 8 columns ≈ 130k tuples ≈ 60–80 MB. Acceptable for
   a one-off; the per-winter chunking in B1 caps a single run at ~16 MB.

**New file: `src/owr/etl/rows_csv.py`** — keeps file I/O out of `extract.py`, which is
deliberately I/O-free below the provider.

```python
def write_rows_csv(path, dataset, rows, provenance, *, getenv=os.environ.get) -> int
def read_rows_csv(stream, dataset, *, origin: str) -> list[dict[str, str]]
```

- Header line = `dataset.columns`. Preceded by `#`-prefixed banner lines carrying `dataset`,
  `table`, `source`, `retrieved_at`, `dataset_version`, and `redact_secrets(source_query)` —
  the same comment-banner convention `scenario_input.read_day_profiles` already documents and
  skips.
- `datetime` → `.isoformat()` (tz-aware, so `datetime.fromisoformat` round-trips on read).
  `None` → empty cell.
- The reader filters `#` and blank lines before `csv.DictReader`, mirroring
  `scenario_input.py:95-99`, and raises if the header does not match `dataset.columns`.

**Tests (add to `tests/test_etl_extract.py` and `tests/test_etl_eia.py`):**

28. `--dataset` choices include `wind`; `build_parser().parse_args(["extract","--dataset",
    "wind", …])` sets `args.dataset == "wind"`.
29. `write_rows_csv` → `read_rows_csv` round-trips a load batch: same row count, `ts` parses
    back to the same tz-aware datetime, floats compare equal.
30. Writing twice produces byte-identical files (determinism, matching the repo's existing CSV
    tie invariant).
31. `monkeypatch.setenv("EIA_API_KEY", SENTINEL)`; the banner in a written file contains
    `***REDACTED***` when the sentinel appears in the source query, and never the sentinel.
32. `read_rows_csv` on a header that does not match `dataset.columns` raises with a clear
    message.
33. `cmd_extract(--dry-run --out tmp)` writes the file, prints `would write N rows`, returns 0.
34. `cmd_extract(--out tmp)` with neither DSN nor `--dry-run` still returns `2` with the
    existing "no database DSN" message.

**Existing tests that change:** none in this phase (`ExtractResult` gains a defaulted field;
`_print_result` output is unchanged when no key is set).

---

## Phase A4 — the 5-minute load problem, and migration 005

`etl extract --dataset load --start 2026-01-05 --end 2026-01-07 --dry-run` returns **576 rows**
= 2 × 288 = 5-minute intervals, while the target table is `raw.hourly_load` with
`load_mw DOUBLE PRECISION`. Two separate defects:

- **Naming/keying:** rows at 5-minute grain land in a table named `hourly`. The PK
  `(source, zone, ts)` still holds, so nothing errors — it silently produces a table whose name
  lies about its contents.
- **Unit trap:** anyone summing `load_mw` over a day gets **12× the energy**. This is the same
  class of error as the 24× threshold defect this plan exists to fix.

### Decision: store native granularity; never aggregate at extract time

Arguments weighed:

*For aggregating in `extract`:* everything downstream is hourly — `DayProfile` takes 24 values,
`peak_window` scans hour triplets, `features.daily_load` is daily, the simulator CSV has an
`hour` column. Storing 12× the rows serves no current consumer.

*For storing native (chosen):*
1. `db/migrations/001_init.sql:15` calls `raw` the "immutable landing zone for API payloads" and
   `PLAN.md` Phase 2 step 1 says "into `raw.*` **immutably**". Aggregating in extract makes the
   raw layer a derived layer.
2. A re-pull is not free (~11 min for the winter set), so a bug in an extract-time aggregation
   is expensive to recover from. Aggregation is recoverable from raw; raw is not recoverable
   from an aggregate.
3. The DST/interval integration is the delicate part. Putting it in the **provider adapter** —
   the one layer that cannot be unit-tested without a network — is the worst possible place for
   it. Storing native puts it in a pure, fully-tested transform (Phase B2).

### Changes

`LoadObservation` gains `interval_minutes: float` (**required**, validated `> 0`):

```python
@dataclass(frozen=True)
class LoadObservation:
    ts: datetime            # interval START, tz-aware
    zone: str
    load_mw: float
    interval_minutes: float
```

`load_observations_from_records(records, zone, *, default_interval_minutes: float | None = None)`
derives it, in order:
1. `Interval End − Interval Start` when both are present (gridstatus supplies both;
   `isone.py:182-183` sets `Interval End = Interval Start + 5min`). **Authoritative.**
2. an explicit `interval_minutes` key on the record.
3. `default_interval_minutes`, if the caller supplied one.
4. otherwise raise — no silent default. A wrong interval is a 12× energy error.

Migration **005** creates the correctly-named target and retargets the dataset:

```python
HOURLY_LOAD = RawDataset(          # keep the CLI key "load"; retarget the table
    name="load",
    table="raw.system_load",
    value_columns=("ts", "zone", "load_mw", "interval_minutes"),
    conflict_key=("source", "zone", "ts"),
    to_values=_load_values,        # + interval_minutes
)
```

`raw.system_load` is granularity-agnostic on purpose: when ISO-NE Web Services credentials
arrive, `hourlysysload` lands in the same table with `interval_minutes = 60`, with no second
rename.

**Existing tests that break, and how (call this out in the commit message):**
`tests/test_etl_extract.py` constructs `LoadObservation(ts=…, zone=…, load_mw=…)` in `_obs()`
and calls `load_observations_from_records` with single records lacking `Interval End`
(lines 92-96, 242-261). Update: add `interval_minutes=5.0` to `_obs()`, add `Interval End` to
the fixture records, and add one test that omitting both the end key and
`default_interval_minutes` raises. Also update
`test_upsert_sql_is_idempotent_on_conflict_key` and
`test_upsert_sql_placeholder_count_matches_columns` for the new column and table name.

### Migration files

**`db/migrations/004_raw_hourly_wind_realized.sql`** (recommended; extractor works without it)

```sql
-- Migration 004 — record how EIA-930 realized generation uses raw.hourly_wind.
-- No new table: the Phase 1 schema already fits (docs/PLAN_EIA_EXTRACTOR.md, Decision 2).
-- horizon_days is part of the PK and therefore implicitly NOT NULL; realized
-- (non-forecast) rows carry 0, meaning "zero days ahead" = actual. Forecast rows,
-- when they exist, carry their lead time in days.
COMMENT ON TABLE  raw.hourly_wind IS
  'Hourly wind generation. Realized rows: gen_mw set, forecast_mw NULL, horizon_days = 0. '
  'Producer encoded in source, e.g. eia930.isne.wind (EIA-930, respondent ISNE, fueltype WND).';
COMMENT ON COLUMN raw.hourly_wind.horizon_days IS
  'Forecast lead time in days. 0 = realized/actual (see docs/HANDOFF.md, open question Q6).';
ALTER TABLE raw.hourly_wind ALTER COLUMN horizon_days SET DEFAULT 0;
ALTER TABLE raw.hourly_wind
  ADD CONSTRAINT hourly_wind_horizon_days_nonneg CHECK (horizon_days >= 0);
```

**`db/migrations/005_raw_system_load_granularity.sql`** (required before any live load write)

```sql
-- Migration 005 — the provider's credential-free ISO-NE load feed
-- (gridstatus ISONE().get_load -> fiveminutesystemload) returns 5-MINUTE intervals,
-- not hourly. Verified live 2026-07-30: 288 rows/day, 276 on spring-forward,
-- 300 on fall-back. Landing those in raw.hourly_load names the table wrongly and
-- invites a 12x energy error on any naive SUM(load_mw).
--
-- raw.* is the immutable landing zone, so the fix is a correctly-named,
-- granularity-agnostic table carrying the interval length, not extract-time
-- aggregation (docs/PLAN_EIA_EXTRACTOR.md, Phase A4).
CREATE TABLE raw.system_load (
    ts               TIMESTAMPTZ NOT NULL,   -- interval START (absolute instant)
    zone             TEXT        NOT NULL,   -- 'ISONE' system-wide or a load zone
    load_mw          DOUBLE PRECISION NOT NULL,
    interval_minutes DOUBLE PRECISION NOT NULL CHECK (interval_minutes > 0),
    source           TEXT        NOT NULL,
    retrieved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_query     TEXT        NOT NULL,
    dataset_version  TEXT        NOT NULL,
    PRIMARY KEY (source, zone, ts)
);
SELECT create_hypertable('raw.system_load', 'ts', if_not_exists => TRUE);
COMMENT ON TABLE raw.system_load IS
  'Interval load at the provider''s native granularity. Energy = SUM(load_mw * '
  'interval_minutes / 60) — never SUM(load_mw). Daily rollups group on '
  '(ts AT TIME ZONE ''America/New_York'')::date.';
COMMENT ON TABLE raw.hourly_load IS
  'SUPERSEDED by raw.system_load (migration 005). Reserved for a genuinely hourly '
  'feed (ISO-NE Web Services hourlysysload), which is still credential-blocked. '
  'Not written by any current code path.';
```

`raw.hourly_load` is left in place rather than dropped: `features.daily_load` and `PLAN.md`
Phase 1 both reference it, and migrations only run on first init (`docker-compose.yml:13-14`),
so dropping it buys nothing. See Q3.

---

## Phase B1 — run the load pull

### Which series

Use **`gridstatus ISONE().get_load()`**, not the ISO Express `whlsecost` CSVs, for three
reasons:

1. **December.** The team's winter is Dec 1 – Feb 28/29. Alexander's ISO Express file set
   (`DATA_SOURCES.md` [3]) contains **no December at all** — five files short. gridstatus can
   pull December today; the ISO Express path needs a new Source plus a five-file top-up first.
2. It runs through the existing `extract` path with **zero new provider code**, verified live.
3. `Native Load` is ISO-NE's system demand series, which is the quantity a demand threshold
   should be defined on. (Caveat: Native Load excludes behind-the-meter solar — immaterial for
   winter evening peaks, but state it. See **R10**.)

Building an ISO Express Source and reconciling the two series is **out of scope** here; record
it as a follow-up.

### Window

Five winters, Dec 1 – Feb 28/29, 2021/22 through 2025/26 = **451 days**
(90 + 90 + 91 + 90 + 90; 2024 is a leap year). `--end` is exclusive at day grain (verified:
Jan 5 → Jan 7 gave 2 days).

```bash
mkdir -p data
for W in 2021:2022 2022:2023 2023:2024 2024:2025 2025:2026; do
  S=${W%%:*}; E=${W##*:}
  uv run python -m owr.etl extract --dataset load \
    --start ${S}-12-01 --end ${E}-03-01 --dry-run \
    --out data/raw_load_${S}_${E}.csv
done
```

Five invocations of ~2.3 min each rather than one 11-minute run. This is shell-level chunking,
not code: a mid-run failure costs one winter instead of all five, and it caps peak memory.
Run it in the background and poll.

**Probe first (5 seconds, blocks the whole phase):**
```bash
uv run python -m owr.etl extract --dataset load \
  --start 2021-12-01 --end 2021-12-02 --dry-run
```
The `fiveminutesystemload` endpoint's earliest supported date is undocumented
(`gridstatus/isone.py:162`). If Dec 2021 fails, fall back to four winters (2022/23–2025/26,
361 days) and record the reduced scope — do **not** silently substitute a different series.

---

## Phase B2 — daily energy, correctly

**New file: `src/owr/etl/daily.py`** (pure; stdlib `zoneinfo` only, no new dependency).

```python
EASTERN = ZoneInfo("America/New_York")

@dataclass(frozen=True)
class IntervalReading:
    ts: datetime          # tz-aware, interval START
    load_mw: float
    interval_hours: float

@dataclass(frozen=True)
class DailyLoad:
    date: date            # LOCAL calendar date
    load_mwh: float
    hours_covered: float
    expected_hours: float # 23 / 24 / 25, derived from the tz
    intervals: int
    complete: bool

def local_day_hours(day: date, tz: ZoneInfo = EASTERN) -> float
def daily_loads_from_readings(readings, *, tz=EASTERN, tolerance_hours=0.01) -> list[DailyLoad]
```

Specification, point by point:

1. **Energy is an integral, never a count.**
   `load_mwh = Σ(load_mw × interval_hours)`. `interval_hours` comes from the row's
   `interval_minutes / 60` — the provider-supplied value carried through A4. Nothing anywhere
   in this pipeline may assume 288 intervals, 24 hours, or a fixed interval count.
2. **Day boundary: local wall-clock (`America/New_York`).** The team's Dec 1 – Feb 28/29 is a
   calendar definition, ISO-NE operates on local days, and gridstatus already fetches per local
   day. Group on `reading.ts.astimezone(tz).date()`.
   `US/Eastern` (what gridstatus tags) and `America/New_York` are the same zone via the tz
   database backward links; use `America/New_York` in our code.
3. **What `ts` stores vs. what the rollup groups by.** `raw.system_load.ts` is `TIMESTAMPTZ` —
   an absolute instant, stored UTC-normalized. It is *not* a local date. The daily rollup
   converts at read time: in Python `ts.astimezone(EASTERN).date()`, in SQL
   `(ts AT TIME ZONE 'America/New_York')::date`. Never group on the raw UTC date.
4. **`local_day_hours`** = `datetime.combine(day + 1d, time(0), tzinfo=tz) −
   datetime.combine(day, time(0), tzinfo=tz)`, in hours. Aware-datetime subtraction uses UTC
   offsets, so this returns 23.0 / 24.0 / 25.0 automatically. **Never hard-code 24.**
5. **DST is handled, not avoided.** Live counts: 2025-03-09 → 276 readings; 2025-06-10 → 288;
   2025-11-02 → 300. Because timestamps are tz-aware absolute instants, every interval is
   exactly 5 minutes and the integral is right on all three days; only the *count* per local
   day varies. `complete = abs(hours_covered − expected_hours) <= tolerance_hours`.
6. **Reject naive timestamps** with a clear error. This is the guard that keeps (5) true: with
   naive local timestamps the fall-back hour repeats and the 01:00–02:00 block is either
   double-counted or silently deduplicated.
7. **Reject duplicate absolute instants**, naming the timestamp. Sort readings before
   integrating; do not assume input order.
8. **Straddle rule:** an interval is attributed wholly to the local date of its **start**. At
   5- and 60-minute grain nothing straddles local midnight. Document it anyway.
9. **Incomplete days are excluded from the p90 population and from window detection**, and are
   reported by `validate`. Including a half-covered day would understate its energy, guarantee
   it never registers as stressed, and drag the percentile down. See **Q2**.
   *Excluding a day removes it from the middle of a calendar run.* Phase B3's run detection is
   date-aware precisely so that this is safe: the gap splits the run instead of silently
   merging across it. Exclusion never raises.

**New file: `src/owr/etl/seasons.py`**

```python
class Season(StrEnum):        # values match features.daily_load's CHECK constraint
    WINTER = "winter"; SUMMER = "summer"; SHOULDER = "shoulder"

def season_for(d: date) -> Season      # month in {12,1,2} -> winter; {6,7,8,9} -> summer; else shoulder
def winter_label(d: date) -> str | None  # "2021/22" for Dec 2021 and Jan/Feb 2022
```

The settled definitions (Dec 1 – Feb 28/29, Jun 1 – Sep 30) land exactly on month boundaries,
so no day-of-month logic is needed and Feb 29 is included for free — which closes
`FACT_CHECK_REPORT.md` 2026-07-30 [Contradicted #4]. March belongs to neither season and must
never be pooled into a seasonal denominator. `winter_label` groups Dec of year *Y* with Jan/Feb
of *Y+1*, which is what Phase B3 needs.

### Tests (`tests/test_etl_daily.py`, `tests/test_etl_seasons.py`)

35. 12 readings of 1000 MW at 5-minute grain over one hour → 1000.0 MWh.
36. Mixed grains (some 5-minute, some 60-minute) integrate correctly — proves nothing assumes a
    constant.
37. **Spring forward** 2025-03-09 America/New_York, 276 synthetic 5-minute readings →
    `hours_covered == 23.0`, `expected_hours == 23.0`, `complete is True`,
    `load_mwh == Σ MW / 12`.
38. **Fall back** 2025-11-02, 300 readings → `hours_covered == 25.0`, `expected_hours == 25.0`,
    `complete is True`. Build the fixture from tz-aware UTC instants so the repeated local hour
    is genuinely distinct.
39. Ordinary day 2025-06-10, 288 readings → 24.0 / 24.0.
40. `local_day_hours` returns 23.0, 24.0, 25.0 for 2025-03-09, 2025-06-10, 2025-11-02.
41. **Local-date grouping:** a reading at `2025-01-01T02:30Z` belongs to local date
    `2024-12-31`.
42. Naive timestamp → `ValueError` naming the offending ts.
43. Duplicate absolute instant → `ValueError` naming the ts.
44. Unsorted input produces the same result as sorted input.
45. A day missing 2 hours → `complete is False`, `hours_covered == 22.0`.
46. `season_for`: 2021-12-01 winter; 2024-02-29 winter; 2024-03-01 shoulder; 2024-05-31
    shoulder; 2024-06-01 summer; 2024-09-30 summer; 2024-10-01 shoulder; 2024-11-30 shoulder.
47. `winter_label`: 2021-12-15 and 2022-02-10 both → `"2021/22"`; 2022-03-01 → `None`.

---

## Phase B3 — threshold and windows, reusing `stress_finder`

### Two problems in the current function, one fix each

**(a) The threshold is computed from the days passed in.** The settled definition takes p90 over
the **pooled** five-winter record (`HANDOFF.md`: "all Dec–Feb days in the five-year set"), then
finds runs **within** each winter. Calling `find_stress_windows` per winter would produce five
different per-winter thresholds.

**(b) Run detection walks the list by index, never by date.** `stress_finder.py:52-68` is
`for i, is_stressed in enumerate(stressed)` with no reference to `days[i].date` in the run
logic. So any list whose consecutive elements are not consecutive calendar days produces merged,
phantom windows. Two live ways to hit this:

- a naively concatenated multi-winter series (2022-02-28 followed by 2022-12-01);
- **a single excluded incomplete day in the middle of a winter** — the ordinary outcome of a
  live network pull, and the one B2 point 9 calls a graceful exclusion. A five-day stressed run
  with day 3 dropped would be reported as one four-day event.

A separate pre-flight gate cannot fix (b): run it *before* exclusion and it passes on the
contiguous calendar list while the post-exclusion list still has the gap; run it *after* and a
single 22-hour day aborts window detection for a whole winter. The check has to live inside the
loop.

### Fix: split the function, and make adjacency date-aware

**Edit `src/owr/stress_finder.py`:**

```python
def find_stress_windows_at_threshold(days, threshold, min_window_days) -> list[StressWindow]:
    """Runs of >= min_window_days consecutive CALENDAR days at or above `threshold`.

    Adjacency is by date, not by list position: a run ends when the next element's
    date is not exactly one day after the current element's. A gap in the series —
    a missing or excluded day — therefore splits a run instead of merging across it.

    Input is expected sorted ascending by date. It is deliberately NOT sorted here;
    an out-of-order series yields shorter runs rather than silently merged ones.
    """

def find_stress_windows(days, severity_percentile, min_window_days) -> list[StressWindow]:
    threshold = percentile_threshold([d.load_mwh for d in days], severity_percentile)
    return find_stress_windows_at_threshold(days, threshold, min_window_days)
```

Run-detection rules, stated so the loop is not re-derived:

- A day is stressed when `day.load_mwh >= threshold` (unchanged, `>=` not `>`).
- Open a run at index `i` when `stressed[i]` and no run is open.
- Extend an open run from `i-1` to `i` only when `stressed[i]` **and**
  `days[i].date == days[i-1].date + timedelta(days=1)`.
- Otherwise close the open run at `i-1`; if `stressed[i]`, immediately open a new run at `i`.
- Close any open run at the end of the list.
- Emit `StressWindow(start=days[run_start].date, end=days[run_end].date,
  days=run_end - run_start + 1)` when the run length `>= min_window_days`.
  `days` stays the count of elements in the run; under date adjacency that is identical to
  `(end - start).days + 1`, so `StressWindow` needs no change.

**Behaviour-change disclosure.** `find_stress_windows` has exactly two production callers:

- `src/owr/cli.py:326` — days come from `scenario_input.read_day_profiles`, which already
  rejects non-consecutive dates (`scenario_input.py:214-221`). **No-op.**
- `src/owr/api/app.py:138` — `_day_profiles` passes the request body straight through with no
  contiguity or ordering check. A client posting a gapped or unsorted day list gets **different
  windows than before**. This is a bug fix, not a regression: the old answer merged across gaps.
  Worth stating in the API's changelog and raising as **Q8**.

Every existing test uses consecutive dates (`tests/test_stress_finder.py` builds
`date(2026,1,1) + timedelta(days=i)`; `tests/test_api.py:41` builds
`date(2026,1,10) + timedelta(days=i)`; both `test_cli.py` call sites go through
`read_day_profiles`), so the whole current suite is unaffected. Confirm by running it.

**Typing:** `find_stress_windows` is annotated `list[DayProfile]`, but `DayProfile` requires
exactly 24 hourly MW values and cannot represent a 23- or 25-hour day, nor a day whose energy
came from 5-minute readings. Add to `src/owr/models.py`:

```python
class DailyLoadLike(Protocol):
    """What stress detection actually needs: a date and a daily energy total.
    DayProfile satisfies this structurally; so does owr.etl.daily.DailyLoad."""
    date: date
    load_mwh: float
```

and widen both functions to `Sequence[DailyLoadLike]`. Annotation-only — zero runtime change
(there is no mypy in CI), but it makes the ETL's use intentional rather than an accidental duck
type. Do **not** mark it `runtime_checkable`: `DayProfile.load_mwh` is a property, and
`isinstance` against a data protocol raises anyway. Do not add it to `owr/__init__.py`'s
`__all__` — it is a typing helper, and there is no export-parity test to satisfy.

### Orchestration — `src/owr/etl/transform.py` (new)

```python
@dataclass(frozen=True)
class ThresholdResult:
    percentile: float
    threshold_mwh: float
    population_days: int
    season: Season
    excluded_incomplete: tuple[date, ...]
    min_mwh: float; median_mwh: float; max_mwh: float

def compute_threshold(daily, *, percentile, season) -> ThresholdResult
def find_windows_per_winter(daily, *, threshold_mwh, min_window_days) -> dict[str, list[StressWindow]]
```

- `compute_threshold` filters to `season_for(d.date) == season and d.complete`, then calls
  `percentile_threshold(...)` — the existing engine function, unchanged, whose docstring already
  guarantees it matches numpy's linear method.
- `find_windows_per_winter` groups by `winter_label`, sorts each group by date, and calls
  `find_stress_windows_at_threshold` per group with the **pooled** threshold.
  Grouping is what makes the Feb-28 → Dec-1 case structurally impossible; date-aware adjacency
  is what makes the within-winter gap case safe. Both are needed, and neither raises.
- **There is no `require_consecutive_dates` hard gate.** Date gaps are a normal consequence of
  excluding incomplete days, so they are *reported*, not fatal: `validate` gains a `date_gaps`
  gate (Phase B4) that lists every within-winter gap and its cause. The transform proceeds.

### Sanity band for the resulting number

ISO-NE system-wide winter load averages roughly 14–16 GW with peaks near 19–20 GW, so a daily
total lands around 3.4–4.0 × 10⁵ MWh and the p90 should land in roughly the
**380,000–420,000 MWh** band. Two cross-checks the implementer should apply before publishing:

- `FACT_CHECK_REPORT.md` records 434,214 MWh as the winter **peak-day** total energy at system
  scale. **A p90 over daily totals must come out below that**, since a percentile of the
  population cannot exceed the population maximum.
- **A result anywhere near 16,750 or 3,504 means the daily aggregation is wrong** — those are
  the hourly-basis numbers this exercise exists to replace.

These are sanity bands, not targets. Record whatever the data gives, including a surprise.

### Tests

In `tests/test_stress_finder.py` (the engine change):

48. **Date-aware adjacency, direct.** Days at dates 1, 2, 4, 5 all above threshold,
    `min_window_days=2` → **two** windows (1–2 and 4–5), not one 1–5 window. This is the
    regression test for (b) and the case with zero coverage today.
49. Days at dates 1, 2, 4 above threshold, `min_window_days=2` → one window (1–2); the isolated
    day 4 is dropped.
50. Out-of-order input (dates 3, 1, 2) is not silently merged: assert the documented
    shorter-runs behaviour rather than a sorted result, pinning the "we do not sort" decision.
51. `find_stress_windows_at_threshold` with an explicit threshold reproduces
    `find_stress_windows` at the percentile that yields that threshold (equivalence test that
    pins the split as behaviour-preserving). The three existing tests must also pass
    unmodified — state that in the commit message.

In `tests/test_etl_transform.py`:

52. `compute_threshold` on a hand-built 20-day winter series matches a hand-computed p90.
53. Summer and shoulder days present in the input are excluded from a `season=WINTER`
    population; `population_days` reflects the filter.
54. Incomplete days are excluded from the population and listed in `excluded_incomplete`.
55. **The blocking case.** A five-day stressed run inside one winter with day 3 marked
    incomplete and therefore excluded → `find_windows_per_winter` returns **two** windows of two
    days each, **not** one four-day window, and **does not raise**.
56. **Naive concatenation, direct.** Two winters concatenated into one list and fed straight to
    `find_stress_windows_at_threshold` (bypassing the grouping) → the stressed Feb-28 and the
    stressed following Dec-1 produce two separate runs. Covers the raw positional hazard at the
    function boundary.
57. **Grouping, in practice.** The same input through `find_windows_per_winter` returns a dict
    keyed by `winter_label` with each winter's windows separated — proving the grouping is what
    keeps the two mechanisms independent, and that test 56's protection is belt to its braces.
58. Pooled threshold, not per-group: construct a low winter and a high winter; assert the low
    winter yields no windows.
59. `min_window_days = 2` excludes isolated single stressed days; `= 1` includes them.
60. `owr.etl.daily.DailyLoad` instances are accepted by `find_stress_windows_at_threshold`
    (the `DailyLoadLike` contract, exercised at runtime).

---

## Phase B4 — `etl transform` and `etl validate`

### Where this work belongs, and why

**In the scaffolded `transform` and `validate` subcommands**, not a one-off script.

- Their existing help text is literally this work: `transform` = "hourly->daily, season tagging,
  percentiles (Phase 2 step 2)"; `validate` = "gap/unit/DST validation gates + report (Phase 2
  step 2)". `cli.py`'s module docstring says they were scaffolded "so they slot in later without
  reshaping the CLI or its argument surface." This is later.
- A script under `examples/` would be untested (nothing there is in the pytest suite) and would
  duplicate logic `PLAN.md` Phase 2 step 2 already assigns to these commands. The p90 threshold
  is going to anchor published numbers; it needs test coverage.

**Interpretation, stated because it departs from the letter of `PLAN.md`:** Phase 2 step 2
envisions `transform` reading `raw.*` and writing `features.*` in Postgres. Implement the
**computation** in pure modules (`daily.py`, `seasons.py`, `transform.py`) and make the
command's **I/O** pluggable — CSV now, Postgres later behind the same pure core. This satisfies
the plan's intent without standing up a database.

### Storage: CSV and stdout, not Postgres

**Recommendation: no database for this deliverable.**

- Postgres + TimescaleDB has *never been run against a live DB* (`HANDOFF.md`). Standing it up
  adds Docker, migration-ordering, hypertable, and connection risk to a task whose output is one
  number and a table of windows.
- **Provenance is not sacrificed.** The extract CSV carries all four provenance columns on every
  row — the identical tuple that would be upserted — plus a banner. The derived outputs carry
  the same provenance in their own banners. The audit chain is complete without a database.
- Raw pulls go to `data/`, which `.gitignore` already excludes (as does the blanket `*.csv`
  rule, with an exception only for `examples/*.csv`). **Do not commit raw pulls.** Commit the
  *numbers* as a markdown record, which is how this repo records findings.

**The CSV shape and `features.daily_load` do not match, and that is a known debt.**
`001_init.sql:64-72` defines `features.daily_load (date, load_mwh, season, demand_percentile)`
plus the four provenance columns. The transform's daily CSV emits
`date, load_mwh, hours_covered, expected_hours, intervals, complete, season, winter_label,
stressed`. So:

- Five columns have **no home in the current schema** — `hours_covered`, `expected_hours`,
  `intervals`, `complete`, `winter_label`. The first four are the DST/gap evidence and belong
  with the daily row, not in a report that gets thrown away; `winter_label` is the grouping key
  Phase B3 needs.
- The CSV **omits** `demand_percentile`, which `features.daily_load` requires and which
  `DayProfile` consumes. It is derivable from the same population as the threshold (the
  empirical rank of each day's energy) and should be added when the Postgres layer lands.

**Nobody should rediscover this later:** before a Postgres I/O layer exists,
`features.daily_load` needs either new columns (a migration 006) or a sibling table for the
coverage/quality fields. Do **not** silently drop the five columns to make the CSV fit the
current schema — they are the audit trail for the exclusion decision in B2 point 9. Recorded as
**Q9**; out of scope for this plan, which writes CSV only.

When Postgres does come up, `features.constants` is the right home for the threshold itself,
stored with its derivation query (`001_init.sql:78-85`, and `PLAN.md` Phase 1's rule that
derived constants are never literals). See **Q4**.

### CLI surface

```
etl transform --input CSV [CSV ...] [--season winter|summer|shoulder|all]
              [--percentile FLOAT] [--min-window-days INT]
              [--output daily.csv] [--windows-output windows.csv]

etl validate  --input CSV [CSV ...]
```

`--percentile` and `--min-window-days` default to `DEFAULT_CONFIG.default_severity_percentile`
(0.90) and `DEFAULT_CONFIG.default_min_stress_window_days` (2) — **read from `owr.config`, not
written as literals**, per repo convention #5. `owr.config` imports only `owr.models`, which is
pure stdlib, so this adds no dependency to the ETL.

`transform` prints a summary block in `_print_result`'s style: percentile, threshold, population
size, per-winter day counts, excluded days, and the window list. `validate` prints a pass/fail
table and returns 1 if any gate fails.

### `src/owr/etl/validate.py` gates

| Gate | Check | Expected on the winter pull |
|---|---|---|
| `tz_aware` | every ts is tz-aware | pass |
| `no_duplicate_instants` | no repeated absolute instant | pass |
| `uniform_interval` | distinct `interval_minutes` values and counts | one value: 5.0 |
| `day_length` | per local date, `hours_covered` vs `local_day_hours` | all 24.0 — **winter contains no DST transition** |
| `date_gaps` | within each `winter_label`, list every missing calendar date and whether it is absent or excluded-incomplete | none, ideally; reported, not fatal |
| `month_coverage` | intervals per (year, month) vs the calendar | Dec/Jan = 31 d, Feb = 28 or 29 d |
| `population_size` | complete winter days | **451** (or 361 on the four-winter fallback) |
| `unit_sanity` | daily totals in 1×10⁵ – 8×10⁵ MWh; hourly-mean MW in 5,000–30,000 | pass; **labelled a sanity band, not a spec** |

`date_gaps` is the repurposed contiguity check: it reports, so a reviewer can see exactly which
days were dropped and why, while `find_stress_windows_at_threshold`'s date-aware adjacency makes
the gap harmless to the window computation. Neither raises.

`day_length` is worth stating precisely: **the five winters contain no DST transition at all**
(spring forward is the second Sunday of March, fall back the first Sunday of November; neither
falls in Dec–Feb, and the same holds for Jun 1 – Sep 30). So DST cannot corrupt the p90
population. The DST machinery in B2 exists because (a) the March files in Alexander's set do
contain a transition, (b) summer work will reach November eventually, and (c) `hours_covered`
vs `local_day_hours` is the gap detector regardless — a 23-hour reading in January means
missing data, not DST.

### Tests (`tests/test_etl_validate.py`, plus CLI cases)

61. Each gate passes on a clean synthetic winter fixture.
62. Each gate fails, individually, on a fixture with exactly that defect, and the report names
    the offending date/timestamp.
63. `date_gaps` reports a mid-winter missing date, distinguishes "absent" from
    "excluded-incomplete", and does **not** raise.
64. `cmd_validate` returns 0 when all gates pass, 1 when any fails.
65. `cmd_transform` on a small fixture writes a daily CSV with columns
    `date,load_mwh,hours_covered,expected_hours,intervals,complete,season,winter_label,stressed`
    and a `#` provenance banner.
66. `cmd_transform` run twice produces byte-identical output (determinism).
67. `cmd_transform` with `--percentile` omitted uses `DEFAULT_CONFIG.default_severity_percentile`
    — assert against the config attribute, not the literal 0.90, so the test cannot drift.
68. `cmd_transform` with multiple `--input` files concatenates and **deduplicates on ts**
    (see R5).
69. `etl transform` and `etl validate` no longer print "not implemented yet".

**Existing test that breaks:** `test_cli_transform_and_validate_are_scaffolded`
(`tests/test_etl_extract.py:411-415`) asserts both commands return 1 with "not implemented yet".
Replace it with tests 64/69. The `_not_implemented` helper becomes unused — delete it (ruff `F`
will not flag an unused module-level function, so this is a manual cleanup).

---

## Phase B5 — the two recorded data anomalies

### One 744-hour file is missing; the arithmetic proves that much and no more

Alexander's series is Jan/Feb/Mar/Jun/Jul across 2022–2026 from the ISO Express `whlsecost`
hourly CSVs — a genuinely hourly source, unrelated to the 5-minute gridstatus feed. So the
5-minute/hourly confusion does **not** explain the shortfall. DST does.

Hours in a complete 25-file set, counting each March at 743 hours (spring forward is the second
Sunday of March in every year 2022–2026, so it always removes one hour from a March file):

| Month | Per file | × 5 years | Subtotal |
|---|---|---|---|
| January | 744 | ×5 | 3,720 |
| February | 672 (696 in 2024) | — | 3,384 |
| March | 743 | ×5 | 3,715 |
| June | 720 | ×5 | 3,600 |
| July | 744 | ×5 | 3,720 |
| **Total (25 files)** | | | **18,139** |

**18,139 − 17,395 = 744.** Both recorded anomalies therefore reduce to one fact: **exactly one
744-hour file is missing**, and the March files are correctly DST-aware at 743 hours each.

**What the arithmetic settles, and what it does not.** It rules out February (672/696), March
(743), and June (720) as the missing file, and it confirms the DST-aware reading — the
alternative (a padded 744-hour March) totals 18,144 and leaves 17,400 after any single removal,
5 hours off, and 5 is exactly the number of Marches. It does **not** identify *which* 744-hour
file: **ten candidates fit equally well** — the five Januaries and the five Julys. July 2026
remains plausible on non-arithmetic grounds (it was the current month at pull time, so its
monthly file would be incomplete or unpublished), which is the guess `DATA_SOURCES.md` [3]
already records. That guess is now narrowed from one-in-25 to one-in-10, not confirmed.

**Do not let `docs/DATA_SOURCES.md` inherit a uniqueness claim the arithmetic cannot support.**
Word the update as: *one 744-hour file — a January or a July — is absent; the file listing
identifies which.* The `ls` settles it in one command:

```bash
ls whlsecost_hourly_4008_*.csv | sort          # expect 24; the absentee is a YYYY01 or YYYY07
for f in whlsecost_hourly_4008_*.csv; do echo "$f $(($(wc -l < "$f") - 1))"; done
# expect 744 / 672 / 743 / 720 / 744 by month, and 696 for 202402
```

Neither check proves no rows are missing *inside* a file; the per-file row counts above are what
close that gap. Record the outcome in `docs/DATA_SOURCES.md` [3], replacing the two open
bullets. Note that this resolves the *NEMA* (4008) series; the system-wide 4000 re-pull is a
separate inventory and still lacks December entirely.

### DST in the new pull

Covered in B2 (items 1–8) and gated in B4 (`day_length`). Summary of the correctness contract:
energy is `Σ MW × interval_hours` with `interval_hours` from provider-supplied interval
boundaries; days are local wall-clock; expected day length is derived from the timezone, never
assumed; and a day whose covered hours differ from its expected hours is excluded and reported
rather than silently included.

---

## Phase B6 — record the results

Do **not** commit `data/`. Produce:

1. **`docs/STRESS_THRESHOLD_P90.md`** (new): the pull's provenance (source, `source_query`,
   `dataset_version`, `retrieved_at`, exact date range, day count), the `validate` report, the
   p90 value in MWh, the population statistics, the excluded days, and the per-winter
   stress-window table (start, end, days, each day's MWh). State plainly that this supersedes
   16,750 MWh and 3,504 MWh, and that Report A's 19-event and Report B's 3-winter-event sets are
   **not comparable** to it (`HANDOFF.md` already says so; the new table is the evidence).
2. **`docs/DATA_SOURCES.md`**: resolve the two [3] bullets with the B5 wording (one 744-hour
   file, identified by the listing — not by the arithmetic); add `raw.system_load` and the EIA
   wind ingest row's implementation status.
3. **`docs/HANDOFF.md`**: update "What works, verified" with the new test count, move Phase 2
   ETL off "fixture-tested only", replace the "Next step" block, and add the open questions
   below — including Q8, the API-visible behaviour change.
4. **`docs/FACT_CHECK_REPORT.md`**: append to the 2026-07-28 addendum that Contradicted #5's
   "a new p90 must be computed" is now done, with the value and a pointer.
5. **`README.md`**: Phase 2 row moves off "⛔ blocked on API credentials" — the load path needs
   none and the wind path needs a free key.

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | The `fiveminutesystemload` endpoint's earliest supported date is undocumented; Dec 2021 may not exist. | One-day probe before the full pull (B1). Documented fallback: four winters, scope change recorded. |
| **R2** | gridstatus localizes ISO-NE timestamps with `ambiguous="infer"`, which can raise on a fall-back day. | Not reachable in Dec–Feb. Hits only if March/November are pulled. Chunked runs localize the failure. |
| **R3** | gridstatus sets `Interval End = period` for EIA hourly (`eia.py:805-809`). If EIA-930's `period` is hour-**beginning**, every wind timestamp is shifted one hour early. | **Must verify before the wind series drives charging-hour selection.** Pull one known day and compare a specific hour against EIA's own web viewer and against the ISO-NE daily fuel-type report summed to daily. A uniform 1-hour shift is immaterial to daily/seasonal totals and material to hour-of-day selection. Not a blocker for this plan's deliverables. |
| **R4** | EIA v2 paginates at 5,000 rows with `n_workers=1` by default; five years hourly ≈ 44k rows ≈ 9 sequential pages. | Acceptable. Raise `n_workers` only if measured slow; do not add it speculatively. |
| **R5** | EIA v2's `end` is **inclusive**, so chained windows can duplicate the boundary hour. The DB upsert absorbs it; the CSV path would double-count. | Dedupe on `ts` when `transform` concatenates multiple `--input` files (test 68). |
| **R6** | `uv sync --group dev` prunes `gridstatus` out of the venv. | Documented in §0. All new tests must import cleanly without it — CI enforces this. |
| **R7** | Deliberate breakage of existing tests: `LoadObservation` gains a required field (A4) and the transform/validate scaffold test is replaced (B4). | Enumerated per phase. The 231-test baseline changes; state the new number in `HANDOFF.md`. |
| **R8** | Broad `except Exception` in `cmd_extract` hides tracebacks. | Accepted trade for the no-leak requirement; the exception **type** is printed. |
| **R9** | `ExtractResult.rows` holds the whole batch in memory (~60–80 MB for 451 days). | Per-winter chunking caps a run at ~16 MB. |
| **R10** | `Native Load` excludes behind-the-meter solar, so daily totals understate gross demand on sunny days. | Immaterial for winter evening peaks; state it in `docs/STRESS_THRESHOLD_P90.md` as a documented choice. |
| **R11** | Positional run detection merges across date gaps — from concatenated winters *or* from a single excluded incomplete day. | Fixed at source: date-aware adjacency inside `find_stress_windows_at_threshold` (B3), covered by tests 48, 55, 56. Grouping by `winter_label` is the second, independent layer. |
| **R12** | The two published thresholds are wrong by ~24× and are quoted in circulating documents. | The record in B6 must say explicitly which numbers it supersedes. |
| **R13** | `EIA.get_dataset` has **no retry or backoff** (`eia.py:92-98`), unlike ISO-NE's `_make_request`, which retries 3× (`isone.py:972-996`). Irrelevant to this plan, whose wind work is a short verification window — but a multi-year wind backfill will hit a transient and lose the whole run. | Flag for whoever does the backfill: chunk per month/season the way B1 chunks per winter, or add retry at that point. Do not add it speculatively now. |
| **R14** | Residual key-exposure paths outside the CLI: urllib3/`http.client` DEBUG wire logging prints `X-Api-Key`; `pytest -l` / `--pdb` / `%debug` print frame locals. | Neither is reachable through the shipped CLI path, and `EIAWindSource` holds no key local. Acknowledged as operator-side residual risk in the module docstring, not designed around. |

---

## Open questions to route to the team

1. **Q1 — p90 population.** `HANDOFF.md` says the threshold is taken over daily totals across
   the pooled five-winter record, not per winter. **Implementing pooled.** Confirm, because
   per-winter would produce a different event set and a load-growth trend would bias the pooled
   version toward flagging recent winters.
2. **Q2 — incomplete days.** **Implementing: excluded** from the population and from window
   detection, and reported. Confirm; the alternative (scale to a full day) invents data.
3. **Q3 — `raw.hourly_load`.** Migration 005 leaves it in place, commented as superseded and
   reserved for a genuinely hourly ISO-NE feed. Drop it instead?
4. **Q4 — where the threshold lives long-term.** `PLAN.md` Phase 1 says derived constants belong
   in `features.constants` with their derivation query. When Postgres comes up, does the p90
   threshold become a `features.constants` row alongside the seasonal denominators?
5. **Q5 — EIA `period` convention** (R3). Needs a primary-source check against EIA's own
   documentation before the wind series anchors anything hour-of-day.
6. **Q6 — `horizon_days = 0` for realized wind.** Confirm before any forecast rows land, since
   it is part of the primary key and a later change means rewriting rows.
7. **Q7 — ISO Express reconciliation.** Building an ISO Express `whlsecost` Source and
   reconciling it against `Native Load` on the overlapping months is deliberately out of scope
   here. Worth doing before either series anchors a published number, and it is also how
   `DATA_SOURCES.md` decision 2's ISO-NE-vs-EIA wind reconciliation would be run.
8. **Q8 — date-aware adjacency changes API behaviour.** `POST /scenarios/{id}/runs` with a
   gapped or unsorted `days` list will now return different `stress_windows` than before (the
   old answer merged across gaps). This is a bug fix, but it is client-visible. Should
   `api/app.py` additionally *reject* non-consecutive day lists, the way
   `scenario_input.read_day_profiles` does for the CLI?
9. **Q9 — `features.daily_load` does not fit the transform output.** Five quality/grouping
   columns have no home and `demand_percentile` is not yet computed. A migration 006 (new
   columns or a sibling table) is needed before a Postgres I/O layer exists. Out of scope here;
   flagged so it is not rediscovered.

---

## Verification

Run after every phase; all of it must pass before the branch is called done.

```bash
uv run ruff check .
uv run pytest                      # baseline 231 passed / 3 skipped changes; record the new count

# A: wind extractor, no key set -> actionable error, exit 2, no traceback
env -u EIA_API_KEY uv run python -m owr.etl extract --dataset wind \
  --start 2026-01-01 --end 2026-01-02 --dry-run ; echo "exit=$?"

# A: wind extractor with a key -> rows, and no key in stdout
EIA_API_KEY=$REAL_KEY uv run python -m owr.etl extract --dataset wind \
  --start 2026-01-01 --end 2026-01-08 --dry-run | tee /tmp/wind.out
grep -c "$REAL_KEY" /tmp/wind.out          # must be 0
grep -c "EIA_API_KEY" /tmp/wind.out        # must be >= 1 (the variable NAME is recorded)

# B: probe, then the five-winter pull (background, ~2.3 min per winter)
uv run python -m owr.etl extract --dataset load --start 2021-12-01 --end 2021-12-02 --dry-run
#   ... the loop from Phase B1 ...

uv run python -m owr.etl validate  --input data/raw_load_*.csv
uv run python -m owr.etl transform --input data/raw_load_*.csv --season winter \
  --output data/daily_load.csv --windows-output data/stress_windows.csv

# regression: the engine and simulator CLI are untouched by all of this
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
uv run python examples/make_synthetic_winter_stress.py && \
  git diff --exit-code examples/synthetic_winter_stress.csv     # must stay byte-identical
git status --short                         # data/ must not appear
```

Hand-check the p90 against the B3 sanity band before writing it into any document. If it lands
outside 380,000–420,000 MWh, find out why before publishing — the number is going to be quoted.

---

## Revision note (rev 2, 2026-07-30)

Changes from rev 1, all in response to adversarial review:

- **B3 rewritten.** Run detection is now date-aware *inside the loop*; `require_consecutive_dates`
  as a hard-fail gate is gone, replaced by a reporting-only `date_gaps` validate gate. Rev 1's
  design would have either aborted a whole winter on one 22-hour day or silently merged across
  the excluded day. Behaviour-change disclosure added for `api/app.py:138` (Q8), together with
  the evidence that the existing suite is unaffected.
- **B5 reworded.** Rev 1 claimed the arithmetic identified July 2026. It identifies only that
  one 744-hour file is missing, with ten candidates (five Januaries, five Julys). The uniqueness
  claim is withdrawn; the `ls` is what settles it, and `DATA_SOURCES.md` must not inherit the
  stronger claim.
- **Test 19 added:** `FakeEIAClient.list_routes`/`list_facets` raise, turning the
  never-call-these rule from a comment into an enforced canary.
- **B4:** explicit `features.daily_load` reconciliation debt written up (Q9) — five columns with
  no home, `demand_percentile` missing.
- **Tests 22–25 and 31:** each now sets or clears `EIA_API_KEY` itself; without it the redaction
  assertions passed vacuously. Test 24 gains an unset-variable mirror case so the redaction is
  proven to be env-driven.
- **R13, R14 added:** no retry/backoff on `EIA.get_dataset` (flagged for the future wind
  backfill); residual key-exposure paths via wire logging and debugger frame locals.
- Test numbering is contiguous 1–69 after the additions.
