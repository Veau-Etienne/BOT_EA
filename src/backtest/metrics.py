from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _max_loss_streak(pnls: pd.Series) -> int:
    max_streak = 0
    streak = 0
    for pnl in pnls:
        if pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def calculate_metrics(
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
    initial_capital: float,
) -> dict[str, Any]:
    if trades.empty:
        final_capital = float(initial_capital)
        return {
            "initial_capital": float(initial_capital),
            "final_capital": final_capital,
            "net_profit": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": float(equity_curve["drawdown_pct"].max()) if "drawdown_pct" in equity_curve else 0.0,
            "profit_factor": 0.0,
            "winrate_pct": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "expectancy": 0.0,
            "gain_loss_ratio": 0.0,
            "trade_count": 0,
            "trades_per_day_avg": 0.0,
            "best_day": 0.0,
            "worst_day": 0.0,
            "best_month": 0.0,
            "worst_month": 0.0,
            "performance_by_month": {},
            "performance_by_year": {},
            "monthly_stability_pct": 0.0,
            "monthly_profit_concentration_pct": 0.0,
            "r_multiple_distribution": {},
            "max_loss_streak": 0,
            "average_holding_minutes": 0.0,
        }

    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["exit_time"] = pd.to_datetime(out["exit_time"])
    pnls = out["net_pnl"].astype(float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    daily = out.groupby(out["exit_time"].dt.date)["net_pnl"].sum()
    exit_time_naive = out["exit_time"].dt.tz_localize(None) if out["exit_time"].dt.tz is not None else out["exit_time"]
    monthly = out.groupby(exit_time_naive.dt.to_period("M"))["net_pnl"].sum()
    yearly = out.groupby(exit_time_naive.dt.to_period("Y"))["net_pnl"].sum()
    max_drawdown_pct = float(equity_curve["drawdown_pct"].max()) if not equity_curve.empty and "drawdown_pct" in equity_curve else 0.0
    net_profit = float(pnls.sum())
    final_capital = float(initial_capital + net_profit)
    positive_months = monthly[monthly > 0]
    monthly_profit_concentration_pct = (
        float(positive_months.max() / net_profit * 100) if net_profit > 0 and len(positive_months) else 100.0 if net_profit > 0 else 0.0
    )
    r_multiples = out["r_multiple"].astype(float) if "r_multiple" in out.columns else pd.Series(dtype=float)
    r_distribution = (
        {
            "count": int(r_multiples.count()),
            "mean": float(r_multiples.mean()),
            "std": float(r_multiples.std(ddof=0)),
            "min": float(r_multiples.min()),
            "p25": float(r_multiples.quantile(0.25)),
            "median": float(r_multiples.quantile(0.50)),
            "p75": float(r_multiples.quantile(0.75)),
            "max": float(r_multiples.max()),
        }
        if len(r_multiples)
        else {}
    )

    return {
        "initial_capital": float(initial_capital),
        "final_capital": final_capital,
        "net_profit": net_profit,
        "total_return_pct": float(net_profit / initial_capital * 100),
        "max_drawdown_pct": max_drawdown_pct,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0,
        "winrate_pct": float((pnls > 0).mean() * 100),
        "average_win": float(wins.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.mean()) if len(losses) else 0.0,
        "expectancy": float(pnls.mean()),
        "gain_loss_ratio": float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else 0.0,
        "trade_count": int(len(out)),
        "trades_per_day_avg": float(out.groupby(out["entry_time"].dt.date).size().mean()),
        "best_day": float(daily.max()) if len(daily) else 0.0,
        "worst_day": float(daily.min()) if len(daily) else 0.0,
        "best_month": float(monthly.max()) if len(monthly) else 0.0,
        "worst_month": float(monthly.min()) if len(monthly) else 0.0,
        "performance_by_month": {str(k): float(v) for k, v in monthly.items()},
        "performance_by_year": {str(k): float(v) for k, v in yearly.items()},
        "monthly_stability_pct": float((monthly > 0).mean() * 100) if len(monthly) else 0.0,
        "monthly_profit_concentration_pct": monthly_profit_concentration_pct,
        "r_multiple_distribution": r_distribution,
        "max_loss_streak": _max_loss_streak(pnls),
        "average_holding_minutes": float(np.nan_to_num(out["holding_minutes"].astype(float).mean(), nan=0.0)),
    }


def metrics_frame(metrics: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for key, value in metrics.items():
        if isinstance(value, dict):
            continue
        rows.append({"metric": key, "value": value})
    return pd.DataFrame(rows)
