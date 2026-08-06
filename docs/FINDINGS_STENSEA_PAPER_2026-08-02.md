# Findings — Dick et al., StEnSea, Journal of Ocean Technology 18(1), 2023

Superseded in part on 2026-08-06 by `docs/PLAN_REVIEW_FIXES.md` decision D1: the
engine now splits the round-trip value itself, so `--efficiency 0.72` is correct
and `sqrt(0.72)` must not be entered.

Date: 2026-08-02. Point-in-time record, not current state.

Source: `docs/source/Dick_et_al_StEnSea_V18N1.pdf`. Nine pages, journal pages 65 to 73.
Authors: Christian Dick and Jonas Sprengelmeyer (Fraunhofer IEE), Gabriel Falzone (RCAM
Technologies). Read 2026-08-02.

**This report has not been fact-checked.** The two load-bearing code claims were spot-checked
by hand and hold: `src/owr/soc_engine.py:21` reads
`soc + charge * efficiency - discharge / efficiency`, and `src/owr/config.py:37` calls that field
"Round-trip efficiency". Every other claim below carries the reader's own citation and no
independent verdict.

---

## Answer first

The paper states **0.72**, and states it as a **round-trip** figure. Open decision 1 in
`docs/HANDOFF.md` is settled. The one-way reading, which would have given a round trip near 0.49,
is dead.

**Two consequences follow immediately.**

1. `soc_engine.py:21` applies its `efficiency` argument once on each leg, so the round trip the
   engine realizes is `efficiency²`. The value that belongs in `Config.default_efficiency` is
   therefore **`sqrt(0.72) = 0.8485`**, not 0.72. A literal 0.72 in that field gives a round trip
   of 0.5184.
2. The paper's rated depth is **750 m**, not the 600 m that Mitchell's `5 MW x 200/600` power
   scaling assumes.

## Source classification

The article carries no abstract, no reference list, and no peer-review statement. It
self-describes as an essay (journal p. 66): "In this essay, we explain the basic working principle
of this storage system and highlight the advantages of a combination with an offshore wind farm in
one of the wind energy areas in California." Author 1 is named as the StEnSea technical project
manager (p. 73).

**Treat this as the developer's own published technical data,** at the same tier as the Fraunhofer
IEE topic page and the Ernst 2024 slide deck already in `docs/DATA_SOURCES.md`. Do not label it a
peer-reviewed paper.

## 1. The efficiency figure

Table 1, "Technical data of the Stored Energy in the Sea (StEnSea) system", journal p. 67. The
table is a raster image, so `pdftotext` drops it; it was read from a 500 dpi render.

> Full cycle efficiency
> η_cycle = η_pump · η_turbine        0.72

**Direction: round trip.** The row names it "Full cycle" and defines it as the product of the pump
and turbine efficiencies. The paper states no other efficiency value anywhere: no separate pump
number, no separate turbine number, no motor or generator number, and no efficiency at any depth
other than the rated one.

Supporting rows, same table:

> Charge capacity        31.1 MWh
> Discharge capacity     22.4 MWh
> Power                  5 MW
> Discharge time         4.5 h
> Installation depth     750 m

