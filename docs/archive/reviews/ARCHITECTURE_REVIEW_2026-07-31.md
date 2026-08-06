# Architecture Review — `Software Architecture Documentation`
Reviewed 2026-07-31. Source artifact: `Software Architecture Documentation.pdf`, 35 pages,
downloaded 2026-07-30 21:05.

Scope: the seven-component specification (Global Assumptions, Global Interface Contract,
Data Governance, Components 1–7) plus the "Archived" V1.0 MVP architecture and Step 1–7
working notes at the end.

Method: claim extraction, dimensional analysis of every formula, cross-check of every
numeric default against the project's own measured data (`docs/FACT_CHECK_REPORT.md`,
p90 computed 2026-07-30), and comparison against primary-source practice per
`docs/DATA_SOURCES.md` conventions. Sources are listed inline; every recommendation
carries one.

---

## 1. What the document specifies

A seven-stage batch pipeline, each stage a "software component" with a purpose, a data
contract, and validation rules:

| # | Component | Job |
|---|---|---|
| 1 | Scenario Configuration | Collect and validate user scenario parameters up front |
| 2 | Data Pipeline | Per winter: extract hourly load/wind/oil/gas, scale wind, validate |
| 3 | Stress Event Detection | Daily load ≥ p90 for ≥ `minimum_window` consecutive days |
| 4 | Simulation Initialization | Set starting SOC and the pre-event charging window |
| 5 | Storage Dispatch Engine | Hourly rolling-forecast dispatch inside each event |
| 6 | Grid Simulation Engine | Apply dispatch, update SOC, advance the clock |
| 7 | Scenario Metrics Engine | Nine scenario metrics + a Scenario Robustness Score |

Three cross-cutting sections govern all seven: **Global Assumptions and Rules** (the
parameter register), **Global Interface Contract** (every component returns a status
envelope with `execution_status`, timings, counts; every exchanged object carries five
version fields), and **Data Governance** (naming, precision, storage, logging).

The default scenario is **3,000 storage units, 60,000 MWh total energy, 4,320 MW power
output, 200 (unit ambiguous) transmission capacity, `minimum_event_window` = 2 days**.

The intent is sound and, in one respect, better than what the project has been running on:
it separates identification from dispatch from measurement, it demands a data contract at
every boundary, and it makes provenance and versioning a first-class interface requirement
rather than an afterthought. The Global Interface Contract in particular is the strongest
part of the document.

---

## 2. Blocking defects

Ordered by how much damage each does if it reaches code.

### B1. The document specifies that nothing shall be assumed, then leaves ~70 values unspecified

"The following engineering decisions require explicit values before implementation. No
implicit assumptions shall be made." Immediately beneath it, **every** System, Storage,
Transmission, Dispatch, Event, and Error-Handling parameter is `@`. The same holds for all
of Data Governance, the entire Component 3 data contract (every column's Required, Type,
Unit and Description), and the Scenario Robustness Score aggregation rule.

Two "Step 6" headings exist. The first is empty; the second carries a formula block
(available supply, capacity margin, peak reduction, net load smoothing, state of charge,
priority weighting) that does not belong under the same number as the first. Step 5
truncates on an empty bullet, and the numbering runs 1–5, 6 (empty), 7, 6 (populated).
Step 1–7 working notes and the archived V1.0 section overlap the component spec without any
statement of which governs.

The document cannot be implemented as written. It is a well-shaped template with the
decisions removed — and its own opening sentence says an implementer must not fill them in.

### B2. Three efficiency values are declared independent when two determine the third

Storage Assumptions lists `charging efficiency`, `discharging efficiency`, and `round-trip
efficiency` as three separate parameters. They are not independent — RTE = η_charge ×
η_discharge by construction. Three free values admit a contradictory triple. (This needs no
citation; it is arithmetic.)

Worse, the archived state equation uses **one** symbol for both directions:

```
soc(t+1) = soc(t) + charge(t)·efficiency − discharge(t)/efficiency
```

That form is only correct if `efficiency` is the **one-way** figure, √RTE. Mitchell's
2026-07-28 spec gives 0.70 without saying which it is. Substituting 0.70 as a round-trip
value into this equation yields an effective round trip of 0.70 × 0.70 = **0.49** — a 30%
understatement of every discharge. `docs/HANDOFF.md` already flags this; the architecture
document reintroduces it rather than closing it.

