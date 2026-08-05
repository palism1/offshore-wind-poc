# Technical Brief

# Future Grid-Stress Scenario Explorer with Auditable AI Support

## Last Updated:

## Jul 27, 2026

# Technical Brief

We are building a decision-support simulator that helps a decision-maker evaluate whether long-duration energy storage off the New England coast could become a practical investment for improving winter grid reliability.

Our decision-maker is a manager responsible for evaluating emerging technologies and preparing technical recommendations that inform the company's long-term planning decisions. Our manager must decide whether or not to make a recommendation for the next New England grid planning cycle, answering: how can we keep enough electricity available for days into a severe winter event? Or to put it another way, how can we ensure sufficient dispatchable energy remains available throughout a prolonged winter event?

That’s a complex problem to solve; serving winter conditions with extended periods of high demand and constrained energy supplies makes electricity more difficult and expensive to deliver reliably. Many technologies have been proposed to improve winter reliability. Our project investigates one promising long-duration storage concept.

Evaluating one solution can require investigating many combinations of storage size, operating policies, and winter event conditions. Rather than commissioning dozens of separate analyses, our simulator allows planners to compare those scenarios interactively. It saves time.

My team has already been researching and reviewing how to close this gap. For every year between 2022 and 2026, winter has consistently exhibited higher wind generation than summer. At the same time, New England has historically experienced its greatest fuel security challenges during prolonged winter cold snaps. Following the operational difficulties of the 2017–2018 winter, ISO New England introduced the 21-Day Energy Assessment to provide earlier warning of potential energy shortfalls and fuel supply risks.

Our research and analysis between 2022 and 2026 showed that winter wind generation frequently provides opportunities to charge long-duration storage before severe winter stress events. This led us to a solution combining existing wind infrastructure and energy storage. 

Our team chose seafloor energy storage units because they represent one promising long-duration storage concept currently under development. Our team selected this type of storage as the technology for this case study because it is specifically designed for long-duration energy storage and can be located. Comparing multiple storage technologies is outside the scope of this project.

This overlap led us to investigate whether storing a portion of winter wind generation for the most severe events could reduce reliance on scarce dispatchable resources. The storage system our team chose to investigate sends energy to the grid when water spins a turbine as it enters a large hollow sphere on the seafloor. To reset the system so it is fully charged, water is pumped out of the sphere with an electric pump.

Our simulator helps explore whether our solution appears promising enough to justify additional engineering investigation. The simulator helps our manager understand how changing system size, operating assumptions, and event characteristics affects the conditions under which the technology becomes a practical investment candidate within our managers budget. The key metrics by category we track to instill confidence in our manager are… 

* Reliability: Capacity Margin Improvement  
* Energy Adequacy: Stress Window Effectiveness  
* Fuel Security: Oil \+ Gas Generation Offset  
* Operational: Storage Utilization  
* Economics: Estimated Capital Costs  
* Decision Confidence: Scenario Robustness Score

# Definitions and Key Concepts

# Definitions and Key Concepts

**Net load:** the amount of total demand for electricity on a grid, not covered by variable

**Gross load:** total demand for electricity on the grid

**Curtailment:** an action taken to restrict energy entering the grid from suppliers when generative potential is higher than demand and / or operational constraints would cause greater grid disruption (i.e., minimal operating ranges for thermal plants)

**Interconnection queue / cluster study:** the regulatory process by which new generation and storage projects gain approval to connect to the grid 

**Summer:** between June 1st and September 30th

**Winter:** between December 1st and February 28th

**Demand response:** the flexibility of the grid to allocate electricity to different markets based on demand

**Resource adequacy:** the ability to meet the total demands of the electrical grid with a diversity of sources

**(Rated) Power Output:** maximum rate an electrical storage device can supply to the grid at any given time

**Storage duration:** from maximum capacity the amount of time it takes to return to empty

**Timescale (grid operations):** the duration of time relative to typically electric grid cycles of demand

**Energy arbitrage:** Buy, store, or consume electricity when prices are low and sell or use it when prices are high

**Load shift:** store electricity when demand is low and distribute when demand is high

**Duck Curve:** graph of electricity demand that moves the historical peak demand based on energy supplied by variable renewable energy sources

**Provenance:** an auditable trail of sources or evidence to review steps in a process