**Arithmetic check (reader's computation).** `22.4 / 31.1 = 0.7203`, which rounds to 0.72. That is
the ratio of energy out at the terminals to energy in at the terminals, which is the definition of
round trip. `22.4 / 5 = 4.48 h` against the stated 4.5 h. Both checks pass.

## 2. What this does to 0.70

The paper's figure is **0.72 round trip**, not 0.70 and not any one-way value. Its basis is its own
Table 1, attributed to a feasibility study (journal pp. 67-68): "The dimensions of the full-scale
system are given in Table 1. They are the result of a feasibility study carried out by HOCHTIEF
Solutions AG before the start of the first research project..." No derivation from component test
data is shown. 0.72 is a design figure.

`docs/DATA_SOURCES.md:287-288` already records 0.70 as the bottom of Fraunhofer's stated 70 to 80
percent band. The paper puts the full-scale design at 0.72, inside that band. **Mitchell's 0.70 is
conservative and is not contradicted.** It sits two points below the published design figure.

The `~0.49` one-way branch must come out of `docs/HANDOFF.md`, `docs/DATA_SOURCES.md:244-245`,
`docs/FACT_CHECK_REPORT.md:148-149`, and the docstrings of
`owr.storage_physics.one_way_from_round_trip` and `round_trip_from_one_way`.

## 3. Pump against turbine

**The paper does not separate them.** It prints the symbols `η_pump` and `η_turbine` in the Table 1
row label and gives only their product.

The table over-determines the split, so it is recoverable in principle. At `ρ = 1025 kg/m³`,
`g = 9.81 m/s²`, `V = 12,249 m³`, `h = 750 m`, gross hydrostatic energy is 25.660 MWh, giving
`η_turbine = 0.873` and `η_pump = 0.825`, product 0.7203. **The reader recommends against adopting
that split, and labels it inference.** Three reasons: the paper states an installation depth, not a
hydraulic head, and the effective head at the valve is lower because the technical unit sits inside
the sphere (Figure 1, p. 67); the paper states no seawater density; and a 3 percent change in
either input moves the split by several percent while leaving the product at 0.72.

**Use the symmetric split instead:** `sqrt(0.72) = 0.8485` each way. It is the convention
`docs/HANDOFF.md` already names, it matches the form of `soc_engine.py:21`, and it reproduces the
product exactly. Record it as a modeling convention, not as a paper figure.

## 4. Head against efficiency — partially addressed, not settled

The paper gives no efficiency at any head other than 750 m, so it cannot serve as evidence for
head-independence in either direction. What it says, journal p. 68:

> An installation in a lower water depth would be possible without a constructive change of the
> concrete sphere, but due to the lower pressure difference between the interior of the sphere and
> the surrounding water, the pump turbine would have to be adjusted and the energy storage
> capacity would decrease.

Three parts, pulling two ways.

- **Supports the team.** The concrete sphere needs no change at a lower depth. The geometry half of
  the shallow-variant argument is now sourced.
- **Cuts against the team.** The pump turbine "would have to be adjusted". The claim at
  `docs/HANDOFF.md:250-251`, that efficiency "is set by the pump-turbine and motor-generator, not
  by the head", assumes the same machine at both heads. The paper says the machine changes, and
  does not say what efficiency the changed machine reaches.
- **Supports the team.** The named consequence of a lower head is that "the energy storage capacity
  would decrease". The paper names capacity, not efficiency, as what the head governs. That is the
  linear energy scaling in `docs/DATA_SOURCES.md:192`.

The same holds in the other direction (journal p. 69): "The entire area in the Morro Bay WEA is at
least 900 m deep, which would require an altered technical unit." The technical unit is
head-specific both ways.

**Verdict for `docs/FACT_CHECK_REPORT.md:111-116`.** The existing verdict, "Overstated. The physics
argument is plausible; it is not evidence", survives and gets stronger. Keep it, and add the p. 68
quote as its source.

**A finding that lowers the stakes on the whole question.** Energy and power both scale linearly
with head, so **duration is head-invariant**. At 200 m the paper's sphere gives
`22.4 x 200/750 = 5.97 MWh` and `5 x 200/750 = 1.333 MW`, a duration of 4.48 h, equal to the
full-scale 4.48 h. The 12 h against 3 h duration argument at `docs/HANDOFF.md:325-328` has a third
answer neither side proposed: **about 4.5 h at any head**, because the geometry sets the duration
and the head cancels.

## 5. Geometry, energy, power, depth

Table 1, journal p. 67, verbatim:

> Outer diameter                34.32 m
> Inner diameter                28.6 m
> Inner volume                  12,249 m³
> Wall thickness                2.86 m
> Concrete quantity             9,260 m³
> Concrete density              2,500 kg/m³
> Weight of the concrete sphere 23,150 t
> Installation depth            750 m
> Charge capacity               31.1 MWh
> Discharge capacity            22.4 MWh
> Power                         5 MW
> Discharge time                4.5 h

Siting band, journal p. 68: "• Water depth: 600 m-800 m". Rated depth, pp. 67-68: "This water depth
threshold is approximately 750 m, which is, therefore, chosen as the rated installation depth.
However, it is possible to install the sphere in lower or higher water depths."

### `src/owr/storage_physics.py` agrees, to the digit

| Check | Function | Result | Table 1 |
|---|---|---|---|
| Inner diameter | `sphere_internal_diameter_m(34.32, 2.86)` | 28.6 | 28.6 m |
| Inner volume | `sphere_internal_volume_m3(34.32, 2.86)` | 12,248.89 m³ | 12,249 m³ |

The module's `pi/6 · D_inner³` convention is the paper's convention.

Two rows do not close, both in the concrete and not in the energy path. The shell computes to
8,917 m³ against a stated 9,260 m³, a 3.7 percent gap. The stated concrete figures are
self-consistent (`9,260 x 2,500 kg/m³ = 23,150 t` exactly). The extra 343 m³ is most likely the
technical unit shaft and base seen in Figure 1.

### The three numbers that could not hold at once

`docs/HANDOFF.md:305-330` records six of Mitchell's figures, three of which conflict. The paper
changes four of the six inputs.

| Mitchell | Paper | Effect |
|---|---|---|
| Outer diameter 30 m | 34.32 m outer, 28.6 m inner | "30 m" is the nominal or inner figure. Confirms `DATA_SOURCES.md:258-259`. |
| Energy 20 MWh | 22.4 MWh discharge, 31.1 MWh charge | Two capacities, not one. See below. |
| Head 200 m against a 600 m reference | Rated depth 750 m | The `x 200/600` scaling uses the wrong reference. |
| Efficiency 0.70, side unstated | 0.72, round trip, stated | Ambiguity resolved. |
| Power 1.67 MW | 5 MW at 750 m, so 1.333 MW at 200 m | Power falls 20 percent. |
| Flow ~1.02 m³/s | Not stated | Implied value 0.76 m³/s. |

**The energy inconsistency dissolves, for a reason nobody had.** The paper carries **two** capacity
numbers for one sphere: 31.1 MWh charge and 22.4 MWh discharge. Every capacity figure in this
repository is a single number. The project must choose which side of the meter its "energy
capacity" sits on, and say so wherever it prints one.

**The paper's own park figures use the charge capacity** (reader's computation). Journal p. 70:
"the standard size of a StEnSea system park considers 80 spheres, which sum up to a power of 400 MW
and a capacity of 2.5 GWh." `80 x 5 MW = 400 MW` matches. `80 x 31.1 MWh = 2.488 GWh` rounds to
2.5 GWh; `80 x 22.4 MWh = 1.792 GWh` does not. The regional figure behaves the same way (pp.
69-70): "Assuming the installation of 400 spheres in an area of one km², the total capacity would
be about 1.5 TWh" — `120 km² x 400 x 31.1 MWh = 1.493 TWh`, against 1.075 TWh at 22.4 MWh.

