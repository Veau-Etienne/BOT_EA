from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.backtest.engine import BacktestConfig
from src.backtest.execution import AssetSpec


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def strategy_config(config: dict[str, Any], strategy_name: str) -> dict[str, Any]:
    strategies = config.get("strategies", {})
    if strategy_name not in strategies:
        raise KeyError(f"Unknown strategy '{strategy_name}'. Available: {sorted(strategies)}")
    return dict(strategies[strategy_name])


def resolve_asset_spec(assets_config: dict[str, Any], symbol: str) -> AssetSpec:
    assets = assets_config.get("assets", {})
    symbol_upper = symbol.upper()
    for name, spec in assets.items():
        aliases = [name, *spec.get("aliases", [])]
        if symbol_upper in {alias.upper() for alias in aliases}:
            return AssetSpec(
                symbol=name,
                point=float(spec["point"]),
                contract_size=float(spec["contract_size"]),
            )
    raise KeyError(f"Unknown asset '{symbol}'. Add it to config/assets.yaml.")


def build_backtest_config(risk_config: dict[str, Any], strategy_cfg: dict[str, Any] | None = None) -> BacktestConfig:
    strategy_cfg = strategy_cfg or {}
    account = risk_config.get("account", {})
    internal = risk_config.get("internal_rules", {})
    costs = risk_config.get("costs", {})
    return BacktestConfig(
        initial_capital=float(account.get("initial_capital", 100000)),
        risk_per_trade_pct=float(strategy_cfg.get("risk_per_trade_pct", internal.get("risk_per_trade_pct", 0.25))),
        max_daily_loss_pct=float(internal.get("max_daily_loss_pct", 1.0)),
        max_total_drawdown_pct=float(internal.get("max_total_drawdown_pct", 5.0)),
        max_trades_per_day=int(strategy_cfg.get("max_trades_per_day", internal.get("max_trades_per_day", 3))),
        max_consecutive_losses=int(internal.get("max_consecutive_losses", 3)),
        no_overnight=bool(internal.get("no_overnight", True)),
        force_flat_time=str(internal.get("force_flat_time", "18:00")),
        spread_points=float(costs.get("spread_points", 20)),
        slippage_points=float(costs.get("slippage_points", 5)),
        commission_per_lot_round_turn=float(costs.get("commission_per_lot_round_turn", 7.0)),
    )
