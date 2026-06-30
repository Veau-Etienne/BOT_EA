from __future__ import annotations

from scripts.compare_mt5_python_trades import MT5_COLUMNS, PYTHON_COLUMNS


def test_python_trade_schema_contains_parity_columns() -> None:
    required = {
        "signal_timestamp",
        "entry_time",
        "side",
        "entry_price",
        "stop_loss",
        "take_profit",
        "exit_time",
        "exit_price",
        "exit_reason",
        "gross_pnl",
        "net_pnl",
        "r_multiple",
    }
    assert required.issubset(PYTHON_COLUMNS)


def test_mt5_trade_replay_schema_contains_expected_columns() -> None:
    required = {
        "signal_timestamp",
        "entry_timestamp",
        "direction",
        "entry_price",
        "stop_loss",
        "take_profit",
        "exit_timestamp",
        "exit_price",
        "exit_reason",
        "gross_pnl",
        "net_pnl",
        "r_multiple",
        "spread_entry",
        "spread_exit",
    }
    assert required.issubset(MT5_COLUMNS)

