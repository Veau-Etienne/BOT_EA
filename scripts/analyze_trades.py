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

from src.backtest.metrics import calculate_metrics
from src.data.loader import load_mt5_ohlcv
from src.indicators.atr import atr
from src.indicators.ema import ema
from src.utils.config import load_yaml, resolve_asset_spec
from src.utils.time import in_time_windows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a rejected strategy trade log.")
    parser.add_argument("--trades", required=True, help="Trades CSV produced by run_backtest.py.")
    parser.add_argument("--data", required=True, help="MT5 OHLCV CSV used by the backtest.")
    parser.add_argument("--output", required=True, help="Markdown analysis output path.")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    return parser.parse_args()


def profit_factor(pnls: pd.Series) -> float:
    wins = pnls[pnls > 0].sum()
    losses = abs(pnls[pnls < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def summary_table(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()
    for name, group in df.groupby(group_col, dropna=False, observed=False):
        pnls = group["net_pnl"].astype(float)
        rows.append(
            {
                group_col: name,
                "trades": len(group),
                "net_pnl": pnls.sum(),
                "profit_factor": profit_factor(pnls),
                "winrate_pct": (pnls > 0).mean() * 100,
                "expectancy": pnls.mean(),
                "avg_r": group["r_multiple"].astype(float).mean() if "r_multiple" in group else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("net_pnl", ascending=False)


def markdown_table(df: pd.DataFrame, max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["_No data._", ""]
    display = df.head(max_rows).copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "inf" if math.isinf(value) else f"{value:.2f}")
    lines = ["| " + " | ".join(display.columns) + " |", "| " + " | ".join(["---"] * len(display.columns)) + " |"]
    for _, row in display.iterrows():
        lines.append("| " + " | ".join(str(value) for value in row.tolist()) + " |")
    lines.append("")
    return lines


def session_name(ts: pd.Timestamp) -> str:
    london = [["08:00", "11:30"]]
    us = [["14:30", "18:00"]]
    if in_time_windows(ts, london):
        return "london"
    if in_time_windows(ts, us):
        return "us"
    return "other"


def add_entry_context(trades: pd.DataFrame, data: pd.DataFrame, timezone: str) -> pd.DataFrame:
    enriched = trades.copy()
    enriched["entry_time"] = pd.to_datetime(enriched["entry_time"], utc=True).dt.tz_convert(timezone)
    enriched["exit_time"] = pd.to_datetime(enriched["exit_time"], utc=True).dt.tz_convert(timezone)
    enriched["entry_hour"] = enriched["entry_time"].dt.hour
    enriched["weekday"] = enriched["entry_time"].dt.day_name()
    enriched["session"] = enriched["entry_time"].map(session_name)

    context = data[["open", "high", "low", "close"]].copy()
    context["atr"] = atr(context, 14)
    context["ema200"] = ema(context["close"], 200)
    if "spread" in data.columns:
        context["spread"] = data["spread"]
    else:
        context["spread"] = pd.NA
    context["ema_distance"] = context["close"] - context["ema200"]
    context["ema_distance_atr"] = context["ema_distance"] / context["atr"]

    enriched = enriched.merge(
        context[["atr", "ema200", "spread", "ema_distance", "ema_distance_atr"]],
        left_on="entry_time",
        right_index=True,
        how="left",
    )

    for column, labels in [
        ("spread", ["low_spread", "mid_spread", "high_spread"]),
        ("atr", ["low_atr", "mid_atr", "high_atr"]),
        ("ema_distance_atr", ["below_far", "near_ema", "above_far"]),
    ]:
        values = enriched[column]
        try:
            enriched[f"{column}_bucket"] = pd.qcut(values.rank(method="first"), q=3, labels=labels)
        except ValueError:
            enriched[f"{column}_bucket"] = "single_bucket"
    return enriched


def initial_r_price(row: pd.Series, contract_size: float) -> float:
    lots = float(row.get("lots", 0.0))
    risk_amount = float(row.get("risk_amount", 0.0))
    if lots > 0 and contract_size > 0 and risk_amount > 0:
        return risk_amount / (lots * contract_size)
    entry = float(row["entry_price"])
    stop = float(row["stop_loss"])
    if abs(entry - stop) > 0:
        return abs(entry - stop)
    target = float(row["take_profit"])
    return max(abs(target - entry) / 2.0, 0.0)


def add_excursions(trades: pd.DataFrame, data: pd.DataFrame, contract_size: float) -> pd.DataFrame:
    out = trades.copy()
    maes: list[float] = []
    mfes: list[float] = []
    hit_half_then_lost: list[bool] = []
    hit_one_then_lost: list[bool] = []

    for _, trade in out.iterrows():
        entry_time = trade["entry_time"]
        exit_time = trade["exit_time"]
        entry_price = float(trade["entry_price"])
        r_price = initial_r_price(trade, contract_size)
        bars = data[(data.index >= entry_time) & (data.index <= exit_time)]
        if bars.empty or r_price <= 0:
            maes.append(0.0)
            mfes.append(0.0)
            hit_half_then_lost.append(False)
            hit_one_then_lost.append(False)
            continue

        if trade["side"] == "long":
            mfe = (float(bars["high"].max()) - entry_price) / r_price
            mae = (entry_price - float(bars["low"].min())) / r_price
        else:
            mfe = (entry_price - float(bars["low"].min())) / r_price
            mae = (float(bars["high"].max()) - entry_price) / r_price
        maes.append(mae)
        mfes.append(mfe)
        lost = float(trade["net_pnl"]) < 0
        hit_half_then_lost.append(lost and mfe >= 0.5)
        hit_one_then_lost.append(lost and mfe >= 1.0)

    out["mae_r"] = maes
    out["mfe_r"] = mfes
    out["hit_0_5r_then_lost"] = hit_half_then_lost
    out["hit_1r_then_lost"] = hit_one_then_lost
    return out


def equity_curve_from_trades(trades: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["equity", "drawdown_pct"])
    ordered = trades.sort_values("exit_time").copy()
    ordered["equity"] = initial_capital + ordered["net_pnl"].astype(float).cumsum()
    ordered["peak"] = ordered["equity"].cummax().clip(lower=initial_capital)
    ordered["drawdown_pct"] = (ordered["peak"] - ordered["equity"]) / ordered["peak"] * 100
    return ordered.set_index("exit_time")[["equity", "drawdown_pct"]]


def simulate_inverse_trades(trades: pd.DataFrame, data: pd.DataFrame, contract_size: float, initial_capital: float) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    force_flat_time = "18:00"

    for _, trade in trades.iterrows():
        entry_time = trade["entry_time"]
        side = "short" if trade["side"] == "long" else "long"
        entry = float(trade["entry_price"])
        risk_price = initial_r_price(trade, contract_size)
        target_distance = abs(float(trade["take_profit"]) - entry)
        if risk_price <= 0 or target_distance <= 0:
            continue

        if side == "long":
            stop = entry - risk_price
            target = entry + target_distance
        else:
            stop = entry + risk_price
            target = entry - target_distance

        day_rows = data[(data.index > entry_time) & (data.index.date == entry_time.date())]
        day_rows = day_rows[day_rows.index.strftime("%H:%M") <= force_flat_time]
        if day_rows.empty:
            continue

        exit_price = float(day_rows.iloc[-1]["close"])
        exit_time = day_rows.index[-1]
        exit_reason = "force_flat"
        for ts, bar in day_rows.iterrows():
            if side == "long":
                if float(bar["low"]) <= stop:
                    exit_price, exit_time, exit_reason = stop, ts, "stop_loss"
                    break
                if float(bar["high"]) >= target:
                    exit_price, exit_time, exit_reason = target, ts, "take_profit"
                    break
            else:
                if float(bar["high"]) >= stop:
                    exit_price, exit_time, exit_reason = stop, ts, "stop_loss"
                    break
                if float(bar["low"]) <= target:
                    exit_price, exit_time, exit_reason = target, ts, "take_profit"
                    break

        sign = 1 if side == "long" else -1
        lots = float(trade.get("lots", 0.0))
        commission = float(trade.get("commission", 0.0))
        gross = (exit_price - entry) * sign * lots * contract_size
        net = gross - commission
        risk_amount = float(trade.get("risk_amount", 0.0))
        rows.append(
            {
                "strategy": "inverse_xau_trend_breakout_theoretical",
                "entry_time": entry_time,
                "exit_time": exit_time,
                "side": side,
                "entry_price": entry,
                "exit_price": exit_price,
                "stop_loss": stop,
                "take_profit": target,
                "lots": lots,
                "risk_amount": risk_amount,
                "gross_pnl": gross,
                "commission": commission,
                "net_pnl": net,
                "r_multiple": net / risk_amount if risk_amount else 0.0,
                "exit_reason": exit_reason,
                "holding_minutes": (exit_time - entry_time).total_seconds() / 60,
            }
        )

    inverse = pd.DataFrame(rows)
    metrics = calculate_metrics(inverse, equity_curve_from_trades(inverse, initial_capital), initial_capital)
    return inverse, metrics


def concentration_of_losses(trades: pd.DataFrame) -> dict[str, float]:
    losses = trades[trades["net_pnl"] < 0]["net_pnl"].abs().sort_values(ascending=False)
    total = float(losses.sum())
    if total <= 0:
        return {"top_1_loss_pct": 0.0, "top_5_losses_pct": 0.0, "top_10_losses_pct": 0.0}
    return {
        "top_1_loss_pct": float(losses.head(1).sum() / total * 100),
        "top_5_losses_pct": float(losses.head(5).sum() / total * 100),
        "top_10_losses_pct": float(losses.head(10).sum() / total * 100),
    }


def main() -> None:
    args = parse_args()
    trades = pd.read_csv(args.trades)
    if trades.empty:
        raise SystemExit("Trade analysis failed: trades file is empty.")
    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    assets = load_yaml(ROOT / "config/assets.yaml")
    asset = resolve_asset_spec(assets, args.symbol)

    trades = add_entry_context(trades, data, args.timezone)
    trades = add_excursions(trades, data, asset.contract_size)
    inverse_trades, inverse_metrics = simulate_inverse_trades(trades, data, asset.contract_size, args.initial_capital)

    stop_trades = trades[trades["exit_reason"] == "stop_loss"]
    tp_trades = trades[trades["exit_reason"] == "take_profit"]
    losses_concentration = concentration_of_losses(trades)

    lines: list[str] = [
        "# XAUUSD M15 Trade Analysis",
        "",
        "## Data",
        "",
        f"- Data period: `{cleaning.first_timestamp}` -> `{cleaning.last_timestamp}`",
        f"- Candles: `{cleaning.rows_out}`",
        f"- Missing bars detected: `{cleaning.missing_bars}`",
        f"- Spread mean/min/max: `{cleaning.spread_mean}` / `{cleaning.spread_min}` / `{cleaning.spread_max}`",
        "",
        "## Core Observations",
        "",
        f"- Trades: `{len(trades)}`",
        f"- Long trades: `{int((trades['side'] == 'long').sum())}`",
        f"- Short trades: `{int((trades['side'] == 'short').sum())}`",
        f"- Trades reaching +0.5R before finishing negative: `{int(trades['hit_0_5r_then_lost'].sum())}`",
        f"- Trades reaching +1R before finishing negative: `{int(trades['hit_1r_then_lost'].sum())}`",
        f"- Average time before SL: `{stop_trades['holding_minutes'].mean():.2f}` minutes",
        f"- Average time before TP: `{tp_trades['holding_minutes'].mean():.2f}` minutes",
        f"- Loss concentration top 1 / top 5 / top 10: `{losses_concentration['top_1_loss_pct']:.2f}%` / `{losses_concentration['top_5_losses_pct']:.2f}%` / `{losses_concentration['top_10_losses_pct']:.2f}%`",
        "",
        "## Longs vs Shorts",
        "",
    ]
    lines += markdown_table(summary_table(trades, "side"))
    for title, column in [
        ("Performance By Entry Hour", "entry_hour"),
        ("Performance By Session", "session"),
        ("Performance By Weekday", "weekday"),
        ("Performance By Spread Bucket", "spread_bucket"),
        ("Performance By ATR Bucket", "atr_bucket"),
        ("Performance By EMA200 Distance Bucket", "ema_distance_atr_bucket"),
        ("Exit Reasons", "exit_reason"),
    ]:
        lines += [f"## {title}", ""]
        lines += markdown_table(summary_table(trades, column))

    lines += [
        "## R Multiple Distribution",
        "",
        "| Statistic | Value |",
        "| --- | ---: |",
    ]
    r = trades["r_multiple"].astype(float)
    for label, value in {
        "count": r.count(),
        "mean": r.mean(),
        "std": r.std(ddof=0),
        "min": r.min(),
        "p25": r.quantile(0.25),
        "median": r.quantile(0.50),
        "p75": r.quantile(0.75),
        "max": r.max(),
    }.items():
        lines.append(f"| {label} | {value:.2f} |")

    lines += [
        "",
        "## MAE / MFE",
        "",
        f"- Mean MAE: `{trades['mae_r'].mean():.2f}R`",
        f"- Median MAE: `{trades['mae_r'].median():.2f}R`",
        f"- Mean MFE: `{trades['mfe_r'].mean():.2f}R`",
        f"- Median MFE: `{trades['mfe_r'].median():.2f}R`",
        "",
        "## Theoretical Inverse Strategy",
        "",
        "This is a diagnostic only. It reverses each observed trade at the same timestamp with symmetric SL/TP distances, reuses the original lot size and commission, and force-flats intraday if neither SL nor TP is hit.",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| net_profit | {inverse_metrics['net_profit']:.2f} |",
        f"| profit_factor | {inverse_metrics['profit_factor']:.2f} |",
        f"| winrate_pct | {inverse_metrics['winrate_pct']:.2f} |",
        f"| expectancy | {inverse_metrics['expectancy']:.2f} |",
        f"| max_drawdown_pct | {inverse_metrics['max_drawdown_pct']:.2f} |",
        f"| trade_count | {inverse_metrics['trade_count']} |",
        "",
    ]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    inverse_path = output.with_suffix(".inverse_trades.csv")
    inverse_trades.to_csv(inverse_path, index=False)
    print(f"Trade analysis written to: {output}")
    print(f"Inverse theoretical trades written to: {inverse_path}")
    print(f"Inverse net profit: {inverse_metrics['net_profit']:.2f}")
    print(f"Inverse profit factor: {inverse_metrics['profit_factor']:.2f}")
    print(f"Inverse expectancy: {inverse_metrics['expectancy']:.2f}")


if __name__ == "__main__":
    main()
