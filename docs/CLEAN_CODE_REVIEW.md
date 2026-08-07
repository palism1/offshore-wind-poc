# Clean Code Review — `src/owr/`

*Applied against the principles in Robert C. Martin's* Clean Code *(2008).  
Each finding lists: **File** · **Issue** · **Rationale** · **Suggested improvement**.*

---

## 1. Function Size

Martin's rule: *functions should do one thing, do it well, and do it only*.
In practice, a function that fits on one screen and reads like a paragraph
satisfies this. The threshold used below is ~30 lines as a warning and ~60 as a
strong signal.

---

**`simulator.py` → `simulate()`**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | ~115 lines; performs input validation, per-day budget allocation, a nested hourly SoC loop, and daily record assembly — four distinct responsibilities. |
| Rationale | Martin: *"The first rule of functions is that they should be small. The second rule of functions is that they should be smaller than that."* A reader must mentally context-switch between orchestration logic and SoC arithmetic in the same function body. |
| Suggested improvement | Extract the inner hourly loop into `_simulate_day(day, budget, asset, config, …) → DailyResult`. Keep `simulate()` as a thin orchestrator that iterates days and accumulates results. |

---

**`cli.py` → `_build_report()`**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | ~165 lines; computes summary metrics, accumulates recharge-mismatch totals, runs a min-margin scan, assembles open-question dicts, and returns a single large output dict. |
| Rationale | This function is doing output formatting, metric aggregation, and data serialisation simultaneously. Changes to any one concern require reading all 165 lines to understand the effect. |
| Suggested improvement | Split into `_compute_metrics(result, …) → Metrics`, `_build_open_questions(args, cfg, …) → list[dict]`, and a thin `_build_report()` that calls both and assembles the final dict. |

---

**`cli.py` → `_run()`**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | ~125 lines; parses and validates input, selects a simulation window, runs pre-charge, runs simulation, and dispatches to the renderer. Five phases in one function. |
| Rationale | The window-selection branch (a 30-line if/else assigning three variables) is a named sub-operation that cannot be unit-tested without running the entire CLI argument object. |
| Suggested improvement | Extract `_select_span(args, windows) → tuple[int, int, str]` for the window-selection logic. Extract argument validation to `build_parser()` or a dedicated `_validate_args(args)` call before any computation begins. |

---

**`simulator.py` → `SimulationResult.hourly_frame()`**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | ~70 lines; declares 10 identically-typed empty lists, appends to all 10 inside a single loop, then constructs a DataFrame by repeating those same 10 names as column labels. |
| Rationale | The parallel-list pattern distributes one logical operation (flatten hourly records to a tabular form) across 30+ lines of boilerplate that can diverge when fields are added. The column list and the append list must be kept in sync by hand. |
| Suggested improvement | Replace with a list-of-dicts comprehension — `rows = [vars(h) for d in self.daily for h in d.hourly]` — then `pd.DataFrame(rows)`. The structure of each row mirrors the structure of `HourlyResult`, making additions self-maintaining. |

---

**`scenario_input.py` → `read_day_profiles()`**

| Field | Detail |
|---|---|
| File | `src/owr/scenario_input.py` |
| Issue | ~185 lines; strips comments, parses a CSV, validates headers, aggregates by date/hour, checks completeness, checks for date gaps, and derives the demand-percentile column when absent. Seven distinct operations. |
| Rationale | A reader wanting to understand *only* the gap-checking logic must skip past CSV parsing and header validation. Each of the seven operations has a different failure mode and testing requirement. |
| Suggested improvement | Decompose into private helpers: `_strip_comments(path)`, `_validate_headers(df)`, `_aggregate_rows(df)`, `_check_completeness(by_date)`, `_check_no_gaps(dates)`, `_derive_percentile(by_date)`. `read_day_profiles()` becomes a six-line orchestrator. |

---

## 2. Argument Count

Martin's rule: *the ideal number of arguments for a function is zero. … More than three arguments requires very special justification — and then shouldn't be used anyway.*

