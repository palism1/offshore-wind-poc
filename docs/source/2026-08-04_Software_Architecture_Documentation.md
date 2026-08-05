
# ✅ 1-Scenario Config

Software Component 1 — Scenario Configuration

Purpose

Collect, validate, and store all user-defined scenario parameters before simulation begins.

User Inputs


| Field | Default | Unit | Description |
|---|---|---|---|
| wind_generation_multiplier | 1.0 | Scalar | Whole-number scalar used to increase or decrease historical wind generation. |
| transmission_capacity | 200.0 | MW | Maximum transmission power capacity |
| total_energy_capcity | 60,000.0 | MWh | Maximum energy capacity for storage |
| reserve_power_output | 4320.0 | MW | Maximum storage power output |
| minimum_event_window | 2 | Days | Minimum stress event duration |

Derived Fields

- total_storage_units
Validation Rules

- All inputs shall be validated before simulation begins.
- Invalid inputs shall terminate execution before data loading.
- Validation ranges:
- wind_generation_multiplier = @
- transmission_capacity = @
- total_capacity = @
- reserve_power_output = @
- minimum_window ≥ @
Data Contract


| Field | Required | Unit | Description |
|---|---|---|---|
| wind_generation_multiplier | Y | Scalar | Historical wind multiplier |
| transmission_capacity | Y | MW | Maximum transmission power capacity |
| total_energy_capcity | Y | MWh | Maximum energy capacity for storage |
| total_storage_units | Y | Storage Units |  |
| reserve_power_output | Y | MW | Maximum storage power output |
| minimum_event_window | Y | Days | Minimum stress event duration |


# ✅ 2-Data Pipeline

Software Component 2 — Data Pipeline

Purpose

Extract, transform, validate, and prepare historical data for simulation.

Data FieldsProcessing Steps

For each historical winter:

- Winter 2021/2022
- Winter 2022/2023
- Winter 2023/2024
- Winter 2024/2025
- Winter 2025/2026
perform the following sequence independently.

Extract Data

Load:

- hourly electrical load
- hourly wind generation observed
- hourly oil generation
- hourly gas generation
- transmission information
Transform DataApply:historical_wind_generation

× wind_generation_multiplier

= scaled_wind_generation

Validate Data

Verify:

- no missing timestamps
- no duplicate timestamps
- chronological ordering
- valid numerical ranges
- @additional validation rules
Data Contract


| Field | Unit | Description |
|---|---|---|
| date | date | Calendar date |
| hour | hour | Hours in a day |
| load_mw | MW | Hourly system load |
| observed_wind_mwh | MWh | Hourly actual observed wind generation |
| scaled_wind_mwh | MWh | Hourly scaled wind generation |
| oil_mwh | MWh | Hourly oil generation |
| gas_mwh | MWh | Hourly liquid natural gas generation |
| load_percentile | % | Pre-processed 5-winters percentile of daily load |

Optional Fields

- @
Validation Rules

- continuous timestamps
- chronological ordering
- no duplicate timestamps
- no null required values
- valid numerical ranges
- @

# ✅ 3-Stress Event Detection

Software Component 3 — Stress Event Detection

Purpose

Identify supply adequacy stress events requiring storage simulation.

Event Detection Rule

A stress event begins when percentile of daily load is ≥90

Store:

- event identifier
- starting date
- ending date
- duration
Data Contract


| Field | Unit | Description |
|---|---|---|
| event_id | n/a | hash value identifier for events |
| winter_id | n/a | hash value identifier for winter |
| event_start_date | date | starting calendar date for an event |
|  |  |  |
|  |  |  |
| event_duration | day | total span of time in day across an event |
|  |  |  |
|  |  |  |

Derived Fields

- event_end_date
- event hour count
- event day count
- @
Validation Rules

- duration ≥ minimum_window
- start precedes end
- event entirely contained within historical winter
- no overlapping event identifiers
- @

# ✅ 4-Simulation Initialization

Software Component 4 — Simulation Initialization

Purpose

Initialize the storage system before each stress event simulation.

Initial Event

Beginning State of Charge

SOC = 0 MWh

Charging Window

