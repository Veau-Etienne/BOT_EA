#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PYTHON_COLUMNS = {
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
MT5_COLUMNS = {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Python trades with MT5 trade replay CSV.")
    parser.add_argument("--python-trades", required=True)
    parser.add_argument("--mt5-trades", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--point-size", type=float, default=0.01)
    parser.add_argument("--price-tolerance-points", type=float, default=5.0)
    parser.add_argument("--pnl-tolerance", type=float, default=2.0)
    return parser.parse_args()


def _python_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="raise").dt.tz_convert("Europe/Paris").dt.tz_localize(None)


def _load_python(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    missing = sorted(PYTHON_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(f"Python trades missing columns: {missing}")
    out = data.copy()
    out["entry_timestamp"] = _python_time(out["entry_time"])
    out["exit_timestamp"] = _python_time(out["exit_time"])
    out["signal_timestamp"] = _python_time(out["signal_timestamp"])
    out["direction"] = out["side"].astype(str).str.lower()
    return out


def _load_mt5(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    missing = sorted(MT5_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(f"MT5 trades missing columns: {missing}")
    out = data.copy()
    out["entry_timestamp"] = pd.to_datetime(out["entry_timestamp"], errors="raise")
    out["exit_timestamp"] = pd.to_datetime(out["exit_timestamp"], errors="raise")
    out["signal_timestamp"] = pd.to_datetime(out["signal_timestamp"], errors="raise")
    out["direction"] = out["direction"].astype(str).str.lower()
    for column in ["entry_price", "stop_loss", "take_profit", "exit_price", "gross_pnl", "net_pnl", "r_multiple"]:
        out[column] = pd.to_numeric(out[column], errors="raise")
    return out


def _table(rows: list[dict[str, object]], columns: list[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def main() -> None:
    args = parse_args()
    py = _load_python(Path(args.python_trades))
    mt5 = _load_mt5(Path(args.mt5_trades))
    joined = py.merge(mt5, on=["signal_timestamp", "entry_timestamp"], how="inner", suffixes=("_python", "_mt5"))

    py_keys = set(zip(py["signal_timestamp"], py["entry_timestamp"]))
    mt5_keys = set(zip(mt5["signal_timestamp"], mt5["entry_timestamp"]))
    missing_mt5 = py[[key not in mt5_keys for key in zip(py["signal_timestamp"], py["entry_timestamp"])]]
    extra_mt5 = mt5[[key not in py_keys for key in zip(mt5["signal_timestamp"], mt5["entry_timestamp"])]]

    mismatches: list[dict[str, object]] = []
    price_failures = 0
    pnl_failures = 0
    reason_failures = 0
    direction_failures = 0
    exit_time_failures = 0
    for _, row in joined.iterrows():
        direction_bad = row["direction_python"] != row["direction_mt5"]
        reason_bad = row["exit_reason_python"] != row["exit_reason_mt5"]
        exit_time_bad = row["exit_timestamp_python"] != row["exit_timestamp_mt5"]
        direction_failures += int(direction_bad)
        reason_failures += int(reason_bad)
        exit_time_failures += int(exit_time_bad)
        max_price_diff = 0.0
        for column in ["entry_price", "stop_loss", "take_profit", "exit_price"]:
            diff_points = abs(float(row[f"{column}_python"]) - float(row[f"{column}_mt5"])) / args.point_size
            max_price_diff = max(max_price_diff, diff_points)
        pnl_diff = abs(float(row["net_pnl_python"]) - float(row["net_pnl_mt5"]))
        if max_price_diff > args.price_tolerance_points:
            price_failures += 1
        if pnl_diff > args.pnl_tolerance:
            pnl_failures += 1
        if direction_bad or reason_bad or exit_time_bad or max_price_diff > args.price_tolerance_points or pnl_diff > args.pnl_tolerance:
            mismatches.append(
                {
                    "signal_timestamp": row["signal_timestamp"],
                    "entry_timestamp": row["entry_timestamp"],
                    "direction_py": row["direction_python"],
                    "direction_mt5": row["direction_mt5"],
                    "exit_py": row["exit_timestamp_python"],
                    "exit_mt5": row["exit_timestamp_mt5"],
                    "reason_py": row["exit_reason_python"],
                    "reason_mt5": row["exit_reason_mt5"],
                    "max_price_diff_points": f"{max_price_diff:.2f}",
                    "net_pnl_diff": f"{pnl_diff:.2f}",
                }
            )

    if not missing_mt5.empty or not extra_mt5.empty or direction_failures or reason_failures or exit_time_failures or price_failures > max(3, 0.02 * len(joined)):
        verdict = "TRADE_PARITY_FAIL"
    elif pnl_failures > max(3, 0.05 * len(joined)):
        verdict = "TRADE_PARITY_WARNING"
    else:
        verdict = "TRADE_PARITY_OK"

    lines = [
        "# Python / MT5 Trade Parity",
        "",
        f"- Verdict : {verdict}",
        f"- Trades Python : {len(py)}",
        f"- Trades MT5 : {len(mt5)}",
        f"- Trades communs : {len(joined)}",
        f"- Manquants MT5 : {len(missing_mt5)}",
        f"- Extras MT5 : {len(extra_mt5)}",
        f"- Direction mismatches : {direction_failures}",
        f"- Exit time mismatches : {exit_time_failures}",
        f"- Exit reason mismatches : {reason_failures}",
        f"- Price mismatches : {price_failures}",
        f"- PnL mismatches : {pnl_failures}",
        "",
        "## Premiers Écarts",
        "",
    ]
    lines.extend(_table(mismatches[:30], ["signal_timestamp", "entry_timestamp", "direction_py", "direction_mt5", "exit_py", "exit_mt5", "reason_py", "reason_mt5", "max_price_diff_points", "net_pnl_diff"]) if mismatches else ["Aucun."])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Verdict: {verdict}")
    print(f"Python trades: {len(py)}")
    print(f"MT5 trades: {len(mt5)}")
    print(f"Common trades: {len(joined)}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
