"""
Run the SQL analyses against the SQLite database, add Python-side statistics,
export tidy CSV tables (ready for Power BI) and draw summary charts.

Usage:
    python src/analyze.py
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "talkbridge.db"
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "outputs"
TABLE_DIR = OUT_DIR / "tables"
CHART_DIR = OUT_DIR / "charts"

ENGINE_V2_DATE = pd.Timestamp(date(2026, 3, 1))

# Chart styling: one validated palette, recessive axes, text in ink colors.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SERIES = {"blue": "#2a78d6", "orange": "#eb6834"}
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
def run_sql(conn: sqlite3.Connection, filename: str) -> pd.DataFrame:
    query = (SQL_DIR / filename).read_text(encoding="utf-8")
    return pd.read_sql_query(query, conn)


def load_translations(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT requested_at, mode, latency_ms, success FROM translations", conn,
        parse_dates=["requested_at"])
    df["engine"] = np.where(df["requested_at"] >= ENGINE_V2_DATE, "engine-v2", "engine-v1")
    return df


# --------------------------------------------------------------------------- #
# Python-side statistics
# --------------------------------------------------------------------------- #
def bootstrap_median_diff(before: np.ndarray, after: np.ndarray,
                          n_boot: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Relative change in median latency (after vs before) with a 95% bootstrap CI."""
    rng = np.random.default_rng(seed)
    point = np.median(after) / np.median(before) - 1
    sample = min(len(before), len(after), 5000)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        b = rng.choice(before, size=sample, replace=True)
        a = rng.choice(after, size=sample, replace=True)
        diffs[i] = np.median(a) / np.median(b) - 1
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(point), float(low), float(high)


def wilson_interval(successes: np.ndarray, n: np.ndarray, z: float = 1.96):
    """95% Wilson score interval for a proportion; stays sensible for small samples."""
    successes = np.asarray(successes, dtype=float)
    n = np.asarray(n, dtype=float)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    # clip tiny floating-point overshoots (e.g. -1e-17) back into [0, 1]
    return np.clip(centre - half, 0, 1), np.clip(centre + half, 0, 1)