Maximum available charging period:

5 days

representing:

7-day forecast

− minimum_window

Subsequent Events

Beginning State of Charge

SOC

= remaining storage from previous event

Initialize:

- storage state
- dispatch history
- recharge history
Data Contract


| Field | Unit | Description |
|---|---|---|
| winter_id | n/a | hash value identifier for winter |
| event_id | n/a | hash value identifier for events |
| current_date | date | today’s calendar date |
| current_hour_index | index | an index referencing the most recent hour in the Eastern Time zone |
| available_charge | MWh | @ |
| remaing_capacity | MWh | @ |
| reserve_power_output | MW | @ |
| charging_window_remaining | hour | @ |
| dispatch_history | n/a | software container storing each hourly energy dispatch in MWh |
| recharge_history | n/a | software container storing each hourly recharge in MWh |

Validation Rules

- SOC ≥ minimum reserve
- SOC ≤ total_capacity
- remaining_capacity ≥ 0
- @

# ✅ 5-Storage Dispatch Engine

Software Component 5 — Storage Dispatch Engine

Purpose

Determine hourly storage operation during each stress event.

Begin Rolling Forecast Simulation

For each hour between:

event_start

and

event_end

…perform:

Evaluate Current System State

Determine:

- available storage energy
- remaining energy capacity
- maximum power output
- available transmission capacity
- @additional operating constraints
- Build Discharge Schedule
Construct an hourly discharge schedule using:

- available storage
- reserve limits
- transmission limits
- @dispatch priorities
NetLoad(t)=Load(t)−Solar(t)−Wind(t)

PeakWeight(t) = NetLoad(t) / ∑NetLoadpeak

Dischargepeak(t) = Epeak × PeakWeight(t)

Ramp(t) = |NetLoad(t)−NetLoad(t−1)|

SmoothWeight(t) = Ramp(t) / ∑Rampwindow

Dischargesmooth(t) = Esmooth × SmoothWeight(t)

TotalDischarge(t) = Dischargepeak(t) OR Dischargesmooth(t)

Estimate Future Recharge Opportunities

Estimate available recharge throughout the remaining forecast horizon.

Predict Storage Trajectory

Forecast:

future SOC

throughout the remaining event.

Determine Current Dispatch

Calculate:

charge_dispatched(t)

subject to:

- storage energy capacity
- reserve power output
- transmission limits
- minimum reserve
- @charging constraints
- @round-trip efficiency
- @dispatch objective
- @additional operating rules
Data Contract


| Field | Unit | Description |
|---|---|---|
| date | date | Calendar date |
| discharge_power | MW | @ |
| charge_power | MW | @ |
| charge_dispatched | MW | @ |
| remaining_capacity | MWh | @ |
| projected_SOC | MWh | @ |
| recharge_opportunity | MWh | @ |
| dispatch_reason | n/a? | @ |

Validation Rules

- discharge ≤ reserve_power_output
- remaining storage ≥ minimum reserve
- projected SOC valid
- transmission constraints satisfied
- @

# ✅ 6-Grid Simulation Engine

Software Component 6 — Grid Simulation Engine

Purpose

Calculate hourly grid behavior after storage dispatch.

For every simulation hour calculate:

- observed net load
- dispatched net load
- capacity dispatched
- updated storage state
- remaining storage
- @additional grid variables
Update:

SOC(t+1)

Confirm:

- stress event continues
- event completed
Advance simulation hour.

Data Contract


| Field | Unit | Description |
|---|---|---|
| date | date | Calendar date |
| observed_load | MW | @ |
| observed_net_load | MW | @ |
| dispatched_net_load | MW | @ |
| charge_dispatched | MW | @ |
| updated_SOC | MWh | @ |
| reserve_power_output | MW | @ |
| oil_generation_actual | MW | @ |
| gas_generation_actual | MW | @ |
| wind_generation_actual | MW | @ |

Derived Fields

- net load reduction
- storage utilization
- transmission utilization
- @
Validation Rules

- power balance satisfied
- storage conservation satisfied
- no negative generation
- @

# ✅ 7-Scenario Metrics Engine

