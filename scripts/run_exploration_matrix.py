#!/usr/bin/env python3
"""V2.4 — Multi-strategy exploration matrix runner.

Usage:
    .venv/bin/python scripts/run_exploration_matrix.py \\
        --matrix config/research/v2_4_xau_exploration.yaml \\
        --output data/reports/v2_4_xau_exploration.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_metrics
from src.backtest.monte_carlo import run_monte_carlo
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def _finite(v: Any, default: float = 0.0) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(n) or math.isinf(n):
        return default
    return n


def _fmt(v: Any, d: int = 2) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(n):
        return ""
    if math.isinf(n):
        return "inf" if n > 0 else "-inf"
    return f"{n:.{d}f}"


def _exploration_verdict(metrics: dict[str, Any], stopped_reason: str | None) -> tuple[str, str]:
    trades = int(_finite(metrics.get("trade_count")))
    pf = _finite(metrics.get("profit_factor"))
    expectancy = _finite(metrics.get("expectancy"))
    dd = _finite(metrics.get("max_drawdown_pct"))
    concentration = _finite(metrics.get("monthly_profit_concentration_pct"))
    stopped = stopped_reason == "max_total_drawdown"

    reasons: list[str] = []
    if stopped:
        reasons.append("stopped_by_drawdown")
    if pf < 1.0:
        reasons.append("pf_below_1")
    if expectancy <= 0:
        reasons.append("negative_expectancy")
    if dd >= 8.0:
        reasons.append(f"dd_{dd:.1f}_pct")
    if trades < 30:
        reasons.append("too_few_trades")

    if stopped or pf < 1.0 or expectancy <= 0 or trades < 30:
        return "REJETÉE", "; ".join(reasons) if reasons else "does_not_pass"

    if pf >= 1.20 and expectancy > 0 and trades >= 100 and dd < 8.0 and not stopped and concentration <= 50.0:
        return "CANDIDAT SÉRIEUX", "pf_gt_1_20_controlled_dd"

    if pf >= 1.05:
        soft: list[str] = []
        if trades < 100:
            soft.append(f"only_{trades}_trades")
        if concentration > 50.0:
            soft.append(f"concentration_{concentration:.0f}pct")
        if dd >= 5.0:
            soft.append(f"dd_{dd:.1f}_pct")
        return "À RETRAVAILLER", "; ".join(soft) if soft else "candidate_needs_validation"

    return "REJETÉE", "; ".join(reasons) if reasons else "pf_too_weak"


def _top3_month_concentration(metrics: dict[str, Any]) -> float:
    monthly = metrics.get("performance_by_month", {})
    net = _finite(metrics.get("net_profit"))
    if net <= 0 or not monthly:
        return 0.0
    positives = sorted([v for v in monthly.values() if v > 0], reverse=True)
    top3 = sum(positives[:3])
    return round(top3 / net * 100, 2)


def _run_entry(
    entry: dict[str, Any],
    cost_multiplier: float,
    assets_cfg: dict[str, Any],
    risk_cfg: dict[str, Any],
    strategies_cfg: dict[str, Any],
) -> dict[str, Any]:
    strategy_name = str(entry["strategy"])
    data_path = ROOT / entry["data"]
    timeframe = str(entry.get("timeframe", "M15"))
    entry_mode = str(entry.get("entry_mode", "next_bar_open"))
    asset_label = str(entry.get("asset", "XAUUSD"))

    strat_cfg = strategy_config(strategies_cfg, strategy_name)
    asset_spec = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    backtest_cfg = replace(backtest_cfg, entry_mode=entry_mode)  # type: ignore[arg-type]

    if cost_multiplier != 1.0:
        backtest_cfg = replace(
            backtest_cfg,
            spread_points=backtest_cfg.spread_points * cost_multiplier,
            slippage_points=backtest_cfg.slippage_points * cost_multiplier,
            commission_per_lot_round_turn=backtest_cfg.commission_per_lot_round_turn * cost_multiplier,
        )

    data, cleaning = load_mt5_ohlcv(str(data_path), timezone="Europe/Paris", timeframe=timeframe)
    if cost_multiplier != 1.0 and "spread" in data.columns:
        data = data.copy()
        data["spread"] = data["spread"].astype(float) * cost_multiplier

    strategy = STRATEGY_REGISTRY[strategy_name](strat_cfg)
    result = BacktestEngine(backtest_cfg, asset_spec).run(data, strategy)
    metrics = calculate_metrics(result.trades, result.equity_curve, backtest_cfg.initial_capital)
    verdict, reason = _exploration_verdict(metrics, result.stopped_reason)

    row: dict[str, Any] = {
        "asset": asset_label,
        "timeframe": timeframe,
        "strategy": strategy_name,
        "entry_mode": entry_mode,
        "cost_multiplier": cost_multiplier,
        "trades": int(_finite(metrics["trade_count"])),
        "pf": round(_finite(metrics["profit_factor"]), 3),
        "expectancy": round(_finite(metrics["expectancy"]), 2),
        "dd": round(_finite(metrics["max_drawdown_pct"]), 2),
        "winrate": round(_finite(metrics["winrate_pct"]), 1),
        "max_losing_streak": int(_finite(metrics["max_loss_streak"])),
        "best_month_pct": round(_finite(metrics["monthly_profit_concentration_pct"]), 1),
        "top3_month_pct": _top3_month_concentration(metrics),
        "monthly_stability": round(_finite(metrics["monthly_stability_pct"]), 1),
        "net_profit": round(_finite(metrics["net_profit"]), 2),
        "verdict": verdict,
        "reason": reason,
        "stopped_reason": result.stopped_reason or "",
        "data_period": f"{cleaning.first_timestamp} → {cleaning.last_timestamp}",
        "_trades_df": result.trades,
        "_initial_capital": backtest_cfg.initial_capital,
        "_metrics": metrics,
    }
    return row


def _run_monte_carlo_for_row(row: dict[str, Any]) -> dict[str, Any]:
    trades_df = row["_trades_df"]
    initial_capital = row["_initial_capital"]
    if not trades_df.empty and _finite(row["pf"]) >= 1.0:
        mc = run_monte_carlo(trades_df, initial_capital, simulations=500)
        row["mc_dd_median"] = round(mc.median_max_drawdown_pct, 2)
        row["mc_dd_p95"] = round(mc.p95_max_drawdown_pct, 2)
        row["mc_ruin_5pct"] = round(mc.risk_of_ruin_pct, 1)
    return row


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    return out


def _daily_pnl(trades_df: pd.DataFrame) -> pd.Series:
    if trades_df.empty:
        return pd.Series(dtype=float)
    t = trades_df.copy()
    t["exit_date"] = pd.to_datetime(t["exit_time"]).dt.date
    return t.groupby("exit_date")["net_pnl"].sum()


def _portfolio_correlation(rows_with_trades: list[dict[str, Any]]) -> str:
    candidates = [r for r in rows_with_trades if _finite(r.get("pf", 0)) >= 1.05 and not r["_trades_df"].empty]
    if len(candidates) < 2:
        return "_Moins de 2 candidats avec PF > 1.05 — portefeuille non exploitable._"

    daily_pnls: dict[str, pd.Series] = {}
    for r in candidates:
        key = f"{r['strategy']}_{r['asset']}_{r['cost_multiplier']}"
        daily_pnls[key] = _daily_pnl(r["_trades_df"])

    combined = pd.DataFrame(daily_pnls).fillna(0)
    if combined.shape[1] < 2:
        return "_Un seul candidat — pas de corrélation._"

    corr = combined.corr()
    lines = ["| | " + " | ".join(corr.columns.tolist()) + " |"]
    lines.append("| --- | " + " | ".join(["---"] * len(corr.columns)) + " |")
    for idx, col_row in corr.iterrows():
        lines.append("| " + str(idx) + " | " + " | ".join(_fmt(v, 2) for v in col_row) + " |")
    return "\n".join(lines)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_Aucun résultat._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for r in rows:
        vals = [str(r.get(c, "")) for c in columns]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _build_report(
    all_rows: list[dict[str, Any]],
    rows_with_trades: list[dict[str, Any]],
    output_path: Path,
) -> str:
    display_cols = [
        "asset", "timeframe", "strategy", "entry_mode", "cost_multiplier",
        "trades", "pf", "expectancy", "dd", "winrate",
        "max_losing_streak", "best_month_pct", "top3_month_pct",
        "verdict", "reason",
    ]
    mc_display = display_cols + ["mc_dd_median", "mc_dd_p95", "mc_ruin_5pct"]

    rejected = [r for r in all_rows if r["verdict"] == "REJETÉE"]
    rework = [r for r in all_rows if r["verdict"] == "À RETRAVAILLER"]
    serious = [r for r in all_rows if r["verdict"] == "CANDIDAT SÉRIEUX"]

    corr_section = _portfolio_correlation(rows_with_trades)

    verdict_summary = (
        f"- Total runs: {len(all_rows)}\n"
        f"- CANDIDAT SÉRIEUX: {len(serious)}\n"
        f"- À RETRAVAILLER: {len(rework)}\n"
        f"- REJETÉE: {len(rejected)}"
    )

    next_action_parts: list[str] = []
    if serious:
        for r in serious:
            next_action_parts.append(
                f"**{r['strategy']} / {r['asset']} {r['timeframe']}** (coûts x{r['cost_multiplier']}) : "
                f"PF {r['pf']}, DD {r['dd']}% → lancer walk-forward et analyse candidat complète."
            )
    elif rework:
        best = sorted(rework, key=lambda r: _finite(r["pf"]), reverse=True)[0]
        next_action_parts.append(
            f"**{best['strategy']} / {best['asset']} {best['timeframe']}** (PF {best['pf']}) : "
            f"À retravailler — explorer variations de paramètres si hypothèse fondamentalement différente."
        )
    else:
        next_action_parts.append(
            "Toutes les stratégies XAU sont rejetées sur ce scan initial. "
            "Ne pas optimiser. Reformuler les hypothèses ou explorer d'autres familles/actifs."
        )

    baseline_rows = [r for r in all_rows if r["strategy"] == "nas_trend_pullback_exclude_monday"]
    baseline_section = _markdown_table(baseline_rows, mc_display if any("mc_dd_p95" in r for r in baseline_rows) else display_cols)

    return f"""# V2.4 — XAU M15/M30 Exploration Matrix

