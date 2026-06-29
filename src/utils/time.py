from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def in_time_windows(ts: pd.Timestamp, windows: list[tuple[str, str]] | list[list[str]]) -> bool:
    current = ts.time()
    for start, end in windows:
        if parse_hhmm(start) <= current <= parse_hhmm(end):
            return True
    return False


DATETIME_FORMATS = (
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


def parse_datetime_series(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    remaining = values.notna() & values.ne("") & values.str.lower().ne("nan")

    for fmt in DATETIME_FORMATS:
        if not remaining.any():
            break
        candidate = pd.to_datetime(values[remaining], format=fmt, errors="coerce")
        parsed.loc[candidate.index] = parsed.loc[candidate.index].fillna(candidate)
        remaining = parsed.isna() & values.ne("") & values.str.lower().ne("nan")

    if remaining.any():
        generic = pd.to_datetime(values[remaining], errors="coerce")
        parsed.loc[generic.index] = parsed.loc[generic.index].fillna(generic)
        remaining = parsed.isna() & values.ne("") & values.str.lower().ne("nan")

    if remaining.any():
        dayfirst = pd.to_datetime(values[remaining], errors="coerce", dayfirst=True)
        parsed.loc[dayfirst.index] = parsed.loc[dayfirst.index].fillna(dayfirst)

    return parsed


def normalize_timezone(series: pd.Series, timezone: str) -> pd.Series:
    dt = parse_datetime_series(series)
    parse_failures = int(dt.isna().sum())
    if parse_failures:
        examples = series[dt.isna()].astype(str).head(5).tolist()
        raise ValueError(
            "Could not parse some datetime values. "
            f"Failures: {parse_failures}. Examples: {examples}. "
            "Expected formats include '2026.01.05 15:30:00', '2026-01-05 15:30', "
            "'05/01/2026 15:30' or separate DATE/TIME MT5 columns."
        )
    if dt.dt.tz is None:
        return dt.dt.tz_localize(ZoneInfo(timezone), nonexistent="shift_forward", ambiguous="NaT")
    return dt.dt.tz_convert(ZoneInfo(timezone))


def session_date(ts: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(ts.date(), tz=ts.tz)