Software Component 7 — Scenario Metrics Engine

Purpose

Calculate scenario performance metrics after each winter simulation.

Capacity Margin Deficit ReductionΔCM(t)=max(0,(+)CM_with_storage(t)-(+)CM_without_storage(t))t=0N(net_load_dispatch(t)-net_load_observed(t)) / t=0N(net_load_observed(t)) • 100

Stress Window Effectiveness

t=0N(charge_dispatched(t)) / t=0N(oil_generation_actual(t)+gas_generation_actual(t))

Fuel-Fired Generation Offset

t=0N(+)(historical_oil_generation(t))+(+)t=0N(historical_gas_generation(t) )+(-)t=0N(wind_generation(t)+(-)t=0Ncapacity_dispatched(t)

Fuel Offset Percentage

fuelfired_generation_offset/t=0Ntotal_generation(t)

Cycle Recharge Mismatch

t=tstarttend(recharge_opporunity(t) - actual_recharged(t))

Average Recharge Mismatch

1Nc=1Ncycle_recharge_mismatch(t)

Recharge Capacity Mismatch

average_recharge_mismatch(t) / maximum_available_capacity

Estimated Capital Costs

est_transmission_cost_per_mile • miles + est_storage_unit_cost • total_unit_count

Cost per Equivalent Full Cycle

est_capital_costs / ((annual_equivalent_full_cycle) • (solution_lifetime))

Scenario Robustness Score

Each winter shall be evaluated independently.

Winter evaluations:

- 2021/2022
- 2022/2023
- 2023/2024
- 2024/2025
- 2025/2026
Evaluation Rule:

Each performance metric shall define:

- acceptable operating range = @
- warning range = @
- failure threshold = @
If any single metric falls outside its acceptable operating range during a winter simulation, that winter automatically receives one robustness failure point.

The final Scenario Robustness Score shall be calculated

from the total number of winter failure points

using: @

Data Contract


| Field | Unit | Description |
|---|---|---|
| winter_id | n/a | hash value identifier for winter |
| capacity_magin_improvement | % | @ |
| stress_window_effectiveness | % | @ |
| fuel_fired_generation_offset | MWh | @ |
| fuel_offset_percentage | % | @ |
| cycle_recharge_mismatch | MWh | @ |
| average_recharge_mismatch | MW | @ |
| recharge_capacity_mismatch | % | @ |
| est_capital_cost | $ | @ |
| annual_equivalent_full_cycles | cycle | @ |
| cost_per_equivalent_full_cycle | $ | @ |
| scenario_robustness_score | score | @ |

Validation Rules

- every metric successfully calculated
- divide-by-zero protection
- undefined values handled according to policy
- @

# ⏳ Global Asmts & Rules

Global Assumptions and Rules

The following engineering decisions require explicit values before implementation. No implicit assumptions shall be made.

System Assumptions

- Simulation time step = @
- Timestamp format = @
- Time zone = @
- Historical data source = @
- Forecast horizon = @
- Forecast update frequency = @
Storage Assumptions

- Maximum charging power = @
- Charging efficiency = @
- Discharging efficiency = @
- Round-trip efficiency = @
- Minimum allowable state of charge = @
- Maximum allowable state of charge = total_capacity
- Self-discharge rate = @
Transmission Assumptions

- Shared transmission rules = @
- Maximum import/export assumptions = @
- Curtailment rules = @
Dispatch Rules

- Primary optimization objective = @
- Secondary optimization objective = @
- Dispatch priority hierarchy = @
- Recharge priority hierarchy = @
- Tie-breaking rules = @
Event Rules

- Minimum stress event duration = minimum_window
- Event merge rules = @
- Event split rules = @
- Overlapping event rules = @
- Event termination rule = @
Error Handling

- Missing data policy = @
- Duplicate timestamp policy = @
- Invalid input policy = @
- Numerical overflow policy = @
- Simulation recovery policy = @
- Logging policy = @
- Version tracking policy = @

# ⏳ Global Interf. Contract

Global Interface Contract

Every software component shall satisfy the following interface requirements.

Inputs

Every component shall receive:

- validated data only
- immutable historical datasets
- immutable scenario configuration
- mutable simulation state only through defined contracts
Outputs

Every component shall produce:

- deterministic outputs
- versioned outputs
- schema-compliant outputs
- validated outputs
Interface Rules

Software components shall never modify another component's output.

Software components shall never bypass an intermediate component.

Every component shall return exactly one of:

Success

- Recoverable Error
- Non-Recoverable Error
- Validation Failure
Each response shall include:


| Field | Description |
|---|---|
| execution_status | @ |
| execution_timestamp | @ |
| software_component | @ |
| execution_duration | @ |
| warning_count | @ |
| error_count | @ |
| execution_message | @ |

Schema Versioning

Every exchanged object shall include:


| Field | Description |
|---|---|
| schema_version | @ |
| software_version | @ |
| simulation_version | @ |
| calculation_version | @ |
| configuration_version | @ |


# ⏳ Gloval Data Governance

Data Governance

All software components shall conform to the following engineering rules.

Naming Convention

- identifier format = @
- timestamp format = @
- units convention = @
- null value representation = @
- missing value representation = @
Precision

- floating point precision = @
- numerical rounding policy = @
- currency precision = @
- timestamp precision = @
Storage

- persistent storage location = @
- temporary storage location = @
- serialization format = @
- compression policy = @
- archive policy = @
Logging

Each component shall record:

- execution start
- execution finish
- warning messages
- validation failures
- execution duration
- software version
- configuration version
- schema version
- @

# 🪦 Archived

V1.0 MVP Architecture

- Gather user inputs
- wind_generative_scale
- transmission_capacity
- total_capacity
- minimum_window
- reserve_power_output
- Begin 5 year loop
- Extract, transform, and load data for current year’s daily loads
- Search for supply adequacy stress events in the current year by daily loads
- Store events by indexes for the first and last hour of the event
- Initialize the simulation
- Calculate state of charge for the beginning of day 0 event dispatch
- The first event
- Starts with 0 MWhs of energy
- Has a 5 day maximum number of days for storing energy before the minimum window—representing the shortest 2-day window in a 7-day forecast
- i+1 Events
- Starts with X MWhs of energy, where X is the charge remaining at the end of the last event
- Same 5 day charge maximum
- Define system state
- Begin a 7-day rolling-window analysis that loops over the starting and ending index to each event
- Evaluate today’s available energy capacity
- Build discharge schedule
- Estimate future recharge opportunities
- Predict future storage trajectory
- Determine today's dispatch strategy
- Calculate grid performance during simulation
- Capacity margin: total load - net load with storage
- Return the remaining storage after grid simulation
- Update system state
- Confirm the stress window hasn’t ended
- Advance the rolling-window loop
- Summarize scenario results
- Capacity Margin Improvement
- Stress Window Effectiveness
- Fuel Offset Percentage
- Recharge Capacity Mismatch
- Estimated Capital Costs
- Cost per Equivalent Full Cycle
- Scenario Robustness Score
- Build an annotation decision package
- Send the decision package to the AI assistant
Step 1 - User Inputs

- Pumped Hydro Storage
- Total Capacity
- Starting Capacity
- Power Output
- Season
- Calendar date range
- Minimum stress event window in days
- Severity stress level based on a percentile of  historical load records
- Transmission limits
Step 2 - Search for stress event in calendar date range

- Calculate daily load as a sum of hourly load in MWh across everyday in time range
- Run a search function over daily loads in that time range looking for windows of X or more stress days (where X is defined by the user)
- Store all windows found
Step 3 - Calculate state of charge for the beginning of the first stress day

- This will frequently be 100%, but both fewer days and lower starting capacity can decrease capacity at the beginning of an event
- Check ∑wind_power(d) for (d=0,N) is greater than soc_max - soc_start
- soc_window_a = soc_max - soc_start
- Else:
- soc_window_a += ∑wind_power(d)
Step 4 - Confirm stress event starting values with the user

- Return to the user the total number of days before the stress event occurs and the state of charge on the first stress day
- List state of charge options for each day the event is moved closer to the first stress day, starting with the first calendar date
- Ask the user what is the first day they’d like to base calculations on
Step 5 - Estimates the daily energy budget for each day

- For hours between the last discharge hour of the previous stress day and the first discharge hour of today
- recoverable_energy = min(ForecastWindEnergycharge​, max_charge • (t_2 - t_1))
- required_recharge = capacitymax - socfloor - strategic_reserve
- recharge_sufficiency_ratio = recoverable_energy / required_recharge
- Check for days with a recharge sufficiency ratio less than 1
- last_day_below = day_index
Step 6 -

Step 7 -

- Recursively call the usable energy
- t starts at 0
- usable_energy(t) = soc(t) - soc_floor - strategic_reserve
- usable_energy is the total energy available to discharge at the start of every hour
- soc is the state of charge or the current amount of energy stored in pumped hydro reserves
- soc_floor is a percentage of total energy capacity the system isn’t typically allowed to discharge
- strategic_reserve is a percentage of total energy capacity the system holds in reserve on top of the state of charge floor, which can be used during early warning signs of system stress and increases optionality
- Check to see if the current hour coupling is within the peak 2 hour coupling
- NetLoad(t)=Load(t)−Solar(t)−Wind(t)
- PeakWeight(t) = NetLoad(t) / ∑NetLoadpeak
- Dischargepeak(t) = Epeak × PeakWeight(t)
- Check to see if current hour is within 4 hours before or after the peak 2 hour coupling
- Ramp(t) = |NetLoad(t)−NetLoad(t−1)|
- SmoothWeight(t) = Ramp(t) / ∑Rampwindow
- Dischargesmooth(t) = Esmooth × SmoothWeight(t)
- Else: check to see if current hour falls outside the first two conditions
- Check wind_power(t) is greater than soc_max - soc(t)
- charge(t)=soc_max - soc(t)
- Else:
- charge(t)=wind_power(t)
- soc(t+1) = soc(t)+charge(t)
- charge is equal to the total historical wind power generated in that hour
- Increase the sum of total days of total_usable_energy within the stress window by the usable_energy of the current hour
- total_usable_energy(d) += usable_energy(t)+charge(t)
Step 6 -

Available Supply(d) = Available Generation(d) + Imports(d)

Capacity Margin(t) = Available Supply(d) - Load(t)

Peak Reduction Allocation

NetLoad(t)=Load(t)−Solar(t)−Wind(t)

PeakWeight(t) = NetLoad(t) / ∑NetLoadpeak

Dischargepeak (t) = Epeak × PeakWeight(t)

Net Load Smoothing Allocation

Ramp(t) = |NetLoad(t)−NetLoad(t−1)|

SmoothWeight(t) = Ramp(t) / ∑Rampwindow

Dischargesmooth(t) = Esmooth × SmoothWeight(t)

ResidualLoad(t)=Load(t)−Wind(t)−Storage(t)

Cost(t)=ResidualLoad(t)×Costgas

Total Dispatch

Discharge(t) = Dischargepeak(t) + Dischargesmooth(t)

∑Discharge(t) ≤ Budget(d)

State of Charge

soc_now >= .33 soc_total + strategic_reserve

soc(t+1) = soc(t)+charge(t) • efficiency - (discharge(t) / efficiency)

usable_energy(t) = soc(t) - soc_floor - strategic_reserve

total_usable_energy=usable_energy(0)+∑ charge(t) for (0,N)

DemandPercentile(d) = Demand(d)/(561,878MWh for summer or 434,214MWh for winter)

FutureWind(d)=∑ WindForecast(i) for (i=d+1, N)

max(FutureWind)=∑ WindForecast(i) for (i=d, N)

WindForecast(d)=FutureWind(d)/max(FutureWind)

Priority(d) = 0.7 DemandPercentile(d) + 0.3 WindForecast(d)

Usable_Energy(d)=∑Usable_Energy(t) for (t=0, 24)

recoverable_wind_energy=min(ForecastWindEnergycharge​, Pcharge,max​×Tcharge​)

required_recharge_energy=capacitymax - socfloor - strategic_reserve

Daily Energy Budget

Budget(d) = Usable_Energy(d) x (Priority(d)/∑Priority)

