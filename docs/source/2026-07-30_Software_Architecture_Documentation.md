# Global Asmts & Rules

Global Assumptions and Rules

The following engineering decisions require explicit values before implementation. No implicit assumptions shall be made.

System Assumptions

* Simulation time step \= @  
* Timestamp format \= @  
* Time zone \= @  
* Historical data source \= @  
* Forecast horizon \= @  
* Forecast update frequency \= @

Storage Assumptions

* Maximum charging power \= @  
* Charging efficiency \= @  
* Discharging efficiency \= @  
* Round-trip efficiency \= @  
* Minimum allowable state of charge \= @  
* Maximum allowable state of charge \= total\_capacity  
* Self-discharge rate \= @

Transmission Assumptions

* Shared transmission rules \= @  
* Maximum import/export assumptions \= @  
* Curtailment rules \= @

Dispatch Rules

* Primary optimization objective \= @  
* Secondary optimization objective \= @  
* Dispatch priority hierarchy \= @  
* Recharge priority hierarchy \= @  
* Tie-breaking rules \= @

Event Rules

* Minimum stress event duration \= minimum\_window  
* Event merge rules \= @  
* Event split rules \= @  
* Overlapping event rules \= @  
* Event termination rule \= @

Error Handling

* Missing data policy \= @  
* Duplicate timestamp policy \= @  
* Invalid input policy \= @  
* Numerical overflow policy \= @  
* Simulation recovery policy \= @  
* Logging policy \= @  
* Version tracking policy \= @

# Global Interf. Contract

Global Interface Contract

Every software component shall satisfy the following interface requirements.

Inputs  
Every component shall receive:

* validated data only  
* immutable historical datasets  
* immutable scenario configuration  
* mutable simulation state only through defined contracts

Outputs  
Every component shall produce:

* deterministic outputs  
* versioned outputs  
* schema-compliant outputs  
* validated outputs

Interface Rules  
Software components shall never modify another component's output.

Software components shall never bypass an intermediate component.

Every component shall return exactly one of:  
Success

* Recoverable Error  
* Non-Recoverable Error  
* Validation Failure

Each response shall include:

| Field | Description |
| :---- | :---- |
| execution\_status | @ |
| execution\_timestamp | @ |
| software\_component | @ |
| execution\_duration | @ |
| warning\_count | @ |
| error\_count | @ |
| execution\_message | @ |

Schema Versioning  
Every exchanged object shall include:

| Field | Description |
| :---- | :---- |
| schema\_version | @ |
| software\_version | @ |
| simulation\_version | @ |
| calculation\_version | @ |
| configuration\_version | @ |

# Gloval Data Governance

Data Governance

All software components shall conform to the following engineering rules.

Naming Convention

* identifier format \= @  
* timestamp format \= @  
* units convention \= @  
* null value representation \= @  
* missing value representation \= @

Precision

* floating point precision \= @  
* numerical rounding policy \= @  
* currency precision \= @  
* timestamp precision \= @

Storage

* persistent storage location \= @  
* temporary storage location \= @  
* serialization format \= @  
* compression policy \= @  
* archive policy \= @

Logging  
Each component shall record:

* execution start  
* execution finish  
* warning messages  
* validation failures  
* execution duration  
* software version  
* configuration version  
* schema version  
* @

# 1-Scenario Config

Software Component 1 — Scenario Configuration

Purpose  
Collect, validate, and store all user-defined scenario parameters before simulation begins.

Data Fields  
Validation Rules

* All inputs shall be validated before simulation begins.  
* Invalid inputs shall terminate execution before data loading.  
* Validation ranges:  
  * wind\_generation\_multiplier \= @  
  * transmission\_capacity \= @  
  * total\_capacity \= @  
  * reserve\_power\_output \= @  
  * minimum\_window ≥ @

Data Contract

| Field | Required | Type | Default | Unit | Description |
| :---- | :---- | :---- | :---- | :---- | :---- |
| scenario\_id | Y | str |  | none | Unique scenario identifier |
| wind\_generation\_multiplier | Y | float | 1.0 | Scalar | Historical wind multiplier |
| transmission\_capacity | Y | float | 200.0 | MW | Maximum transmission power capacity |
| total\_energy\_capcity | Y | float | 60,000.0 | MWh | Maximum energy capacity for storage |
| total\_storage\_units | Y | int | 3000 | Storage Units |  |
| reserve\_power\_output | Y | float | 4320.0 | MW | Maximum storage power output |
| minimum\_event\_window | Y | int | 2 | Days | Minimum stress event duration |

# 2-Data Pipeline

Software Component 2 — Data Pipeline

