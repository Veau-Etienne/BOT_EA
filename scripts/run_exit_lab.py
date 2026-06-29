#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.execution import exit_price, side_sign
from src.backtest.exit_lab import (
    default_exit_policies,
    run_exit_lab,
)
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config
from src.utils.time import in_time_windows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare exit policies on fixed strategy entries.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", default="xau_trend_breakout", choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--fixed-spread-threshold", type=float, default=50.0)
    return parser.parse_args()


def fmt(value: Any, decimals: int = 2) -> str:
    if isinstance(value, float):
        if value == float("inf"):
            return "inf"
        return f"{value:.{decimals}f}"
    return str(value)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 10) -> list[str]:
    if df.empty:
        return ["_No data._", ""]
    view = df[columns].head(max_rows).copy()
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(fmt(value) for value in row.tolist()) + " |")
    lines.append("")
    return lines


def session_name(ts: pd.Timestamp) -> str:
    if in_time_windows(ts, [["08:00", "11:30"]]):
        return "london"
    if in_time_windows(ts, [["14:30", "18:00"]]):
        return "us"
    return "other"


def plus1_loser_report(
    original: pd.DataFrame,
    trailing_after_1r: pd.DataFrame,
    output_csv: Path,
    output_md: Path,
    asset_point: float,
    slippage_points: float,
    contract_size: float,
) -> pd.DataFrame:
    if original.empty:
        losers = pd.DataFrame()
    else:
        losers = original[(original["net_pnl"] < 0) & (original["mfe_r"] >= 1.0)].copy()

    trailing_lookup = trailing_after_1r.set_index("entry_time") if not trailing_after_1r.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, trade in losers.iterrows():
        entry_time = pd.Timestamp(trade["entry_time"])
        side = trade["side"]
        sign = side_sign(side)
        lots = float(trade["lots"])
        risk_amount = float(trade["risk_amount"])
        entry = float(trade["entry_price"])
        r_price = risk_amount / (lots * contract_size) if lots and contract_size else abs(float(trade["entry_price"]) - float(trade["stop_loss"]))
        one_r_mid = entry + sign * r_price
        one_r_exit = exit_price(one_r_mid, side, float(trade["spread"]), slippage_points, asset_point)
        gross_1r = (one_r_exit - entry) * sign * lots * contract_size
        commission = float(trade["commission"])
        exit_1r_net = gross_1r - commission
        break_even_net = -commission
        partial_1r_net = gross_1r * 0.5 + float(trade["gross_pnl"]) * 0.5 - commission
        trailing_net = None
        if not trailing_lookup.empty and entry_time in trailing_lookup.index:
            trailing_row = trailing_lookup.loc[entry_time]
            if isinstance(trailing_row, pd.DataFrame):
                trailing_row = trailing_row.iloc[0]
            trailing_net = float(trailing_row["net_pnl"])
        rows.append(
            {
                "entry_time": entry_time,
                "entry_hour": entry_time.hour,
                "session": session_name(entry_time),
                "side": side,
                "mfe_r": float(trade["mfe_r"]),
                "mae_r": float(trade["mae_r"]),
                "holding_minutes": float(trade["holding_minutes"]),
                "spread": float(trade["spread"]),
                "original_net_pnl": float(trade["net_pnl"]),
                "exit_at_1r_net_pnl": exit_1r_net,
                "break_even_at_1r_net_pnl": break_even_net,
                "partial_50_at_1r_net_pnl": partial_1r_net,
                "trailing_after_1r_net_pnl": trailing_net,
            }
        )

    out = pd.DataFrame(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)

    lines = [
        "# +1R Losers Analysis",
        "",
        f"- Trades that reached +1R then finished negative: `{len(out)}`",
    ]
    if not out.empty:
        lines.extend(
            [
                f"- Original combined PnL: `{out['original_net_pnl'].sum():.2f}`",
                f"- If exited at +1R: `{out['exit_at_1r_net_pnl'].sum():.2f}`",
                f"- If break-even after +1R: `{out['break_even_at_1r_net_pnl'].sum():.2f}`",
                f"- If partial 50% at +1R: `{out['partial_50_at_1r_net_pnl'].sum():.2f}`",
                f"- If trailing after +1R: `{out['trailing_after_1r_net_pnl'].dropna().sum():.2f}`",
                "",
                "## Trades",
                "",
            ]
        )
        columns = [
            "entry_time",
            "session",
            "side",
            "mfe_r",
            "mae_r",
            "holding_minutes",
            "spread",
            "original_net_pnl",
            "exit_at_1r_net_pnl",
            "break_even_at_1r_net_pnl",
            "partial_50_at_1r_net_pnl",
            "trailing_after_1r_net_pnl",
        ]
        lines += markdown_table(out.sort_values("original_net_pnl"), columns, max_rows=50)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    args = parse_args()
    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    strategy = STRATEGY_REGISTRY[args.strategy](strat_cfg)

    spread_series = data["spread"].dropna() if "spread" in data.columns else pd.Series(dtype=float)
    spread_p75 = float(spread_series.quantile(0.75)) if len(spread_series) else None
    spread_p90 = float(spread_series.quantile(0.90)) if len(spread_series) else None
    policies = default_exit_policies(spread_p75, spread_p90, args.fixed_spread_threshold)
    results, trades_by_policy, entries = run_exit_lab(
        data,
        strategy,
        asset,
        backtest_cfg.initial_capital,
        min(strategy.risk_per_trade_pct, backtest_cfg.risk_per_trade_pct),
        backtest_cfg.spread_points,
        backtest_cfg.slippage_points,
        backtest_cfg.commission_per_lot_round_turn,
        policies,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    results.to_csv(csv_path, index=False)

    plus_md = output.with_name(output.name.replace("exit_lab", "plus1R_losers"))
    plus_csv = plus_md.with_suffix(".csv")
    plus1 = plus1_loser_report(
        trades_by_policy.get("original_sl_1_5atr_tp_2_5atr", pd.DataFrame()),
        trades_by_policy.get("trailing_atr_1_after_1r", pd.DataFrame()),
        plus_csv,
        plus_md,
        asset.point,
        backtest_cfg.slippage_points,
        asset.contract_size,
    )

    top_columns = [
        "exit_policy",
        "trade_count",
        "net_profit",
        "profit_factor",
        "winrate_pct",
        "expectancy",
        "max_drawdown_pct",
        "max_loss_streak",
        "sharpe_simple",
        "break_even_pct",
        "time_stop_pct",
        "trailing_stop_pct",
        "monthly_profit_concentration_pct",
        "robust_exit_score",
    ]
    top_pf = results.sort_values(["profit_factor", "expectancy"], ascending=[False, False])
    top_exp = results.sort_values(["expectancy", "profit_factor"], ascending=[False, False])
    top_score = results.sort_values(["robust_exit_score", "profit_factor"], ascending=[False, False])

    lines = [
        "# XAUUSD M15 Exit Lab",
        "",
        "Fixed-entry diagnostic. This report compares exit engines on the same strategy entries. It is not a tradable validation by itself.",
        "",
        f"- Strategy: `{args.strategy}`",
        f"- Data period: `{cleaning.first_timestamp}` -> `{cleaning.last_timestamp}`",
        f"- Candles: `{cleaning.rows_out}`",
        f"- Fixed entries collected: `{len(entries)}`",
        f"- Spread p75/p90: `{spread_p75}` / `{spread_p90}`",
        f"- +1R losers analyzed: `{len(plus1)}`",
        "",
        "## Top 10 By Robust Exit Score",
        "",
    ]
    lines += markdown_table(top_score, top_columns, max_rows=10)
    lines += ["## Top 10 By Profit Factor", ""]
    lines += markdown_table(top_pf, top_columns, max_rows=10)
    lines += ["## Top 10 By Expectancy", ""]
    lines += markdown_table(top_exp, top_columns, max_rows=10)
    lines += [
        "## All Results",
        "",
        f"CSV: `{csv_path}`",
        "",
        "## +1R Losers",
        "",
        f"Markdown: `{plus_md}`",
        f"CSV: `{plus_csv}`",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")

    print(f"Exit Lab markdown written to: {output}")
    print(f"Exit Lab CSV written to: {csv_path}")
    print(f"+1R losers markdown written to: {plus_md}")
    print(f"+1R losers CSV written to: {plus_csv}")
    print("Top 5 by robust score:")
    print(top_score[top_columns].head(5).to_string(index=False))
    print("Top 5 by profit factor:")
    print(top_pf[top_columns].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
