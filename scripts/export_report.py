#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.metrics import calculate_metrics
from src.backtest.monte_carlo import run_monte_carlo
from src.backtest.reporting import build_backtest_report, write_backtest_report
from src.backtest.validation import validate_strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a markdown report from backtest CSV outputs.")
    parser.add_argument("--trades", required=True)
    parser.add_argument("--equity", required=True)
    parser.add_argument("--initial-capital", type=float, default=100000)
    parser.add_argument("--output", default=str(ROOT / "data/reports/report.md"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trades = pd.read_csv(args.trades)
    equity = pd.read_csv(args.equity, index_col=0)
    metrics = calculate_metrics(trades, equity, args.initial_capital)
    mc_result = run_monte_carlo(trades, args.initial_capital, simulations=1000)
    validation = validate_strategy(metrics, mc_result.p95_max_drawdown_pct)
    report = build_backtest_report(metrics, validation, asdict(mc_result))
    output = write_backtest_report(args.output, report)
    print(f"Report written to: {output}")


if __name__ == "__main__":
    main()
