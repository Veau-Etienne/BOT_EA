#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.walk_forward import walk_forward_grid_search
from src.data.loader import load_mt5_ohlcv
from src.optimization.defaults import DEFAULT_GRID
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run walk-forward validation for a strategy.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", default="xau_trend_breakout", choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--grid-json", help="JSON parameter grid.")
    parser.add_argument("--objective", default="profit_factor")
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--output", default=str(ROOT / "data/reports/walk_forward.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    grid = json.loads(args.grid_json) if args.grid_json else DEFAULT_GRID[args.strategy]
    results = walk_forward_grid_search(
        data,
        STRATEGY_REGISTRY[args.strategy],
        strat_cfg,
        grid,
        backtest_cfg,
        asset,
        folds=args.folds,
        objective=args.objective,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output, index=False)

    columns = [
        "fold",
        *[f"param_{key}" for key in grid.keys()],
        "train_net_profit",
        "train_profit_factor",
        "train_trade_count",
        "test_net_profit",
        "test_profit_factor",
        "test_trade_count",
        "return_degradation_pct",
        "profit_factor_degradation_pct",
        "test_robustness_score",
        "verdict",
    ]
    available = [column for column in columns if column in results.columns]
    print(f"Rows loaded: {cleaning.rows_out} | Period: {cleaning.first_timestamp} -> {cleaning.last_timestamp}")
    print(results[available].to_string(index=False) if not results.empty else "No walk-forward folds produced.")
    print(f"Walk-forward results written to: {output}")


if __name__ == "__main__":
    main()