### B3. The default scenario is internally inconsistent and roughly 4× oversized

The defaults are self-consistent on two of three axes and broken on the third:

- 3,000 units × 20 MWh = 60,000 MWh ✓ matches `total_energy_capcity`
- 4,320 MW ÷ 3,000 units = **1.44 MW/unit** — this is the flow-consistent figure from the
  `HANDOFF.md` physics check (Q = 1.02 m³/s, h = 200 m, η = 0.70), **not** Mitchell's
  stated 1.67 MW. The document has silently adopted one horn of that dilemma.
- But it kept **20 MWh/unit**, which the same check shows is the full-depth (600–800 m)
  rating. At h = 200 m and η = 0.70 a 30 m sphere holds **~5 MWh**.

Adopting the 1.44 MW resolution while retaining 20 MWh is picking one side of the
inconsistency and one side of the resolution. If the sphere really is ~5 MWh at 200 m, the
fleet is **15,000 MWh, not 60,000** — and every downstream result is 4× optimistic.

### B4. Transmission capacity is given in MWh and set to a value that makes the asset inert

`transmission_capacity`, default **200.0 MWh**, "Maximum transmission energy capacity."
Transmission is a thermal/stability **power** limit, in MW — this is how ISO-NE states
interface and tie limits. Both readings fail:

- If it means 200 MW: the fleet can deliver 200 of its 4,320 MW, **4.6%**. The other 95%
  is stranded, and the simulation measures a transmission constraint rather than a storage
  concept.
- If it literally means 200 MWh: an energy cap 300× smaller than the reservoir, which is
  not a transmission quantity at all.

Component 2's data contract compounds it — `load_mw` is described as "Maximum transmission
energy capacity," a copy-paste from this row. Hourly load is not a transmission limit.

### B5. Stress detection uses a demand percentile to answer a fuel-adequacy question

Component 3's stated purpose is "Identify **supply adequacy** stress events." Its rule
ranks **daily demand**. These are different things, and the project's own framing says so:
`HANDOFF.md` records the 2026-07-27 reframing to winter **fuel adequacy**.

