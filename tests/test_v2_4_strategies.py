"""Tests V2.4 — XAU M15/M30 new strategy families."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.strategies import STRATEGY_REGISTRY
from src.utils.config import load_yaml, strategy_config

ROOT = Path(__file__).resolve().parents[1]


def _load_cfg(name: str) -> dict:
    return strategy_config(load_yaml(ROOT / "config/strategies.yaml"), name)


def _sample_xau_m15() -> pd.DataFrame:
    """Synthetic XAUUSD M15 data over 5 trading days."""
    # Use week days only, London session
    index = pd.date_range("2025-01-07 08:00", periods=300, freq="15min", tz="Europe/Paris")
    price = 2000.0
    closes = []
    for k in range(len(index)):
        price += ((-1) ** k) * 2.0 + 0.5
        closes.append(price)
    closes = pd.Series(closes, index=index)
    return pd.DataFrame(
        {
            "open": closes - 1.0,
            "high": closes + 5.0,
            "low": closes - 5.0,
            "close": closes,
            "tick_volume": 100,
            "spread": 30,
        },
        index=index,
    )


def _sample_xau_m30() -> pd.DataFrame:
    """Synthetic XAUUSD M30 data."""
    index = pd.date_range("2025-01-07 08:00", periods=150, freq="30min", tz="Europe/Paris")
    price = 2000.0
    closes = []
    for k in range(len(index)):
        price += ((-1) ** k) * 3.0 + 0.5
        closes.append(price)
    closes = pd.Series(closes, index=index)
    return pd.DataFrame(
        {
            "open": closes - 1.5,
            "high": closes + 8.0,
            "low": closes - 8.0,
            "close": closes,
            "tick_volume": 100,
            "spread": 30,
        },
        index=index,
    )


# ── Registration ────────────────────────────────────────────────────────────

def test_all_v2_4_strategies_registered() -> None:
    names = [
        "xau_liquidity_sweep_reversal",
        "xau_m30_htf_trend_pullback",
        "xau_volatility_compression_retest",
        "xau_m30_session_momentum_continuation",
    ]
    for name in names:
        assert name in STRATEGY_REGISTRY, f"Strategy not registered: {name}"


def test_all_v2_4_strategies_importable() -> None:
    from src.strategies.xau_liquidity_sweep_reversal import XAULiquiditySweepReversal
    from src.strategies.xau_m30_htf_trend_pullback import XAUm30HTFTrendPullback
    from src.strategies.xau_m30_session_momentum_continuation import XAUm30SessionMomentumContinuation
    from src.strategies.xau_volatility_compression_retest import XAUVolatilityCompressionRetest

    assert XAULiquiditySweepReversal.name == "xau_liquidity_sweep_reversal"
    assert XAUm30HTFTrendPullback.name == "xau_m30_htf_trend_pullback"
    assert XAUVolatilityCompressionRetest.name == "xau_volatility_compression_retest"
    assert XAUm30SessionMomentumContinuation.name == "xau_m30_session_momentum_continuation"


# ── Config ──────────────────────────────────────────────────────────────────

def test_v2_4_strategies_in_config() -> None:
    names = [
        "xau_liquidity_sweep_reversal",
        "xau_m30_htf_trend_pullback",
        "xau_volatility_compression_retest",
        "xau_m30_session_momentum_continuation",
    ]
    for name in names:
        cfg = _load_cfg(name)
        assert "symbol" in cfg, f"No symbol in config for {name}"
        assert cfg["symbol"] == "XAUUSD", f"Expected XAUUSD symbol for {name}"


# ── Prepare / no lookahead ───────────────────────────────────────────────────

@pytest.mark.parametrize("strategy_name,data_fn", [
    ("xau_liquidity_sweep_reversal", _sample_xau_m15),
    ("xau_m30_htf_trend_pullback", _sample_xau_m30),
    ("xau_volatility_compression_retest", _sample_xau_m15),
    ("xau_m30_session_momentum_continuation", _sample_xau_m30),
])
def test_prepare_does_not_lookahead(strategy_name: str, data_fn) -> None:
    cfg = _load_cfg(strategy_name)
    strategy = STRATEGY_REGISTRY[strategy_name](cfg)
    data = data_fn()
    changed = data.copy()
    split = len(data) * 3 // 4  # 75% cutoff, guaranteed within bounds
    changed.iloc[split:, changed.columns.get_loc("close")] += 5000.0

    prepared_a = strategy.prepare(data)
    prepared_b = strategy.prepare(changed)

    # Indicators up to split // 2 must be identical (well before the change)
    check_up_to = split // 2
    for col in prepared_a.columns:
        if col not in ("open", "high", "low", "close", "spread", "tick_volume"):
            pd.testing.assert_series_equal(
                prepared_a[col].iloc[:check_up_to],
                prepared_b[col].iloc[:check_up_to],
                check_names=False,
                obj=f"{strategy_name}.{col}[:{check_up_to}]",
            )


# ── Signal validity ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("strategy_name,data_fn", [
    ("xau_liquidity_sweep_reversal", _sample_xau_m15),
    ("xau_m30_htf_trend_pullback", _sample_xau_m30),
    ("xau_volatility_compression_retest", _sample_xau_m15),
    ("xau_m30_session_momentum_continuation", _sample_xau_m30),
])
def test_signals_have_valid_sl_tp(strategy_name: str, data_fn) -> None:
    cfg = _load_cfg(strategy_name)
    strategy = STRATEGY_REGISTRY[strategy_name](cfg)
    data = data_fn()
    prepared = strategy.prepare(data)
    signals = [strategy.generate_signal(i, prepared) for i in range(len(prepared))]
    signals = [s for s in signals if s is not None]

    for sig in signals:
        assert sig.stop_loss is not None, f"{strategy_name}: SL is None"
        assert sig.take_profit is not None, f"{strategy_name}: TP is None"
        risk = abs(float(sig.take_profit) - float(sig.stop_loss))
        assert risk > 0, f"{strategy_name}: SL == TP (zero risk)"
        if sig.direction == "long":
            assert float(sig.take_profit) > float(sig.stop_loss), f"{strategy_name}: long TP <= SL"
        else:
            assert float(sig.take_profit) < float(sig.stop_loss), f"{strategy_name}: short TP >= SL"


# ── No overnight: signals only during configured sessions ────────────────────

def test_liquidity_sweep_no_signal_outside_session() -> None:
    cfg = _load_cfg("xau_liquidity_sweep_reversal")
    strategy = STRATEGY_REGISTRY["xau_liquidity_sweep_reversal"](cfg)
    # Build data with timestamps only in 00:00-07:59 (outside session)
    index = pd.date_range("2025-01-07 00:00", periods=100, freq="15min", tz="Europe/Paris")
    data = pd.DataFrame(
        {
            "open": [2000.0] * 100,
            "high": [2010.0] * 100,
            "low": [1990.0] * 100,
            "close": [2005.0] * 100,
            "spread": [30] * 100,
        },
        index=index,
    )
    prepared = strategy.prepare(data)
    signals = [strategy.generate_signal(i, prepared) for i in range(len(prepared))]
    assert all(s is None for s in signals), "Should produce no signal outside configured sessions"


# ── Exploration matrix script importable ────────────────────────────────────

def test_exploration_matrix_script_importable() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_exploration_matrix",
        ROOT / "scripts/run_exploration_matrix.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # Just import, don't execute main()
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert hasattr(module, "main")