Purpose  
Extract, transform, validate, and prepare historical data for simulation.

Data FieldsProcessing Steps  
For each historical winter:

* Winter 2021/2022  
* Winter 2022/2023  
* Winter 2023/2024  
* Winter 2024/2025  
* Winter 2025/2026

perform the following sequence independently.

Extract Data  
Load:

* hourly electrical load  
* hourly wind generation  
* hourly oil generation  
* hourly gas generation  
* transmission information

Transform Data  
Apply:  
historical\_wind\_generation  
× wind\_generation\_multiplier  
\= scaled\_wind\_generation

Validate Data  
Verify:

* no missing timestamps  
* no duplicate timestamps  
* chronological ordering  
* valid numerical ranges  
* @additional validation rules

Data Contract

| Field | Required | Type | Unit | Description |
| :---- | :---- | :---- | :---- | :---- |
| date | Y | YYYY-MM-DD | date | Calendar date |
| hour | Y | int | hour | Hours in a day |
| load\_mw | Y | float | MW | Hourly system load |
| wind\_mwh | N | float | MWh | Hourly wind generation |
| oil\_mwh | N | float | MWh | Hourly oil generation |
| gas\_mwh | N | float | MWh | Hourly liquid natural gas generation |
| demand\_percentile | N | float, constant per date | % | Daily? historical percentile of demand load |
| wind\_forecast\_frac | N | float, constant per date | ratio | Daily? wind generation fraction of total 7-day wind generation |

Optional Fields

* @

Validation Rules

* continuous timestamps  
* chronological ordering  
* no duplicate timestamps  
* no null required values  
* valid numerical ranges  
* @

# 3-Stress Event Detection

Software Component 3 — Stress Event Detection  
Purpose

Identify supply adequacy stress events requiring storage simulation.

Event Detection Rule

Calculate:  
historical\_daily\_load

Determine:  
90th historical daily load percentile

A stress event begins when:  
daily\_load ≥ 90th percentile  
for  
minimum\_window  
consecutive days.

Store:

* event identifier  
* starting timestamp  
* ending timestamp  
* duration

Data Contract

| Field | Required | Type | Unit | Description |
| :---- | :---- | :---- | :---- | :---- |
| event\_id | @ | @ | @ | @ |
| winter\_id | @ | @ | @ | @ |
| event\_start\_timestamp | @ | @ | @ | @ |
| event\_end\_timestamp | @ | @ | @ | @ |
| first\_hour\_index | @ | int | hour | @ |
| last\_hour\_index | @ | int | hour | @ |
| event\_duration | @ | int | day | @ |
| peak\_daily\_load | @ | tuple? | MW? | @ |
| percentile\_threshold | @ | floatint | %Percentile | @ |

Derived Fields

* event hour count  
* event day count  
* @

Validation Rules

* duration ≥ minimum\_window  
* start precedes end  
* event entirely contained within historical winter  
* no overlapping event identifiers  
* @

# 4-Simulation Initialization

Software Component 4 — Simulation Initialization

Purpose  
Initialize the storage system before each stress event simulation.

Initial Event  
Beginning State of Charge  
SOC \= 0 MWh

Charging Window  
Maximum available charging period:  
5 days  
representing:  
7-day forecast  
− minimum\_window

Subsequent Events  
Beginning State of Charge  
SOC  
\= remaining storage from previous event

Initialize:

* storage state  
* dispatch history  
* recharge history

Data Contract

| Field | Required | Type | Unit | Description |
| :---- | :---- | :---- | :---- | :---- |
| simulation\_id | @ | @ | @ | @ |
| event\_id | @ | @ | @ | @ |
| current\_timestamp | @ | @ | @ | @ |
| current\_hour\_index | @ | int | hour | @ |
| state\_of\_charge | @ | float | MWh | @ |
| remaing\_capacity | @ | float | MWh | @ |
| reserve\_power\_output | @ | float | MW | @ |
| charging\_window\_remaining | @ | int | hour | @ |
| dispatch\_history | @ | @ | @ | @ |
| recharge\_history | @ | @ | @ | @ |

Validation Rules

* SOC ≥ minimum reserve  
* SOC ≤ total\_capacity  
* remaining\_capacity ≥ 0  
* @

# 5-Storage Dispatch Engine

Software Component 5 — Storage Dispatch Engine

Purpose  
Determine hourly storage operation during each stress event.

Begin Rolling Forecast Simulation  
For each hour between:  
event\_start  
and  
event\_end  
perform:  
Evaluate Current System State  
Determine:

