from __future__ import annotations

from typing import Any


def list_symbols() -> list[dict[str, Any]]:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The MetaTrader5 Python package is not available. On macOS/Wine, prefer exporting history to CSV from MT5 "
            "then run scripts/run_backtest.py. Direct MT5 Python access is usually reliable only on Windows."
        ) from exc

    if not mt5.initialize():
        raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")
    try:
        symbols = mt5.symbols_get()
        if symbols is None:
            raise RuntimeError(f"mt5.symbols_get() failed: {mt5.last_error()}")
        return [dict(symbol._asdict()) if hasattr(symbol, "_asdict") else dict(symbol) for symbol in symbols]
    finally:
        mt5.shutdown()


def export_history_instructions() -> str:
    return (
        "MT5 CSV export: open MT5, press Ctrl+U, select the symbol, open the Bars tab, choose M15, "
        "download the period, then Export to CSV. Put the file in data/raw/ and run scripts/run_backtest.py."
    )
