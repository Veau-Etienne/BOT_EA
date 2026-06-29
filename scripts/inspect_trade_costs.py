#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_metrics
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect trade cost realism for a strategy/data pair.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--asset", required=True, help="Asset label, for example US100_H1.")
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--assets-config", default=str(ROOT / "config/assets.yaml"))
    parser.add_argument("--risk-config", default=str(ROOT / "config/risk.yaml"))
    parser.add_argument("--strategies-config", default=str(ROOT / "config/strategies.yaml"))
    return parser.parse_args()


def _run_with_spread_multiplier(data: pd.DataFrame, multiplier: float, backtest_cfg, asset, strategy_name: str, strat_cfg: dict) -> dict:
    adjusted = data.copy()
    if "spread" in adjusted.columns:
        adjusted["spread"] = adjusted["spread"].astype(float) * multiplier
    adjusted_cfg = replace(
        backtest_cfg,
        spread_points=backtest_cfg.spread_points * multiplier,
        slippage_points=backtest_cfg.slippage_points * multiplier,
        commission_per_lot_round_turn=backtest_cfg.commission_per_lot_round_turn * multiplier,
    )
    strategy = STRATEGY_REGISTRY[strategy_name](strat_cfg)
    result = BacktestEngine(adjusted_cfg, asset).run(adjusted, strategy)
    return calculate_metrics(result.trades, result.equity_curve, adjusted_cfg.initial_capital)


def main() -> None:
    args = parse_args()
    strategies_cfg = load_yaml(args.strategies_config)
    risk_cfg = load_yaml(args.risk_config)
    assets_cfg = load_yaml(args.assets_config)
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)

    spreads = data["spread"].astype(float) if "spread" in data.columns else pd.Series([backtest_cfg.spread_points])
    base_metrics = _run_with_spread_multiplier(data, 1.0, backtest_cfg, asset, args.strategy, strat_cfg)

    failure_multiplier: float | None = None
    stress_rows = []
    for multiplier in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]:
        metrics = _run_with_spread_multiplier(data, multiplier, backtest_cfg, asset, args.strategy, strat_cfg)
        pf = float(metrics["profit_factor"]) if metrics["profit_factor"] not in ("inf", "nan") else float("inf")
        stress_rows.append((multiplier, metrics["trade_count"], metrics["net_profit"], metrics["expectancy"], metrics["profit_factor"], metrics["max_drawdown_pct"]))
        if failure_multiplier is None and pf < 1.0:
            failure_multiplier = multiplier

    mean_spread = float(spreads.mean())
    median_spread = float(spreads.median())
    cost_per_round_turn_points = mean_spread + 2 * backtest_cfg.slippage_points
    estimated_cost_per_unit = cost_per_round_turn_points * asset.point * asset.contract_size + backtest_cfg.commission_per_lot_round_turn
    cost_to_expectancy_ratio = estimated_cost_per_unit / abs(float(base_metrics["expectancy"])) if float(base_metrics["expectancy"]) != 0 else float("inf")

    lines = [
        f"# Cost Inspection - {args.asset} / {args.strategy}",
        "",
        f"- Point size : {asset.point}",
        f"- Contract size : {asset.contract_size}",
        f"- Rows loaded : {cleaning.rows_out}",
        f"- Spread mean : {mean_spread:.2f} points",
        f"- Spread median : {median_spread:.2f} points",
        f"- Spread p75 : {float(spreads.quantile(0.75)):.2f} points",
        f"- Spread p90 : {float(spreads.quantile(0.90)):.2f} points",
        f"- Spread min/max : {float(spreads.min()):.2f} / {float(spreads.max()):.2f} points",
        f"- Slippage configured : {backtest_cfg.slippage_points:.2f} points per side",
        f"- Commission configured : {backtest_cfg.commission_per_lot_round_turn:.2f} per lot round turn",
        f"- Estimated round-turn cost per 1 lot : {estimated_cost_per_unit:.2f}",
        f"- Base expectancy : {float(base_metrics['expectancy']):.2f}",
        f"- Estimated cost / expectancy ratio : {cost_to_expectancy_ratio:.2f}",
        f"- First tested cost level with PF < 1 : {failure_multiplier if failure_multiplier is not None else 'not reached up to x3.0'}",
        "",
        "## Execution Cost Stress",
        "",
        "| Multiplier | Trades | Net profit | Expectancy | Profit factor | Max DD |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for multiplier, trades, net_profit, expectancy, pf, max_dd in stress_rows:
        lines.append(f"| {multiplier:.2f} | {trades} | {net_profit:.2f} | {expectancy:.2f} | {pf} | {max_dd:.2f}% |")
    lines.extend(
        [
            "",
            "## Référence V1.9",
            "",
            "- Stress coûts x1.5 : PF 1.161, encore positif mais faible.",
            "- Stress coûts x2 : PF 0.665, échec.",
            "- Conclusion : le candidat doit rester non-live tant que les coûts broker MT5 ne sont pas confirmés.",
        ]
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Spread mean: {mean_spread:.2f} points")
    print(f"Estimated round-turn cost per 1 lot: {estimated_cost_per_unit:.2f}")
    print(f"PF < 1 first tested at: {failure_multiplier if failure_multiplier is not None else 'not reached'}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