* available storage energy  
* remaining energy capacity  
* maximum power output  
* available transmission capacity  
* @additional operating constraints  
* Build Discharge Schedule

Construct an hourly discharge schedule using:

* available storage  
* reserve limits  
* transmission limits  
* @dispatch priorities

Estimate Future Recharge Opportunities  
Estimate available recharge throughout the remaining forecast horizon.

Predict Storage Trajectory  
Forecast:  
future SOC  
throughout the remaining event.

Determine Current Dispatch  
Calculate:  
capacity\_dispatched(t)  
subject to:

* storage energy capacity  
* reserve power output  
* transmission limits  
* minimum reserve  
* @charging constraints  
* @round-trip efficiency  
* @dispatch objective  
* @additional operating rules

Data Contract

| Field | Required | Type | Unit | Description |
| :---- | :---- | :---- | :---- | :---- |
| date | Y | YYYY-MM-DD | date | Calendar date |
| discharge\_power | @ | float | MW | @ |
| charge\_power | @ | float | MW | @ |
| dispatched\_capacity | @ | float | MWh | @ |
| remaining\_capacity | @ | float | MWh | @ |
| projected\_SOC | @ | float | MWh | @ |
| recharge\_opportunity | @ | float | MWh | @ |
| dispatch\_reason | @ | @ | @ | @ |

Validation Rules

* discharge ≤ reserve\_power\_output  
* remaining storage ≥ minimum reserve  
* projected SOC valid  
* transmission constraints satisfied  
* @

# 6-Grid Simulation Engine

Software Component 6 — Grid Simulation Engine

Purpose  
Calculate hourly grid behavior after storage dispatch.  
For every simulation hour calculate:

* observed net load  
* dispatched net load  
* capacity dispatched  
* updated storage state  
* remaining storage  
* @additional grid variables

Update:  
SOC(t+1)  
Confirm:

* stress event continues  
* event completed

Advance simulation hour.  
Data Contract

| Field | Required | Type | Unit | Description |
| :---- | :---- | :---- | :---- | :---- |
| date | Y | YYYY-MM-DD | date | Calendar date |
| observed\_load | @ | float | MW | @ |
| observed\_net\_load | @ | float | MW | @ |
| dispatched\_net\_load | @ | float | MW | @ |
| capacity\_dispatched | @ | float | MW | @ |
| updated\_SOC | @ | float | MWh | @ |
| reserve\_power\_output | @ | float | MW | @ |
| oil\_generation\_actual | @ | float | MW | @ |
| gas\_generation\_actual | @ | float | MW | @ |
| wind\_generation\_actual | @ | float | MW | @ |

Derived Fields

* net load reduction  
* storage utilization  
* transmission utilization  
* @

Validation Rules

* power balance satisfied  
* storage conservation satisfied  
* no negative generation  
* @

# 7-Scenario Metrics Engine

Software Component 7 — Scenario Metrics Engine

Purpose  
Calculate scenario performance metrics after each winter simulation.

Capacity Margin Improvement  
t=0N(net\_load\_dispatch(t)-net\_load\_observed(t)) / t=0N(net\_load\_observed(t)) • 100

Stress Window Effectiveness  
t=0N(capacity\_dispatched(t)) / t=0N(oil\_generation\_actual(t) \+gas\_generation\_actual(t)+wind\_generation\_actual(t))

