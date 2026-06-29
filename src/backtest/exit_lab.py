from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from src.backtest.execution import AssetSpec, entry_price, exit_price, side_sign
from src.backtest.metrics import calculate_metrics
from src.strategies.base import BaseStrategy, Direction
from src.utils.time import parse_hhmm


@dataclass(frozen=True)
class ExitPolicy:
    name: str
    kind: str
    params: dict[str, Any]


@dataclass(frozen=True)
class EntryCandidate:
    entry_time: pd.Timestamp
    side: Direction
    entry_mid: float
    entry_price: float
    original_stop: float
    original_target: float
    lots: float
    risk_amount: float
    risk_price: float
    spread_points: float
    atr: float | None
    metadata: dict[str, Any]


def default_exit_policies(spread_p75: float | None = None, spread_p90: float | None = None, fixed_spread: float = 50.0) -> list[ExitPolicy]:
    policies = [
        ExitPolicy("original_sl_1_5atr_tp_2_5atr", "original", {}),
        *[ExitPolicy(f"tp_{r:g}r", "tp_r", {"tp_r": r}) for r in [1.0, 1.25, 1.5, 2.0]],
        *[ExitPolicy(f"break_even_at_{r:g}r", "break_even", {"be_trigger_r": r}) for r in [0.5, 0.75, 1.0]],
        ExitPolicy("partial_50_at_0_5r_rest_original", "partial", {"partial_trigger_r": 0.5, "partial_fraction": 0.5, "rest": "original"}),
        ExitPolicy("partial_50_at_1r_rest_original", "partial", {"partial_trigger_r": 1.0, "partial_fraction": 0.5, "rest": "original"}),
        ExitPolicy("partial_50_at_1r_rest_trailing_atr", "partial", {"partial_trigger_r": 1.0, "partial_fraction": 0.5, "rest": "trailing_atr", "trail_atr_mult": 1.0}),
        ExitPolicy("trailing_atr_1_after_0_5r", "trailing_atr", {"trail_trigger_r": 0.5, "trail_atr_mult": 1.0}),
        ExitPolicy("trailing_atr_1_after_1r", "trailing_atr", {"trail_trigger_r": 1.0, "trail_atr_mult": 1.0}),
        ExitPolicy("trailing_atr_1_5_after_1r", "trailing_atr", {"trail_trigger_r": 1.0, "trail_atr_mult": 1.5}),
        ExitPolicy("trailing_structure_after_1r", "trailing_structure", {"trail_trigger_r": 1.0, "lookback": 3}),
        ExitPolicy("time_stop_45m_if_not_0_5r", "time_stop", {"minutes": 45, "min_mfe_r": 0.5}),
        ExitPolicy("time_stop_60m_if_not_0_5r", "time_stop", {"minutes": 60, "min_mfe_r": 0.5}),
        ExitPolicy("time_stop_90m_regardless", "time_stop", {"minutes": 90, "regardless": True}),
        ExitPolicy("time_stop_120m_regardless", "time_stop", {"minutes": 120, "regardless": True}),
        ExitPolicy("force_flat_london_end", "session_exit", {"session_end": "11:30"}),
        ExitPolicy("force_flat_us_end", "session_exit", {"session_end": "18:00"}),
        ExitPolicy("no_new_trade_last_60m_session", "entry_filter", {"no_new_last_minutes": 60}),
    ]
    if spread_p75 is not None:
        policies.append(ExitPolicy("spread_filter_p75", "spread_filter", {"max_spread": float(spread_p75)}))
    if spread_p90 is not None:
        policies.append(ExitPolicy("spread_filter_p90", "spread_filter", {"max_spread": float(spread_p90)}))
    policies.append(ExitPolicy(f"spread_filter_fixed_{fixed_spread:g}", "spread_filter", {"max_spread": fixed_spread}))
    return policies


