from __future__ import annotations

from itertools import product
from typing import Any

import pandas as pd

from src.backtest.engine import BacktestConfig, BacktestEngine
from src.backtest.execution import AssetSpec
from src.backtest.metrics import calculate_metrics
from src.backtest.validation import robustness_score
from src.strategies.base import BaseStrategy


def parameter_combinations(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(grid.keys())
    values = [grid[key] for key in keys]
    return [dict(zip(keys, combo)) for combo in product(*values)]


def run_grid_search(
    data: pd.DataFrame,
    strategy_cls: type[BaseStrategy],
    base_strategy_config: dict[str, Any],
    param_grid: dict[str, list[Any]],
    backtest_config: BacktestConfig,
    asset: AssetSpec,
    objective: str = "profit_factor",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for params in parameter_combinations(param_grid):
        strategy_config = {**base_strategy_config, **params}
        result = BacktestEngine(backtest_config, asset).run(data, strategy_cls(strategy_config))
        metrics = calculate_metrics(result.trades, result.equity_curve, backtest_config.initial_capital)
        warnings: list[str] = []
        if metrics["trade_count"] < 100:
            warnings.append("too_few_trades")
        if metrics["net_profit"] > 0 and metrics["monthly_profit_concentration_pct"] > 40:
            warnings.append("profit_concentrated")
        if metrics["monthly_stability_pct"] < 50 and metrics["trade_count"] > 0:
            warnings.append("weak_monthly_stability")
        rows.append(
            {
                **params,
                **metrics,
                "robustness_score": robustness_score(metrics),
                "overfit_warnings": ";".join(warnings),
                "stopped_reason": result.stopped_reason,
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    ascending = objective in {"max_drawdown_pct"}
    return out.sort_values(objective, ascending=ascending).reset_index(drop=True)
