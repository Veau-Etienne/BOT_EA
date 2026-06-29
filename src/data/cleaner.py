from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.utils.time import normalize_timezone


@dataclass(frozen=True)
class CleaningReport:
    rows_in: int
    rows_out: int
    duplicates_removed: int
    missing_bars: int
    first_timestamp: str | None
    last_timestamp: str | None
    spread_mean: float | None = None
    spread_min: float | None = None
    spread_max: float | None = None


TIMEFRAME_TO_PANDAS = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


def clean_ohlcv(df: pd.DataFrame, timezone: str = "Europe/Paris", timeframe: str = "M15") -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    out = df.copy()
    out["time"] = normalize_timezone(out["time"], timezone)
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    for col in ["open", "high", "low", "close", "tick_volume", "volume", "spread"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out.sort_values("time")
    before_dupes = len(out)
    out = out.drop_duplicates(subset=["time"], keep="last")
    duplicates_removed = before_dupes - len(out)
    out = out.set_index("time")

    freq = TIMEFRAME_TO_PANDAS.get(timeframe.upper())
    missing_bars = 0
    if freq and len(out) > 1:
        expected = pd.date_range(out.index.min(), out.index.max(), freq=freq)
        missing_bars = int(len(expected.difference(out.index)))

    out = out[["open", "high", "low", "close"] + [c for c in ["tick_volume", "volume", "spread"] if c in out.columns]]
    spread = out["spread"].dropna() if "spread" in out.columns else pd.Series(dtype=float)
    report = CleaningReport(
        rows_in=rows_in,
        rows_out=len(out),
        duplicates_removed=duplicates_removed,
        missing_bars=missing_bars,
        first_timestamp=str(out.index.min()) if len(out) else None,
        last_timestamp=str(out.index.max()) if len(out) else None,
        spread_mean=float(spread.mean()) if len(spread) else None,
        spread_min=float(spread.min()) if len(spread) else None,
        spread_max=float(spread.max()) if len(spread) else None,
    )
    return out, report
