from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.backtest.execution import AssetSpec, Position, close_position, create_position, maybe_move_trailing_stop
from src.backtest.portfolio import Portfolio
from src.strategies.base import BaseStrategy
from src.utils.time import parse_hhmm


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100000.0
    risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 1.0
    max_total_drawdown_pct: float = 5.0
    max_trades_per_day: int = 3
    max_consecutive_losses: int = 3
    no_overnight: bool = True
    force_flat_time: str = "18:00"
    spread_points: float = 20.0
    slippage_points: float = 5.0
    commission_per_lot_round_turn: float = 7.0
    diagnostic_full_sample: bool = False


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    stopped_reason: str | None


class BacktestEngine:
    def __init__(self, config: BacktestConfig, asset: AssetSpec):
        self.config = config
        self.asset = asset

    def run(self, data: pd.DataFrame, strategy: BaseStrategy) -> BacktestResult:
        prepared = strategy.prepare(data)
        portfolio = Portfolio.create(self.config.initial_capital)
        open_position: Position | None = None
        trades: list[dict[str, Any]] = []
        equity_points: list[dict[str, Any]] = []
        stopped_reason: str | None = None

        current_day: object | None = None
        day_start_equity = portfolio.equity
        trades_today = 0
        consecutive_losses_today = 0
        blocked_day: object | None = None
        force_flat_at = parse_hhmm(self.config.force_flat_time)

        for i, (ts, row) in enumerate(prepared.iterrows()):
            if current_day != ts.date():
                current_day = ts.date()
                day_start_equity = portfolio.equity
                trades_today = 0
                consecutive_losses_today = 0
                blocked_day = None

            spread_points = float(row["spread"]) if "spread" in prepared.columns and pd.notna(row.get("spread")) else self.config.spread_points

            if open_position is not None:
                maybe_move_trailing_stop(open_position, row)
                exit_mid: float | None = None
                exit_reason: str | None = None
                if open_position.side == "long":
                    hit_stop = float(row["low"]) <= open_position.stop_loss
                    hit_target = float(row["high"]) >= open_position.take_profit
                    if hit_stop:
                        exit_mid, exit_reason = open_position.stop_loss, "stop_loss"
                    elif hit_target:
                        exit_mid, exit_reason = open_position.take_profit, "take_profit"
                else:
                    hit_stop = float(row["high"]) >= open_position.stop_loss
                    hit_target = float(row["low"]) <= open_position.take_profit
                    if hit_stop:
                        exit_mid, exit_reason = open_position.stop_loss, "stop_loss"
                    elif hit_target:
                        exit_mid, exit_reason = open_position.take_profit, "take_profit"

                if exit_reason is None and self.config.no_overnight and ts.time() >= force_flat_at:
                    exit_mid, exit_reason = float(row["close"]), "force_flat"

                if exit_reason is not None and exit_mid is not None:
                    trade = close_position(
                        open_position,
                        ts,
                        exit_mid,
                        exit_reason,  # type: ignore[arg-type]
                        self.asset,
                        spread_points,
                        self.config.slippage_points,
                        self.config.commission_per_lot_round_turn,
                    )
                    trades.append(trade)
                    portfolio.apply_pnl(float(trade["net_pnl"]))
                    consecutive_losses_today = consecutive_losses_today + 1 if trade["net_pnl"] < 0 else 0
                    if consecutive_losses_today >= self.config.max_consecutive_losses:
                        blocked_day = current_day
                    open_position = None

            daily_pnl = portfolio.equity - day_start_equity
            daily_loss_limit = self.config.initial_capital * self.config.max_daily_loss_pct / 100
            if not self.config.diagnostic_full_sample and daily_pnl <= -daily_loss_limit:
                blocked_day = current_day

            if not self.config.diagnostic_full_sample and portfolio.drawdown_pct >= self.config.max_total_drawdown_pct:
                stopped_reason = "max_total_drawdown"
                break

            equity_points.append({"time": ts, "equity": portfolio.equity, "drawdown_pct": portfolio.drawdown_pct})

            if open_position is not None:
                continue
            if blocked_day == current_day:
                continue
            if self.config.no_overnight and ts.time() >= force_flat_at:
                continue
            max_trades = strategy.max_trades_per_day or self.config.max_trades_per_day
            if trades_today >= max_trades:
                continue

            signal = strategy.generate_signal(i, prepared)
            if signal is None:
                continue
            risk_pct = min(strategy.risk_per_trade_pct, self.config.risk_per_trade_pct)
            position = create_position(
                signal,
                float(row["close"]),
                portfolio.equity,
                risk_pct,
                self.asset,
                spread_points,
                self.config.slippage_points,
            )
            if position is not None:
                open_position = position
                trades_today += 1

        if open_position is not None and len(prepared):
            ts = prepared.index[-1]
            row = prepared.iloc[-1]
            spread_points = float(row["spread"]) if "spread" in prepared.columns and pd.notna(row.get("spread")) else self.config.spread_points
            trade = close_position(
                open_position,
                ts,
                float(row["close"]),
                "end_of_backtest",
                self.asset,
                spread_points,
                self.config.slippage_points,
                self.config.commission_per_lot_round_turn,
            )
            trades.append(trade)
            portfolio.apply_pnl(float(trade["net_pnl"]))

        return BacktestResult(
            trades=pd.DataFrame(trades),
            equity_curve=pd.DataFrame(equity_points).set_index("time") if equity_points else pd.DataFrame(columns=["equity", "drawdown_pct"]),
            stopped_reason=stopped_reason,
        )
