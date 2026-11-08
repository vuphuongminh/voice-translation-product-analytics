"""
Generate a synthetic dataset for a fictional voice translation app ("TalkBridge").

All data is randomly generated. It does not come from, and does not describe,
any real company, product or user.

Tables produced:
    users          one row per user (signup date, country, platform, channel)
    sessions       one row per app session
    translations   one row per translation request (mode, languages, latency)
    subscriptions  one row per paid subscription start
    releases       app engine releases (used for before/after analysis)

Usage:
    python src/generate_data.py --users 5000 --seed 42
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "talkbridge.db"

START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 4, 30)          # last day of observed activity
ENGINE_V2_DATE = date(2026, 3, 1)     # fictional release: faster speech engine

COUNTRIES = {
    "VN": 0.22, "US": 0.12, "KR": 0.09, "JP": 0.08, "FR": 0.06, "DE": 0.05,
    "TH": 0.05, "ID": 0.05, "PH": 0.04, "GB": 0.04, "AU": 0.03, "CA": 0.03,
    "SG": 0.03, "IN": 0.03, "BR": 0.02, "ES": 0.02, "IT": 0.02, "MX": 0.02,
}
LANGUAGES = ["vi", "en", "ko", "ja", "fr", "de", "th", "id", "zh", "es"]
HOME_LANGUAGE = {
    "VN": "vi", "US": "en", "KR": "ko", "JP": "ja", "FR": "fr", "DE": "de",
    "TH": "th", "ID": "id", "PH": "en", "GB": "en", "AU": "en", "CA": "en",
    "SG": "en", "IN": "en", "BR": "es", "ES": "es", "IT": "en", "MX": "es",
}
CHANNELS = {"organic_search": 0.35, "app_store_feature": 0.25,
            "social_ads": 0.25, "referral": 0.15}
# channel effect on how engaged a user tends to be
CHANNEL_ENGAGEMENT = {"organic_search": 1.0, "app_store_feature": 0.9,
                      "social_ads": 0.7, "referral": 1.3}


def _choice(rng: np.random.Generator, weights: dict, size: int) -> np.ndarray:
    keys = list(weights)
    p = np.array(list(weights.values()), dtype=float)
    return rng.choice(keys, size=size, p=p / p.sum())


def make_users(rng: np.random.Generator, n_users: int) -> pd.DataFrame:
    n_days = (END_DATE - START_DATE).days + 1
    # signups grow over time (simple linear ramp)
    day_weights = np.linspace(1.0, 2.5, n_days)
    signup_offsets = rng.choice(n_days, size=n_users, p=day_weights / day_weights.sum())

    users = pd.DataFrame({
        "user_id": np.arange(1, n_users + 1),
        "signup_date": [START_DATE + timedelta(days=int(d)) for d in signup_offsets],
        "country": _choice(rng, COUNTRIES, n_users),
        "platform": rng.choice(["ios", "android"], size=n_users, p=[0.55, 0.45]),
        "channel": _choice(rng, CHANNELS, n_users),
    })
    users["onboarding_completed"] = rng.random(n_users) < 0.78
    return users.sort_values(["signup_date", "user_id"]).reset_index(drop=True)


def make_activity(rng: np.random.Generator, users: pd.DataFrame):
    sessions, translations, subscriptions = [], [], []
    session_id = 0
    translation_id = 0

    for u in users.itertuples(index=False):
        if not u.onboarding_completed:
            # users who drop during onboarding still have one session
            session_id += 1
            sessions.append((session_id, u.user_id,
                             datetime.combine(u.signup_date, datetime.min.time())
                             + timedelta(hours=int(rng.integers(7, 23))),
                             int(rng.integers(20, 120))))
            continue

        engagement = rng.gamma(shape=2.0, scale=0.5) * CHANNEL_ENGAGEMENT[u.channel]
        base_p = min(0.6, 0.18 * engagement)
        decay = rng.uniform(0.02, 0.08)       # how fast the user churns
        home = HOME_LANGUAGE[u.country]
        paid = False
        never_translates = rng.random() < 0.12
        if never_translates:
            base_p *= 0.3                     # and they rarely come back

        day = u.signup_date
        while day <= END_DATE:
            age = (day - u.signup_date).days
            p_active = 1.0 if age == 0 else base_p * np.exp(-decay * age) + 0.01
            # users active after the faster engine shipped churn a little less
            if day >= ENGINE_V2_DATE:
                p_active *= 1.12
            if rng.random() < min(p_active, 1.0):
                for _ in range(1 + rng.poisson(0.4)):
                    session_id += 1
                    start = datetime.combine(day, datetime.min.time()) + timedelta(
                        hours=int(rng.integers(6, 24)), minutes=int(rng.integers(0, 60)))
                    duration = int(rng.gamma(2.0, 90))
                    sessions.append((session_id, u.user_id, start, duration))

                    # some users open the app but never try a translation
                    if never_translates:
                        n_translations = 0
                    else:
                        n_translations = rng.poisson(2.5 * engagement) + 1
                    for _ in range(n_translations):
                        translation_id += 1
                        mode = "voice_to_voice" if rng.random() < 0.45 else "voice_to_text"
                        target = rng.choice([l for l in LANGUAGES if l != home])
                        base_latency = 1400 if mode == "voice_to_voice" else 900
                        if day >= ENGINE_V2_DATE:
                            base_latency *= 0.7    # ~30% faster on engine v2
                        latency = int(rng.lognormal(np.log(base_latency), 0.35))
                        success = rng.random() < (0.96 if day >= ENGINE_V2_DATE else 0.93)
                        translations.append((
                            translation_id, session_id, u.user_id,
                            start + timedelta(seconds=int(rng.integers(0, max(duration, 1)))),
                            mode, home, target, latency, success))

                if not paid and not never_translates and age >= 2 and rng.random() < 0.015 * engagement:
                    paid = True
                    plan = "annual" if rng.random() < 0.3 else "monthly"
                    subscriptions.append((len(subscriptions) + 1, u.user_id, day, plan,
                                          49.99 if plan == "annual" else 5.99))
            day += timedelta(days=1)

    sessions_df = pd.DataFrame(sessions, columns=[
        "session_id", "user_id", "session_start", "duration_sec"])
    translations_df = pd.DataFrame(translations, columns=[
        "translation_id", "session_id", "user_id", "requested_at", "mode",
        "source_lang", "target_lang", "latency_ms", "success"])
    subs_df = pd.DataFrame(subscriptions, columns=[
        "subscription_id", "user_id", "start_date", "plan", "price_usd"])
    return sessions_df, translations_df, subs_df


def make_releases() -> pd.DataFrame:
    return pd.DataFrame({
        "release_id": [1, 2],
        "version": ["engine-v1", "engine-v2"],
        "release_date": [START_DATE, ENGINE_V2_DATE],
        "notes": ["Baseline speech engine", "Streaming speech engine with context cache"],
    })


def build_tables(n_users: int, seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    users = make_users(rng, n_users)
    sessions, translations, subs = make_activity(rng, users)
    return {"users": users, "sessions": sessions, "translations": translations,
            "subscriptions": subs, "releases": make_releases()}


def write_outputs(tables: dict[str, pd.DataFrame], raw_dir: Path = RAW_DIR,
                  db_path: Path = DB_PATH) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        for name, df in tables.items():
            df.to_csv(raw_dir / f"{name}.csv", index=False)
            out = df.copy()
            for col in out.columns:
                series = out[col]
                if pd.api.types.is_datetime64_any_dtype(series):
                    out[col] = series.dt.strftime("%Y-%m-%d %H:%M:%S")
                elif pd.api.types.is_bool_dtype(series):
                    out[col] = series.astype(int)
                elif len(series) and isinstance(series.iloc[0], date):
                    out[col] = series.astype(str)
            out.to_sql(name, conn, index=False)
        conn.executescript("""
            CREATE INDEX idx_sessions_user ON sessions(user_id);
            CREATE INDEX idx_translations_user ON translations(user_id);
            CREATE INDEX idx_translations_time ON translations(requested_at);
        """)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--users", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    tables = build_tables(args.users, args.seed)
    write_outputs(tables)
    for name, df in tables.items():
        print(f"{name:<14} {len(df):>8,} rows")
    print(f"SQLite database written to {DB_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
