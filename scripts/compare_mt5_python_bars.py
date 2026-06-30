#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.loader import load_mt5_ohlcv
from src.indicators.atr import atr
from src.indicators.ema import ema


OHLC_COLUMNS = ["open", "high", "low", "close"]
INDICATOR_COLUMNS = ["ema_fast", "ema_slow", "ema200", "atr"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Python H1 bars with MT5 Strategy Tester H1 bars and indicators.")
    parser.add_argument("--python-bars", required=True)
    parser.add_argument("--mt5-bars", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--point-size", type=float, default=0.01)
    parser.add_argument("--price-tolerance-points", type=float, default=1.0)
    parser.add_argument("--indicator-tolerance-points", type=float, default=5.0)
    parser.add_argument("--timezone", default="Europe/Paris")
    return parser.parse_args()


def _naive_index(index: pd.Index) -> pd.DatetimeIndex:
    ts = pd.to_datetime(index)
    if getattr(ts, "tz", None) is not None:
        return ts.tz_localize(None)
    return pd.DatetimeIndex(ts)


def _prepare_python(path: Path, timezone: str) -> pd.DataFrame:
    data, _ = load_mt5_ohlcv(path, timezone=timezone, timeframe="H1")
    out = data.copy()
    out.index = _naive_index(out.index)
    out["ema_fast"] = ema(out["close"], 20)
    out["ema_slow"] = ema(out["close"], 50)
    out["ema200"] = ema(out["close"], 200)
    out["atr"] = atr(out, 14)
    return out


def _prepare_mt5(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    required = {"timestamp", *OHLC_COLUMNS}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"CSV MT5 colonnes manquantes: {missing}")
    out = data.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="raise")
    for column in [*OHLC_COLUMNS, "tick_volume", "spread", *INDICATOR_COLUMNS]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.drop_duplicates("timestamp", keep="last").sort_values("timestamp").set_index("timestamp")
    out.index = _naive_index(out.index)
    return out


def _diff_stats(joined: pd.DataFrame, columns: list[str], point_size: float) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for column in columns:
        left = f"{column}_python"
        right = f"{column}_mt5"
        if left not in joined or right not in joined:
            continue
        diff = (joined[left] - joined[right]).abs() / point_size
        diff = diff.dropna()
        rows.append(
            {
                "field": column,
                "mean_points": float(diff.mean()) if len(diff) else 0.0,
                "max_points": float(diff.max()) if len(diff) else 0.0,
                "count_gt_1": int((diff > 1.0).sum()) if len(diff) else 0,
                "count_gt_5": int((diff > 5.0).sum()) if len(diff) else 0,
            }
        )
    return rows


def _table(rows: list[dict[str, object]], columns: list[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def _preview_timestamps(values: list[pd.Timestamp]) -> list[str]:
    if not values:
        return ["Aucun."]
    return [f"- {value}" for value in values[:20]]


def _divergence_preview(joined: pd.DataFrame, point_size: float, tolerance_points: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if joined.empty:
        return rows
    diffs = pd.DataFrame(index=joined.index)
    for column in OHLC_COLUMNS:
        diffs[column] = (joined[f"{column}_python"] - joined[f"{column}_mt5"]).abs() / point_size
    mask = diffs.max(axis=1) > tolerance_points
    for ts, row in joined.loc[mask].head(20).iterrows():
        rows.append(
            {
                "timestamp": ts,
                "max_ohlc_diff_points": f"{float(diffs.loc[ts].max()):.2f}",
                "open_py": f"{row['open_python']:.2f}",
                "open_mt5": f"{row['open_mt5']:.2f}",
                "close_py": f"{row['close_python']:.2f}",
                "close_mt5": f"{row['close_mt5']:.2f}",
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    py = _prepare_python(Path(args.python_bars), args.timezone)
    mt5 = _prepare_mt5(Path(args.mt5_bars))
    joined = py.merge(mt5, left_index=True, right_index=True, how="inner", suffixes=("_python", "_mt5"))

    py_times = set(py.index)
    mt5_times = set(mt5.index)
    missing_python = sorted(mt5_times - py_times)
    missing_mt5 = sorted(py_times - mt5_times)

    price_stats = _diff_stats(joined, OHLC_COLUMNS, args.point_size)
    spread_stats = _diff_stats(joined, ["spread"], 1.0)
    indicator_stats = _diff_stats(joined, INDICATOR_COLUMNS, args.point_size)

    price_fail_count = sum(int(row["count_gt_1"]) for row in price_stats)
    indicator_fail_count = 0
    for column in INDICATOR_COLUMNS:
        left = f"{column}_python"
        right = f"{column}_mt5"
        if left in joined and right in joined:
            diff = (joined[left] - joined[right]).abs() / args.point_size
            indicator_fail_count += int((diff > args.indicator_tolerance_points).sum())

    if missing_python or missing_mt5 or price_fail_count > max(10, 0.01 * len(joined)):
        verdict = "BAR_PARITY_FAIL"
    elif indicator_fail_count > max(10, 0.05 * len(joined)):
        verdict = "BAR_PARITY_WARNING"
    else:
        verdict = "BAR_PARITY_OK"

    monthly = []
    if not joined.empty:
        max_diff = pd.DataFrame(index=joined.index)
        for column in OHLC_COLUMNS:
            max_diff[column] = (joined[f"{column}_python"] - joined[f"{column}_mt5"]).abs() / args.point_size
        significant = max_diff.max(axis=1) > args.price_tolerance_points
        if significant.any():
            counts = significant[significant].groupby(significant[significant].index.to_period("M")).size().sort_values(ascending=False)
            monthly = [{"period": str(period), "significant_ohlc_diffs": int(count)} for period, count in counts.head(12).items()]

    lines = [
        "# Python / MT5 Bar Parity",
        "",
        f"- Verdict : {verdict}",
        f"- Bougies Python : {len(py)}",
        f"- Bougies MT5 : {len(mt5)}",
        f"- Timestamps communs : {len(joined)}",
        f"- Timestamps manquants Python : {len(missing_python)}",
        f"- Timestamps manquants MT5 : {len(missing_mt5)}",
        f"- Tolérance prix : {args.price_tolerance_points:.2f} points",
        f"- Tolérance indicateurs : {args.indicator_tolerance_points:.2f} points",
        "",
        "## Écarts OHLC",
        "",
        *_table(price_stats, ["field", "mean_points", "max_points", "count_gt_1", "count_gt_5"]),
        "",
        "## Écarts Spread",
        "",
        *(_table(spread_stats, ["field", "mean_points", "max_points", "count_gt_1", "count_gt_5"]) if spread_stats else ["Spread indisponible dans un des datasets."]),
        "",
        "## Écarts Indicateurs",
        "",
        *_table(indicator_stats, ["field", "mean_points", "max_points", "count_gt_1", "count_gt_5"]),
        "",
        "## Premiers Timestamps Manquants Python",
        "",
        *_preview_timestamps(missing_python),
        "",
        "## Premiers Timestamps Manquants MT5",
        "",
        *_preview_timestamps(missing_mt5),
        "",
        "## Premières Divergences OHLC Significatives",
        "",
    ]
    preview = _divergence_preview(joined, args.point_size, args.price_tolerance_points)
    lines.extend(_table(preview, ["timestamp", "max_ohlc_diff_points", "open_py", "open_mt5", "close_py", "close_mt5"]) if preview else ["Aucune."])
    lines.extend(["", "## Concentration Mensuelle Des Divergences", ""])
    lines.extend(_table(monthly, ["period", "significant_ohlc_diffs"]) if monthly else ["Aucune concentration significative."])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Verdict: {verdict}")
    print(f"Python bars: {len(py)}")
    print(f"MT5 bars: {len(mt5)}")
    print(f"Common timestamps: {len(joined)}")
    print(f"Missing Python: {len(missing_python)}")
    print(f"Missing MT5: {len(missing_mt5)}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
