"""Sanity checks for the data generator, the SQL queries and the statistics."""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analyze  # noqa: E402
import generate_data  # noqa: E402


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data")
    tables = generate_data.build_tables(n_users=400, seed=1)
    db_path = folder / "test.db"
    generate_data.write_outputs(tables, raw_dir=folder / "raw", db_path=db_path)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def test_generator_is_reproducible():
    a = generate_data.build_tables(n_users=100, seed=3)
    b = generate_data.build_tables(n_users=100, seed=3)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_translations_belong_to_known_sessions(db):
    orphans = db.execute("""
        SELECT COUNT(*) FROM translations t
        LEFT JOIN sessions s ON s.session_id = t.session_id
        WHERE s.session_id IS NULL
    """).fetchone()[0]
    assert orphans == 0


def test_no_activity_before_signup(db):
    early = db.execute("""
        SELECT COUNT(*) FROM sessions s JOIN users u ON u.user_id = s.user_id
        WHERE DATE(s.session_start) < u.signup_date
    """).fetchone()[0]
    assert early == 0


def test_active_user_counts_are_nested(db):
    dau = analyze.run_sql(db, "01_daily_active_users.sql")
    assert (dau["dau"] <= dau["wau"]).all()
    assert (dau["wau"] <= dau["mau"]).all()


def test_retention_is_a_rate(db):
    retention = analyze.run_sql(db, "02_weekly_retention_cohorts.sql")
    assert retention["retention_rate"].between(0, 1).all()
    week0 = retention[retention["week_number"] == 0]
    assert (week0["retention_rate"] == 1).all()   # everyone is active in signup week


def test_funnel_never_grows(db):
    funnel = analyze.funnel_long(analyze.run_sql(db, "03_activation_funnel.sql"))
    assert funnel["users"].is_monotonic_decreasing
    assert funnel["users"].iloc[0] == 400


def test_bootstrap_detects_known_change():
    rng = np.random.default_rng(0)
    before = rng.lognormal(np.log(1000), 0.3, 4000)
    after = rng.lognormal(np.log(700), 0.3, 4000)
    change, low, high = analyze.bootstrap_median_diff(before, after, n_boot=300)
    assert low <= change <= high
    assert -0.35 < change < -0.25


def test_country_breakdown_covers_every_user(db):
    countries = analyze.run_sql(db, "06_country_breakdown.sql")
    assert countries["users"].sum() == 400
    assert countries["paid_conversion"].between(0, 1).all()


def test_wilson_interval_contains_the_rate():
    low, high = analyze.wilson_interval(np.array([5, 0]), np.array([100, 20]))
    assert low[0] < 0.05 < high[0]
    assert low[1] >= 0 and high[1] > 0      # zero successes still gives an upper bound
