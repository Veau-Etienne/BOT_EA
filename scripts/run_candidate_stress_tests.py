#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
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
    parser = argparse.ArgumentParser(description="Stress test a candidate strategy from strict trades.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--trades", required=True)
    parser.add_argument("--asset", required=True)
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


def _profit_factor(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses > 0:
        return float(wins / losses)
    return float("inf") if wins > 0 else 0.0


def _max_drawdown_pct(pnl: pd.Series, initial_capital: float = 100000.0) -> float:
    if pnl.empty:
        return 0.0
    equity = initial_capital + pnl.cumsum()
    peaks = equity.cummax()
    return float(((peaks - equity) / peaks * 100).max())


def _metrics_from_pnl(name: str, trades: pd.DataFrame, pnl: pd.Series) -> dict[str, Any]:
    return {
        "test": name,
        "trades": int(len(pnl)),
        "profit_net": float(pnl.sum()) if len(pnl) else 0.0,
        "profit_factor": _profit_factor(pnl),
        "expectancy": float(pnl.mean()) if len(pnl) else 0.0,
        "max_drawdown": _max_drawdown_pct(pnl),
        "winrate": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "verdict": _stress_verdict(len(pnl), _profit_factor(pnl), float(pnl.mean()) if len(pnl) else 0.0),
    }


def _stress_verdict(trades: int, pf: float, expectancy: float) -> str:
    if trades < 100:
        return "FRAGILE"
    if pf < 1.0 or expectancy < 0:
        return "ÉCHEC"
    if pf >= 1.05 and expectancy > 0:
        return "OK"
    return "FRAGILE"


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = ["test", "trades", "profit_net", "profit_factor", "expectancy", "max_drawdown", "winrate", "verdict"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame[columns].iterrows():
        values: list[str] = []
        for column in columns:
            value = row[column]
            if pd.api.types.is_number(value):
                values.append(str(int(value)) if column == "trades" else _fmt(value, 3 if column == "profit_factor" else 2))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _run_cost_scenario(name: str, data: pd.DataFrame, strategy_name: str, strategy_cfg: dict[str, Any], backtest_cfg, asset_spec, factor: float) -> dict[str, Any]:
    cfg = replace(
        backtest_cfg,
        slippage_points=backtest_cfg.slippage_points * factor,
        commission_per_lot_round_turn=backtest_cfg.commission_per_lot_round_turn * factor,
    )
    stressed = data.copy()
    if "spread" in stressed.columns:
        stressed["spread"] = stressed["spread"].astype(float) * factor
    else:
        cfg = replace(cfg, spread_points=cfg.spread_points * factor)
    result = BacktestEngine(cfg, asset_spec).run(stressed, STRATEGY_REGISTRY[strategy_name](strategy_cfg))
    metrics = calculate_metrics(result.trades, result.equity_curve, cfg.initial_capital)
    return {
        "test": name,
        "trades": metrics["trade_count"],
        "profit_net": metrics["net_profit"],
        "profit_factor": metrics["profit_factor"],
        "expectancy": metrics["expectancy"],
        "max_drawdown": metrics["max_drawdown_pct"],
        "winrate": metrics["winrate_pct"],
        "verdict": _stress_verdict(metrics["trade_count"], metrics["profit_factor"], metrics["expectancy"]),
    }


def _run_slippage_scenario(name: str, data: pd.DataFrame, strategy_name: str, strategy_cfg: dict[str, Any], backtest_cfg, asset_spec, factor: float) -> dict[str, Any]:
    cfg = replace(backtest_cfg, slippage_points=backtest_cfg.slippage_points * factor)
    result = BacktestEngine(cfg, asset_spec).run(data, STRATEGY_REGISTRY[strategy_name](strategy_cfg))
    metrics = calculate_metrics(result.trades, result.equity_curve, cfg.initial_capital)
    return {
        "test": name,
        "trades": metrics["trade_count"],
        "profit_net": metrics["net_profit"],
        "profit_factor": metrics["profit_factor"],
        "expectancy": metrics["expectancy"],
        "max_drawdown": metrics["max_drawdown_pct"],
        "winrate": metrics["winrate_pct"],
        "verdict": _stress_verdict(metrics["trade_count"], metrics["profit_factor"], metrics["expectancy"]),
    }


def _run_risk_scenario(name: str, data: pd.DataFrame, strategy_name: str, strategy_cfg: dict[str, Any], backtest_cfg, asset_spec, risk_pct: float) -> dict[str, Any]:
    strategy_cfg = {**strategy_cfg, "risk_per_trade_pct": risk_pct}
    cfg = replace(backtest_cfg, risk_per_trade_pct=risk_pct)
    result = BacktestEngine(cfg, asset_spec).run(data, STRATEGY_REGISTRY[strategy_name](strategy_cfg))
    metrics = calculate_metrics(result.trades, result.equity_curve, cfg.initial_capital)
    verdict = _stress_verdict(metrics["trade_count"], metrics["profit_factor"], metrics["expectancy"])
    if risk_pct > 0.50 and verdict == "OK":
        verdict = "INFO_ONLY"
    return {
        "test": name,
        "trades": metrics["trade_count"],
        "profit_net": metrics["net_profit"],
        "profit_factor": metrics["profit_factor"],
        "expectancy": metrics["expectancy"],
        "max_drawdown": metrics["max_drawdown_pct"],
        "winrate": metrics["winrate_pct"],
        "verdict": verdict,
    }


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output_csv = output.with_suffix(".csv")
    data_path = Path(args.data)
    trades_path = Path(args.trades)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    if not trades_path.is_absolute():
        trades_path = ROOT / trades_path

    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    strategy_cfg = strategy_config(strategies_cfg, args.strategy)
    asset_spec = resolve_asset_spec(assets_cfg, strategy_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strategy_cfg)
    data, cleaning = load_mt5_ohlcv(data_path, timezone=args.timezone, timeframe=args.timeframe)
    trades = pd.read_csv(trades_path)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert(cleaning.first_timestamp[-6:] if False else data.index.tz)
    trades["month"] = trades["exit_time"].dt.tz_localize(None).dt.to_period("M").astype(str)
    trades = trades.sort_values("exit_time").reset_index(drop=True)
    pnl = trades["net_pnl"].astype(float)
    rows: list[dict[str, Any]] = [_metrics_from_pnl("baseline", trades, pnl)]

    monthly = trades.groupby("month")["net_pnl"].sum().sort_values(ascending=False)
    if len(monthly):
        rows.append(_metrics_from_pnl("without_best_month", trades[~trades["month"].isin(monthly.head(1).index)], trades.loc[~trades["month"].isin(monthly.head(1).index), "net_pnl"].astype(float)))
    rows.append(_metrics_from_pnl("without_top3_months", trades[~trades["month"].isin(monthly.head(3).index)], trades.loc[~trades["month"].isin(monthly.head(3).index), "net_pnl"].astype(float)))
    top5_indices = trades["net_pnl"].astype(float).nlargest(5).index
    top10_indices = trades["net_pnl"].astype(float).nlargest(10).index
    without_top5 = trades.drop(index=top5_indices).sort_values("exit_time")
    without_top10 = trades.drop(index=top10_indices).sort_values("exit_time")
    rows.append(_metrics_from_pnl("without_top5_trades", without_top5, without_top5["net_pnl"].astype(float)))
    rows.append(_metrics_from_pnl("without_top10_trades", without_top10, without_top10["net_pnl"].astype(float)))
    rows.append(_run_cost_scenario("costs_x1_5", data, args.strategy, strategy_cfg, backtest_cfg, asset_spec, 1.5))
    rows.append(_run_cost_scenario("costs_x2", data, args.strategy, strategy_cfg, backtest_cfg, asset_spec, 2.0))
    rows.append(_run_slippage_scenario("slippage_degraded_x2", data, args.strategy, strategy_cfg, backtest_cfg, asset_spec, 2.0))
    for risk in [0.25, 0.50, 0.75, 1.00]:
        rows.append(_run_risk_scenario(f"risk_{risk:.2f}_pct", data, args.strategy, strategy_cfg, backtest_cfg, asset_spec, risk))

    frame = pd.DataFrame(rows)
    frame.to_csv(output_csv, index=False)
    report = f"""# Stress Tests - {args.asset} / {args.strategy}

## Résumé

- Data: `{args.data}`
- Période: {cleaning.first_timestamp} -> {cleaning.last_timestamp}
- CSV: `{output_csv}`
- Note: les scénarios risque > 0.50% sont informatifs seulement.

{_markdown_table(frame)}
"""
    output.write_text(report, encoding="utf-8")
    print(f"Stress report: {output}")
    print(f"Stress CSV: {output_csv}")
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