**Branche :** research/v2.4-xau-m15-m30-strategy-exploration
**Rapport :** `{output_path}`
**Protocole :** backtest brut strict, entry_mode next_bar_open, coûts x1.0 et x1.5, aucune optimisation.

## Résumé

{verdict_summary}

## Tous les résultats

{_markdown_table(all_rows, display_cols)}

## Candidats sérieux (PF > 1.20)

{_markdown_table(serious, mc_display if serious and "mc_dd_p95" in serious[0] else display_cols) if serious else "_Aucun candidat sérieux sur ce scan._"}

## À retravailler (PF 1.05-1.20)

{_markdown_table(rework, display_cols) if rework else "_Aucune stratégie à retravailler._"}

## Rejetées

{_markdown_table(rejected, ["asset", "timeframe", "strategy", "cost_multiplier", "trades", "pf", "expectancy", "dd", "verdict", "reason"])}

## Corrélation inter-stratégies (candidats PF > 1.05)

{corr_section}

## Baseline US100 H1 (comparaison)

{baseline_section}

## Prochaine action recommandée

{"  ".join(f"- {s}" for s in next_action_parts)}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V2.4 exploration matrix runner.")
    parser.add_argument("--matrix", required=True, help="Path to exploration YAML.")
    parser.add_argument("--output", default=str(ROOT / "data/reports/v2_4_xau_exploration.md"))
    parser.add_argument("--assets-config", default=str(ROOT / "config/assets.yaml"))
    parser.add_argument("--risk-config", default=str(ROOT / "config/risk.yaml"))
    parser.add_argument("--strategies-config", default=str(ROOT / "config/strategies.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_cfg = load_yaml(args.matrix)
    assets_cfg = load_yaml(args.assets_config)
    risk_cfg = load_yaml(args.risk_config)
    strategies_cfg = load_yaml(args.strategies_config)

    candidate_threshold = float(matrix_cfg.get("candidate_threshold_pf", 1.05))
    auto_mc = bool(matrix_cfg.get("candidate_auto_monte_carlo", True))

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    rows_raw: list[dict[str, Any]] = []  # keep private fields for correlation
    all_rows: list[dict[str, Any]] = []

    for entry in matrix_cfg.get("entries", []):
        multipliers: list[float] = [float(m) for m in entry.get("cost_multipliers", [1.0])]
        for cost_mult in multipliers:
            try:
                row = _run_entry(entry, cost_mult, assets_cfg, risk_cfg, strategies_cfg)
                rows_raw.append(row)
                pf = _finite(row.get("pf", 0))
                should_mc = auto_mc and pf >= candidate_threshold and not row.get("_trades_df", pd.DataFrame()).empty
                if should_mc:
                    _run_monte_carlo_for_row(row)
                clean = _clean_row(row)
                all_rows.append(clean)
                status = clean["verdict"]
                mc_info = f", MC p95 DD {clean.get('mc_dd_p95', 'n/a')}%" if "mc_dd_p95" in clean else ""
                print(
                    f"  {entry['strategy']} / {entry.get('asset')} {entry.get('timeframe')} "
                    f"x{cost_mult} → {clean['trades']} trades, PF {clean['pf']}, DD {clean['dd']}%{mc_info} → {status}"
                )
            except Exception as exc:
                import traceback
                print(f"  ERROR {entry.get('strategy')} x{cost_mult}: {exc}")
                traceback.print_exc()
                err_row: dict[str, Any] = {
                    "asset": entry.get("asset", ""),
                    "timeframe": entry.get("timeframe", ""),
                    "strategy": entry.get("strategy", ""),
                    "entry_mode": entry.get("entry_mode", "next_bar_open"),
                    "cost_multiplier": cost_mult,
                    "trades": 0, "pf": 0.0, "expectancy": 0.0, "dd": 0.0,
                    "winrate": 0.0, "max_losing_streak": 0,
                    "best_month_pct": 0.0, "top3_month_pct": 0.0, "monthly_stability": 0.0,
                    "net_profit": 0.0, "verdict": "ERREUR", "reason": str(exc),
                    "stopped_reason": "", "data_period": "",
                }
                all_rows.append(err_row)

    report = _build_report(all_rows, rows_raw, output)
    output.write_text(report, encoding="utf-8")

    # Also write CSV
    csv_path = output.with_suffix(".csv")
    safe_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in all_rows]
    pd.DataFrame(safe_rows).to_csv(csv_path, index=False)

    print(f"\nReport: {output}")
    print(f"CSV:    {csv_path}")

    serious = [r for r in all_rows if r.get("verdict") == "CANDIDAT SÉRIEUX"]
    rework = [r for r in all_rows if r.get("verdict") == "À RETRAVAILLER"]
    rejected = [r for r in all_rows if r.get("verdict") == "REJETÉE"]
    print(f"CANDIDAT SÉRIEUX: {len(serious)} | À RETRAVAILLER: {len(rework)} | REJETÉE: {len(rejected)}")


if __name__ == "__main__":
    main()