def collect_entries(
    data: pd.DataFrame,
    strategy: BaseStrategy,
    asset: AssetSpec,
    initial_capital: float,
    risk_per_trade_pct: float,
    spread_points_default: float,
    slippage_points: float,
) -> tuple[list[EntryCandidate], pd.DataFrame]:
    prepared = strategy.prepare(data)
    entries: list[EntryCandidate] = []
    current_day: object | None = None
    trades_today = 0
    max_trades = strategy.max_trades_per_day or 3
    risk_amount = initial_capital * risk_per_trade_pct / 100

    for i, (ts, row) in enumerate(prepared.iterrows()):
        if current_day != ts.date():
            current_day = ts.date()
            trades_today = 0
        if trades_today >= max_trades:
            continue

        signal = strategy.generate_signal(i, prepared)
        if signal is None:
            continue

        spread = float(row["spread"]) if "spread" in prepared.columns and pd.notna(row.get("spread")) else spread_points_default
        entry_mid = float(row["close"])
        price = entry_price(entry_mid, signal.direction, spread, slippage_points, asset.point)
        risk_price = abs(price - float(signal.stop_loss))
        if risk_price <= 0:
            continue
        lots = risk_amount / (risk_price * asset.contract_size)
        if lots <= 0:
            continue
        entries.append(
            EntryCandidate(
                entry_time=ts,
                side=signal.direction,
                entry_mid=entry_mid,
                entry_price=price,
                original_stop=float(signal.stop_loss),
                original_target=float(signal.take_profit),
                lots=lots,
                risk_amount=risk_amount,
                risk_price=risk_price,
                spread_points=spread,
                atr=float(row["atr"]) if "atr" in prepared.columns and pd.notna(row.get("atr")) else None,
                metadata=signal.metadata,
            )
        )
        trades_today += 1
    return entries, prepared


def _target_from_r(entry: EntryCandidate, r_multiple: float) -> float:
    return entry.entry_price + side_sign(entry.side) * entry.risk_price * r_multiple


def _favorable_r(entry: EntryCandidate, bar: pd.Series) -> float:
    if entry.side == "long":
        return (float(bar["high"]) - entry.entry_price) / entry.risk_price
    return (entry.entry_price - float(bar["low"])) / entry.risk_price


def _adverse_r(entry: EntryCandidate, bar: pd.Series) -> float:
    if entry.side == "long":
        return (entry.entry_price - float(bar["low"])) / entry.risk_price
    return (float(bar["high"]) - entry.entry_price) / entry.risk_price


def _price_for_r(entry: EntryCandidate, r_multiple: float) -> float:
    return entry.entry_price + side_sign(entry.side) * entry.risk_price * r_multiple


def _entry_allowed_by_policy(entry: EntryCandidate, policy: ExitPolicy) -> bool:
    if policy.kind == "spread_filter":
        return entry.spread_points <= float(policy.params["max_spread"])
    if policy.kind == "entry_filter":
        minutes = int(policy.params.get("no_new_last_minutes", 0))
        if minutes <= 0:
            return True
        hour_min = entry.entry_time.hour * 60 + entry.entry_time.minute
        london_end = 11 * 60 + 30
        us_end = 18 * 60
        if 8 * 60 <= hour_min <= london_end:
            return hour_min <= london_end - minutes
        if 14 * 60 + 30 <= hour_min <= us_end:
            return hour_min <= us_end - minutes
    return True


def _close_piece(entry: EntryCandidate, exit_mid: float, fraction: float, asset: AssetSpec, slippage_points: float) -> float:
    price = exit_price(exit_mid, entry.side, entry.spread_points, slippage_points, asset.point)
    return (price - entry.entry_price) * side_sign(entry.side) * entry.lots * fraction * asset.contract_size


