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

from src.data.loader import load_mt5_ohlcv
from src.indicators.atr import atr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a strategy candidate from a strict backtest trade log.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--trades", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    return parser.parse_args()


def _fmt(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number) or math.isinf(number):
        return ""
    return f"{number:.{decimals}f}"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_Aucun résultat._"
    available = [column for column in columns if column in frame.columns]
    lines = ["| " + " | ".join(available) + " |", "| " + " | ".join(["---"] * len(available)) + " |"]
    for _, row in frame[available].iterrows():
        values: list[str] = []
        for column in available:
            value = row[column]
            if pd.api.types.is_number(value):
                if column in {"trades", "wins", "losses"}:
                    values.append(str(int(value)))
                elif "factor" in column:
                    values.append(_fmt(value, 3))
                else:
                    values.append(_fmt(value, 2))
            else:
                values.append("" if pd.isna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _profit_factor(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses > 0:
        return float(wins / losses)
    return float("inf") if wins > 0 else 0.0


def _group_stats(frame: pd.DataFrame, group: str) -> pd.DataFrame:
    if frame.empty or group not in frame.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for key, part in frame.groupby(group, dropna=False):
        pnl = part["net_pnl"].astype(float)
        rows.append(
            {
                group: key,
                "trades": len(part),
                "net_profit": pnl.sum(),
                "profit_factor": _profit_factor(pnl),
                "winrate": (pnl > 0).mean() * 100 if len(pnl) else 0.0,
                "expectancy": pnl.mean() if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("net_profit", ascending=False)


def _max_loss_streak(pnls: pd.Series) -> int:
    streak = 0
    max_streak = 0
    for pnl in pnls:
        if pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _stagnation(equity: pd.Series) -> tuple[int, str, str]:
    if equity.empty:
        return 0, "", ""
    peaks = equity.cummax()
    underwater = equity < peaks
    best_len = 0
    best_start = ""
    best_end = ""
    current_len = 0
    current_start = ""
    for timestamp, is_underwater in underwater.items():
        if is_underwater:
            if current_len == 0:
                current_start = str(timestamp)
            current_len += 1
            if current_len > best_len:
                best_len = current_len
                best_start = current_start
                best_end = str(timestamp)
        else:
            current_len = 0
            current_start = ""
    return best_len, best_start, best_end


def _candidate_verdict(
    trade_count: int,
    profit_factor: float,
    expectancy: float,
    concentration_best: float,
    concentration_top3: float,
    monthly_stability: float,
    max_loss_streak: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if trade_count < 100:
        reasons.append("too_few_trades")
    if profit_factor < 1.0:
        reasons.append("profit_factor_below_1")
    if expectancy < 0:
        reasons.append("negative_expectancy")
    if concentration_best > 40:
        reasons.append("profit_concentrated_best_month")
    if concentration_top3 > 75:
        reasons.append("profit_concentrated_top3_months")
    if monthly_stability < 50:
        reasons.append("weak_monthly_stability")
    if max_loss_streak >= 10:
        reasons.append("long_losing_streak")
    if profit_factor < 1.0 or expectancy < 0:
        return "rejetée", reasons
    if concentration_best > 40 or concentration_top3 > 75 or monthly_stability < 50 or max_loss_streak >= 10:
        return "trop concentrée", reasons
    if profit_factor < 1.20:
        return "fragile", reasons or ["pf_below_validation_threshold"]
    return "stable", reasons


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    trades_path = Path(args.trades)
    output = Path(args.output)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    if not trades_path.is_absolute():
        trades_path = ROOT / trades_path
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    data, cleaning = load_mt5_ohlcv(data_path, timezone=args.timezone, timeframe=args.timeframe)
    market = data.copy()
    market["atr_14"] = atr(market, 14)
    trades = pd.read_csv(trades_path)
    if trades.empty:
        raise SystemExit("No trades to analyze.")
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert(data.index.tz)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert(data.index.tz)
    trades = trades.sort_values("exit_time").reset_index(drop=True)

    enriched = trades.copy()
    enriched["month"] = enriched["exit_time"].dt.tz_localize(None).dt.to_period("M").astype(str)
    enriched["year"] = enriched["exit_time"].dt.tz_localize(None).dt.to_period("Y").astype(str)
    enriched["entry_hour"] = enriched["entry_time"].dt.hour
    enriched["weekday"] = enriched["entry_time"].dt.day_name()
    enriched = enriched.join(market[["atr_14", "spread"]], on="entry_time")
    enriched["atr_regime"] = pd.qcut(enriched["atr_14"].rank(method="first"), 3, labels=["low", "mid", "high"])
    enriched["spread_regime"] = pd.qcut(enriched["spread"].rank(method="first"), 3, labels=["low", "mid", "high"])

    monthly = _group_stats(enriched, "month").sort_values("month")
    yearly = _group_stats(enriched, "year").sort_values("year")
    side_stats = _group_stats(enriched, "side")
    hour_stats = _group_stats(enriched, "entry_hour").sort_values("entry_hour")
    weekday_stats = _group_stats(enriched, "weekday")
    atr_stats = _group_stats(enriched, "atr_regime")
    spread_stats = _group_stats(enriched, "spread_regime")
    pnls = enriched["net_pnl"].astype(float)
    net_profit = float(pnls.sum())
    gross_profit = float(pnls[pnls > 0].sum())
    positive_months = monthly[monthly["net_profit"] > 0].copy()
    best_month_profit = float(positive_months["net_profit"].max()) if not positive_months.empty else 0.0
    top3_profit = float(positive_months["net_profit"].nlargest(3).sum()) if not positive_months.empty else 0.0
    concentration_best = best_month_profit / net_profit * 100 if net_profit > 0 else 0.0
    concentration_top3 = top3_profit / net_profit * 100 if net_profit > 0 else 0.0
    all_months = pd.period_range(enriched["exit_time"].min().tz_localize(None).to_period("M"), enriched["exit_time"].max().tz_localize(None).to_period("M"), freq="M")
    traded_months = set(enriched["month"])
    months_without_trade = [str(month) for month in all_months if str(month) not in traded_months]
    equity = args.initial_capital + pnls.cumsum()
    equity.index = enriched["exit_time"]
    equity_frame = pd.DataFrame({"time": enriched["exit_time"], "equity": equity.values, "net_pnl": pnls.values})
    equity_csv = output.with_suffix(".equity.csv")
    equity_frame.to_csv(equity_csv, index=False)
    stagnation_trades, stagnation_start, stagnation_end = _stagnation(equity)
    r_multiples = enriched["r_multiple"].astype(float) if "r_multiple" in enriched.columns else pd.Series(dtype=float)
    r_distribution = pd.DataFrame(
        [
            {
                "count": len(r_multiples),
                "mean": r_multiples.mean(),
                "std": r_multiples.std(ddof=0),
                "min": r_multiples.min(),
                "p25": r_multiples.quantile(0.25),
                "median": r_multiples.quantile(0.50),
                "p75": r_multiples.quantile(0.75),
                "max": r_multiples.max(),
            }
        ]
    )
    max_loss_streak = _max_loss_streak(pnls)
    profit_factor = _profit_factor(pnls)
    expectancy = float(pnls.mean())
    monthly_stability = float((monthly["net_profit"] > 0).mean() * 100) if not monthly.empty else 0.0
    verdict, reasons = _candidate_verdict(
        len(enriched),
        profit_factor,
        expectancy,
        concentration_best,
        concentration_top3,
        monthly_stability,
        max_loss_streak,
    )

    report = f"""# Candidate Analysis - {args.asset} / {args.strategy}

## Résumé

- Période data: {cleaning.first_timestamp} -> {cleaning.last_timestamp}
- Bougies: {cleaning.rows_out}
- Trades: {len(enriched)}
- Profit net: {_fmt(net_profit)}
- Profit factor: {_fmt(profit_factor, 3)}
- Expectancy: {_fmt(expectancy)}
- Winrate: {_fmt((pnls > 0).mean() * 100)}
- Profit brut positif: {_fmt(gross_profit)}
- Concentration meilleur mois: {_fmt(concentration_best)}%
- Concentration top 3 mois: {_fmt(concentration_top3)}%
- Stabilité mensuelle: {_fmt(monthly_stability)}%
- Max losing streak: {max_loss_streak}
- Plus longue stagnation en trades: {stagnation_trades} ({stagnation_start} -> {stagnation_end})
- Equity CSV: `{equity_csv}`
- Verdict candidat: {verdict}
- Raisons: {", ".join(reasons) if reasons else "aucune alerte majeure"}

## Performance Mois Par Mois

{_markdown_table(monthly, ["month", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Performance Par Année

{_markdown_table(yearly, ["year", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Mois Sans Trade

{", ".join(months_without_trade) if months_without_trade else "Aucun mois sans trade dans la fenêtre de trades."}

## Longs Vs Shorts

{_markdown_table(side_stats, ["side", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Performance Par Heure

{_markdown_table(hour_stats, ["entry_hour", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Performance Par Jour De Semaine

{_markdown_table(weekday_stats, ["weekday", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Performance Par Régime ATR

{_markdown_table(atr_stats, ["atr_regime", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Performance Selon Spread

{_markdown_table(spread_stats, ["spread_regime", "trades", "net_profit", "profit_factor", "winrate", "expectancy"])}

## Distribution Des R Multiples

{_markdown_table(r_distribution, ["count", "mean", "std", "min", "p25", "median", "p75", "max"])}
"""
    output.write_text(report, encoding="utf-8")
    print(f"Candidate report: {output}")
    print(f"Equity CSV: {equity_csv}")
    print(f"Verdict: {verdict}")
    print(f"Profit factor: {profit_factor:.3f} | Expectancy: {expectancy:.2f} | Best month concentration: {concentration_best:.2f}% | Top 3 concentration: {concentration_top3:.2f}%")


if __name__ == "__main__":
    main()
