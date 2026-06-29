#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_metrics, metrics_frame
from src.backtest.monte_carlo import run_monte_carlo
from src.backtest.reporting import build_backtest_report, latest_copy, write_backtest_report
from src.backtest.validation import validate_strategy
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local trading strategy backtest.")
    parser.add_argument("--data", required=True, help="CSV file exported from MT5.")
    parser.add_argument("--strategy", default="xau_trend_breakout", choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--assets-config", default=str(ROOT / "config/assets.yaml"))
    parser.add_argument("--risk-config", default=str(ROOT / "config/risk.yaml"))
    parser.add_argument("--strategies-config", default=str(ROOT / "config/strategies.yaml"))
    parser.add_argument("--reports-dir", default=str(ROOT / "data/reports"))
    parser.add_argument("--diagnostic-full-sample", action="store_true", help="Ignore drawdown limits for analysis only.")
    parser.add_argument("--cost-multiplier", type=float, default=1.0, help="Multiply spread, slippage and commission for execution stress tests.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategies_cfg = load_yaml(args.strategies_config)
    risk_cfg = load_yaml(args.risk_config)
    assets_cfg = load_yaml(args.assets_config)
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    if args.cost_multiplier <= 0:
        raise ValueError("--cost-multiplier must be positive")
    if args.cost_multiplier != 1.0:
        backtest_cfg = replace(
            backtest_cfg,
            spread_points=backtest_cfg.spread_points * args.cost_multiplier,
            slippage_points=backtest_cfg.slippage_points * args.cost_multiplier,
            commission_per_lot_round_turn=backtest_cfg.commission_per_lot_round_turn * args.cost_multiplier,
        )
    if args.diagnostic_full_sample:
        backtest_cfg = replace(backtest_cfg, diagnostic_full_sample=True)

    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    if args.cost_multiplier != 1.0 and "spread" in data.columns:
        data = data.copy()
        data["spread"] = data["spread"].astype(float) * args.cost_multiplier
    strategy = STRATEGY_REGISTRY[args.strategy](strat_cfg)
    result = BacktestEngine(backtest_cfg, asset).run(data, strategy)
    metrics = calculate_metrics(result.trades, result.equity_curve, backtest_cfg.initial_capital)
    monte_carlo = run_monte_carlo(result.trades, backtest_cfg.initial_capital, simulations=500)
    validation = validate_strategy(metrics, monte_carlo.p95_max_drawdown_pct, diagnostic_full_sample=args.diagnostic_full_sample)

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    prefix = reports_dir / f"{args.strategy}_{Path(args.data).stem}"
    trades_path = prefix.with_suffix(".trades.csv")
    equity_path = prefix.with_suffix(".equity.csv")
    metrics_path = prefix.with_suffix(".metrics.csv")
    summary_path = prefix.with_suffix(".summary.json")
    report_path = prefix.with_suffix(".report.md")
    result.trades.to_csv(trades_path, index=False)
    result.equity_curve.to_csv(equity_path)
    metrics_frame(metrics).to_csv(prefix.with_suffix(".metrics.csv"), index=False)
    report = build_backtest_report(
        metrics,
        validation,
        asdict(monte_carlo),
        title=f"{args.strategy} Backtest",
        diagnostic_full_sample=args.diagnostic_full_sample,
    )
    write_backtest_report(report_path, report)
    latest_copy(trades_path, reports_dir / "latest_trades.csv")
    latest_copy(equity_path, reports_dir / "latest_equity.csv")
    latest_copy(report_path, reports_dir / "latest_report.md")
    short_reports_dir = ROOT / "reports"
    latest_copy(trades_path, short_reports_dir / "latest_trades.csv")
    latest_copy(equity_path, short_reports_dir / "latest_equity.csv")
    latest_copy(report_path, short_reports_dir / "latest_report.md")
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "cleaning": asdict(cleaning),
                "metrics": metrics,
                "monte_carlo": asdict(monte_carlo),
                "validation": asdict(validation),
                "stopped_reason": result.stopped_reason,
                "diagnostic_full_sample": args.diagnostic_full_sample,
                "cost_multiplier": args.cost_multiplier,
            },
            handle,
            indent=2,
            default=_json_safe,
        )

    latest_copy(summary_path, reports_dir / "latest_summary.json")
    latest_copy(summary_path, short_reports_dir / "latest_summary.json")

    print(f"Rows loaded: {cleaning.rows_out} (duplicates removed: {cleaning.duplicates_removed}, missing bars: {cleaning.missing_bars})")
    print(f"Data period: {cleaning.first_timestamp} -> {cleaning.last_timestamp}")
    if cleaning.spread_mean is not None:
        print(f"Spread: avg={cleaning.spread_mean:.2f}, min={cleaning.spread_min:.2f}, max={cleaning.spread_max:.2f}")
    if args.diagnostic_full_sample:
        print("MODE DIAGNOSTIC — non tradable, drawdown limits ignored for analysis.")
    if args.cost_multiplier != 1.0:
        print(f"Cost multiplier: x{args.cost_multiplier:.2f}")
    print(f"Trades: {metrics['trade_count']}")
    print(f"Final capital: {metrics['final_capital']:.2f}")
    print(f"Net profit: {metrics['net_profit']:.2f}")
    print(f"Return: {metrics['total_return_pct']:.2f}%")
    print(f"Max drawdown: {metrics['max_drawdown_pct']:.2f}%")
    print(f"Profit factor: {metrics['profit_factor']}")
    print(f"Verdict: {validation.verdict} (robustness score: {validation.robustness_score}/100)")
    for warning in validation.warnings:
        print(f"Warning: {warning}")
    print(f"Reports written with prefix: {prefix}")
    print(f"Latest report: {reports_dir / 'latest_report.md'}")


if __name__ == "__main__":
    main()
