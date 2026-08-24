# Q19 descriptive window analysis (Q19-tehran-city-longseries)

## Scope and method

- Time basis: UTC product-day dates; inclusive windows end on the stated UTC date.
- Analysis cutoff: **2026-07-31 UTC**. The supplied daily table extends through **2026-08-02 UTC**, and later rows are excluded.
- A daily value is included only when `qualified == true`; no interpolation or imputation is applied.
- `mean_of_daily_means` is the arithmetic mean of the retained daily `mean` values. Relative change is `(window mean - complete baseline mean) / complete baseline mean * 100`.
- Strict is the primary QA mode; permissive is a sensitivity analysis.

## Window summary

| QA mode | Window | Qualified days | Mean of daily means | Relative change vs complete baseline |
|---|---|---:|---:|---:|
| strict | baseline | 47 | 67.231834906946 | 0.000000% |
| strict | conflict | 20 | 55.619915661608 | -17.271460% |
| strict | ceasefire_evaluation | 11 | 61.358262705519 | -8.736296% |
| strict | extended_monitoring | 83 | 59.752430113881 | -11.124796% |
| permissive | baseline | 48 | 65.202541411444 | 0.000000% |
| permissive | conflict | 20 | 54.722791838263 | -16.072609% |
| permissive | ceasefire_evaluation | 12 | 58.574161795361 | -10.165830% |
| permissive | extended_monitoring | 84 | 59.863431544922 | -8.188500% |

## Interpretation limits

These are descriptive radiance summaries only. They do not establish causal attribution, conflict effects, outage, damage, or recovery. The extended-monitoring window is not treated as a homogeneous ceasefire or recovery phase.

The Event Tracker overall-ranking verdict is `indeterminate`. Therefore, the analysis does not treat the target as an established highest-ranked complete event-census unit; any ranking support is limited to the qualified exact-coordinate subset described by the Event Tracker artifact.

Source rows read: 428. The analysis uses only dates through 2026-07-31 UTC.
