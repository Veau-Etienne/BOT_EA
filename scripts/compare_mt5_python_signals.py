#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PRICE_COLUMNS = ["entry_price", "stop_loss", "take_profit"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Python and MT5 strategy signal exports.")
    parser.add_argument("--python-signals", required=True)
    parser.add_argument("--mt5-signals", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--point-size", type=float, default=0.01)
    parser.add_argument("--tolerance-points", type=float, default=5.0)
    return parser.parse_args()


def _load(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} introuvable: {path}")
    data = pd.read_csv(path)
    required = {"timestamp", "direction", *PRICE_COLUMNS}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"{label} colonnes manquantes: {missing}")
    data = data.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise")
    data["direction"] = data["direction"].astype(str).str.lower()
    for column in PRICE_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="raise")
    return data


def _price_diff_points(joined: pd.DataFrame, column: str, point_size: float) -> pd.Series:
    return (joined[f"{column}_python"] - joined[f"{column}_mt5"]).abs() / point_size


def _markdown_preview(data: pd.DataFrame) -> list[str]:
    columns = ["timestamp", "direction", *PRICE_COLUMNS]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in data[columns].head(20).iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return lines


def main() -> None:
    args = parse_args()
    python_path = Path(args.python_signals)
    mt5_path = Path(args.mt5_signals)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    py = _load(python_path, "CSV Python")
    mt5 = _load(mt5_path, "CSV MT5")
    joined = py.merge(mt5, on="timestamp", how="inner", suffixes=("_python", "_mt5"))

    py_times = set(py["timestamp"])
    mt5_times = set(mt5["timestamp"])
    missing_mt5 = py[~py["timestamp"].isin(mt5_times)].copy()
    extra_mt5 = mt5[~mt5["timestamp"].isin(py_times)].copy()

    direction_mismatch = int((joined["direction_python"] != joined["direction_mt5"]).sum()) if not joined.empty else 0
    max_diffs = {column: 0.0 for column in PRICE_COLUMNS}
    mean_diffs = {column: 0.0 for column in PRICE_COLUMNS}
    price_failures = 0
    for column in PRICE_COLUMNS:
        if joined.empty:
            continue
        diffs = _price_diff_points(joined, column, args.point_size)
        max_diffs[column] = float(diffs.max())
        mean_diffs[column] = float(diffs.mean())
        price_failures += int((diffs > args.tolerance_points).sum())

    if len(py) == 0 and len(mt5) == 0:
        verdict = "PARITY_WARNING"
    elif missing_mt5.empty and extra_mt5.empty and direction_mismatch == 0 and price_failures == 0:
        verdict = "PARITY_OK"
    elif (
        len(joined) == 0
        or direction_mismatch > 0
        or len(missing_mt5) > max(5, 0.05 * len(py))
        or len(extra_mt5) > max(5, 0.05 * len(mt5))
        or price_failures > max(5, 0.05 * max(len(joined), 1))
    ):
        verdict = "PARITY_FAIL"
    else:
        verdict = "PARITY_WARNING"

    lines = [
        "# Python / MT5 Signal Parity",
        "",
        f"- Verdict : {verdict}",
        f"- Signaux Python : {len(py)}",
        f"- Signaux MT5 : {len(mt5)}",
        f"- Timestamps communs : {len(joined)}",
        f"- Manquants côté MT5 : {len(missing_mt5)}",
        f"- Extras côté MT5 : {len(extra_mt5)}",
        f"- Mismatches direction : {direction_mismatch}",
        f"- Tolérance prix : {args.tolerance_points:.2f} points",
        "",
        "## Écarts Prix",
        "",
        "| Champ | Écart moyen points | Écart max points |",
        "| --- | ---: | ---: |",
    ]
    for column in PRICE_COLUMNS:
        lines.append(f"| {column} | {mean_diffs[column]:.2f} | {max_diffs[column]:.2f} |")
    lines.extend(["", "## Premiers Manquants MT5", ""])
    if missing_mt5.empty:
        lines.append("Aucun.")
    else:
        lines.extend(_markdown_preview(missing_mt5))
    lines.extend(["", "## Premiers Extras MT5", ""])
    if extra_mt5.empty:
        lines.append("Aucun.")
    else:
        lines.extend(_markdown_preview(extra_mt5))

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Verdict: {verdict}")
    print(f"Common timestamps: {len(joined)}")
    print(f"Missing MT5: {len(missing_mt5)}")
    print(f"Extra MT5: {len(extra_mt5)}")
    print(f"Report: {output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Erreur comparaison parité: {exc}", file=sys.stderr)
        raise SystemExit(1)
