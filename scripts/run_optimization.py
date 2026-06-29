#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.loader import load_mt5_ohlcv
from src.optimization.defaults import DEFAULT_GRID
from src.optimization.exporter import export_top_strategies
from src.optimization.grid_search import run_grid_search
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple grid search.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", default="xau_trend_breakout", choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--grid-json", help="JSON parameter grid, for example '{\"sl_atr\":[1.2,1.5]}'")
    parser.add_argument("--objective", default="profit_factor")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--output", default=str(ROOT / "data/reports/optimization.csv"))
    parser.add_argument("--export-dir", default=str(ROOT / "data/exports"))
    parser.add_argument("--top-n", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    data, _ = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    grid = json.loads(args.grid_json) if args.grid_json else DEFAULT_GRID[args.strategy]
    results = run_grid_search(data, STRATEGY_REGISTRY[args.strategy], strat_cfg, grid, backtest_cfg, asset, args.objective)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output, index=False)
    exported = export_top_strategies(results, args.strategy, strat_cfg, list(grid.keys()), args.export_dir, args.top_n)
    display_columns = [
        *grid.keys(),
        "net_profit",
        "profit_factor",
        "trade_count",
        "max_drawdown_pct",
        "monthly_stability_pct",
        "monthly_profit_concentration_pct",
        "robustness_score",
        "overfit_warnings",
    ]
    available_columns = [column for column in display_columns if column in results.columns]
    print(results.head(10)[available_columns].to_string(index=False))
    flagged = results.head(args.top_n)
    for rank, row in flagged.iterrows():
        warnings = row.get("overfit_warnings", "")
        if warnings:
            print(f"Warning rank {rank + 1}: {warnings}")
    print(f"Optimization results written to: {output}")
    print("Best strategy configs exported:")
    for path in exported:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