---

**`simulator.py` → `simulate()` — 7 parameters**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | `asset`, `window_days`, `starting_soc`, `available_capacity_mw`, `config`, `peak_weight`, `smooth_weight` — seven parameters. |
| Rationale | The two weight parameters (`peak_weight`, `smooth_weight`) always travel together and represent a single concept: the blending strategy for discharge. Passing them as separate floats forces every call site to unpack and re-pass both. |
| Suggested improvement | Introduce a `DispatchWeights(peak: float, smooth: float)` dataclass (or reuse an existing named tuple). Reduce the signature to five parameters; consider whether `config` could carry the weights, reducing it further to four. |

---

**`cli.py` → `_build_report()` — 13 keyword-only parameters**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | 13 keyword-only arguments: `args`, `day_set`, `days`, `windows`, `span`, `window_label`, `lead_days_used`, `s0`, `soc_at_start`, `asset`, `cfg`, `result` — and one positional `result`. |
| Rationale | A 13-argument function is a strong signal that the function is doing too much. It also makes call sites verbose and fragile — adding a new metric requires threading another parameter through the entire call chain. |
| Suggested improvement | Bundle the simulation context (`asset`, `cfg`, `result`, `days`, `windows`, `span`, `window_label`, `lead_days_used`, `s0`, `soc_at_start`) into a `ReportContext` dataclass that `_run()` constructs and passes as one object. |

---

## 3. Naming

Martin's rule: *use intention-revealing names … avoid mental mapping … use pronounceable names … don't be cute.*

---

**`simulator.py` → `dp`, `ds`**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | `dp, ds = d_peak[h] * ratio, d_smooth[h] * ratio` — single-letter variables that abbreviate "discharge peak" and "discharge smooth". |
| Rationale | A reader must hold the earlier list names in working memory to decode the abbreviations. There is no gain in conciseness: both variables appear only a few lines below their definition. |
| Suggested improvement | `discharge_peak_scaled, discharge_smooth_scaled = d_peak[h] * ratio, d_smooth[h] * ratio`. |

---

**`simulator.py` → `d_total`, `d_peak`, `d_smooth`**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | The `d_` prefix is ambiguous. In the same function, `d` also loops over `DailyResult` objects (`for i, day in enumerate(window_days): … DailyResult`). A reader may parse `d_total` as "daily total". |
| Rationale | Name collisions with loop variables erode trust in variable names. |
| Suggested improvement | Rename to `hourly_discharge`, `hourly_discharge_peak`, `hourly_discharge_smooth` to make the per-hour nature explicit. |

---

**`dispatch.py` → `pw`, `sw`**

| Field | Detail |
|---|---|
| File | `src/owr/dispatch.py` |
| Issue | `pw = peak_weight / total_weight` and `sw = smooth_weight / total_weight` — two-letter abbreviations for normalised blending weights. |
| Rationale | The variables appear in the formula immediately below, but the formula uses the abbreviated names, making it harder to read the mathematical intent. |
| Suggested improvement | `peak_weight_n, smooth_weight_n = peak_weight / total_weight, smooth_weight / total_weight` (the `_n` suffix for "normalised" is a common physics/controls convention). |

---

**`cli.py` → `s0`**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | `s0` is used for the starting state of charge passed to `_build_report()` and `simulate()`. The name is borrowed from mathematical notation. |
| Rationale | Martin: *"Use pronounceable names."* `s0` fails this test. It also carries no unit information; units are critical in an energy simulation. |
| Suggested improvement | `initial_soc_mwh`. |

---

**`cli.py` → `n` (window selector)**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | `n = args.window` — `n` is used as a window index. In the Python ecosystem `n` conventionally means "count" or "number of items". |
| Rationale | The name triggers a false prior. A reader familiar with Python will assume `n` is a count and be surprised when it is used as an offset into a list. |
| Suggested improvement | `window_index = args.window`. |

