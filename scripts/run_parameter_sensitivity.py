#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_metrics
from src.backtest.validation import robustness_score
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a light one-factor parameter sensitivity check.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--timezone", default="Europe/Paris")
    return parser.parse_args()


def _fmt(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return ""
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return f"{number:.{decimals}f}"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_Aucun résultat._"
    available = [column for column in columns if column in frame.columns]
    lines = ["| " + " | ".join(available) + " |", "| " + " | ".join(["---"] * len(available)) + " |"]
    for _, row in frame[available].iterrows():
        values: list[str] = []
        for column in available:
            value = row[column]
            if pd.api.types.is_number(value):
                if column in {"trades"}:
                    values.append(str(int(value)))
                elif column == "profit_factor":
                    values.append(_fmt(value, 3))
                else:
                    values.append(_fmt(value, 2))
            else:
                values.append("" if pd.isna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _scanner_verdict(metrics: dict[str, Any], stopped_reason: str | None) -> tuple[str, str]:
    reasons: list[str] = []
    pf = float(metrics["profit_factor"])
    expectancy = float(metrics["expectancy"])
    dd = float(metrics["max_drawdown_pct"])
    trades = int(metrics["trade_count"])
    concentration = float(metrics["monthly_profit_concentration_pct"])
    net_profit = float(metrics["net_profit"])
    if stopped_reason:
        reasons.append(stopped_reason)
    if trades < 100:
        reasons.append("too_few_trades")
    if pf < 1.0:
        reasons.append("profit_factor_below_1")
    if expectancy < 0:
        reasons.append("negative_expectancy")
    if dd >= 8:
        reasons.append("drawdown_above_8_pct")
    if net_profit > 0 and concentration > 40:
        reasons.append("profit_concentrated_best_month")
    if pf > 1.20 and expectancy > 0 and trades >= 100 and dd < 8 and not (net_profit > 0 and concentration > 40) and not stopped_reason:
        return "VALIDABLE", "passes_basic_rules"
    if pf >= 1.05 and expectancy >= 0 and dd < 8 and trades >= 100 and not stopped_reason:
        return "À RETRAVAILLER", ";".join(reasons or ["candidate_needs_validation"])
    return "REJETÉE", ";".join(reasons or ["does_not_meet_candidate_rules"])


def _candidate_configs(base: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    configs: list[tuple[str, dict[str, Any]]] = [("baseline", dict(base))]
    one_factor_values = {
        "ema_fast": [15, int(base.get("ema_fast", 20)), 25],
        "ema_slow": [150, int(base.get("ema_slow", 200)), 250],
        "atr_period": [10, 14, 20],
        "tp_r_multiple": [1.0, float(base.get("tp_r_multiple", 1.5)), 2.0],
        "sl_atr_multiplier": [1.0, float(base.get("sl_atr_multiplier", 1.5)), 2.0],
        "max_trades_per_day": [1, int(base.get("max_trades_per_day", 2))],
        "avoid_until": ["15:30", str(base.get("avoid_until", "15:45")), "16:00"],
        "trade_until": ["17:00", str(base.get("trade_until", "18:00")), "19:00"],
    }
    seen = {repr(sorted(base.items()))}
    for key, values in one_factor_values.items():
        for value in values:
            config = dict(base)
            config[key] = value
            if key in {"avoid_until", "trade_until"}:
                start = config.get("avoid_until", base.get("avoid_until", "15:45"))
                end = config.get("trade_until", base.get("trade_until", "18:00"))
                config["sessions"] = [[start, end]]
            fingerprint = repr(sorted(config.items()))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            configs.append((f"{key}={value}", config))
    return configs


def _stability_summary(frame: pd.DataFrame) -> tuple[str, str]:
    positive = frame[(frame["profit_factor"] >= 1.05) & (frame["expectancy"] >= 0) & (frame["trades"] >= 100)]
    validish = positive[positive["profit_concentration_best_month"] <= 40]
    if len(validish) >= 5:
        return "plateau_acceptable", f"{len(validish)} variations keep PF >= 1.05, expectancy >= 0, trades >= 100 and concentration <= 40%."
    if len(positive) >= 5:
        return "fragile_concentrated", f"{len(positive)} variations are positive, but concentration remains the main defect."
    if len(positive) >= 2:
        return "fragile", f"Only {len(positive)} variations remain positive enough."
    return "instable", "No robust plateau around baseline."


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output_csv = output.with_suffix(".csv")
    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    base_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, base_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, base_cfg)
    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    rows: list[dict[str, Any]] = []
    for label, config in _candidate_configs(base_cfg):
        result = BacktestEngine(backtest_cfg, asset).run(data, STRATEGY_REGISTRY[args.strategy](config))
        metrics = calculate_metrics(result.trades, result.equity_curve, backtest_cfg.initial_capital)
        verdict, reason = _scanner_verdict(metrics, result.stopped_reason)
        rows.append(
            {
                "variation": label,
                "ema_fast": config.get("ema_fast"),
                "ema_slow": config.get("ema_slow"),
                "atr_period": config.get("atr_period"),
                "tp_r_multiple": config.get("tp_r_multiple"),
                "sl_atr_multiplier": config.get("sl_atr_multiplier"),
                "max_trades_per_day": config.get("max_trades_per_day"),
                "avoid_until": config.get("avoid_until"),
                "trade_until": config.get("trade_until"),
                "trades": metrics["trade_count"],
                "profit_net": metrics["net_profit"],
                "profit_factor": metrics["profit_factor"],
                "expectancy": metrics["expectancy"],
                "max_drawdown": metrics["max_drawdown_pct"],
                "winrate": metrics["winrate_pct"],
                "profit_concentration_best_month": metrics["monthly_profit_concentration_pct"],
                "monthly_stability": metrics["monthly_stability_pct"],
                "robustness_score": robustness_score(metrics),
                "verdict": verdict,
                "reason": reason,
            }
        )
    frame = pd.DataFrame(rows).sort_values(["robustness_score", "profit_factor"], ascending=False).reset_index(drop=True)
    frame.to_csv(output_csv, index=False)
    stability, stability_reason = _stability_summary(frame)
    positive_count = int(((frame["profit_factor"] >= 1.05) & (frame["expectancy"] >= 0) & (frame["trades"] >= 100)).sum())
    report = f"""# Parameter Sensitivity - {args.strategy}

## Résumé

- Data: `{args.data}`
- Période: {cleaning.first_timestamp} -> {cleaning.last_timestamp}
- Variations testées: {len(frame)}
- Variations PF >= 1.05, expectancy >= 0, trades >= 100: {positive_count}
- Verdict sensibilité: {stability}
- Raison: {stability_reason}
- CSV: `{output_csv}`

## Résultats

{_markdown_table(frame, ["variation", "ema_fast", "ema_slow", "atr_period", "tp_r_multiple", "sl_atr_multiplier", "max_trades_per_day", "avoid_until", "trade_until", "trades", "profit_factor", "expectancy", "max_drawdown", "profit_concentration_best_month", "robustness_score", "verdict", "reason"])}
"""
    output.write_text(report, encoding="utf-8")
    print(f"Sensitivity report: {output}")
    print(f"Sensitivity CSV: {output_csv}")
    print(f"Verdict sensibilité: {stability} ({stability_reason})")
    print(frame.head(10)[["variation", "trades", "profit_factor", "expectancy", "max_drawdown", "profit_concentration_best_month", "robustness_score", "verdict"]].to_string(index=False))


if __name__ == "__main__":
    main()
