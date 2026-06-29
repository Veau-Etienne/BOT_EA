from __future__ import annotations

from pathlib import Path

import pandas as pd


TIMEFRAME_TO_PANDAS = {
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


def resample_ohlcv(data: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = TIMEFRAME_TO_PANDAS.get(timeframe.upper())
    if rule is None:
        raise ValueError(f"Unsupported target timeframe '{timeframe}'. Supported: {sorted(TIMEFRAME_TO_PANDAS)}")
    if data.empty:
        return data.copy()

    aggregations: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "tick_volume" in data.columns:
        aggregations["tick_volume"] = "sum"
    if "volume" in data.columns:
        aggregations["volume"] = "sum"
    if "spread" in data.columns:
        aggregations["spread"] = "mean"

    out = data.resample(rule, label="left", closed="left").agg(aggregations)
    out = out.dropna(subset=["open", "high", "low", "close"])
    ordered = ["open", "high", "low", "close", *[col for col in ["tick_volume", "volume", "spread"] if col in out.columns]]
    return out[ordered]


def write_ohlcv_csv(data: pd.DataFrame, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = data.reset_index()
    first_column = out.columns[0]
    if first_column != "time":
        out = out.rename(columns={first_column: "time"})
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(path, index=False)