---

**`cli.py` → `w0`, `w1`**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | `w0`, `w1` are the start and end indices into the day list for the selected stress window. |
| Rationale | The names carry no information about what the index represents. |
| Suggested improvement | `first_day_idx, last_day_idx`. |

---

**`simulator.py` → `usable_energy_vals`**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | The `_vals` suffix conveys no information that the type annotation `list[float]` does not already convey. |
| Rationale | Noise suffixes (`_vals`, `_list`, `_data`) clutter names without adding meaning. |
| Suggested improvement | `usable_energies`. |

---

## 4. Dead Code

Martin's rule: *dead code … should be deleted from the codebase. It creates noise and can mislead a reader.*

---

**`simulator.py` → `discharged_today`**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | `discharged_today = 0.0` is initialised before the inner hourly loop and `discharged_today += discharge` is accumulated inside it. The variable is never read after the inner loop closes and is not stored in `DailyResult`. |
| Rationale | A reader encountering `discharged_today` inside the loop will expect it to influence downstream logic. Following the variable to its end — and discovering it has no downstream use — wastes time and erodes confidence that the code is correct. |
| Suggested improvement | Delete the variable and its accumulation line. If a "total discharge per day" metric is needed in future, derive it from `DailyResult.hourly` rather than accumulating a throwaway variable in the simulation loop. |

---

## 5. Comments

Martin's rule: *explain yourself in code … a comment is a failure to express yourself in code … don't add obvious noise comments … comments should explain why, not what.*

---

**`dispatch.py` — "what" comment**

| Field | Detail |
|---|---|
| File | `src/owr/dispatch.py` |
| Issue | `# Normalize each signal to a shape (sums to 1), then blend by the weights.` describes the operation the code is about to perform — which is already apparent from reading the code. |
| Rationale | A comment that repeats the code is noise. When the code changes the comment may not, making it actively misleading. |
| Suggested improvement | Replace with a *why* comment: `# Normalise to a unit shape so that signal magnitude doesn't inflate one component's contribution to the budget.` |

---

**`dispatch.py` — unexplained "provisional"**

| Field | Detail |
|---|---|
| File | `src/owr/dispatch.py` |
| Issue | `# Provisional per-hour split of the budget.` — the word "provisional" is unexplained. |
| Rationale | A reader will reasonably ask: "provisional relative to what?" The answer (the power-cap clipping that follows may reduce the actual delivered power below this split) is critical for understanding the algorithm, but is absent from the comment. |
| Suggested improvement | `# Initial per-hour target; actual delivery may be clipped below this by the MW power cap in the caller.` |

---

**`cli.py` — duplication comment without a TODO**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | The comment on `_severity_reduction` notes it is a copy of a function that exists elsewhere but does not mark this as technical debt. |
| Rationale | Without a `# TODO` or issue reference, the comment is an observation with no action attached. Future maintainers have no automated way to find or track the debt. |
| Suggested improvement | Add `# TODO: deduplicate — identical copies exist in api/app.py and metrics.py (see refactoring_candidates.md §Duplicate Logic)`. |

---

**`simulator.py` — a good example to follow**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | n/a — this is a positive finding. |
| Rationale | The inline comment `# Discharge, clamped again against the live SoC (budget is an energy cap, but SoC must never cross the reserve floor within the day)` answers *why* a second clamp is needed even though one already exists in `soc_engine`. This is exactly what Martin means by a comment that earns its place. |
| Suggested improvement | Use this comment as a template for other non-obvious guards in the codebase. |

---

## 6. Abstraction Level

Martin's rule: *we want every function to be followed by those at the next level of abstraction so that we can read the program, descending one level of abstraction at a time.*

---