Fuel-Fired Generation Offset  
t=0N(oil\_generation(t))+t=0N(gas\_generation(t) )- (t=0N(wind\_generation(t) \+t=0Ncapacity\_dispatched(t))

Fuel Offset Percentage  
fuelfired\_generation\_offset/t=0Ntotal\_generation(t)

Cycle Recharge Mismatch  
t=tstarttend(recharge\_opporunity(t) \- actual\_recharged(t))

Average Recharge Mismatch  
 1Nc=1Ncycle\_recharge\_mismatch(t)

Recharge Capacity Mismatch  
average\_cycle\_recharge\_utilization(t) / maximum\_available\_capacity

Estimated Capital Costs  
est\_transmission\_cost\_per\_mile • miles \+ est\_storage\_unit\_cost • total\_unit\_count

Cost per Equivalent Full Cycle  
est\_capital\_costs / ((annual\_equivalent\_full\_cycle) • (solution\_lifetime))

Scenario Robustness Score  
Each winter shall be evaluated independently.  
Winter evaluations:

* 2021/2022  
* 2022/2023  
* 2023/2024  
* 2024/2025  
* 2025/2026

Evaluation Rule:  
Each performance metric shall define:

* acceptable operating range \= @  
* warning range \= @  
* failure threshold \= @

If any single metric falls outside its acceptable operating range during a winter simulation, that winter automatically receives one robustness failure point.

The final Scenario Robustness Score shall be calculated   
from the total number of winter failure points   
using: @  
Data Contract

| Field | Required | Type | Unit | Description |
| :---- | :---- | :---- | :---- | :---- |
| scenario\_id | @ | @ | @ | @ |
| winter\_id | @ | @ | @ | @ |
| capacity\_magin\_improvement | @ | float | % | @ |
| stress\_window\_effectiveness | @ | float | % | @ |
| fuel\_fired\_generation\_offset | @ | float | MWh | @ |
| fuel\_offset\_percentage | @ | float | % | @ |
| cycle\_recharge\_mismatch | @ | float | MWh | @ |
| average\_recharge\_mismatch | @ | float | MW | @ |
| recharge\_capacity\_mismatch | @ | float | % | @ |
| est\_capital\_cost | @ | float | $ | @ |
| annual\_equivalent\_full\_cycles | @ | float | cycle | @ |
| cost\_per\_equivalent\_full\_cycle | @ | float | $ | @ |
| scenario\_robustness\_score | @ | float | score | @ |

Validation Rules

* every metric successfully calculated  
* divide-by-zero protection  
* undefined values handled according to policy  
* @

# Archived

V1.0 MVP Architecture

1. Gather user inputs  
   1. wind\_generative\_scale  
   2. transmission\_capacity  
   3. total\_capacity  
   4. minimum\_window  
   5. reserve\_power\_output  
2. Begin 5 year loop  
3. Extract, transform, and load data for current year’s daily loads  
4. Search for supply adequacy stress events in the current year by daily loads  
   1. Store events by indexes for the first and last hour of the event  
5. Initialize the simulation   
   1. Calculate state of charge for the beginning of day 0 event dispatch  
      1. The first event  
         1. Starts with 0 MWhs of energy  
         2. Has a 5 day maximum number of days for storing energy before the minimum window—representing the shortest 2-day window in a 7-day forecast  
      2. i+1 Events  
         1. Starts with X MWhs of energy, where X is the charge remaining at the end of the last event  
         2. Same 5 day charge maximum  
   2. Define system state  
6. Begin a 7-day rolling-window analysis that loops over the starting and ending index to each event  
   1. Evaluate today’s available energy capacity  
   2. Build discharge schedule  
   3. Estimate future recharge opportunities  
   4. Predict future storage trajectory  
7. Determine today's dispatch strategy  
8. Calculate grid performance during simulation  
   1. Capacity margin: total load \- net load with storage  
9. Return the remaining storage after grid simulation  
10. Update system state  
11. Confirm the stress window hasn’t ended  
12. Advance the rolling-window loop  
13. Summarize scenario results  
    1. Capacity Margin Improvement  
    2. Stress Window Effectiveness  
    3. Fuel Offset Percentage  
    4. Recharge Capacity Mismatch  
    5. Estimated Capital Costs  
    6. Cost per Equivalent Full Cycle  
    7. Scenario Robustness Score  
14. Build an annotation decision package  
15. Send the decision package to the AI assistant

Step 1 \- User Inputs

* Pumped Hydro Storage  
  * Total Capacity  
  * Starting Capacity  
  * Power Output  
* Season  
  * Calendar date range  
* Minimum stress event window in days  
  * Severity stress level based on a percentile of  historical load records  
* Transmission limits

Step 2 \- Search for stress event in calendar date range

* Calculate daily load as a sum of hourly load in MWh across everyday in time range  
* Run a search function over daily loads in that time range looking for windows of X or more stress days (where X is defined by the user)  
* Store all windows found

Step 3 \- Calculate state of charge for the beginning of the first stress day

* This will frequently be 100%, but both fewer days and lower starting capacity can decrease capacity at the beginning of an event  
* Check ∑wind\_power(d) for (d=0,N) is greater than soc\_max \- soc\_start  
  * soc\_window\_a \= soc\_max \- soc\_start  
  * Else:  
    * soc\_window\_a \+= ∑wind\_power(d)

Step 4 \- Confirm stress event starting values with the user

* Return to the user the total number of days before the stress event occurs and the state of charge on the first stress day  
* List state of charge options for each day the event is moved closer to the first stress day, starting with the first calendar date  
* Ask the user what is the first day they’d like to base calculations on

Step 5 \- Estimates the daily energy budget for each day

* For hours between the last discharge hour of the previous stress day and the first discharge hour of today  
  * recoverable\_energy \= min(ForecastWindEnergycharge​, max\_charge • (t\_2 \- t\_1))  
  * required\_recharge \= capacitymax \- socfloor \- strategic\_reserve  
  * recharge\_sufficiency\_ratio \= recoverable\_energy / required\_recharge  
  * Check for days with a recharge sufficiency ratio less than 1  
    * last\_day\_below \= day\_index  
* 

Step 6 \- 

* 

Step 7 \- 

* Recursively call the usable energy   
  * t starts at 0  
  * usable\_energy(t) \= soc(t) \- soc\_floor \- strategic\_reserve  
    * usable\_energy is the total energy available to discharge at the start of every hour  
    * soc is the state of charge or the current amount of energy stored in pumped hydro reserves  
    * soc\_floor is a percentage of total energy capacity the system isn’t typically allowed to discharge  
    * strategic\_reserve is a percentage of total energy capacity the system holds in reserve on top of the state of charge floor, which can be used during early warning signs of system stress and increases optionality  
  * Check to see if the current hour coupling is within the peak 2 hour coupling  
    * NetLoad(t)=Load(t)−Solar(t)−Wind(t)  
    * PeakWeight(t) \= NetLoad(t) / ∑NetLoadpeak  
    * Dischargepeak(t) \= Epeak × PeakWeight(t)  
  * Check to see if current hour is within 4 hours before or after the peak 2 hour coupling  
    * Ramp(t) \= |NetLoad(t)−NetLoad(t−1)|  
    * SmoothWeight(t) \= Ramp(t) / ∑Rampwindow  
    * Dischargesmooth(t) \= Esmooth × SmoothWeight(t)  
  * Else: check to see if current hour falls outside the first two conditions  
    * Check wind\_power(t) is greater than soc\_max \- soc(t)  
      * charge(t)=soc\_max \- soc(t)  
      * Else:  
        * charge(t)=wind\_power(t)  
    * soc(t+1) \= soc(t)+charge(t)  
      * charge is equal to the total historical wind power generated in that hour  
  * Increase the sum of total days of total\_usable\_energy within the stress window by the usable\_energy of the current hour  
    * total\_usable\_energy(d) \+= usable\_energy(t)+charge(t)  
* Calculate what 80% of the total energy budget for the stress window  
  * Sum of wind power forecasts  
  * The difference of today’s state of charge minus constant reserve of 33% total capacity  
  * Sum of the previous two calculations for a total energy budget  
  * Product of total energy budget times 0.80  
* A simple average of 80% energy budget divided by number of days across the window

Step 6 \-   
Available Supply(d) \= Available Generation(d) \+ Imports(d)  
Capacity Margin(t) \= Available Supply(d) \- Load(t)

Peak Reduction Allocation  
NetLoad(t)=Load(t)−Solar(t)−Wind(t)  
PeakWeight(t) \= NetLoad(t) / ∑NetLoadpeak  
Dischargepeak (t) \= Epeak × PeakWeight(t)

Net Load Smoothing Allocation  
Ramp(t) \= |NetLoad(t)−NetLoad(t−1)|  
SmoothWeight(t) \= Ramp(t) / ∑Rampwindow  
Dischargesmooth(t) \= Esmooth × SmoothWeight(t)

ResidualLoad(t)=Load(t)−Wind(t)−Storage(t)  
Cost(t)=ResidualLoad(t)×Costgas

Total Dispatch  
Discharge(t) \= Dischargepeak(t) \+ Dischargesmooth(t)  
∑Discharge(t) ≤ Budget(d)

State of Charge  
soc\_now \>= .33 soc\_total \+ strategic\_reserve  
soc(t+1) \= soc(t)+charge(t) • efficiency \- (discharge(t) / efficiency)  
usable\_energy(t) \= soc(t) \- soc\_floor \- strategic\_reserve  
total\_usable\_energy=usable\_energy(0)+∑ charge(t) for (0,N)  
DemandPercentile(d) \= Demand(d)/(561,878MWh for summer or 434,214MWh for winter)  
FutureWind(d)=∑ WindForecast(i) for (i=d+1, N)  
max(FutureWind)=∑ WindForecast(i) for (i=d, N)  
WindForecast(d)=FutureWind(d)/max(FutureWind)  
Priority(d) \= 0.7 DemandPercentile(d) \+ 0.3 WindForecast(d)  
Usable\_Energy(d)=∑Usable\_Energy(t) for (t=0, 24\)

recoverable\_wind\_energy=min(ForecastWindEnergycharge​, Pcharge,max​×Tcharge​)  
required\_recharge\_energy=capacitymax \- socfloor \- strategic\_reserve

Daily Energy Budget  
Budget(d) \= Usable\_Energy(d) x (Priority(d)/∑Priority)