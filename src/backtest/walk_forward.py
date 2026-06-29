from __future__ import annotations

from typing import Any

import pandas as pd

from src.backtest.engine import BacktestConfig, BacktestEngine
from src.backtest.execution import AssetSpec
from src.backtest.metrics import calculate_metrics
from src.backtest.validation import robustness_score
from src.optimization.grid_search import run_grid_search
from src.strategies.base import BaseStrategy


def _scalar_metrics(metrics: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items() if not isinstance(value, dict)}


def _degradation(train_value: float, test_value: float) -> float:
    if train_value <= 0:
        return 0.0 if test_value >= train_value else 100.0
    return max(0.0, (train_value - test_value) / abs(train_value) * 100.0)


def _fold_verdict(test_metrics: dict[str, Any], return_degradation_pct: float) -> str:
    if (
        test_metrics["trade_count"] == 0
        or test_metrics["expectancy"] <= 0
        or test_metrics["profit_factor"] < 1.0
        or test_metrics["max_drawdown_pct"] >= 12.0
    ):
        return "rejeté"
    if test_metrics["trade_count"] < 20:
        return "fragile"
    if (
        test_metrics["profit_factor"] > 1.10
        and test_metrics["expectancy"] > 0
        and test_metrics["max_drawdown_pct"] < 8.0
        and return_degradation_pct <= 50.0
    ):
        return "OK"
    return "fragile"


def walk_forward_grid_search(
    data: pd.DataFrame,
    strategy_cls: type[BaseStrategy],
    base_strategy_config: dict[str, Any],
    param_grid: dict[str, list[Any]],
    backtest_config: BacktestConfig,
    asset: AssetSpec,
    folds: int = 3,
    objective: str = "profit_factor",
) -> pd.DataFrame:
    if folds < 1:
        raise ValueError("folds must be >= 1")
    if len(data) < folds * 20:
        raise ValueError("not enough data for walk-forward")

    fold_size = len(data) // (folds + 1)
    rows: list[dict[str, Any]] = []
    for fold in range(folds):
        train_start = 0
        train_end = fold_size * (fold + 1)
        test_start = train_end
        test_end = min(test_start + fold_size, len(data))
        train = data.iloc[train_start:train_end]
        test = data.iloc[test_start:test_end]
        if train.empty or test.empty:
            continue

        search = run_grid_search(train, strategy_cls, base_strategy_config, param_grid, backtest_config, asset, objective)
        if search.empty:
            continue
        best_params = {key: search.iloc[0][key] for key in param_grid.keys()}
        train_metrics = {key: search.iloc[0][key] for key in search.columns if key not in param_grid and not isinstance(search.iloc[0][key], dict)}
        strategy = strategy_cls({**base_strategy_config, **best_params})
        test_result = BacktestEngine(backtest_config, asset).run(test, strategy)
        test_metrics = calculate_metrics(test_result.trades, test_result.equity_curve, backtest_config.initial_capital)
        train_return = float(train_metrics.get("total_return_pct", 0.0))
        test_return = float(test_metrics.get("total_return_pct", 0.0))
        train_pf = float(train_metrics.get("profit_factor", 0.0))
        test_pf = float(test_metrics.get("profit_factor", 0.0))
        return_degradation_pct = _degradation(train_return, test_return)
        pf_degradation_pct = _degradation(train_pf if train_pf != float("inf") else 999.0, test_pf if test_pf != float("inf") else 999.0)
        rows.append(
            {
                "fold": fold + 1,
                "train_start": str(train.index.min()),
                "train_end": str(train.index.max()),
                "test_start": str(test.index.min()),
                "test_end": str(test.index.max()),
                **{f"param_{k}": v for k, v in best_params.items()},
                **{f"train_{k}": v for k, v in train_metrics.items()},
                **_scalar_metrics(test_metrics, "test"),
                "return_degradation_pct": return_degradation_pct,
                "profit_factor_degradation_pct": pf_degradation_pct,
                "test_robustness_score": robustness_score(test_metrics),
                "verdict": _fold_verdict(test_metrics, return_degradation_pct),
            }
        )
    return pd.DataFrame(rows)
