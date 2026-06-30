#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import load_yaml, strategy_config
from src.utils.time import in_time_windows, parse_hhmm


DST_DATES = {
    pd.Timestamp("2023-03-26"),
    pd.Timestamp("2023-10-29"),
    pd.Timestamp("2024-03-31"),
    pd.Timestamp("2024-10-27"),
    pd.Timestamp("2025-03-30"),
    pd.Timestamp("2025-10-26"),
    pd.Timestamp("2026-03-29"),
    pd.Timestamp("2026-10-25"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Python/MT5 signal parity differences with bar and indicator context.")
    parser.add_argument("--python-signals", required=True)
    parser.add_argument("--mt5-signals", required=True)
    parser.add_argument("--python-bars", required=True)
    parser.add_argument("--mt5-bars", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--strategy", default="nas_trend_pullback_exclude_monday")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--point-size", type=float, default=0.01)
    return parser.parse_args()


def _naive_index(index: pd.Index) -> pd.DatetimeIndex:
    ts = pd.to_datetime(index)
    if getattr(ts, "tz", None) is not None:
        return ts.tz_localize(None)
    return pd.DatetimeIndex(ts)


def _load_signals(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise")
    data["direction"] = data["direction"].astype(str).str.lower()
    return data


def _load_python_prepared(path: Path, strategy_name: str, timezone: str) -> tuple[pd.DataFrame, dict[str, object]]:
    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    cfg = strategy_config(strategies_cfg, strategy_name)
    data, _ = load_mt5_ohlcv(path, timezone=timezone, timeframe="H1")
    data.index = _naive_index(data.index)
    strategy = STRATEGY_REGISTRY[strategy_name](cfg)
    prepared = strategy.prepare(data)
    prepared.index = _naive_index(prepared.index)
    return prepared, cfg


def _load_mt5_bars(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise")
    for column in ["open", "high", "low", "close", "spread", "ema_fast", "ema_slow", "ema200", "atr"]:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.drop_duplicates("timestamp", keep="last").sort_values("timestamp").set_index("timestamp")
    data.index = _naive_index(data.index)
    return data


def _near_dst(ts: pd.Timestamp) -> bool:
    date = pd.Timestamp(ts.date())
    return any(abs((date - dst).days) <= 2 for dst in DST_DATES)


def _condition_context(ts: pd.Timestamp, direction: str, prepared: pd.DataFrame, cfg: dict[str, object]) -> tuple[str, list[str], dict[str, object]]:
    if ts not in prepared.index:
        return "DATA_MISMATCH", ["timestamp_absent_python_bars"], {}
    i = int(prepared.index.get_loc(ts))
    if i < 2:
        return "WARMUP_MISMATCH", ["not_enough_previous_bars"], {"index": i}

    row = prepared.iloc[i]
    prev = prepared.iloc[i - 1]
    reasons: list[str] = []
    context: dict[str, object] = {"index": i}

    if ts.weekday() == 0:
        reasons.append("blocked_by_monday_filter")
    if not in_time_windows(ts, cfg.get("sessions", [["15:45", "18:00"]])):
        reasons.append("outside_session")
    if ts.time() < parse_hhmm(str(cfg.get("avoid_until", "15:45"))) or ts.time() > parse_hhmm(str(cfg.get("trade_until", "18:00"))):
        reasons.append("outside_trade_window")
    max_spread = cfg.get("max_spread")
    if max_spread is not None and "spread" in prepared.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
        reasons.append("spread_filter")
    if pd.isna(row.get("ema_slow")) or pd.isna(row.get("ema_mid_slope")) or pd.isna(row.get("atr")) or float(row.get("atr", 0) or 0) <= 0:
        reasons.append("indicator_missing_or_warmup")
    elif float(row["atr"]) < float(cfg.get("atr_min_filter", 0)):
        reasons.append("atr_filter")

    if reasons:
        cause = "FILTER_MISMATCH" if any("filter" in reason or "outside" in reason for reason in reasons) else "WARMUP_MISMATCH"
        return cause, reasons, context

    close = float(row["close"])
    open_ = float(row["open"])
    atr_value = float(row["atr"])
    swing_lookback = int(cfg.get("swing_lookback", 5))
    recent = prepared.iloc[max(0, i - swing_lookback) : i + 1]
    pullback_ema = "ema_fast" if int(cfg.get("pullback_ema", 20)) <= 20 else "ema_mid"

    long_ok = close > float(row["ema_slow"]) and float(row["ema_mid_slope"]) > 0
    short_ok = close < float(row["ema_slow"]) and float(row["ema_mid_slope"]) < 0
    pullback_long = float(prev["low"]) <= float(prev[pullback_ema])
    pullback_short = float(prev["high"]) >= float(prev[pullback_ema])
    resume_long = close > open_ and close > float(prev["high"])
    resume_short = close < open_ and close < float(prev["low"])

    context.update(
        {
            "py_close": close,
            "py_atr": atr_value,
            "py_ema_fast": float(row["ema_fast"]),
            "py_ema_slow": float(row["ema_mid"]),
            "py_ema200": float(row["ema_slow"]),
            "long_ok": long_ok,
            "short_ok": short_ok,
            "pullback_long": pullback_long,
            "pullback_short": pullback_short,
            "resume_long": resume_long,
            "resume_short": resume_short,
            "recent_low": float(recent["low"].min()),
            "recent_high": float(recent["high"].max()),
        }
    )

    if direction == "long":
        if not long_ok:
            reasons.append("ema_trend_or_slope")
        if not pullback_long:
            reasons.append("pullback_condition")
        if not resume_long:
            reasons.append("resume_condition")
    else:
        if not short_ok:
            reasons.append("ema_trend_or_slope")
        if not pullback_short:
            reasons.append("pullback_condition")
        if not resume_short:
            reasons.append("resume_condition")

    if not reasons:
        return "UNKNOWN", ["python_rules_would_signal_same_timestamp"], context
    if "ema_trend_or_slope" in reasons:
        return "INDICATOR_MISMATCH", reasons, context
    return "ENTRY_RULE_MISMATCH", reasons, context


def _indicator_diffs(ts: pd.Timestamp, prepared: pd.DataFrame, mt5_bars: pd.DataFrame, point_size: float) -> dict[str, object]:
    if ts not in prepared.index or ts not in mt5_bars.index:
        return {}
    py = prepared.loc[ts]
    mt5 = mt5_bars.loc[ts]
    mapping = {"atr": "atr", "ema_fast": "ema_fast", "ema_mid": "ema_slow", "ema_slow": "ema200"}
    out: dict[str, object] = {}
    for py_col, mt5_col in mapping.items():
        if py_col in py and mt5_col in mt5 and pd.notna(py[py_col]) and pd.notna(mt5[mt5_col]):
            out[f"{mt5_col}_diff_points"] = abs(float(py[py_col]) - float(mt5[mt5_col])) / point_size
    return out


def _table(rows: list[dict[str, object]], columns: list[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def main() -> None:
    args = parse_args()
    py_signals = _load_signals(Path(args.python_signals))
    mt5_signals = _load_signals(Path(args.mt5_signals))
    prepared, cfg = _load_python_prepared(Path(args.python_bars), args.strategy, args.timezone)
    mt5_bars = _load_mt5_bars(Path(args.mt5_bars))

    py_times = set(py_signals["timestamp"])
    mt5_times = set(mt5_signals["timestamp"])
    extra_mt5 = mt5_signals[~mt5_signals["timestamp"].isin(py_times)].copy()
    missing_mt5 = py_signals[~py_signals["timestamp"].isin(mt5_times)].copy()

    rows: list[dict[str, object]] = []
    cause_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for _, signal in extra_mt5.iterrows():
        ts = pd.Timestamp(signal["timestamp"])
        cause, reasons, context = _condition_context(ts, str(signal["direction"]), prepared, cfg)
        diffs = _indicator_diffs(ts, prepared, mt5_bars, args.point_size)
        if cause == "INDICATOR_MISMATCH" and diffs:
            large_diffs = [key for key, value in diffs.items() if isinstance(value, float) and value > 5.0]
            if large_diffs:
                reasons.extend(large_diffs)
        cause_counts[cause] += 1
        reason_counts.update(reasons)
        rows.append(
            {
                "timestamp": ts,
                "direction": signal["direction"],
                "day": ts.day_name(),
                "hour": ts.hour,
                "near_dst": _near_dst(ts),
                "cause": cause,
                "reasons": ",".join(reasons),
                "atr_diff_points": f"{float(diffs.get('atr_diff_points', 0.0)):.2f}" if diffs else "",
                "ema200_diff_points": f"{float(diffs.get('ema200_diff_points', 0.0)):.2f}" if diffs else "",
                "py_close": f"{float(context.get('py_close', 0.0)):.2f}" if "py_close" in context else "",
            }
        )

    missing_rows: list[dict[str, object]] = []
    for _, signal in missing_mt5.iterrows():
        ts = pd.Timestamp(signal["timestamp"])
        diffs = _indicator_diffs(ts, prepared, mt5_bars, args.point_size)
        missing_rows.append(
            {
                "timestamp": ts,
                "direction": signal["direction"],
                "day": ts.day_name(),
                "hour": ts.hour,
                "timestamp_in_mt5_bars": ts in mt5_bars.index,
                "near_dst": _near_dst(ts),
                "atr_diff_points": f"{float(diffs.get('atr_diff_points', 0.0)):.2f}" if diffs else "",
                "ema200_diff_points": f"{float(diffs.get('ema200_diff_points', 0.0)):.2f}" if diffs else "",
            }
        )

    if extra_mt5.empty and missing_mt5.empty:
        top_cause = "NONE"
        verdict = "PARITY_FIXED"
    elif cause_counts:
        top_cause = cause_counts.most_common(1)[0][0]
        verdict = f"{top_cause}_CONFIRMED" if top_cause != "UNKNOWN" else "PARITY_STILL_FAIL"
    else:
        top_cause = "UNKNOWN"
        verdict = "PARITY_STILL_FAIL"

    lines = [
        "# Signal Difference Analysis",
        "",
        f"- Verdict : {verdict}",
        f"- Signaux Python : {len(py_signals)}",
        f"- Signaux MT5 : {len(mt5_signals)}",
        f"- Extras MT5 analysés : {len(extra_mt5)}",
        f"- Manquants MT5 analysés : {len(missing_mt5)}",
        "",
        "## Causes Probables",
        "",
        *_table([{"cause": key, "count": value} for key, value in cause_counts.most_common()], ["cause", "count"]),
        "",
        "## Raisons Détaillées",
        "",
        *_table([{"reason": key, "count": value} for key, value in reason_counts.most_common()], ["reason", "count"]),
        "",
        "## Extras MT5",
        "",
        *_table(rows[:50], ["timestamp", "direction", "day", "hour", "near_dst", "cause", "reasons", "atr_diff_points", "ema200_diff_points", "py_close"]),
        "",
        "## Signaux Python Manquants Côté MT5",
        "",
    ]
    if missing_rows:
        lines.extend(_table(missing_rows, ["timestamp", "direction", "day", "hour", "timestamp_in_mt5_bars", "near_dst", "atr_diff_points", "ema200_diff_points"]))
    else:
        lines.append("Aucun.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Verdict: {verdict}")
    print(f"Extra MT5: {len(extra_mt5)}")
    print(f"Missing MT5: {len(missing_mt5)}")
    print(f"Top cause: {top_cause}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
