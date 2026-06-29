from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.cleaner import TIMEFRAME_TO_PANDAS, clean_ohlcv
from src.data.mt5_export_parser import read_mt5_csv


@dataclass(frozen=True)
class GapInfo:
    start: str
    end: str
    missing_bars: int


@dataclass(frozen=True)
class DataDiagnostics:
    path: str
    timeframe: str
    timezone: str
    period_start: str | None
    period_end: str | None
    raw_rows: int
    clean_rows: int
    duplicates: int
    missing_values: dict[str, int]
    temporal_gaps: int
    largest_gaps: list[GapInfo]
    abnormal_candles: dict[str, int]
    spread_mean: float | None
    spread_min: float | None
    spread_max: float | None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["largest_gaps"] = [asdict(gap) for gap in self.largest_gaps]
        return out


def _gap_report(data: pd.DataFrame, timeframe: str, limit: int = 10) -> tuple[int, list[GapInfo]]:
    freq = TIMEFRAME_TO_PANDAS.get(timeframe.upper())
    if not freq or len(data) < 2:
        return 0, []

    expected_delta = pd.Timedelta(freq)
    diffs = data.index.to_series().diff().dropna()
    gaps = diffs[diffs > expected_delta]
    infos: list[GapInfo] = []
    total_missing = 0
    for end_ts, delta in gaps.sort_values(ascending=False).head(limit).items():
        missing = max(0, int(delta / expected_delta) - 1)
        total_missing += missing
        start_ts = data.index[data.index.get_loc(end_ts) - 1]
        infos.append(GapInfo(start=str(start_ts), end=str(end_ts), missing_bars=missing))

    if len(gaps) > limit:
        for delta in gaps.sort_values(ascending=False).iloc[limit:]:
            total_missing += max(0, int(delta / expected_delta) - 1)

    return total_missing, infos


def _abnormal_candles(data: pd.DataFrame) -> dict[str, int]:
    if data.empty:
        return {
            "invalid_ohlc": 0,
            "non_positive_prices": 0,
            "zero_range": 0,
            "extreme_range": 0,
        }

    invalid_ohlc = (
        (data["high"] < data[["open", "close"]].max(axis=1))
        | (data["low"] > data[["open", "close"]].min(axis=1))
        | (data["high"] < data["low"])
    )
    non_positive = (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
    candle_range = data["high"] - data["low"]
    zero_range = candle_range <= 0
    median_range = candle_range[candle_range > 0].median()
    if pd.isna(median_range) or median_range <= 0:
        extreme_range = pd.Series(False, index=data.index)
    else:
        extreme_range = candle_range > median_range * 10

    return {
        "invalid_ohlc": int(invalid_ohlc.sum()),
        "non_positive_prices": int(non_positive.sum()),
        "zero_range": int(zero_range.sum()),
        "extreme_range": int(extreme_range.sum()),
    }


def diagnose_csv(path: str | Path, timezone: str = "Europe/Paris", timeframe: str = "M15") -> DataDiagnostics:
    raw = read_mt5_csv(path)
    missing_values = {column: int(raw[column].isna().sum()) for column in raw.columns}
    clean, cleaning = clean_ohlcv(raw, timezone=timezone, timeframe=timeframe)
    gaps, largest_gaps = _gap_report(clean, timeframe)
    spread = clean["spread"].dropna() if "spread" in clean.columns else pd.Series(dtype=float)
    return DataDiagnostics(
        path=str(path),
        timeframe=timeframe,
        timezone=timezone,
        period_start=cleaning.first_timestamp,
        period_end=cleaning.last_timestamp,
        raw_rows=cleaning.rows_in,
        clean_rows=cleaning.rows_out,
        duplicates=cleaning.duplicates_removed,
        missing_values=missing_values,
        temporal_gaps=gaps,
        largest_gaps=largest_gaps,
        abnormal_candles=_abnormal_candles(clean),
        spread_mean=float(spread.mean()) if len(spread) else None,
        spread_min=float(spread.min()) if len(spread) else None,
        spread_max=float(spread.max()) if len(spread) else None,
    )


def diagnostics_markdown(report: DataDiagnostics) -> str:
    lines = [
        "# Data Diagnostics",
        "",
        f"- File: `{report.path}`",
        f"- Timeframe: `{report.timeframe}`",
        f"- Timezone: `{report.timezone}`",
        f"- Period: `{report.period_start}` -> `{report.period_end}`",
        f"- Raw rows: `{report.raw_rows}`",
        f"- Clean rows: `{report.clean_rows}`",
        f"- Duplicates removed: `{report.duplicates}`",
        f"- Temporal gaps / missing bars: `{report.temporal_gaps}`",
        "",
        "## Missing Values",
        "",
        "| Column | Missing |",
        "| --- | ---: |",
    ]
    for column, count in report.missing_values.items():
        lines.append(f"| {column} | {count} |")

    lines.extend(["", "## Abnormal Candles", "", "| Check | Count |", "| --- | ---: |"])
    for key, value in report.abnormal_candles.items():
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Spread",
            "",
            f"- Mean: `{report.spread_mean}`",
            f"- Min: `{report.spread_min}`",
            f"- Max: `{report.spread_max}`",
            "",
            "## Largest Gaps",
            "",
            "| From | To | Missing bars |",
            "| --- | --- | ---: |",
        ]
    )
    if report.largest_gaps:
        for gap in report.largest_gaps:
            lines.append(f"| {gap.start} | {gap.end} | {gap.missing_bars} |")
    else:
        lines.append("| none | none | 0 |")
    return "\n".join(lines) + "\n"
