#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.loader import load_mt5_ohlcv
from src.indicators.atr import atr
from src.utils.config import load_yaml, resolve_asset_spec


@dataclass(frozen=True)
class AssetInput:
    label: str
    symbol: str
    timeframe: str
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run data/config sanity checks before adding new strategies.")
    parser.add_argument("--assets", nargs="+", required=True, metavar="SYMBOL:CSV")
    parser.add_argument("--output", default=str(ROOT / "data/reports/sanity_check.md"))
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--assets-config", default=str(ROOT / "config/assets.yaml"))
    parser.add_argument("--risk-config", default=str(ROOT / "config/risk.yaml"))
    return parser.parse_args()


def _parse_asset_inputs(items: list[str], default_timeframe: str) -> list[AssetInput]:
    assets: list[AssetInput] = []
    for item in items:
        if ":" not in item:
            raise ValueError(f"Invalid asset spec '{item}'. Expected SYMBOL:path/to/file.csv.")
        label, raw_path = item.split(":", 1)
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = ROOT / path
        label_upper = label.strip().upper()
        symbol = label_upper
        timeframe = default_timeframe.upper()
        label_match = re.fullmatch(r"(.+)_(M\d+|H\d+|D\d+)", label_upper)
        if label_match:
            symbol = label_match.group(1)
            timeframe = label_match.group(2)
        else:
            path_match = re.fullmatch(r"(.+)_(M\d+|H\d+|D\d+)", path.stem.upper())
            if path_match:
                timeframe = path_match.group(2)
        assets.append(AssetInput(label=label_upper, symbol=symbol, timeframe=timeframe, path=path))
    return assets


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _stats(series: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {"mean": 0.0, "min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "mean": float(clean.mean()),
        "min": float(clean.min()),
        "p25": float(clean.quantile(0.25)),
        "median": float(clean.quantile(0.50)),
        "p75": float(clean.quantile(0.75)),
        "p95": float(clean.quantile(0.95)),
        "p99": float(clean.quantile(0.99)),
        "max": float(clean.max()),
    }


def _fmt(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number) or math.isinf(number):
        return ""
    return f"{number:.{decimals}f}"


def _session_count(data: pd.DataFrame, start: str, end: str) -> int:
    times = data.index.time
    start_t = pd.Timestamp(start).time()
    end_t = pd.Timestamp(end).time()
    return int(((times >= start_t) & (times <= end_t)).sum())


def _hour_summary(data: pd.DataFrame) -> str:
    if data.empty:
        return ""
    counts = data.groupby(data.index.hour).size()
    active = counts[counts > 0]
    if active.empty:
        return ""
    return f"{int(active.index.min()):02d}:00-{int(active.index.max()):02d}:59"


def _verdict(issues: list[str], warnings: list[str]) -> str:
    if issues:
        return "CONFIG À CORRIGER"
    if warnings:
        return "DATA SUSPECTE"
    return "DATA OK"


def _analyze_asset(asset: AssetInput, assets_config: dict[str, Any], risk_config: dict[str, Any], timezone: str) -> dict[str, Any]:
    spec = resolve_asset_spec(assets_config, asset.symbol)
    data, cleaning = load_mt5_ohlcv(asset.path, timezone=timezone, timeframe=asset.timeframe)
    if data.empty:
        raise ValueError(f"No data loaded for {asset.label}: {asset.path}")

    spread_points = pd.to_numeric(data["spread"], errors="coerce") if "spread" in data.columns else pd.Series(dtype=float)
    spread_stats = _stats(spread_points)
    spread_price = spread_points * spec.point if len(spread_points) else pd.Series(dtype=float)
    spread_price_stats = _stats(spread_price)
    ranges = data["high"].astype(float) - data["low"].astype(float)
    range_stats = _stats(ranges)
    atr_values = atr(data, 14)
    atr_stats = _stats(atr_values)
    zero_range = int((ranges <= 0).sum())
    q1 = ranges.quantile(0.25)
    q3 = ranges.quantile(0.75)
    iqr = q3 - q1
    extreme_threshold = q3 + 5 * iqr if iqr > 0 else ranges.quantile(0.999)
    extreme_candles = int((ranges > extreme_threshold).sum())
    rows = len(data)
    zero_range_pct = zero_range / rows * 100
    extreme_pct = extreme_candles / rows * 100

    costs = risk_config.get("costs", {})
    slippage_points = float(costs.get("slippage_points", 0.0))
    commission = float(costs.get("commission_per_lot_round_turn", 0.0))
    observed_spread = spread_stats["mean"] if len(spread_points.dropna()) else float(assets_config["assets"][spec.symbol].get("default_spread_points", 0.0))
    round_trip_cost_points = observed_spread + 2 * slippage_points
    round_trip_cost_price = round_trip_cost_points * spec.point
    round_trip_cost_dollars = round_trip_cost_price * spec.contract_size + commission
    avg_range_price = range_stats["mean"]
    cost_vs_avg_range_pct = round_trip_cost_price / avg_range_price * 100 if avg_range_price > 0 else 0.0
    default_spread = float(assets_config["assets"][spec.symbol].get("default_spread_points", observed_spread))
    spread_default_delta_pct = abs(observed_spread - default_spread) / default_spread * 100 if default_spread > 0 else 0.0

    issues: list[str] = []
    warnings: list[str] = []
    if spec.point <= 0:
        issues.append("point_size_invalid")
    if not len(spread_points.dropna()):
        warnings.append("spread_missing")
    if spread_default_delta_pct > 80:
        issues.append("observed_spread_far_from_config_default")
    if zero_range_pct > 2:
        warnings.append("many_zero_range_candles")
    if extreme_pct > 1:
        warnings.append("many_extreme_candles")
    if cost_vs_avg_range_pct > 35:
        warnings.append("transaction_cost_large_vs_average_candle_range")
    if cleaning.rows_out < 1000:
        warnings.append("short_history")

    return {
        "asset": asset.label,
        "base_asset": spec.symbol,
        "timeframe": asset.timeframe,
        "file": str(asset.path),
        "start": cleaning.first_timestamp,
        "end": cleaning.last_timestamp,
        "rows": rows,
        "timezone": str(data.index.tz),
        "missing_bars": cleaning.missing_bars,
        "point_size": spec.point,
        "contract_size": spec.contract_size,
        "spread_points_mean": spread_stats["mean"],
        "spread_points_min": spread_stats["min"],
        "spread_points_max": spread_stats["max"],
        "spread_price_mean": spread_price_stats["mean"],
        "spread_price_min": spread_price_stats["min"],
        "spread_price_max": spread_price_stats["max"],
        "spread_default_points": default_spread,
        "spread_default_delta_pct": spread_default_delta_pct,
        "spread_coherence": "OK" if spec.point > 0 and spread_price_stats["mean"] >= 0 else "CHECK",
        "round_trip_cost_points": round_trip_cost_points,
        "round_trip_cost_price": round_trip_cost_price,
        "round_trip_cost_dollars_per_lot": round_trip_cost_dollars,
        "cost_vs_avg_range_pct": cost_vs_avg_range_pct,
        "trading_hours": _hour_summary(data),
        "london_candles": _session_count(data, "08:00", "10:00"),
        "us_open_candles": _session_count(data, "15:30", "17:00"),
        "zero_range_candles": zero_range,
        "zero_range_pct": zero_range_pct,
        "extreme_candles": extreme_candles,
        "extreme_threshold": float(extreme_threshold),
        "extreme_pct": extreme_pct,
        "range_mean": range_stats["mean"],
        "range_median": range_stats["median"],
        "range_p95": range_stats["p95"],
        "range_p99": range_stats["p99"],
        "atr_mean": atr_stats["mean"],
        "atr_median": atr_stats["median"],
        "atr_p95": atr_stats["p95"],
        "atr_p99": atr_stats["p99"],
        "issues": ";".join(issues),
        "warnings": ";".join(warnings),
        "verdict": _verdict(issues, warnings),
    }


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_Aucun résultat._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame[columns].iterrows():
        values: list[str] = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(_fmt(value, 4 if "price" in column or column == "point_size" else 2))
            else:
                values.append("" if pd.isna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _build_report(frame: pd.DataFrame, output_csv: Path) -> str:
    summary_columns = [
        "asset",
        "timeframe",
        "rows",
        "start",
        "end",
        "timezone",
        "spread_points_mean",
        "spread_price_mean",
        "point_size",
        "round_trip_cost_dollars_per_lot",
        "cost_vs_avg_range_pct",
        "verdict",
        "issues",
        "warnings",
    ]
    distribution_columns = [
        "asset",
        "range_mean",
        "range_median",
        "range_p95",
        "range_p99",
        "atr_mean",
        "atr_median",
        "atr_p95",
        "atr_p99",
        "zero_range_candles",
        "extreme_candles",
    ]
    session_columns = ["asset", "trading_hours", "london_candles", "us_open_candles", "missing_bars"]
    return f"""# Sanity Check V1.6

## Résumé

Résultats CSV: `{output_csv}`

{_markdown_table(frame, summary_columns)}

## Horaires Et Sessions

{_markdown_table(frame, session_columns)}

## Ranges Et ATR

{_markdown_table(frame, distribution_columns)}

## Test De Coût De Transaction

Le coût simule une entrée/sortie immédiate avec spread moyen observé, deux slippages et commission round turn par lot.

{_markdown_table(frame, ["asset", "spread_points_mean", "round_trip_cost_points", "round_trip_cost_price", "round_trip_cost_dollars_per_lot", "range_mean", "cost_vs_avg_range_pct"])}
"""


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output_csv = output.with_suffix(".csv")
    assets_config = load_yaml(args.assets_config)
    risk_config = load_yaml(args.risk_config)
    rows = [_analyze_asset(asset, assets_config, risk_config, args.timezone) for asset in _parse_asset_inputs(args.assets, args.timeframe)]
    frame = pd.DataFrame(rows)
    frame.to_csv(output_csv, index=False)
    output.write_text(_build_report(frame, output_csv), encoding="utf-8")
    print(f"Sanity check report: {output}")
    print(f"Sanity check CSV: {output_csv}")
    print(frame[["asset", "rows", "spread_points_mean", "round_trip_cost_dollars_per_lot", "cost_vs_avg_range_pct", "verdict", "issues", "warnings"]].to_string(index=False))


if __name__ == "__main__":
    main()