**So the paper's headline capacity claims are charge-side.** `StorageAsset.total_mwh` is
discharge-side by every other convention in `src/owr/metrics.py`, so 22.4 MWh is the right value
there, and 2.5 GWh per 80 spheres is not comparable to it.

**Power scaling changes.** Mitchell's 1.67 MW comes from `5 MW x 200/600`. At the paper's rated
750 m the same method gives `5 MW x 200/750 = 1.333 MW`. The 600 m figure is the bottom of the
siting band, not the rated depth.

**Flow.** The paper states none. `Q = V / t = 12,249 / (4.48 x 3600) = 0.76 m³/s`, and the same
value follows from `P = rho·g·Q·h·eta_turbine` at 5 MW, 750 m and the implied 0.873. Mitchell's
1.02 m³/s does not appear in this paper and does not follow from it. Flow and duration are both
head-invariant, so 0.76 m³/s applies at 200 m too.

**Shallow-variant energy rises.** `docs/DATA_SOURCES.md:278` records 4.79 MWh at 200 m, computed at
`eta = 0.70` treated as one-way generating. The paper's own scaling gives
`22.4 x 200/750 = 5.97 MWh`, a 25 percent increase. Sphere count for a 40 to 60 GWh reserve falls
from about 8,400-12,500 to about **6,700-10,000**. Both counts still rest on Report A's 40 to
60 GWh target, whose derivation `docs/FACT_CHECK_REPORT.md:133-137` already flags as loose.