**`simulator.py` → `simulate()` — mixed levels in one loop body**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | The outer `for i, day` loop mixes high-level orchestration (priority scoring, budget allocation, daily record construction) with low-level detail (SoC mutation, list appending, margin arithmetic). The inner `for h` loop is a third abstraction level nested inside both. |
| Rationale | Martin: *"In order to make sure our functions are doing 'one thing', we need to make sure that the statements within our function are all at the same level of abstraction."* A reader must shift mental gears three times within a single function. |
| Suggested improvement | The outer loop body should read like prose: `budget = allocate_daily_budget(day, asset, config)` → `daily = _simulate_day(day, budget, soc, asset, config)` → `results.append(daily)`. The hourly arithmetic lives entirely in `_simulate_day`. |

---

**`simulator.py` — named operation embedded as inline ternary**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | `ratio = discharge / d_total[h] if d_total[h] > 0 else 0.0` is a guard-and-divide that performs "scale the peak/smooth split to the actually-delivered discharge". The operation has a name; the code does not give it one. |
| Rationale | An unnamed inline ternary inside a double loop increases cognitive load. Extracting it to a named expression — even a single assignment — communicates intent. |
| Suggested improvement | `delivery_ratio = discharge / d_total[h] if d_total[h] > 0 else 0.0  # actual vs. budgeted`. |

---

## 7. Duplication

Martin's rule: *duplication may be the root of all evil in software … when the same algorithm is implemented over and over again.*

---

**`cli.py` — eight near-identical open-question dict literals**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | Eight dict literals are constructed in sequence, each with the same five keys (`id`, `flags`, `value_used`, `note`, `handoff_ref`) and the same structure, differing only in the values. |
| Rationale | Each literal must be read individually to spot the differences. Adding a sixth key requires eight edits. One missing key introduces a schema inconsistency that is invisible until runtime. |
| Suggested improvement | Define a small `_oq(id, flags, value_used, note, handoff_ref)` factory function (or a named tuple / dataclass). Construct the list as `[_oq("rsr", …), _oq("capacity", …), …]`. The structure is stated once; deviations become immediately visible. |

---

**`cli.py` — duplicate nested generator**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | `sum(h.discharge for d in result.daily for h in d.hourly)` and `sum(h.charge for d in result.daily for h in d.hourly)` appear two lines apart and share an identical traversal pattern. |
| Rationale | If `DailyResult` or `HourlyResult` changes its structure, both generators must be updated. If the loop structure is wrong in one, it is wrong in both. |
| Suggested improvement | Extract `_sum_hourly(result, attr)` or pre-flatten: `hourly = [h for d in result.daily for h in d.hourly]` then `sum(h.discharge for h in hourly)`, `sum(h.charge for h in hourly)`. |

---

## 8. Control Flow

Martin's rule: *functions should descend into one level of abstraction per call … avoid deeply nested control structures … extract conditionals.*

---

**`cli.py` → `_run()` — symmetric if/else assigns the same three variables**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | `if args.window == "all": … else: …` — both branches assign `lead`, `span`, and `window_label`. The two branches are symmetric: they perform the same *goal* (span selection) via different logic but cannot be distinguished by name. |
| Rationale | When both branches of a conditional assign the same variables, the conditional is a single computation with two cases. Extracting it to a named function makes the goal explicit, reduces `_run()` by ~30 lines, and makes the selection logic independently testable. |
| Suggested improvement | `lead, span, window_label = _select_span(args, windows)`. |

---

**`cli.py` → `_run()` — argument validation after parse boundary**

| Field | Detail |
|---|---|
| File | `src/owr/cli.py` |
| Issue | Numeric range checks (`cycles_per_year <= 0`, `efficiency <= 0`, etc.) are performed inside `_run()` after argument parsing rather than in `build_parser()` or a dedicated validator. |
| Rationale | Mixing validation with simulation logic in `_run()` makes `_run()` responsible for two things: validating inputs and running a simulation. Validation failures produce ad-hoc error messages rather than consistent `argparse`-style error formatting. |
| Suggested improvement | Add `argparse` `type=` validators for numeric ranges, or extract `_validate_args(args) → None` called immediately after `parser.parse_args()` before any simulation state is created. |

