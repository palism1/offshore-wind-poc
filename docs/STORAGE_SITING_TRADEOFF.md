# Storage Siting Trade-off — Efficiency vs. Transmission Distance

Date: 2026-07-28 · Status: screening calculation, not an engineering study

## The question

Mitchell's 2026-07-27 post argues that StEnSea's 0.80 round-trip efficiency survives the
longer transmission run: "even with longer transmission lines you'd need hundreds of miles
of wiring to drop below the top end of a Liquid Air Energy Storage system."

This checks that claim and answers the follow-on: at what transmission distance does a
far-sited, high-efficiency asset stop beating a near-sited, low-efficiency one?

## Two architectures

| | A — StEnSea, deep water | B — LAES + thermal, onshore near load |
|---|---|---|
| Storage round-trip | 0.80 (Fraunhofer published) | 0.50–0.70 |
| Path | wind → storage (co-located offshore) → mainland | wind → mainland → storage (at load) |
| Transmission on the stored path | 155–215 mi = **249–346 km** | 35–42 mi = **56–68 km** |
| Technology required | HVDC (HVAC impractical beyond ~80–100 km) | HVAC viable |

## Loss model

η_T(D) = (1 − 0.0125)² × (1 − 0.003 · D/100)

Two VSC converter stations at ~1.25% each, cable at ~0.3% per 100 km. These are
mid-range published figures; NordLink at 600 km runs 4–5% end to end, which this model
reproduces.

## Result — delivered energy per MWh of wind routed through storage

| Architecture | Transmission η | Storage η | **Delivered** |
|---|---|---|---|
| A — StEnSea @ 249 km | 0.968 | 0.80 | **77.4%** |
| A — StEnSea @ 346 km | 0.965 | 0.80 | **77.2%** |
| B — LAES @ 68 km, best case | 0.973 | 0.70 | **68.2%** |
| B — LAES @ 68 km, worst case | 0.973 | 0.50 | **48.7%** |

**Mitchell's claim is correct, and by a much larger margin than stated.** The extra
190–280 km of subsea run costs about **3 percentage points**. LAES gives up 10 to 30.

## Crossover distance

Setting A equal to B's best case (0.70 LAES at 68 km) and solving for D:

> 0.80 × 0.9752 × (1 − 0.00003 D) = 0.70 × 0.9736
> **D ≈ 4,200 km** (~2,600 miles)

Against a hypothetical 0.75 LAES the crossover is still ~2,100 km. Against the 0.50 case
there is no crossover at any buildable distance.

**Transmission distance never decides this on efficiency.** New England is not big enough
for the loss term to matter.

## So the pivot has to be argued on capital cost, and there it looks different

Path A needs 190–280 km more subsea cable than Path B, and it forces HVDC where Path B
could use HVAC.

| Item | Delta, A over B |
|---|---|
| Extra cable, 190–280 km @ €2–5M/km | €0.4–1.4B |
| Two HVDC converter stations Path B avoids @ €300–600M each | €0.6–1.2B |
| **Total** | **≈ €1.0–2.6B** |

Now value the efficiency advantage. StEnSea's edge over best-case LAES is ~9 points on
throughput. For a 12,600 MWh NEMA event, Path A consumes ~16,300 MWh of wind against Path
B's ~18,500 — about **2,200 MWh less wind per full cycle**.

| Duty cycle | Extra wind consumed by LAES per year | Value @ $50/MWh | 25-year undiscounted |
|---|---|---|---|
| Strategic winter reserve, ~10 cycles/yr | ~22,000 MWh | ~$1.1M/yr | ~$28M |
| General arbitrage asset, ~200 cycles/yr | ~439,000 MWh | ~$22M/yr | ~$550M |

**At the duty cycle this project actually models — a strategic reserve held for multi-day
winter events — the efficiency advantage is worth roughly 1–3% of the transmission capital
penalty.** The efficiency argument does not pay for deep-water siting.

At 200 cycles a year it becomes a real argument, within the same order of magnitude as the
capex delta. That is a different product from the one in our executive summary, and it is
close to Keith Trnka's market-misalignment question: a storage asset that earns in
short-term markets cycles often, and a strategic winter reserve does not.

## What this means for the pivot

1. **Drop the efficiency argument for deep-water siting.** It is true and it is not worth
   enough to matter. Anyone who checks will find the loss term is ~3%.
2. **The pivot toward closer siting is justified on capital cost.** €1.0–2.6B of avoided
   cable and converter stations dwarfs the energy value at reserve duty cycles.
3. **Cycle count is the hidden variable.** The trade-off inverts somewhere between 10 and
   200 cycles per year. Nothing in the current scope pins it down, and both the siting
   decision and the capex metric depend on it. This should become an explicit scenario
   input.
4. **This strengthens rather than weakens the case for a simulator.** The answer moves with
   duty cycle, event frequency and energy price, and none of those can be eyeballed.

## Assumptions and limits

- Screening-level. Cable sizing, seabed conditions, converter topology, and installation
  logistics are not modeled.
- Costs are European-market figures; US offshore construction typically runs higher, which
  widens the capex gap and strengthens the conclusion.
- LAES round-trip range 0.50–0.70 is taken from Mitchell's post and has not been checked
  against a primary source. That check is worth doing before this drives a decision.
- The seafloor-area constraint on 1,300–2,200 units is independent of everything here and
  may bind first.

## Sources

- StEnSea full-scale unit spec (20 MWh, 30 m, 600–800 m, η 0.80): https://www.iee.fraunhofer.de/en/topics/stensea.html
- HVDC submarine losses and converter station losses: https://publications.jrc.ec.europa.eu/repository/bitstream/JRC97720/ld-na-27527-en-n.pdf
- HVDC cable and converter capital costs: https://neomarketdata.com/costs-of-hvdc-submarine-cables
- Event pricing ($443/MWh, Event 17, Jan 25–31 2026): `docs/archive/reviews/FINDINGS_REVIEW_2026-07-24.md`