## 6. Other claims this paper moves

**The Ernst 2024 slide figures are now corroborated by an independent 2023 publication.**
`docs/DATA_SOURCES.md:247-268` rests entirely on one slide deck for the sphere geometry.

| Field | Ernst 2024 slides | Dick 2023, Table 1 |
|---|---|---|
| Inner diameter | 28.60 m | 28.6 m |
| Working volume | 12,000 m³ | 12,249 m³ |
| Wall thickness | 2.7 m | 2.86 m |
| Discharge capacity | 21 MWh | 22.4 MWh |
| Power | 5 MW | 5 MW |
| Discharge time | 4.2 h | 4.5 h |
| Efficiency | 70 to 80 percent | 0.72 |
| Depth | 70 bar / 700 m | 750 m |

The two sources differ by a few percent throughout and never contradict. The 2.7 m against 2.86 m
agreement kills the 0.5 to 1.0 m wall band for good, which `docs/DATA_SOURCES.md:272-274` and
`tests/test_storage_physics.py` still carry.

**Full-scale power is 5 MW here, flat.** `docs/FACT_CHECK_REPORT.md:108-110` corrects the
repository to "5 to 7 MW" from the Fraunhofer topic page. Two Fraunhofer-authored sources now
disagree on the range. Record the disagreement; do not silently pick a side.

**Demonstration status.** Journal p. 68: "During the first research project in 2016, a 1:10 scaled
prototype was built and successfully tested in Lake Constance... Additional simulations and
analysis regarding the full-scale system moved the StEnSea system from Technology Readiness Level
(TRL) 2 to 5." And p. 69: "The planned work would move the technology to TRL 6, preparing the
realization of commercial full-scale systems."

**TRL 5 as of 2023. No full-scale sphere exists.** The 22.4 MWh and the 0.72 are design values from
a feasibility study, not measured values from a built machine. Use that wording on any slide.

**The offshore wind pairing is the developer's own stated use case,** not a project invention.
Journal p. 70: "Floating offshore wind farms, like other renewable technologies, are also weather
dependent and there is a chance that there is no demand for electricity during particularly strong
winds. The generated wind energy would then have to be curtailed or stored."

**Note the mismatch with this project's thesis.** Fraunhofer's stated driver is wind curtailment.
Report A found zero hours of negative net load on ISO-NE, and `docs/HANDOFF.md:266-291` has already
moved the project to an opportunity-cost charging model. The paper's motivating case does not hold
in New England, while the machine still does. Say that before anyone cites the paper as support for
the New England thesis.

**An internal inconsistency in the paper.** Table 2, p. 68, gives a worldwide potential of 817 TWh
over 111,659 km², and 75 TWh over 10,226 km² for the United States, which is 7,317 MWh per km². At
the paper's own density of 400 spheres per km² and 31.1 MWh per sphere, one km² holds 12,440 MWh.
The Table 2 rows imply about **235 spheres per km²**, not 400. The paper explains neither. Do not
mix figures across the two.

## What the paper does not answer

Gaps. Do not fill them from other sources.

1. **No hydraulic head.** Only an installation depth of 750 m.
2. **No seawater density.** The 1025 kg/m³ at `storage_physics.py:18` remains an assumption.
3. **No separate pump or turbine efficiency.** Only the product.
4. **No efficiency at any other head.** Nothing for 200 m, nothing for the band ends.
5. **No flow rate and no charge time.**
6. **No wall thickness or pressure rating for a shallow sphere.** The blocker at
   `docs/DATA_SOURCES.md:293-296` stands untouched.
