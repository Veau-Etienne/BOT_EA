#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.monte_carlo import run_monte_carlo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Monte Carlo simulations from a trades CSV.")
    parser.add_argument("--trades", required=True, help="Trades CSV produced by run_backtest.py.")
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--thresholds", default="5,8,10,15", help="Drawdown ruin thresholds in percent.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(ROOT / "data/reports/monte_carlo.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trades = pd.read_csv(args.trades)
    thresholds = [float(item.strip()) for item in args.thresholds.split(",") if item.strip()]
    result = run_monte_carlo(
        trades,
        initial_capital=args.initial_capital,
        simulations=args.simulations,
        ruin_drawdown_pct=thresholds[0] if thresholds else 5.0,
        ruin_thresholds_pct=thresholds,
        seed=args.seed,
    )
    payload = asdict(result)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Simulations: {result.simulations}")
    print(f"Median drawdown: {result.median_max_drawdown_pct:.2f}%")
    print(f"95th percentile drawdown: {result.p95_max_drawdown_pct:.2f}%")
    print("Risk of ruin by threshold:")
    for threshold, probability in result.risk_of_ruin_by_threshold_pct.items():
        print(f"  - {threshold}: {probability:.2f}%")
    print(f"Worst simulated final equity: {result.worst_final_equity:.2f}")
    print(f"Worst simulated drawdown: {result.worst_max_drawdown_pct:.2f}%")
    if result.recommended_risk_per_trade_pct > 0:
        print(f"Recommended max risk per trade: {result.recommended_risk_per_trade_pct:.2f}%")
    else:
        print("Recommended max risk per trade: pause/reduce below 0.10% until the strategy improves")
    print(f"Monte Carlo JSON written to: {output}")


if __name__ == "__main__":
    main()
