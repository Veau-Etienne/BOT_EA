from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MonteCarloResult:
    simulations: int
    median_final_equity: float
    p05_final_equity: float
    p95_final_equity: float
    median_max_drawdown_pct: float
    p95_max_drawdown_pct: float
    worst_final_equity: float
    worst_max_drawdown_pct: float
    risk_of_ruin_pct: float
    risk_of_ruin_by_threshold_pct: dict[str, float]
    recommended_risk_per_trade_pct: float


def _max_drawdown_pct(equity: np.ndarray) -> float:
    peaks = np.maximum.accumulate(equity)
    drawdowns = (peaks - equity) / peaks * 100
    return float(np.max(drawdowns))


def run_monte_carlo(
    trades: pd.DataFrame,
    initial_capital: float,
    simulations: int = 1000,
    ruin_drawdown_pct: float = 5.0,
    ruin_thresholds_pct: Sequence[float] = (5.0, 8.0, 10.0, 15.0),
    seed: int = 42,
) -> MonteCarloResult:
    thresholds_input = tuple(sorted({float(ruin_drawdown_pct), *[float(threshold) for threshold in ruin_thresholds_pct]}))
    if trades.empty:
        thresholds = {f"{threshold:.0f}%": 0.0 for threshold in thresholds_input}
        return MonteCarloResult(simulations, initial_capital, initial_capital, initial_capital, 0.0, 0.0, initial_capital, 0.0, 0.0, thresholds, 0.0)

    pnls = trades["net_pnl"].astype(float).to_numpy()
    rng = np.random.default_rng(seed)
    final_equities = []
    max_drawdowns = []
    ruin_counts = {float(threshold): 0 for threshold in thresholds_input}
    for _ in range(simulations):
        shuffled = rng.permutation(pnls)
        equity = initial_capital + np.cumsum(shuffled)
        full_curve = np.insert(equity, 0, initial_capital)
        dd = _max_drawdown_pct(full_curve)
        final_equities.append(float(full_curve[-1]))
        max_drawdowns.append(dd)
        for threshold in ruin_counts:
            if dd >= threshold:
                ruin_counts[threshold] += 1

    p95_dd = float(np.percentile(max_drawdowns, 95))
    if p95_dd <= 5:
        recommended_risk = 0.5
    elif p95_dd <= 10:
        recommended_risk = 0.25
    elif p95_dd <= 15:
        recommended_risk = 0.10
    else:
        recommended_risk = 0.0
    if len(pnls) < 30:
        recommended_risk = 0.0
    elif len(pnls) < 100:
        recommended_risk = min(recommended_risk, 0.10)

    return MonteCarloResult(
        simulations=simulations,
        median_final_equity=float(np.percentile(final_equities, 50)),
        p05_final_equity=float(np.percentile(final_equities, 5)),
        p95_final_equity=float(np.percentile(final_equities, 95)),
        median_max_drawdown_pct=float(np.percentile(max_drawdowns, 50)),
        p95_max_drawdown_pct=p95_dd,
        worst_final_equity=float(np.min(final_equities)),
        worst_max_drawdown_pct=float(np.max(max_drawdowns)),
        risk_of_ruin_pct=float(ruin_counts.get(float(ruin_drawdown_pct), 0) / simulations * 100),
        risk_of_ruin_by_threshold_pct={f"{threshold:.0f}%": float(count / simulations * 100) for threshold, count in ruin_counts.items()},
        recommended_risk_per_trade_pct=recommended_risk,
    )