7. **No cost figure, no cycle life, no cycles per year.** Open decision 5 gets nothing.
8. **No New England or Gulf of Maine content.** California only.

## What changes if this paper is adopted

### Config constants

- **`src/owr/config.py:89`, `default_efficiency: float = 1.0`.** Set it to **0.8485**, which is
  `sqrt(0.72)`. **Do not set 0.72.** `soc_engine.py:21` applies the value once on each leg, so the
  realized round trip is `efficiency²`. At 0.8485 that is 0.72. At 0.72 it would be 0.5184.
- **`src/owr/config.py:36-44`, the `default_efficiency` docstring.** Its first line reads
  "Round-trip efficiency in `soc(t+1)=soc(t)+charge*eff-discharge/eff`". **That is wrong as
  written, and it is the naming error that produced the ambiguity.** The field is the **one-way**
  factor. Rewrite it to name the one-way reading, give the round trip as the square, and cite
  Table 1. Remove "Undecided." Correct the "StEnSea 0.80" figure to 0.72 round trip, or restate it
  as the 70 to 80 percent band.
- **`src/owr/models.py:26-27`, the `StorageAsset.efficiency` docstring,** carries the same wrong
  wording. Fix both together or they drift.

### Documentation

- **`docs/HANDOFF.md`.** Close open decision 1: 0.72 round trip, config value `sqrt(0.72)`, source
  Table 1. Correct the power-scaling reference at line 335 from 600 m to 750 m. In the "Sphere
  spec" block, record the paper's figures and the head-invariant ~4.5 h duration. Correct the
  shallow-variant energy from ~5 MWh to 5.97 MWh and the power from 1.67 MW to 1.333 MW. Correct
  the sphere count from 8,000-12,000 to 6,700-10,000. At line 250, add that the paper requires an
  adjusted pump turbine at a lower head, so head-independence stays unproven.
- **`docs/DATA_SOURCES.md`.** Add the paper as a numbered source with its Table 1. Correct lines
  244-245, which still present the round-trip against one-way question as open. Add the charge
  against discharge capacity distinction, which no section carries. Correct line 278.
- **`docs/FACT_CHECK_REPORT.md`.** Move the Unverifiable item at lines 148-149, "Whether 0.70 is
  the round-trip or one-way figure", to **Verified**, with the Table 1 quote. Keep the item at
  lines 145-147 where it is. Add the TRL 5 status and the 5 MW against 5-7 MW disagreement.

### Code and tests

- **`src/owr/storage_physics.py:180-205`.** The `one_way_from_round_trip` and
  `round_trip_from_one_way` docstrings both say "The team has not decided". That is now false. Keep
  both functions; replace the wording and cite the paper.
- **`tests/test_storage_physics.py`.** The 0.5 to 1.0 m wall band was already known wrong. The
  701-779 m recovery band and the 4.49-5.00 MWh shallow band both descend from it. Repin against
  the paper's exact geometry, where `sphere_internal_volume_m3(34.32, 2.86)` returns 12,248.89 m³
  against a published 12,249 m³. That is a stronger test than a band.

### Claims moving to Verified

1. Full-scale round-trip efficiency 0.72, a full-cycle figure defined as `eta_pump · eta_turbine`.
2. Geometry: 34.32 m outer, 28.6 m inner, 2.86 m wall, 12,249 m³ working volume.
3. Discharge capacity 22.4 MWh, charge capacity 31.1 MWh, 5 MW, 4.5 h.
4. Rated installation depth 750 m, inside a 600-800 m siting band.
5. TRL 5, reached on a 1:10 prototype in Lake Constance in 2016.
6. Energy capacity falls with a lower head, and the pump turbine must be adjusted for it.

### Claims staying Unverifiable

1. The 200 m shallow variant's efficiency.
2. The 200 m shallow variant's wall thickness and pressure rating.
3. Any separate pump or turbine efficiency.
