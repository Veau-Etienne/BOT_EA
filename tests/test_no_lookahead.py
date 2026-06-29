from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.resampler import resample_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import load_yaml, strategy_config


ROOT = Path(__file__).resolve().parents[1]


def _strategy():
    cfg = strategy_config(load_yaml(ROOT / "config/strategies.yaml"), "nas_trend_pullback_exclude_monday")
    return STRATEGY_REGISTRY["nas_trend_pullback_exclude_monday"](cfg)


def _sample_data() -> pd.DataFrame:
    index = pd.date_range("2025-01-07 15:00", periods=260, freq="h", tz="Europe/Paris")
    close = pd.Series(range(10000, 10000 + len(index)), index=index, dtype=float)
    data = pd.DataFrame(
        {
            "open": close - 2.0,
            "high": close + 8.0,
            "low": close - 8.0,
            "close": close,
            "tick_volume": 100,
            "spread": 130,
        },
        index=index,
    )
    return data


def test_resampler_h1_left_labels_without_future_close() -> None:
    index = pd.date_range("2025-01-07 15:00", periods=8, freq="15min", tz="Europe/Paris")
    source = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6, 7, 8],
            "high": [2, 3, 4, 5, 6, 7, 8, 9],
            "low": [0, 1, 2, 3, 4, 5, 6, 7],
            "close": [10, 20, 30, 40, 50, 60, 70, 80],
            "spread": [100, 110, 120, 130, 140, 150, 160, 170],
        },
        index=index,
    )
    out = resample_ohlcv(source, "H1")

    assert out.iloc[0]["open"] == 1
    assert out.iloc[0]["close"] == 40
    assert out.iloc[1]["open"] == 5
    assert out.iloc[1]["close"] == 80
    assert out.index[0] == index[0]


def test_strategy_prepare_does_not_change_past_when_future_changes() -> None:
    strategy = _strategy()
    data = _sample_data()
    changed_future = data.copy()
    changed_future.iloc[220:, changed_future.columns.get_loc("close")] += 10000

    prepared_a = strategy.prepare(data)
    prepared_b = strategy.prepare(changed_future)

    pd.testing.assert_series_equal(prepared_a["ema_fast"].iloc[:180], prepared_b["ema_fast"].iloc[:180])
    pd.testing.assert_series_equal(prepared_a["ema_mid"].iloc[:180], prepared_b["ema_mid"].iloc[:180])
    pd.testing.assert_series_equal(prepared_a["ema_slow"].iloc[:180], prepared_b["ema_slow"].iloc[:180])
    pd.testing.assert_series_equal(prepared_a["atr"].iloc[:180], prepared_b["atr"].iloc[:180])


def test_exclude_monday_blocks_monday_signal(monkeypatch) -> None:
    from src.strategies.nas_trend_pullback import NASTrendPullback

    strategy = _strategy()
    monday = pd.DataFrame({"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5]}, index=[pd.Timestamp("2025-01-06 16:00", tz="Europe/Paris")])

    def forbidden_super_signal(self, i, data):  # noqa: ANN001
        raise AssertionError("parent signal logic should not run on Monday")

    monkeypatch.setattr(NASTrendPullback, "generate_signal", forbidden_super_signal)
    assert strategy.generate_signal(0, monday) is None


def test_generated_signals_have_timestamp_stop_and_target() -> None:
    strategy = _strategy()
    data = _sample_data()
    prepared = strategy.prepare(data)
    signals = [strategy.generate_signal(i, prepared) for i in range(len(prepared))]
    signals = [signal for signal in signals if signal is not None]

    for signal in signals:
        assert signal.timestamp is not None
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert abs(float(signal.take_profit) - float(signal.stop_loss)) > 0
