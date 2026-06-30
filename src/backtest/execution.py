from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from src.strategies.base import Direction, StrategySignal


ExitReason = Literal["stop_loss", "take_profit", "force_flat", "end_of_backtest"]


@dataclass(frozen=True)
class AssetSpec:
    symbol: str
    point: float
    contract_size: float


@dataclass
class Position:
    side: Direction
    entry_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    lots: float
    risk_amount: float
    initial_r: float
    metadata: dict[str, Any] = field(default_factory=dict)


def side_sign(side: Direction) -> int:
    return 1 if side == "long" else -1


def entry_price(mid_price: float, side: Direction, spread_points: float, slippage_points: float, point: float) -> float:
    half_spread = spread_points * point / 2
    slippage = slippage_points * point
    return mid_price + half_spread + slippage if side == "long" else mid_price - half_spread - slippage


def exit_price(mid_price: float, side: Direction, spread_points: float, slippage_points: float, point: float) -> float:
    half_spread = spread_points * point / 2
    slippage = slippage_points * point
    return mid_price - half_spread - slippage if side == "long" else mid_price + half_spread + slippage


def position_size_lots(
    equity: float,
    risk_per_trade_pct: float,
    entry: float,
    stop_loss: float,
    asset: AssetSpec,
) -> tuple[float, float]:
    price_risk = abs(entry - stop_loss)
    if price_risk <= 0:
        return 0.0, 0.0
    risk_amount = equity * risk_per_trade_pct / 100
    risk_per_lot = price_risk * asset.contract_size
    lots = risk_amount / risk_per_lot
    return max(0.0, lots), risk_amount


def create_position(
    signal: StrategySignal,
    mid_price: float,
    equity: float,
    risk_per_trade_pct: float,
    asset: AssetSpec,
    spread_points: float,
    slippage_points: float,
    entry_time: pd.Timestamp | None = None,
    entry_mode: str = "bar_close",
) -> Position | None:
    price = entry_price(mid_price, signal.direction, spread_points, slippage_points, asset.point)
    lots, risk_amount = position_size_lots(equity, risk_per_trade_pct, price, signal.stop_loss, asset)
    if lots <= 0 or signal.stop_loss == price:
        return None
    metadata = dict(signal.metadata)
    metadata["signal_timestamp"] = signal.timestamp
    metadata["entry_mode"] = entry_mode
    return Position(
        side=signal.direction,
        entry_time=entry_time if entry_time is not None else signal.timestamp,
        entry_price=price,
        stop_loss=float(signal.stop_loss),
        take_profit=float(signal.take_profit),
        lots=lots,
        risk_amount=risk_amount,
        initial_r=abs(price - float(signal.stop_loss)),
        metadata=metadata,
    )


def close_position(
    position: Position,
    exit_time: pd.Timestamp,
    exit_mid_price: float,
    reason: ExitReason,
    asset: AssetSpec,
    spread_points: float,
    slippage_points: float,
    commission_per_lot_round_turn: float,
) -> dict[str, Any]:
    price = exit_price(exit_mid_price, position.side, spread_points, slippage_points, asset.point)
    gross_pnl = (price - position.entry_price) * side_sign(position.side) * position.lots * asset.contract_size
    commission = commission_per_lot_round_turn * position.lots
    net_pnl = gross_pnl - commission
    return {
        "strategy": position.metadata.get("strategy"),
        "signal_timestamp": position.metadata.get("signal_timestamp"),
        "entry_mode": position.metadata.get("entry_mode"),
        "entry_time": position.entry_time,
        "exit_time": exit_time,
        "side": position.side,
        "entry_price": position.entry_price,
        "exit_price": price,
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "lots": position.lots,
        "risk_amount": position.risk_amount,
        "gross_pnl": gross_pnl,
        "commission": commission,
        "net_pnl": net_pnl,
        "r_multiple": net_pnl / position.risk_amount if position.risk_amount else 0.0,
        "exit_reason": reason,
        "holding_minutes": (exit_time - position.entry_time).total_seconds() / 60,
    }


def maybe_move_trailing_stop(position: Position, row: pd.Series) -> None:
    if not position.metadata.get("trailing_enabled"):
        return
    start_r = float(position.metadata.get("trailing_start_r", 1.0))
    if position.side == "long":
        if float(row["high"]) - position.entry_price >= start_r * position.initial_r:
            position.stop_loss = max(position.stop_loss, position.entry_price)
    else:
        if position.entry_price - float(row["low"]) >= start_r * position.initial_r:
            position.stop_loss = min(position.stop_loss, position.entry_price)