ISO-NE's own study of this question does not use a load percentile. The
[Operational Fuel-Security Analysis](https://www.iso-ne.com/static-assets/documents/2018/01/20180117_operational_fuel-security_analysis.pdf)
models whether enough fuel is available across an entire winter under 23 resource-mix
scenarios, and measures stress as **hours of OP-4 and OP-7 emergency actions** and the
**magnitude of load shedding**. Its framing: fuel-security risk is "the possibility that
power plants won't have or be able to get the fuel they need to run." The standard
adequacy measures are likewise output-side — LOLH and LOLE for frequency, **EUE** for
magnitude and duration in MWh — not input-side load percentiles
([NYSRC, *Resource Adequacy Metrics and Their Applications*, 2020](https://www.nysrc.org/wp-content/uploads/2023/03/Resource-Adequacy-Metric-Report-Final-4-20-20206431.pdf)).

The project's own 2026-07-30 measurement is the proof: **summer days out-rank winter days**
on total load, so a load percentile taken over the full year finds a summer problem and
nearly no winter problem. Ranking days by load is a weak proxy for the thing being studied.

### B6. The percentile population is still unspecified

"90th historical daily load percentile" — over which population? Per winter, pooled across
winters, or pooled across the year? Measured 2026-07-30: winter-against-winter gives
**four** events; winter-against-the-year gives close to none. The document does not say,
and the choice determines the headline number.

### B7. Five winters are specified; three exist

Component 2 and the Scenario Robustness Score both enumerate winters 2021/22 → 2025/26.
The free `gridstatus` feed begins 2023-06-30; a 2022 request returns zero rows
(`docs/FACT_CHECK_REPORT.md`). Two of five winters cannot be populated without the
credentialed ISO-NE feed. Component 2's "no missing timestamps" validation will hard-fail
on both, and the Robustness Score divides by a winter count that will never be reached.

### B8. There is no mechanism to recharge between events

Component 5 loops "for each hour between `event_start` and `event_end`." Component 4 sets
subsequent events' starting SOC to "remaining storage from previous event." Component 6
advances the hour inside the event only.

Nothing simulates the **gap** between events — which is precisely when a wind-charged asset
refills. As specified, storage is drained monotonically across a winter and the fourth
event starts near-empty regardless of how much wind blew in between. The archived Step 5
notes contain the missing piece (`recoverable_energy` over the hours between events), but
it is not lifted into any component. Of the two "Step 6" headings, the first is empty and
the second holds an unrelated formula block, so neither carries the inter-event logic
forward.

### B9. The dispatch engine has perfect foresight and calls it forecasting

Component 5 says "Estimate future recharge opportunities… Predict storage trajectory
throughout the remaining event," and the archived formulas use `WindForecast(i)`. But
Component 2 extracts only **historical** generation, and `wind_forecast_frac` is defined as
"wind generation fraction of total 7-day wind generation" — computed from actuals. That is
hindsight relabelled.

This is a known modelling bias. A 2026 retrospective of Europe's 2022 crisis compared
perfect foresight against a two-week rolling horizon on the same system and found limited
foresight reproduced observed dispatch more accurately, with the gap widest under high fuel-price
volatility — the condition this project studies
([Karkossa, Saretta, Gullach & Victoria, arXiv:2606.16486](https://arxiv.org/abs/2606.16486)).

The result this architecture produces is an **upper bound**, and nothing in the document
says so.

### B10. Six of the nine metrics are dimensionally or definitionally broken

| Metric | Defect |
|---|---|
| **Capacity Margin Improvement** | `Σ(net_load_dispatch − net_load_observed) · 100%` — a sum of MW differences times 100%, with **no denominator**. Not a percentage of anything. Sign is also inverted: dispatching storage lowers net load, so this is negative when the asset works. |
| **Stress Window Effectiveness** | `Σ dispatched / Σ(oil + gas + wind)`. Wind in the denominator makes this not a fuel-displacement ratio; adding more wind lowers "effectiveness". |
| **Fuel-Fired Generation Offset** | `Σoil + Σgas − (Σwind + Σdispatched)`. Subtracting wind generation from fuel generation has no physical meaning. `HANDOFF.md` records what the metric is *for* — fuel MWh added pre-event, minus (more expensive) fuel MWh displaced during the event. This formula computes neither term. |
| **Recharge Capacity Mismatch** | `average_cycle_recharge_utilization(t) / maximum_available_capacity` — the numerator is **never defined anywhere in the document**, and a quantity named "mismatch" is computed as a ratio. |
| **Cost per Equivalent Full Cycle** | `est_capital_costs / (annual_EFC · lifetime)`. Capex-only. PNNL's LCOS — cost per unit of discharge energy throughput — additionally counts O&M, augmentations/replacements/major overhauls, calendar and cycle life, DoD limits, taxes and debt costs ([PNNL LCOS Estimates](https://www.pnnl.gov/projects/esgc-cost-performance/lcos-estimates)). Undiscounted capex-per-cycle is not comparable to any published $/MWh storage cost. It also omits **charging energy cost**, which Mitchell's own charging model prices at pre-event LNG — not zero. |
| **Scenario Robustness Score** | "If any single metric falls outside its acceptable operating range… one robustness failure point." Unweighted, binary, equal-severity aggregation over metrics that are strongly correlated (Fuel Offset and Fuel Offset Percentage are the same quantity twice). A 1% miss counts the same as a total failure. The final aggregation rule is `@`. |

### B11. Step 4 requires interactive input mid-run, contradicting the determinism requirement

Archived Step 4: "Ask the user what is the first day they'd like to base calculations on."
The Global Interface Contract requires **deterministic outputs** from every component. A
mid-run human prompt makes runs non-reproducible, blocks scenario sweeps, and makes CI
impossible. If the choice matters it is a scenario parameter, not a prompt.

---

## 3. Design concerns (not blocking, but unsourced or over-constrained)

### D1. Three stacked derating factors, none sourced

A 33% SOC floor, a strategic reserve on top of it, and an 80% cap on the daily energy
budget. Compounded: 60,000 × (1 − 0.33) × 0.80 = **32,160 MWh usable**, 54% of nameplate,
before the strategic reserve is subtracted.

None of the three is sourced anywhere in the document. A 33% floor is a familiar figure from
battery practice, where it is justified by depth-of-discharge effects on cycle life; a
submerged sphere's limits are hydraulic instead (submergence, cavitation, turbine efficiency
at low head). I did not find a primary source establishing either the battery figure's
transferability or a hydraulic equivalent, so this is flagged as **unsourced**, not as
wrong. It needs a stated derivation before it silently removes 46% of the fleet.

### D2. `Priority(d) = 0.7·DemandPercentile(d) + 0.3·WindForecast(d)` — unsourced weights

Both terms are unitless so it computes, but 0.7/0.3 appears nowhere else and has no stated
derivation. This is a design choice, and per repo convention #5 it belongs in `config.py`
as a labeled constant with a sensitivity test, not embedded in a formula.

### D3. Net load subtracts solar, which the pipeline never extracts

`NetLoad(t) = Load(t) − Solar(t) − Wind(t)`. Component 2's extract list is load, wind, oil,
gas, transmission. Solar is missing. In ISO-NE much solar is behind-the-meter and already
netted out of reported load, so subtracting a separately-sourced solar series risks
double-counting. Either way the document contradicts itself.

### D4. The scale sanity check the document never performs

Against the project's own measured p90 of **385,833 MWh/day**:

| Quantity | MWh | % of one p90 winter day |
|---|---|---|
| Nameplate 60,000 MWh | 60,000 | **15.5%** |
| Usable after floor + 80% budget | 32,160 | **8.3%** |
| Usable vs. the 11-day Jan–Feb 2026 event (4,244,163 MWh) | 32,160 | **0.76%** |

And 4,320 MW is roughly 22% of ISO-NE's winter peak — a single asset larger than any
storage facility in the interconnection. Neither figure is discussed. The architecture
should not be able to run a scenario this size without printing that ratio.

### D5. Unit mixing inside a single hourly row

Component 2's contract carries `load_mw` in **MW** alongside `wind_mwh`, `oil_mwh`,
`gas_mwh` in **MWh**, in the same hourly record. On an hourly step these are numerically
equal, which is exactly the coincidence that produced the 24× threshold error already
documented in `FACT_CHECK_REPORT.md`. Other type errors in the same tables:
`percentile_threshold` typed `int` (cannot express 0.90); `peak_daily_load` typed "tuple?"
with unit "MW?" when daily load is energy (MWh); `demand_percentile` a float % while
`percentile_threshold` is an int.

### D6. Naming collisions

`total_capacity` (Component 1 validation ranges) vs `total_energy_capcity` (Component 1
data contract, misspelled) vs `total_capacity` (Global Assumptions, "Maximum allowable
state of charge = total_capacity"). Three names, one concept, one typo. Similarly
`minimum_window` vs `minimum_event_window`.

### D7. "Never bypass an intermediate component" is stricter than the pipeline needs

A hard no-bypass rule forbids the Metrics Engine reading scenario configuration directly,
which it must do (capex per unit, unit count). Strict layering here buys nothing and will
be violated on day one.

### D8. Determinism is required but unenforceable as specified

"Deterministic outputs" with `Version tracking policy = @`. Reproducibility needs pinned
dependency versions, fixed seeds, and a stable float-summation order — none stated. The
project already has the raw material (`uv.lock`, provenance rows) but the contract does not
reference it.

---

## 4. Recommended changes

Each carries a source. Ordered by leverage.

**R1. Replace the load-percentile trigger with a fuel/energy-adequacy trigger, and keep the
load percentile only as a screening filter.**
Detect on an energy-margin quantity — available fuel-secure generation plus imports minus
load, integrated over the window — and report shortfall hours and unserved energy rather
than a day count. ISO-NE studies this question that way
([OFSA](https://www.iso-ne.com/static-assets/documents/2018/01/20180117_operational_fuel-security_analysis.pdf):
whether enough fuel exists across a whole winter, scored in emergency-action hours and
load-shed magnitude), and it maps onto the standard adequacy measures — LOLH for frequency,
EUE for magnitude in MWh
([NYSRC 2020](https://www.nysrc.org/wp-content/uploads/2023/03/Resource-Adequacy-Metric-Report-Final-4-20-20206431.pdf)).
It also dissolves the summer-vs-winter ranking problem, because fuel scarcity is seasonal
in a way that demand height is not.

**R2. Collapse the three efficiency parameters to two and state which one 0.70 is.**
Specify `eta_charge` and `eta_discharge`; derive RTE = η_c × η_d and never accept it as
input. Rewrite the state equation as `soc(t+1) = soc(t) + charge·η_c − discharge/η_d`. Add
a unit test asserting a full charge/discharge round trip returns exactly RTE. For a
standard definition to adopt in the glossary, open
[SAND2013-7084 / PNNL-22010](https://www.osti.gov/biblio/1096455) — I confirmed the record
but have not read the text, so do not paste a definition from it unopened.

**R3. Adopt rolling-horizon dispatch with an explicit forecast-error model, and label the
perfect-foresight run as an upper bound.**
Keep the current formulation as a deliberate "perfect foresight" ceiling scenario, add a
realistic run where the forecast is the actual series plus a calibrated error, and report
both. The gap between them is the value at risk from forecast quality. The two-week
rolling horizon in [arXiv:2606.16486](https://arxiv.org/abs/2606.16486) is a documented
choice of window; that paper is also the evidence that the ceiling run overstates.

**R4. Simulate the full winter, not only the event windows.**
Run the hourly loop continuously across Dec 1 – Feb 28/29 with events as annotations on the
timeline rather than as the loop bounds. This is the only way inter-event recharge is
represented, and it matches ISO-NE's own study design, which models the **entire winter
period** rather than selected days
([OFSA](https://www.iso-ne.com/static-assets/documents/2018/01/20180117_operational_fuel-security_analysis.pdf)).
It also removes the arbitrary SOC = 0 initialization: add a spin-up winter whose results
are discarded.

**R5. Rebuild the cost metrics on the PNNL LCOS method.**
Replace "Cost per Equivalent Full Cycle" with a levelized cost per MWh discharged. PNNL's
page enumerates the components: capex, O&M, augmentations/replacements/major overhauls,
calendar and cycle life, DoD limits, taxes and debt costs
([LCOS Estimates](https://www.pnnl.gov/projects/esgc-cost-performance/lcos-estimates)).
Add charging energy, which is not free — Mitchell's 2026-07-28 model prices it at pre-event
LNG. Publish the discount rate and lifetime as scenario inputs. Open the LCOS workbook
documentation for the discount-rate convention before adopting one; I did not.

**R6. Fix the six broken metric formulas before any of them is implemented.**
Capacity Margin Improvement needs a denominator and a sign convention:
`(Σ observed − Σ dispatched) / Σ observed × 100`. Stress Window Effectiveness should drop
wind from the denominator. Fuel-Fired Generation Offset should be written as the two-term
quantity `HANDOFF.md` already defines (fuel added pre-event minus fuel displaced in-event),
not a subtraction of wind from fuel. Define `average_cycle_recharge_utilization` or delete
the metric that uses it. Every metric gets a stated unit and a dimensional-consistency
test. Source: the project's own repo convention #3 — a verdict before a number reaches a
deliverable. The defects here are arithmetic and need no external authority.

**R7. Replace the binary Robustness Score with a severity-weighted, explicitly-defined
aggregation — or drop it.**
Equal-weight binary failure points over correlated metrics is not a robustness measure.
If a single number is wanted, weight by severity and state the weights. Adequacy practice
reports frequency and magnitude as separate metrics — LOLE/LOLH count occasions, EUE
measures MWh — because neither alone describes the risk
([NYSRC 2020](https://www.nysrc.org/wp-content/uploads/2023/03/Resource-Adequacy-Metric-Report-Final-4-20-20206431.pdf)).
A vector beats a scalar that hides which metric failed.

**R8. Correct the storage defaults, or state which two of {diameter, head, energy} are
fixed.**
Either 20 MWh/unit at 600–800 m, or ~5 MWh/unit at 200 m — the current mix of 1.44 MW/unit
(the 200 m answer) with 20 MWh/unit (the 700 m answer) cannot hold. The governing relation
is the one already adopted in `HANDOFF.md`, `P = ρ·g·Q·h·η`, with energy scaling roughly
linearly in head. Whichever is chosen, print the resulting duration (E/P) and the fleet's
share of a p90 winter day at scenario-validation time.

**R9. Restate transmission as a power limit in MW and validate it against the fleet.**
`transmission_capacity_mw`, with a Component 1 validation rule that rejects any scenario
where it is below some stated fraction of `reserve_power_output`, or warns loudly that the
run measures a transmission constraint. Interface and tie limits are stated in MW
throughout ISO-NE's transmission planning material; energy caps on a wire are not a
physical quantity.

**R10. Adopt an explicit units and time convention in Data Governance and enforce it in
type names.**
Suffix every field with its unit (`load_mw`, `energy_mwh`) — already half-done — and never
mix power and energy in one record without both being labeled. Store all timestamps as
UTC in ISO 8601 with the interval length on every row; the project's raw load schema
already does this (`interval_minutes` on every row, per `docs/HANDOFF.md`), so this is
propagating an existing good decision rather than inventing one. This is the direct
countermeasure to the 24× error recorded in `docs/FACT_CHECK_REPORT.md`.

**R11. Source the SOC floor or remove it.**
No source is given in the document and I found none that transfers a battery DoD floor to
a submerged pumped-hydro sphere. State the hydraulic constraint that sets the floor, or set
it to zero and let the strategic reserve be the only operational floor. Either way, stop
compounding three derates silently — print usable energy as a fraction of nameplate in
every scenario summary. This one is a **gap flag, not a finding**.

**R12. Delete every `@`, or mark the document `DRAFT — not implementable`.**
Each `@` is an unresolved team decision. Give each one an owner and a date, in the same
register format `docs/HANDOFF.md` already uses for open questions 1–8, and surface
disagreements as decisions rather than filling them in silently (repo convention #4).

**R13. Make Step 4's interactive prompt a scenario parameter.**
`charge_window_start_day`, defaulted and labeled, with the alternatives reported as a
sensitivity sweep. This restores the determinism the Global Interface Contract already
requires.

**R14. Reconcile the archived V1.0 section with the component spec, or remove it.**
Step 5's `recoverable_energy` logic is the only place inter-event recharge is described, and
it lives in a section labeled "Archived." Step 6 appears twice — once empty, once holding an
unrelated formula block — so the step numbering itself needs repairing before the content
can be traced. Either promote the logic into Component 4/5 or mark the archived block
explicitly superseded, with a note on which parts were absorbed.

**R15. State the data coverage honestly in Component 2 and the Robustness Score.**
Three winters, 2023/24 – 2025/26, on the free feed. Make winter count a derived property of
the data rather than a hard-coded list of five, and have the Robustness Score normalize by
winters actually simulated.

---

## 5. What to keep

Not everything here is a problem, and the parts worth defending are worth naming:

- **The Global Interface Contract.** A uniform status envelope, five version fields on every
  exchanged object, and a validated-input/validated-output rule at every boundary. This is
  the auditability the project's title claims, expressed as a contract.
- **Separation of identification from dispatch from measurement.** Components 3, 5, and 7
  being distinct is what allows the p90 population question to be re-decided without
  touching dispatch.
- **Per-winter independent evaluation.** Treating each winter as its own trial is the right
  shape for a small sample, even though the aggregation on top of it needs rework.
- **Immutable historical data, mutable state only through defined contracts.** Correct, and
  the precondition for the determinism the document asks for.

---

## 6. Verdict summary

| Section | Verdict |
|---|---|
| Global Assumptions and Rules | **Contradicted** — self-negating (B1) |
| Global Interface Contract | **Verified** as sound design; incomplete (`@` fields) |
| Data Governance | **Unverifiable** — every value is `@` |
| C1 Scenario Configuration | **Contradicted** — units (B4), naming (D6), defaults (B3) |
| C2 Data Pipeline | **Contradicted** — five winters, three exist (B7); units (D5); solar (D3) |
| C3 Stress Event Detection | **Contradicted** — wrong construct for the question (B5); population unspecified (B6) |
| C4 Simulation Initialization | **Contradicted** — no inter-event recharge (B8); arbitrary SOC=0 |
| C5 Storage Dispatch Engine | **Contradicted** — perfect foresight presented as forecasting (B9) |
| C6 Grid Simulation Engine | **Unverifiable** — too thin to assess |
| C7 Scenario Metrics Engine | **Contradicted** — 6 of 9 metrics defective (B10) |
| Archived V1.0 | **Contradicted** — conflicts with C1–C7, status unstated (B1, R14) |

---

## Source verification, 2026-07-31

Every URL below was fetched. Status is what I could confirm by reading the document, not
what a search snippet asserted.

| Source | Status |
|---|---|
| ISO-NE, *Operational Fuel-Security Analysis*, 17 Jan 2018 | **Verified** — fetched and read. Studies winter 2024/2025 across 23 resource-mix scenarios. Measures stress as hours of OP-4 / OP-7 emergency actions and magnitude of load shedding. Frames fuel-security risk as "the possibility that power plants won't have or be able to get the fuel they need." |
| arXiv:2606.16486 (Karkossa, Saretta, Gullach, Victoria; 15 Jun 2026) | **Verified** — compares "perfect foresight vs a two-week rolling-horizon optimization"; limited foresight improves accuracy, most at high fuel-price volatility. |
| NYSRC, *Resource Adequacy Metrics and Their Applications*, 20 Apr 2020 | **Verified** — fetched and read. Defines LOLH, LOLEV, LOLE, LOLP, EUE. States EUE is energy-centric, capturing magnitude and duration. Cites NERC *Probabilistic Adequacy and Measures* (July 2018) as the basis for its definitions. |
| Sandia/PNNL, *Protocol for Uniformly Measuring and Expressing the Performance of Energy Storage Systems* | **Partly verified** — OSTI record confirms SAND2013-7084 (2013), Ferreira, Rose, Schoenwald, Bray, Conover, Kintner-Meyer, Viswanathan; SNL + PNNL. The PNNL-22010 Rev. 2 PDF exists but exceeded the fetch size limit, so I have **not** read its RTE wording. Do not quote it without opening it. |
| PNNL, LCOS Estimates | **Verified** — defines LCOS as cost per unit of discharge energy throughput ($/kWh); lists capex, O&M, ARMO, calendar/cycle life, DoD limits, taxes and debt costs. The page does **not** state a WACC value; that came from the workbook documentation, which I did not open. |
| NERC, *Probabilistic Adequacy and Measures* | **Not verified** — nerc.com returned HTTP 403. Its existence and July 2018 date are corroborated by the NYSRC report's footnote. Cite NYSRC, not this, until someone opens it. |
| NREL, docs.nrel.gov/docs/fy22osti/80688.pdf | **Withdrawn** — the host did not resolve on two attempts. The perfect-foresight quote attributed to it came from a search snippet only. Removed from this review; arXiv:2606.16486 carries the same point and was read. |
| *Energies* 18(7):1751 | **Withdrawn** — mdpi.com returned HTTP 403. Unread. |
| Lazard LCOS v7.0 | **Withdrawn** — not fetched, and not load-bearing for any recommendation. |
| Clean Energy Reviews, battery DoD | **Withdrawn** — a vendor-adjacent blog, which repo convention #3 does not accept as a source. The SOC-floor finding is restated below as "unsourced in the document," which is what it is. |

## Sources

Read in full:

- ISO New England, *Operational Fuel-Security Analysis*, 17 Jan 2018 — https://www.iso-ne.com/static-assets/documents/2018/01/20180117_operational_fuel-security_analysis.pdf
- NYSRC Resource Adequacy Working Group, *Resource Adequacy Metrics and Their Applications*, 20 Apr 2020 — https://www.nysrc.org/wp-content/uploads/2023/03/Resource-Adequacy-Metric-Report-Final-4-20-20206431.pdf
- Karkossa, Saretta, Gullach & Victoria, *Can Optimal Dispatch Models Recreate Reality? A Retrospective Analysis of Europe's 2022 Energy Crisis Using PyPSA-Eur*, arXiv:2606.16486, 15 Jun 2026 — https://arxiv.org/abs/2606.16486
- PNNL, LCOS Estimates — https://www.pnnl.gov/projects/esgc-cost-performance/lcos-estimates

Record confirmed, full text not read — do not quote:

- Ferreira et al., *Protocol for Uniformly Measuring and Expressing the Performance of Energy Storage Systems*, SAND2013-7084, SNL/PNNL, 2013 — https://www.osti.gov/biblio/1096455 (PNNL-side copy: PNNL-22010 Rev. 2)
- NERC, *Probabilistic Adequacy and Measures*, July 2018 — named in the NYSRC report; nerc.com returns 403
- PNNL, Energy Storage Cost and Performance Database — https://www.pnnl.gov/projects/esgc-cost-performance

Internal references: `docs/HANDOFF.md`, `docs/FACT_CHECK_REPORT.md`, `docs/DATA_SOURCES.md`.
