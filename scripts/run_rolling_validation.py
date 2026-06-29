#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_metrics
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rolling-window validation for a strategy.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--window-months", type=int, default=6)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--timezone", default="Europe/Paris")
    return parser.parse_args()


def _fmt(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return ""
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return f"{number:.{decimals}f}"


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = ["window_months", "start", "end", "trades", "profit_factor", "expectancy", "max_drawdown", "net_profit", "result"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame[columns].iterrows():
        values = []
        for column in columns:
            value = row[column]
            if pd.api.types.is_number(value):
                values.append(str(int(value)) if column in {"window_months", "trades"} else _fmt(value, 3 if column == "profit_factor" else 2))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _run_windows(data: pd.DataFrame, strategy_name: str, strategy_cfg: dict[str, Any], backtest_cfg, asset_spec, window_months: int, step_months: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    start = data.index.min().tz_localize(None).to_period("M").to_timestamp()
    last = data.index.max().tz_localize(None).to_period("M").to_timestamp()
    current = start
    while current <= last:
        end = current + pd.DateOffset(months=window_months) - pd.Timedelta(hours=1)
        if end > data.index.max().tz_localize(None):
            break
        start_ts = pd.Timestamp(current, tz=data.index.tz)
        end_ts = pd.Timestamp(end, tz=data.index.tz)
        sample = data[(data.index >= start_ts) & (data.index <= end_ts)]
        result = BacktestEngine(backtest_cfg, asset_spec).run(sample, STRATEGY_REGISTRY[strategy_name](strategy_cfg))
        metrics = calculate_metrics(result.trades, result.equity_curve, backtest_cfg.initial_capital)
        positive = metrics["profit_factor"] >= 1.0 and metrics["expectancy"] >= 0 and metrics["trade_count"] >= 10
        rows.append(
            {
                "window_months": window_months,
                "start": str(start_ts.date()),
                "end": str(end_ts.date()),
                "trades": metrics["trade_count"],
                "profit_factor": metrics["profit_factor"],
                "expectancy": metrics["expectancy"],
                "max_drawdown": metrics["max_drawdown_pct"],
                "net_profit": metrics["net_profit"],
                "result": "positive" if positive else "negative",
            }
        )
        current = current + pd.DateOffset(months=step_months)
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output_csv = output.with_suffix(".csv")
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    strategy_cfg = strategy_config(strategies_cfg, args.strategy)
    asset_spec = resolve_asset_spec(assets_cfg, strategy_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strategy_cfg)
    data, cleaning = load_mt5_ohlcv(data_path, timezone=args.timezone, timeframe=args.timeframe)
    frames = [
        _run_windows(data, args.strategy, strategy_cfg, backtest_cfg, asset_spec, args.window_months, args.step_months),
        _run_windows(data, args.strategy, strategy_cfg, backtest_cfg, asset_spec, 12, args.step_months),
    ]
    frame = pd.concat([item for item in frames if not item.empty], ignore_index=True)
    frame.to_csv(output_csv, index=False)
    positives = int((frame["result"] == "positive").sum()) if not frame.empty else 0
    total = len(frame)
    verdict = "majoritairement_positive" if total and positives / total >= 0.6 else "fragile"
    report = f"""# Rolling Validation - {args.strategy}

## Résumé

- Data: `{args.data}`
- Période: {cleaning.first_timestamp} -> {cleaning.last_timestamp}
- Fenêtres: {total}
- Fenêtres positives: {positives}
- Verdict rolling: {verdict}
- CSV: `{output_csv}`

{_markdown_table(frame)}
"""
    output.write_text(report, encoding="utf-8")
    print(f"Rolling report: {output}")
    print(f"Rolling CSV: {output_csv}")
    print(f"Windows: {total} | Positive: {positives} | Verdict: {verdict}")
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
