# Power BI dashboard

The `.pbix` file is not stored in this repository (it is a large binary file).
Instead, this folder documents how to rebuild the dashboard from the exported
tables, so every step can be reviewed and reproduced.

## 1. Load the data

In Power BI Desktop: **Get data > Text/CSV** and load these files from `outputs/tables/`:

| Table | Grain | Used for |
|---|---|---|
| `daily_active_users.csv` | one row per day | DAU / WAU / MAU trend, stickiness |
| `retention_cohorts.csv` | cohort week x week number | retention matrix |
| `funnel_overall.csv` | one row per funnel step | funnel visual |
| `funnel_by_channel.csv` | one row per channel | channel comparison |
| `feature_usage_weekly.csv` | week x mode | latency and success trend |
| `language_pairs_top15.csv` | one row per language pair | top language pairs |
| `latency_impact.csv` | one row per mode | engine v2 before / after cards |
| `country_breakdown.csv` | one row per country | market comparison with confidence intervals |

Set data types: `activity_date`, `cohort_week` and `week_start` as **Date**;
rates as **Percentage**.

## 2. Model

Add a `Calendar` table and relate it to `daily_active_users[activity_date]`
and `feature_usage_weekly[week_start]` (one-to-many, single direction).

```DAX
Calendar =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2026, 1, 1 ), DATE ( 2026, 4, 30 ) ),
    "Week Start", [Date] - WEEKDAY ( [Date], 2 ) + 1,
    "Month", FORMAT ( [Date], "YYYY-MM" )
)
```

## 3. Measures

See [`measures.dax`](measures.dax).

## 4. Report pages

1. **Overview** - cards for latest DAU, MAU, stickiness; line chart of DAU (7-day average).
2. **Retention** - matrix with `cohort_week` on rows, `week_number` on columns,
   `Retention Rate` as values, conditional formatting with a single blue scale.
   Filter `is_complete_week = TRUE` so unfinished weeks do not look like churn.
3. **Funnel** - funnel visual on `funnel_overall`, slicer on channel using `funnel_by_channel`.
4. **Engine v2 impact** - cards for median latency before / after per mode,
   line chart of `avg_latency_ms` by week with a constant line at 2026-03-01.