---

## 9. Readability

Martin's rule: *code should read like well-written prose … the ratio of time spent reading versus writing is well over 10 to 1 … making it easy to read makes it easier to write.*

---

**`simulator.py` → `hourly_frame()` — 10 parallel empty lists**

| Field | Detail |
|---|---|
| File | `src/owr/simulator.py` |
| Issue | The method opens with 10 `[] ` declarations, then enters a loop that appends to all 10, then names all 10 as DataFrame columns. Three separate places must stay in sync when the output schema changes. |
| Rationale | The mechanical symmetry obscures the transformation: "convert a list of `HourlyResult` objects to a tabular form". When that intention is stated directly, the structure cannot diverge. |
| Suggested improvement | `pd.DataFrame([h.__dict__ for d in self.daily for h in d.hourly])` if `HourlyResult` is a dataclass, or an explicit list-of-dicts comprehension with selected fields. |

---

**`soc_engine.py` → two conceptual steps fused in one expression**

| Field | Detail |
|---|---|
| File | `src/owr/soc_engine.py` |
| Issue | `return max(0.0, soc - asset.min_soc_mwh) * asset.one_way_efficiency` — "floor at reserve" and "scale by efficiency" are two distinct physical operations fused into one line. |
| Rationale | The expression is correct and concise, but a reader must parse both operations simultaneously. When one changes (e.g., adding a temperature-derate factor), the correct insertion point is not obvious. |
| Suggested improvement | `available_mwh = max(0.0, soc - asset.min_soc_mwh)` then `return available_mwh * asset.one_way_efficiency`. The two-step structure matches the physics description in engineering documentation. |

---

## Summary Table

| # | File | Principle | Severity |
|---|---|---|---|
| 1 | `simulator.py` → `simulate()` | Function size | High |
| 2 | `cli.py` → `_build_report()` | Function size | High |
| 3 | `cli.py` → `_run()` | Function size | High |
| 4 | `simulator.py` → `hourly_frame()` | Function size | Medium |
| 5 | `scenario_input.py` → `read_day_profiles()` | Function size | High |
| 6 | `simulator.py` → `simulate()` — 7 params | Argument count | High |
| 7 | `cli.py` → `_build_report()` — 13 params | Argument count | High |
| 8 | `simulator.py` → `dp`, `ds` | Naming | Medium |
| 9 | `simulator.py` → `d_total`, `d_peak`, `d_smooth` | Naming | Medium |
| 10 | `dispatch.py` → `pw`, `sw` | Naming | Medium |
| 11 | `cli.py` → `s0` | Naming | Medium |
| 12 | `cli.py` → `n` | Naming | Low |
| 13 | `cli.py` → `w0`, `w1` | Naming | Low |
| 14 | `simulator.py` → `usable_energy_vals` | Naming | Low |
| 15 | `simulator.py` → `discharged_today` | Dead code | Medium |
| 16 | `dispatch.py` — "what" comment | Comments | Low |
| 17 | `dispatch.py` — unexplained "provisional" | Comments | Low |
| 18 | `cli.py` — missing TODO marker | Comments | Low |
| 19 | `simulator.py` → mixed abstraction in loop | Abstraction level | High |
| 20 | `simulator.py` → unnamed inline ternary | Abstraction level | Low |
| 21 | `cli.py` → 8 identical dict literals | Duplication | Medium |
| 22 | `cli.py` → duplicate nested generator | Duplication | Low |
| 23 | `cli.py` → `_run()` if/else span selection | Control flow | Medium |
| 24 | `cli.py` → validation inside `_run()` | Control flow | Medium |
| 25 | `simulator.py` → `hourly_frame()` parallel lists | Readability | Medium |
| 26 | `soc_engine.py` → fused expression | Readability | Low |

**High**: warrants a dedicated refactor story before the codebase grows.  
**Medium**: address during the next planned refactor sprint.  
**Low**: opportunistic — fix when touching the file for another reason.