**Strategic reserve dispatch:** charging during wind surplus / low-price periods, holding charge for declared reliability events rather than daily peak-shaving (per the team's revised framing).

**Location archetype:** one of the project's four categories of storage siting.

**Total (Energy) Capacity:** the maximum amount of energy that a storage device can safely be charged

**Transmission Capacity:** the maximum amount of power a transmission line can move instantaneously

**Available Charge:** the remaining charge after the protected reserve is dropped from the state of charge

**LNG:** liquid natural gas

**Aggregate Power Output:** the amount of power that a system can send to the grid based on specifications at the unit-level, where the number of units is more than one

**State of Charge:** the amount of energy remaining in system storage

**Stress Window:** a group of consecutive days where the peak daily total load sits above the 90th percentile

**Minimum Window:** the fewest number of days that define a window where peak daily total load sits above the 90th percentile

**Charge Rate:** the power a storage system can store in any given instance

**Wind Generation Scale:** a scalar integer that adjusts the size of wind energy created across every hour; and equivalent measurement to adding more wind turbines

# Regulatory Policies

# Regulatory Policies. 

**1\. FERC Order No. 2023 / 2023-A (Interconnection Queue Reform)** Mandates that interconnection customers can connect to the transmission system in a reliable, efficient, transparent, timely, and fair manner, building on standardized procedures from Order Nos. 2003, 2006, and 845\.  
**2\. ISO-NE's Cluster Study Implementation.** ISO-NE's first cluster study under the new framework includes 26 interconnection requests: 21 battery storage, two solar, and three wind projects, with most located in Massachusetts (two each in Connecticut, Maine, Vermont; one in New Hampshire; none in Rhode Island), and is scheduled for completion by August 6, 2026\.  
**5\. ISO-NE's Order 2023 Storage-Specific Compliance Path** ISO-NE is pursuing an alternative compliance pathway specifically for storage resource interconnection, attempting to avoid a "control technology" requirement.

# Assumptions

# Assumptions for the New England

* Validating  
  * The risks of load-forecasting uncertainty can be mitigated by redistributing wind energy.  
  * Timing of the peak generation for offshore wind may not align with the highest demand for the day.  
* Supporting Data  
  * There are multi-day events that strain the grid system, and they appear to be concentrated and recurring.  
  * The peak of wind generation occurs in the winter.  
  * Electric price spikes are driven by gas constraints and load  
* Determinants  
  * This project will not meet all the needs of the evolving methods to meet resource adequacy  
  * Total capacity is co-located with offshore wind.   
  * Temperature change does not affect total capacity, power output, or charge rate.  
  * Redundancies in the system are preferred by grid planners.

# Variables & Inputs

# Variables of Interest

* Independent  
  * Power (MW)  
    * Total Load  
    * Net Load  
    * Transmission Capacity  
  * Energy (MWh)  
    * Wind Energy  
    * Total Capacity  
    * Available Charge  
    * Import Prices ($/MWh)  
    * Price of LNG ($/MMBtu or converted to $/MWh)  
  * Other  
    * Calendar Date Range (timestamps)  
    * Minimum Window (days)  
    * Peak Hour Triplet (timestamp / index)  
* Dependent  
  * Power (MW)  
    * Aggregate Power Output  
  * Energy (MWh)  
    * Starting Capacity  
    * Capacity Margin Improvement  
    * Peak Total Dispatch  
    * Curtailment  
    * Capacity Utilization  
    * Daily Energy Budget (MWh/day)  
  * Other  
    * State of Charge (ratio or %)  
    * Stress Window Effectiveness (ratio or %)  
    * LNG Cost ($)  
    * Import Cost ($)  
* Constants  
  * Power  
    * Unit Power Output (MW)  
    * Unit Charge Rate (MW)  
  * Energy (MWh)  
    * Protected Reserve (MWh)  
    * Protected Reserve Floor (MWh)  
  * Wind Generation Scale (Dimensionless)

# Required Inputs

* Wind Generation Scale  
* Total Capacity  
* Reserve Power Output  
* Minimum Window  
* Transmission Capacity

* ~~Grid Inflexibility (future option)~~  
* ~~Natural gas inventory (future option)~~

# Constraints & Rules

# Constraints

* Minimum Window ≥ 2  
* Protected Reserve \= 30% Total Capacity  
* Protected Reserve Floor \= 20% Total Capacity  
* 20% ≤ State of Charge ≤ 100%  
* 0 ≤ Available Charge ≤ 70% Total Capacity  
* All variables with $ units ≥ 0.01 OR \= 0.00

# System Rules

* Reliability of grids comes first. Economics comes second. Efficiency comes third.

# Metrics

# Metrics

* V1.0

Capacity Margin Improvement=t=0N(net\_load\_dispatch(t)-net\_load\_observed(t)) / t=0N(net\_load\_observed(t)) • 100  
CMI Score: (0, ≤0MW; 50, \=75; 100, ≥150)

Stress Window Effectiveness \=t=0N(capacity\_dispatched(t)) / t=0N(oil\_generation\_actual(t)  
\+gas\_generation\_actual(t)+wind\_generation\_actual(t))

SWE Score: \[0, 0%; 100, 100%\]

Fuel–Fired Generation Offset \=t=0N(oil\_generation(t))+t=0N(gas\_generation(t) )- (t=0N(wind\_generation(t) \+t=0Ncapacity\_dispatched(t))  
Fuel Offset Percentage \=fuelfired\_generation\_offset/t=0Ntotal\_generation(t)  
FFGO Score: \[0, 0%; 100, 100%\]

Cycle Recharge Mismatch \=t=tstarttend(recharge\_opporunity(t) \- actual\_recharged(t))  
Average Recharge Mismatch \= 1Nc=1Ncycle\_recharge\_mismatch(t)  
Recharge Capacity Mismatch= average\_cycle\_recharge\_utilization / maximum\_available\_capacity  
RCM Score:

| RCM % | 0 | ±0.5 | ±1.0 | ±1.5 | ±2.0 | ±2.5 | ±3.0 | ±3.5 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Score | 100 | 98 | 95 | 92 | 90 | 87 | 84 | 81 |

| RCM % | ±4.0 | ±4.5 | ±5.0 | ±6.0 | ±7.0 | ±8.0 | ±9.0 | ±10.0 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Score | 78 | 76 | 75 | 68 | 60 | 50 | 42 | 35 |

| RCM % | ±12.5 | ±15.0 | \>±20 |  |  |  |  |  |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Score | 20 | 10 | 0 |  |  |  |  |  |

Estimated Capital Costs \= est\_transmission\_cost\_per\_mile • miles \+ est\_storage\_unit\_cost • total\_unit\_count

Cost per Equivalent Full Cycle \= est\_capital\_costs / ((annual\_equivalent\_full\_cycle) • (solution\_lifetime))

* Scenario Robustness Score  
  * (Thresholds)  
    * Capacity Margin Improvement:   
    * Stress Window Effectiveness:  
    * Fuel-Fired Generation Offset:  
    * Recharge Capacity Mismatch:  
* V1.1  
  * LNG Cost  
  * Import Costs

# Success Criteria

# Success Criteria

* TBD