def simulate_exit_policy(
    entries: list[EntryCandidate],
    data: pd.DataFrame,
    policy: ExitPolicy,
    asset: AssetSpec,
    initial_capital: float,
    slippage_points: float,
    commission_per_lot_round_turn: float,
    force_flat_time: str = "18:00",
    day_groups: dict[object, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    force_flat_at = parse_hhmm(force_flat_time)
    day_groups = day_groups or {day: day_df for day, day_df in data.groupby(data.index.date)}

    for entry in entries:
        if not _entry_allowed_by_policy(entry, policy):
            continue

        stop = entry.original_stop
        target = entry.original_target
        if policy.kind == "tp_r":
            target = _target_from_r(entry, float(policy.params["tp_r"]))

        day_bars = day_groups.get(entry.entry_time.date())
        if day_bars is None:
            continue
        bars = day_bars[(day_bars.index > entry.entry_time) & (day_bars.index.time <= force_flat_at)]
        if bars.empty:
            continue
        bar_index_values = bars.index
        highs = bars["high"].to_numpy()
        lows = bars["low"].to_numpy()
        closes = bars["close"].to_numpy()

        remaining_fraction = 1.0
        gross = 0.0
        partial_done = False
        be_active = False
        trailing_active = False
        max_mfe = 0.0
        max_mae = 0.0
        exit_reason: str | None = None
        exit_time = bar_index_values[-1]
        exit_mid = float(closes[-1])

        for bar_index in range(len(bars)):
            ts = bar_index_values[bar_index]
            high_value = float(highs[bar_index])
            low_value = float(lows[bar_index])
            close_value = float(closes[bar_index])
            if entry.side == "long":
                mfe = (high_value - entry.entry_price) / entry.risk_price
                mae = (entry.entry_price - low_value) / entry.risk_price
            else:
                mfe = (entry.entry_price - low_value) / entry.risk_price
                mae = (high_value - entry.entry_price) / entry.risk_price
            max_mfe = max(max_mfe, mfe)
            max_mae = max(max_mae, mae)

            if entry.side == "long":
                stop_hit = low_value <= stop
                target_hit = high_value >= target
            else:
                stop_hit = high_value >= stop
                target_hit = low_value <= target

            if stop_hit:
                exit_mid = stop
                exit_time = ts
                if be_active and abs(stop - entry.entry_price) < 1e-9:
                    exit_reason = "break_even"
                elif trailing_active:
                    exit_reason = "trailing_stop"
                else:
                    exit_reason = "stop_loss"
                gross += _close_piece(entry, exit_mid, remaining_fraction, asset, slippage_points)
                remaining_fraction = 0.0
                break

            if target_hit and policy.params.get("rest") != "trailing_atr":
                exit_mid = target
                exit_time = ts
                exit_reason = "take_profit"
                gross += _close_piece(entry, exit_mid, remaining_fraction, asset, slippage_points)
                remaining_fraction = 0.0
                break

            if policy.kind == "break_even" and not be_active and mfe >= float(policy.params["be_trigger_r"]):
                stop = entry.entry_price
                be_active = True

            if policy.kind in {"trailing_atr", "trailing_structure"} and not trailing_active and mfe >= float(policy.params.get("trail_trigger_r", 1.0)):
                trailing_active = True

            if policy.kind == "partial" and not partial_done and mfe >= float(policy.params["partial_trigger_r"]):
                fraction = float(policy.params.get("partial_fraction", 0.5))
                partial_mid = _price_for_r(entry, float(policy.params["partial_trigger_r"]))
                gross += _close_piece(entry, partial_mid, fraction, asset, slippage_points)
                remaining_fraction -= fraction
                partial_done = True
                if policy.params.get("rest") == "trailing_atr":
                    trailing_active = True

            if trailing_active:
                if policy.kind == "trailing_structure":
                    lookback = int(policy.params.get("lookback", 3))
                    start = max(0, bar_index - lookback)
                    if bar_index > start:
                        if entry.side == "long":
                            stop = max(stop, float(lows[start:bar_index].min()))
                        else:
                            stop = min(stop, float(highs[start:bar_index].max()))
                else:
                    atr_value = entry.atr or float(high_value - low_value)
                    mult = float(policy.params.get("trail_atr_mult", 1.0))
                    if entry.side == "long":
                        stop = max(stop, high_value - atr_value * mult)
                    else:
                        stop = min(stop, low_value + atr_value * mult)

            if policy.kind == "time_stop":
                holding = (ts - entry.entry_time).total_seconds() / 60
                should_exit = holding >= int(policy.params["minutes"])
                if should_exit and not policy.params.get("regardless", False):
                    should_exit = max_mfe < float(policy.params.get("min_mfe_r", 0.5))
                if should_exit:
                    exit_mid = close_value
                    exit_time = ts
                    exit_reason = "time_stop"
                    gross += _close_piece(entry, exit_mid, remaining_fraction, asset, slippage_points)
                    remaining_fraction = 0.0
                    break

            if policy.kind == "session_exit" and ts.time() >= parse_hhmm(str(policy.params["session_end"])):
                exit_mid = close_value
                exit_time = ts
                exit_reason = "session_exit"
                gross += _close_piece(entry, exit_mid, remaining_fraction, asset, slippage_points)
                remaining_fraction = 0.0
                break

        if remaining_fraction > 0:
            exit_reason = exit_reason or "force_flat"
            gross += _close_piece(entry, exit_mid, remaining_fraction, asset, slippage_points)

        commission = commission_per_lot_round_turn * entry.lots
        net = gross - commission
        rows.append(
            {
                "strategy": policy.name,
                "entry_time": entry.entry_time,
                "exit_time": exit_time,
                "side": entry.side,
                "entry_price": entry.entry_price,
                "exit_price": exit_price(exit_mid, entry.side, entry.spread_points, slippage_points, asset.point),
                "stop_loss": stop,
                "take_profit": target,
                "lots": entry.lots,
                "risk_amount": entry.risk_amount,
                "gross_pnl": gross,
                "commission": commission,
                "net_pnl": net,
                "r_multiple": net / entry.risk_amount if entry.risk_amount else 0.0,
                "exit_reason": exit_reason,
                "holding_minutes": (exit_time - entry.entry_time).total_seconds() / 60,
                "mfe_r": max_mfe,
                "mae_r": max_mae,
                "spread": entry.spread_points,
                "atr": entry.atr,
                "partial_done": partial_done,
            }
        )

    return pd.DataFrame(rows)


def equity_curve_from_trades(trades: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["equity", "drawdown_pct"])
    ordered = trades.sort_values("exit_time").copy()
    ordered["equity"] = initial_capital + ordered["net_pnl"].astype(float).cumsum()
    ordered["peak"] = ordered["equity"].cummax().clip(lower=initial_capital)
    ordered["drawdown_pct"] = (ordered["peak"] - ordered["equity"]) / ordered["peak"] * 100
    return ordered.set_index("exit_time")[["equity", "drawdown_pct"]]


def max_loss_streak(pnls: pd.Series) -> int:
    streak = 0
    best = 0
    for pnl in pnls:
        if pnl < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def simple_sharpe(pnls: pd.Series) -> float:
    std = float(pnls.std(ddof=0))
    if std <= 0:
        return 0.0
    return float(pnls.mean() / std * (len(pnls) ** 0.5))


def exit_policy_metrics(trades: pd.DataFrame, initial_capital: float) -> dict[str, Any]:
    metrics = calculate_metrics(trades, equity_curve_from_trades(trades, initial_capital), initial_capital)
    if trades.empty:
        metrics.update(
            {
                "sharpe_simple": 0.0,
                "break_even_pct": 0.0,
                "time_stop_pct": 0.0,
                "trailing_stop_pct": 0.0,
                "robust_exit_score": 0.0,
            }
        )
        return metrics

    pnls = trades["net_pnl"].astype(float)
    metrics["sharpe_simple"] = simple_sharpe(pnls)
    metrics["break_even_pct"] = float(((trades["exit_reason"] == "break_even") | (trades["r_multiple"].astype(float).abs() <= 0.05)).mean() * 100)
    metrics["time_stop_pct"] = float((trades["exit_reason"] == "time_stop").mean() * 100)
    metrics["trailing_stop_pct"] = float((trades["exit_reason"] == "trailing_stop").mean() * 100)
    metrics["robust_exit_score"] = robust_exit_score(metrics)
    return metrics


def robust_exit_score(metrics: dict[str, Any]) -> float:
    pf = min(float(metrics.get("profit_factor", 0.0)), 3.0)
    expectancy = float(metrics.get("expectancy", 0.0))
    trades = float(metrics.get("trade_count", 0.0))
    dd = float(metrics.get("max_drawdown_pct", 0.0))
    concentration = float(metrics.get("monthly_profit_concentration_pct", 100.0 if metrics.get("net_profit", 0.0) > 0 else 0.0))
    loss_streak = float(metrics.get("max_loss_streak", 0.0))

    score = 0.0
    score += max(0.0, (pf - 1.0) / 0.5 * 30.0)
    score += 20.0 if expectancy > 0 else max(-20.0, expectancy / 25.0)
    score += min(15.0, trades / 100.0 * 15.0)
    score += max(0.0, 15.0 - dd / 8.0 * 15.0)
    score += max(0.0, 10.0 - max(0.0, concentration - 40.0) / 60.0 * 10.0)
    score += max(0.0, 10.0 - loss_streak)
    return round(max(0.0, min(100.0, score)), 2)


def run_exit_lab(
    data: pd.DataFrame,
    strategy: BaseStrategy,
    asset: AssetSpec,
    initial_capital: float,
    risk_per_trade_pct: float,
    spread_points: float,
    slippage_points: float,
    commission_per_lot_round_turn: float,
    policies: list[ExitPolicy],
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[EntryCandidate]]:
    entries, _ = collect_entries(data, strategy, asset, initial_capital, risk_per_trade_pct, spread_points, slippage_points)
    rows: list[dict[str, Any]] = []
    trades_by_policy: dict[str, pd.DataFrame] = {}
    day_groups = {day: day_df[day_df.index.time <= pd.Timestamp("18:00").time()] for day, day_df in data.groupby(data.index.date)}
    for policy in policies:
        trades = simulate_exit_policy(
            entries,
            data,
            policy,
            asset,
            initial_capital,
            slippage_points,
            commission_per_lot_round_turn,
            day_groups=day_groups,
        )
        trades_by_policy[policy.name] = trades
        metrics = exit_policy_metrics(trades, initial_capital)
        rows.append(
            {
                "exit_policy": policy.name,
                "kind": policy.kind,
                **{key: value for key, value in metrics.items() if not isinstance(value, dict)},
                "performance_by_month": metrics.get("performance_by_month", {}),
                "performance_by_year": metrics.get("performance_by_year", {}),
            }
        )
    return pd.DataFrame(rows), trades_by_policy, entries