def latency_impact(translations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mode, grp in translations.groupby("mode"):
        before = grp.loc[grp["engine"] == "engine-v1", "latency_ms"].to_numpy()
        after = grp.loc[grp["engine"] == "engine-v2", "latency_ms"].to_numpy()
        change, low, high = bootstrap_median_diff(before, after)
        rows.append({
            "mode": mode,
            "p50_before_ms": int(np.median(before)),
            "p50_after_ms": int(np.median(after)),
            "p95_before_ms": int(np.percentile(before, 95)),
            "p95_after_ms": int(np.percentile(after, 95)),
            "median_change_pct": round(100 * change, 1),
            "ci95_low_pct": round(100 * low, 1),
            "ci95_high_pct": round(100 * high, 1),
            "success_before": round(grp.loc[grp["engine"] == "engine-v1", "success"].mean(), 4),
            "success_after": round(grp.loc[grp["engine"] == "engine-v2", "success"].mean(), 4),
        })
    return pd.DataFrame(rows)


def retention_matrix(retention: pd.DataFrame) -> pd.DataFrame:
    """Pivot cohorts x week_number and hide cells the data cannot observe yet."""
    matrix = retention.pivot(index="cohort_week", columns="week_number", values="retention_rate")
    last_day = pd.Timestamp(date(2026, 4, 30))
    for cohort in matrix.index:
        # a week is complete only for the cohort's latest signup day (Sunday)
        cohort_end = pd.Timestamp(cohort) + pd.Timedelta(days=6)
        weeks_observable = ((last_day - cohort_end).days + 1) // 7 - 1
        matrix.loc[cohort, matrix.columns > weeks_observable] = np.nan
    return matrix


def cohort_week1_by_engine(retention: pd.DataFrame) -> pd.DataFrame:
    w1 = retention[retention["week_number"] == 1].copy()
    if "is_complete_week" in w1:
        w1 = w1[w1["is_complete_week"]]     # skip cohorts whose week 1 is not over yet
    w1["engine"] = np.where(pd.to_datetime(w1["cohort_week"]) >= ENGINE_V2_DATE,
                            "engine-v2", "engine-v1")
    out = w1.groupby("engine").apply(
        lambda g: pd.Series({
            "cohorts": len(g),
            "users": int(g["cohort_users"].sum()),
            "week1_retention": round(g["retained_users"].sum() / g["cohort_users"].sum(), 4),
        }), include_groups=False).reset_index()
    return out


def funnel_long(funnel: pd.DataFrame) -> pd.DataFrame:
    steps = ["signed_up", "completed_onboarding", "first_translation",
             "ten_plus_translations", "subscribed"]
    total = funnel[steps].sum()
    out = pd.DataFrame({"step": steps, "users": total.values.astype(int)})
    out["step_order"] = range(1, len(steps) + 1)
    out["pct_of_signups"] = (out["users"] / out["users"].iloc[0]).round(4)
    out["pct_of_previous"] = (out["users"] / out["users"].shift(1)).round(4).fillna(1.0)
    return out


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _style(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT_PRIMARY, pad=22 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_SECONDARY)


def _figure(width=9, height=4.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def chart_active_users(dau: pd.DataFrame, path: Path) -> None:
    fig, ax = _figure()
    x = pd.to_datetime(dau["activity_date"])
    ax.plot(x, dau["dau"].rolling(7, min_periods=1).mean(), color=SERIES["blue"], linewidth=2)
    ax.axvline(ENGINE_V2_DATE, color=TEXT_SECONDARY, linewidth=1, linestyle="--")
    ax.text(ENGINE_V2_DATE, ax.get_ylim()[1] * 0.97, "  engine v2 release",
            color=TEXT_SECONDARY, fontsize=9, va="top")
    ax.set_ylim(0, None)
    _style(ax, "Daily active users (7-day average)", "Synthetic data, Jan - Apr 2026")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_retention_heatmap(matrix: pd.DataFrame, path: Path) -> None:
    fig, ax = _figure(9, 5.2)
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    cmap.set_bad(SURFACE)
    # week 0 is 100% by definition, so it is left out to keep contrast for later weeks
    matrix = matrix.drop(columns=0, errors="ignore")
    data = matrix.to_numpy(dtype=float)
    im = ax.imshow(np.ma.masked_invalid(data), cmap=cmap, vmin=0, vmax=0.5, aspect="auto")
    ax.set_xticks(range(len(matrix.columns)), [f"W{c}" for c in matrix.columns])
    ax.set_yticks(range(len(matrix.index)), [str(i)[:10] for i in matrix.index])
    for (r, c), val in np.ndenumerate(data):
        if not np.isnan(val):
            ax.text(c, r, f"{val:.0%}", ha="center", va="center", fontsize=7,
                    color="white" if val > 0.3 else TEXT_PRIMARY)
    _style(ax, "Weekly retention by signup cohort",
           "Share of each weekly cohort active N weeks after signup; blank = not yet observable")
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(labelsize=8, colors=TEXT_SECONDARY)
    cbar.outline.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_funnel(funnel: pd.DataFrame, path: Path) -> None:
    fig, ax = _figure(9, 4.2)
    labels = ["Signed up", "Completed onboarding", "First translation",
              "10+ translations", "Subscribed"]
    colors = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
    y = np.arange(len(funnel))[::-1]
    ax.barh(y, funnel["users"], color=colors, height=0.6)
    for yi, users, pct in zip(y, funnel["users"], funnel["pct_of_signups"]):
        ax.text(users, yi, f"  {users:,}  ({pct:.1%})", va="center", fontsize=9,
                color=TEXT_PRIMARY)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, funnel["users"].max() * 1.25)
    _style(ax, "Activation funnel", "All acquisition channels")
    ax.grid(False)
    ax.set_xticks([])
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_country_conversion(countries: pd.DataFrame, path: Path, top_n: int = 10) -> None:
    """Paid conversion for the largest markets, sorted so the best market is on top."""
    top = countries.nlargest(top_n, "users").sort_values("paid_conversion")
    fig, ax = _figure(9, 4.6)
    ax.barh(top["country"], top["paid_conversion"], color=SERIES["blue"], height=0.6)
    if "paid_ci95_low" in top:
        err = [top["paid_conversion"] - top["paid_ci95_low"],
               top["paid_ci95_high"] - top["paid_conversion"]]
        ax.errorbar(top["paid_conversion"], top["country"], xerr=err, fmt="none",
                    ecolor=TEXT_SECONDARY, elinewidth=1, capsize=3)
        label_x = top["paid_ci95_high"]
    else:
        label_x = top["paid_conversion"]
    for country, x, rate, users in zip(top["country"], label_x, top["paid_conversion"], top["users"]):
        ax.text(x, country, f"  {rate:.1%}  (n={users:,})", va="center", fontsize=9,
                color=TEXT_PRIMARY)
    ax.set_xlim(0, label_x.max() * 1.45)
    _style(ax, f"Paid conversion by country (top {top_n} markets by users)",
           "Whiskers: 95% Wilson confidence interval")
    ax.grid(False)
    ax.set_xticks([])
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_latency(feature_usage: pd.DataFrame, path: Path) -> None:
    fig, ax = _figure()
    names = {"voice_to_text": ("Voice to text", SERIES["blue"]),
             "voice_to_voice": ("Voice to voice", SERIES["orange"])}
    for mode, grp in feature_usage.groupby("mode"):
        label, color = names[mode]
        x = pd.to_datetime(grp["week_start"])
        ax.plot(x, grp["avg_latency_ms"], color=color, linewidth=2, marker="o",
                markersize=4, label=label)
        ax.text(x.iloc[-1], grp["avg_latency_ms"].iloc[-1], f"  {label}",
                color=TEXT_PRIMARY, fontsize=9, va="center")
    ax.axvline(ENGINE_V2_DATE, color=TEXT_SECONDARY, linewidth=1, linestyle="--")
    ax.set_ylim(0, None)
    ax.set_ylabel("ms", color=TEXT_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="lower left", labelcolor=TEXT_PRIMARY)
    _style(ax, "Average translation latency by week", "Dashed line: engine v2 release")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def write_summary(dau, funnel, latency, w1, path: Path) -> None:
    peak = dau.loc[dau["dau"].idxmax()]
    last = dau.iloc[-1]
    stickiness = last["dau"] / last["mau"]
    lines = [
        "# Analysis summary (generated)",
        "",
        "All figures come from the synthetic dataset in this repository.",
        "",
        "## Engagement",
        f"- Peak DAU: {int(peak['dau']):,} on {peak['activity_date']}",
        f"- Stickiness on the last day (DAU/MAU): {stickiness:.1%}",
        "",
        "## Activation funnel",
    ]
    for row in funnel.itertuples():
        lines.append(f"- {row.step}: {row.users:,} users "
                     f"({row.pct_of_signups:.1%} of signups, {row.pct_of_previous:.1%} of previous step)")
    lines += ["", "## Engine v2 latency impact (median, 95% bootstrap CI)"]
    for row in latency.itertuples():
        lines.append(f"- {row.mode}: {row.p50_before_ms} ms -> {row.p50_after_ms} ms "
                     f"({row.median_change_pct:+.1f}%, CI {row.ci95_low_pct:+.1f}% to "
                     f"{row.ci95_high_pct:+.1f}%); success rate "
                     f"{row.success_before:.1%} -> {row.success_after:.1%}")
    lines += ["", "## Week-1 retention, cohorts before vs after engine v2 (observational)"]
    for row in w1.itertuples():
        lines.append(f"- {row.engine}: {row.week1_retention:.1%} "
                     f"({int(row.users):,} users in {int(row.cohorts)} cohorts)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("Database not found. Run `python src/generate_data.py` first.")
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        dau = run_sql(conn, "01_daily_active_users.sql")
        retention = run_sql(conn, "02_weekly_retention_cohorts.sql")
        funnel_by_channel = run_sql(conn, "03_activation_funnel.sql")
        feature_usage = run_sql(conn, "04_feature_usage.sql")
        language_pairs = run_sql(conn, "05_language_pairs.sql")
        countries = run_sql(conn, "06_country_breakdown.sql")
        translations = load_translations(conn)

    dau["stickiness"] = (dau["dau"] / dau["mau"]).round(4)
    paid = (countries["paid_conversion"] * countries["users"]).round()
    low, high = wilson_interval(paid, countries["users"])
    countries["paid_ci95_low"] = low.round(4)
    countries["paid_ci95_high"] = high.round(4)
    cohort_end = pd.to_datetime(retention["cohort_week"]) + pd.Timedelta(days=6)
    days_left = (pd.Timestamp(date(2026, 4, 30)) - cohort_end).dt.days
    retention["is_complete_week"] = retention["week_number"] <= (days_left + 1) // 7 - 1
    funnel = funnel_long(funnel_by_channel)
    latency = latency_impact(translations)
    matrix = retention_matrix(retention)
    w1 = cohort_week1_by_engine(retention)

    tables = {
        "daily_active_users": dau,
        "retention_cohorts": retention,
        "funnel_by_channel": funnel_by_channel,
        "funnel_overall": funnel,
        "feature_usage_weekly": feature_usage,
        "language_pairs_top15": language_pairs,
        "country_breakdown": countries,
        "latency_impact": latency,
        "week1_retention_by_engine": w1,
    }
    for name, df in tables.items():
        df.to_csv(TABLE_DIR / f"{name}.csv", index=False)

    chart_active_users(dau, CHART_DIR / "daily_active_users.png")
    chart_retention_heatmap(matrix, CHART_DIR / "retention_heatmap.png")
    chart_funnel(funnel, CHART_DIR / "activation_funnel.png")
    chart_latency(feature_usage, CHART_DIR / "latency_by_week.png")
    chart_country_conversion(countries, CHART_DIR / "country_conversion.png")
    write_summary(dau, funnel, latency, w1, OUT_DIR / "summary.md")

    print(f"Wrote {len(tables)} tables to {TABLE_DIR.relative_to(ROOT)}")
    print(f"Wrote 5 charts to {CHART_DIR.relative_to(ROOT)}")
    print((OUT_DIR / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
