#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestConfig, BacktestEngine
from src.backtest.execution import AssetSpec
from src.backtest.metrics import calculate_metrics
from src.backtest.monte_carlo import run_monte_carlo
from src.backtest.validation import robustness_score
from src.backtest.walk_forward import walk_forward_grid_search
from src.data.cleaner import CleaningReport
from src.data.loader import load_mt5_ohlcv
from src.optimization.defaults import DEFAULT_GRID
from src.optimization.grid_search import run_grid_search
from src.strategies import STRATEGY_REGISTRY
from src.strategies.base import BaseStrategy
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


MIN_VALID_TRADES = 100
MIN_REWORK_TRADES = 50


CSV_COLUMNS = [
    "asset",
    "strategy",
    "timeframe",
    "start_date",
    "end_date",
    "trades",
    "profit_net",
    "profit_factor",
    "winrate",
    "expectancy",
    "max_drawdown",
    "max_losing_streak",
    "best_month",
    "worst_month",
    "profit_concentration_best_month",
    "verdict",
    "rejection_reason",
]


@dataclass(frozen=True)
class AssetInput:
    label: str
    symbol: str
    timeframe: str
    path: Path


@dataclass(frozen=True)
class LoadedAsset:
    input: AssetInput
    spec: AssetSpec
    data: pd.DataFrame
    cleaning: CleaningReport


@dataclass(frozen=True)
class RawScan:
    row: dict[str, Any]
    data: pd.DataFrame
    trades: pd.DataFrame
    strategy_cls: type[BaseStrategy]
    strategy_config: dict[str, Any]
    backtest_config: BacktestConfig
    asset_spec: AssetSpec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan all compatible raw strategy backtests for one or more assets.")
    parser.add_argument(
        "--assets",
        nargs="+",
        required=True,
        metavar="SYMBOL:CSV",
        help="Asset/data pairs, for example XAUUSD:data/raw/XAUUSD_M15.csv US100:data/raw/US100_M15.csv.",
    )
    parser.add_argument("--output", default=str(ROOT / "data/reports/strategy_scanner.md"))
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--assets-config", default=str(ROOT / "config/assets.yaml"))
    parser.add_argument("--risk-config", default=str(ROOT / "config/risk.yaml"))
    parser.add_argument("--strategies-config", default=str(ROOT / "config/strategies.yaml"))
    parser.add_argument(
        "--optimize-candidates",
        action="store_true",
        help="Run light optimization, Monte Carlo and walk-forward only for scanner candidates.",
    )
    parser.add_argument(
        "--diagnostic-full-sample",
        action="store_true",
        help="Ignore max total drawdown stops for diagnostics only. Results are non tradable and never VALIDABLE.",
    )
    parser.add_argument("--objective", default="robustness_score", help="Objective used for optional candidate optimization.")
    return parser.parse_args()


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    if math.isinf(number):
        return 999.0 if number > 0 else -999.0
    return number


def _display_float(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return ""
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return f"{number:.{decimals}f}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _parse_asset_inputs(items: list[str]) -> list[AssetInput]:
    assets: list[AssetInput] = []
    for item in items:
        if ":" not in item:
            raise ValueError(f"Invalid asset spec '{item}'. Expected SYMBOL:path/to/file.csv.")
        label, raw_path = item.split(":", 1)
        label = label.strip()
        if not label:
            raise ValueError(f"Invalid asset spec '{item}'. Symbol is empty.")
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = ROOT / path
        label_upper = label.upper()
        symbol = label_upper
        timeframe = ""
        match = re.fullmatch(r"(.+)_(M\d+|H\d+|D\d+)", label_upper)
        if match:
            symbol = match.group(1)
            timeframe = match.group(2)
        if not timeframe:
            stem_match = re.fullmatch(r"(.+)_(M\d+|H\d+|D\d+)", path.stem.upper())
            if stem_match:
                timeframe = stem_match.group(2)
        assets.append(AssetInput(label=label_upper, symbol=symbol, timeframe=timeframe, path=path))
    return assets


def _resolved_symbol(assets_config: dict[str, Any], symbol: str) -> str:
    return resolve_asset_spec(assets_config, symbol).symbol.upper()


def _strategy_matches_asset(strategy_symbol: str, asset_symbol: str, assets_config: dict[str, Any]) -> bool:
    try:
        return _resolved_symbol(assets_config, strategy_symbol) == _resolved_symbol(assets_config, asset_symbol)
    except KeyError:
        return strategy_symbol.upper() == asset_symbol.upper()


def _compatible_strategies(asset_label: str, strategies_config: dict[str, Any], assets_config: dict[str, Any]) -> list[str]:
    compatible: list[str] = []
    for name, config in strategies_config.get("strategies", {}).items():
        if name not in STRATEGY_REGISTRY:
            continue
        symbol = str(config.get("symbol", ""))
        if symbol and _strategy_matches_asset(symbol, asset_label, assets_config):
            compatible.append(name)
    return sorted(compatible)


def _scanner_robustness_score(metrics: dict[str, Any], stopped_reason: str | None) -> float:
    score = robustness_score(metrics)
    if stopped_reason == "max_total_drawdown":
        score -= 25.0
    if _finite(metrics.get("trade_count")) < MIN_REWORK_TRADES:
        score -= 15.0
    if _finite(metrics.get("expectancy")) <= 0:
        score -= 15.0
    if _finite(metrics.get("profit_factor")) < 1.0:
        score -= 10.0
    return round(max(0.0, min(100.0, score)), 2)


def _scanner_verdict(metrics: dict[str, Any], stopped_reason: str | None) -> tuple[str, str]:
    trades = int(_finite(metrics.get("trade_count")))
    pf = _finite(metrics.get("profit_factor"))
    expectancy = _finite(metrics.get("expectancy"))
    dd = _finite(metrics.get("max_drawdown_pct"))
    net_profit = _finite(metrics.get("net_profit"))
    concentration = _finite(metrics.get("monthly_profit_concentration_pct"))
    stopped_by_drawdown = stopped_reason == "max_total_drawdown"
    concentrated = net_profit > 0 and concentration > 40.0

    hard_reasons: list[str] = []
    if stopped_by_drawdown:
        hard_reasons.append("stopped_by_drawdown")
    if trades < MIN_REWORK_TRADES:
        hard_reasons.append("too_few_trades")
    if pf < 1.0:
        hard_reasons.append("profit_factor_below_1")
    elif pf < 1.05:
        hard_reasons.append("profit_factor_too_weak")
    if expectancy < 0:
        hard_reasons.append("negative_expectancy")
    if dd >= 12.0:
        hard_reasons.append("drawdown_above_12_pct")
    elif dd >= 8.0:
        hard_reasons.append("drawdown_above_8_pct")
    if concentrated:
        hard_reasons.append("profit_concentrated_best_month")
    if net_profit < 0:
        hard_reasons.append("negative_net_profit")

    validable = (
        pf > 1.20
        and expectancy > 0
        and trades >= MIN_VALID_TRADES
        and dd < 8.0
        and not concentrated
        and not stopped_by_drawdown
    )
    if validable:
        return "VALIDABLE", "passes_scanner_rules"

    if stopped_by_drawdown or trades < MIN_REWORK_TRADES or pf < 1.0 or expectancy < 0 or dd >= 12.0:
        return "REJETÉE", ";".join(hard_reasons)

    reworkable = pf >= 1.05 and pf <= 1.20 and trades >= MIN_REWORK_TRADES and dd < 12.0
    if reworkable:
        reasons = hard_reasons or ["candidate_needs_validation"]
        if trades < MIN_VALID_TRADES:
            reasons.append("sample_below_100_trades")
        return "À RETRAVAILLER", ";".join(dict.fromkeys(reasons))

    return "REJETÉE", ";".join(hard_reasons or ["does_not_meet_scanner_candidate_rules"])


def _load_assets(asset_inputs: list[AssetInput], assets_config: dict[str, Any], timezone: str, default_timeframe: str) -> list[LoadedAsset]:
    loaded: list[LoadedAsset] = []
    for asset_input in asset_inputs:
        if not asset_input.path.exists():
            raise FileNotFoundError(f"Data file not found for {asset_input.label}: {asset_input.path}")
        spec = resolve_asset_spec(assets_config, asset_input.symbol)
        timeframe = asset_input.timeframe or default_timeframe
        data, cleaning = load_mt5_ohlcv(asset_input.path, timezone=timezone, timeframe=timeframe)
        loaded.append(LoadedAsset(input=asset_input, spec=spec, data=data, cleaning=cleaning))
    return loaded


def _row_from_metrics(
    loaded_asset: LoadedAsset,
    strategy_name: str,
    strategy_timeframe: str,
    metrics: dict[str, Any],
    stopped_reason: str | None,
    diagnostic_full_sample: bool,
) -> dict[str, Any]:
    verdict, reason = _scanner_verdict(metrics, stopped_reason)
    if diagnostic_full_sample:
        reason = ";".join([reason, "diagnostic_full_sample_non_tradable"]) if reason else "diagnostic_full_sample_non_tradable"
        if verdict == "VALIDABLE":
            verdict = "À RETRAVAILLER"
    row = {
        "asset": loaded_asset.input.label,
        "base_asset": loaded_asset.spec.symbol,
        "strategy": strategy_name,
        "timeframe": strategy_timeframe,
        "start_date": loaded_asset.cleaning.first_timestamp,
        "end_date": loaded_asset.cleaning.last_timestamp,
        "trades": int(metrics["trade_count"]),
        "profit_net": float(metrics["net_profit"]),
        "profit_factor": float(metrics["profit_factor"]),
        "winrate": float(metrics["winrate_pct"]),
        "expectancy": float(metrics["expectancy"]),
        "max_drawdown": float(metrics["max_drawdown_pct"]),
        "max_losing_streak": int(metrics["max_loss_streak"]),
        "best_month": float(metrics["best_month"]),
        "worst_month": float(metrics["worst_month"]),
        "profit_concentration_best_month": float(metrics["monthly_profit_concentration_pct"]),
        "verdict": verdict,
        "rejection_reason": reason,
        "robustness_score": _scanner_robustness_score(metrics, stopped_reason),
        "monthly_stability": float(metrics["monthly_stability_pct"]),
        "stopped_reason": stopped_reason or "",
        "diagnostic_full_sample": diagnostic_full_sample,
        "data_rows": loaded_asset.cleaning.rows_out,
        "missing_bars": loaded_asset.cleaning.missing_bars,
    }
    return row


def _run_raw_scans(
    loaded_assets: list[LoadedAsset],
    strategies_config: dict[str, Any],
    risk_config: dict[str, Any],
    assets_config: dict[str, Any],
    diagnostic_full_sample: bool,
) -> list[RawScan]:
    scans: list[RawScan] = []
    for loaded_asset in loaded_assets:
        strategy_names = _compatible_strategies(loaded_asset.input.symbol, strategies_config, assets_config)
        for strategy_name in strategy_names:
            strat_cfg = strategy_config(strategies_config, strategy_name)
            strategy_cls = STRATEGY_REGISTRY[strategy_name]
            asset_spec = resolve_asset_spec(assets_config, strat_cfg["symbol"])
            backtest_config = build_backtest_config(risk_config, strat_cfg)
            if diagnostic_full_sample:
                backtest_config = replace(backtest_config, diagnostic_full_sample=True)
            result = BacktestEngine(backtest_config, asset_spec).run(loaded_asset.data, strategy_cls(strat_cfg))
            metrics = calculate_metrics(result.trades, result.equity_curve, backtest_config.initial_capital)
            row = _row_from_metrics(
                loaded_asset,
                strategy_name,
                loaded_asset.input.timeframe or str(strat_cfg.get("timeframe", "M15")),
                metrics,
                result.stopped_reason,
                diagnostic_full_sample,
            )
            scans.append(
                RawScan(
                    row=row,
                    data=loaded_asset.data,
                    trades=result.trades,
                    strategy_cls=strategy_cls,
                    strategy_config=strat_cfg,
                    backtest_config=backtest_config,
                    asset_spec=asset_spec,
                )
            )
    return scans


def _sort_for_top(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.sort_values(column, ascending=False).head(10)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_Aucun résultat._"
    available = [column for column in columns if column in frame.columns]
    if not available:
        return "_Aucune colonne disponible._"
    lines = ["| " + " | ".join(available) + " |", "| " + " | ".join(["---"] * len(available)) + " |"]
    for _, row in frame[available].iterrows():
        values = []
        for column in available:
            value = row[column]
            if column in {"trades", "max_losing_streak", "data_rows", "missing_bars"} and pd.api.types.is_number(value):
                values.append(str(int(value)))
            elif pd.api.types.is_number(value):
                if "profit_factor" in column:
                    values.append(_display_float(value, 3))
                elif "expectancy" in column or "drawdown" in column or "profit" in column or "delta" in column:
                    values.append(_display_float(value, 2))
                else:
                    values.append(_display_float(value, 2))
            elif column in {"profit_factor"}:
                values.append(_display_float(value, 3))
            elif column in {
                "profit_net",
                "winrate",
                "expectancy",
                "max_drawdown",
                "best_month",
                "worst_month",
                "profit_concentration_best_month",
                "robustness_score",
                "monthly_stability",
            }:
                values.append(_display_float(value, 2))
            else:
                values.append("" if pd.isna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _recommend_next_action(frame: pd.DataFrame, optimize_candidates: bool, diagnostic_full_sample: bool) -> str:
    if diagnostic_full_sample:
        return "Mode diagnostic full sample : ne pas trader ni optimiser directement. Utiliser ces résultats pour détecter un problème de coût/timeframe ou reformuler les hypothèses."
    if frame.empty:
        return "Aucune combinaison n'a été testée. Vérifier les fichiers CSV et les symboles configurés."
    validable = frame[frame["verdict"] == "VALIDABLE"]
    reworkable = frame[frame["verdict"] == "À RETRAVAILLER"]
    if not validable.empty:
        best = validable.sort_values("robustness_score", ascending=False).iloc[0]
        return (
            f"Approfondir {best['asset']} / {best['strategy']} avec walk-forward, Monte Carlo complet et revue trade par trade "
            "avant toute exécution live."
        )
    if not reworkable.empty:
        best = reworkable.sort_values("robustness_score", ascending=False).iloc[0]
        if optimize_candidates:
            return f"Analyser les artefacts candidat pour {best['asset']} / {best['strategy']} puis décider si l'hypothèse mérite une V2."
        return (
            f"Lancer l'option --optimize-candidates uniquement sur les candidats, en commençant par "
            f"{best['asset']} / {best['strategy']}."
        )
    return "Tout est rejeté sur ce scan brut. Ne pas optimiser ces paramètres; formuler de nouvelles hypothèses ou changer de timeframe."


def _build_markdown_report(
    frame: pd.DataFrame,
    loaded_assets: list[LoadedAsset],
    output_csv: Path,
    optimize_candidates: bool,
    candidate_artifacts: list[str],
    diagnostic_full_sample: bool,
) -> str:
    counts = frame["verdict"].value_counts().to_dict() if not frame.empty else {}
    total = int(len(frame))
    rejected = int(counts.get("REJETÉE", 0))
    reworkable = int(counts.get("À RETRAVAILLER", 0))
    validable = int(counts.get("VALIDABLE", 0))
    score_sorted = _sort_for_top(frame, "robustness_score")
    pf_sorted = _sort_for_top(frame, "profit_factor")
    expectancy_sorted = _sort_for_top(frame, "expectancy")

    asset_lines = [
        "| asset | base_asset | timeframe | file | rows | period | missing_bars | spread_avg |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for loaded in loaded_assets:
        cleaning = loaded.cleaning
        period = f"{cleaning.first_timestamp} -> {cleaning.last_timestamp}"
        spread = "" if cleaning.spread_mean is None else _display_float(cleaning.spread_mean, 2)
        asset_lines.append(
            f"| {loaded.input.label} | {loaded.spec.symbol} | {loaded.input.timeframe or ''} | {loaded.input.path} | {cleaning.rows_out} | {period} | {cleaning.missing_bars} | {spread} |"
        )

    columns = [
        "asset",
        "timeframe",
        "strategy",
        "trades",
        "profit_net",
        "profit_factor",
        "expectancy",
        "max_drawdown",
        "robustness_score",
        "verdict",
        "rejection_reason",
    ]
    reworkable_frame = frame[frame["verdict"] == "À RETRAVAILLER"].sort_values("robustness_score", ascending=False) if not frame.empty else pd.DataFrame()
    rejected_frame = frame[frame["verdict"] == "REJETÉE"].sort_values(["robustness_score", "profit_factor"], ascending=False) if not frame.empty else pd.DataFrame()
    detail_parts: list[str] = []
    for asset in sorted(frame["asset"].unique()) if not frame.empty else []:
        per_asset = frame[frame["asset"] == asset].sort_values(["verdict", "robustness_score"], ascending=[True, False])
        detail_parts.append(f"### {asset}\n\n{_markdown_table(per_asset, columns)}")

    rejected_reasons = frame[frame["verdict"] == "REJETÉE"][["asset", "strategy", "rejection_reason"]] if not frame.empty else pd.DataFrame()
    artifacts = "\n".join(f"- {artifact}" for artifact in candidate_artifacts) if candidate_artifacts else "- Aucun artefact candidat généré."
    if diagnostic_full_sample:
        validation_mode = "Diagnostic full sample non tradable. L'arrêt max_total_drawdown est ignoré et aucun résultat ne peut être VALIDABLE."
    elif optimize_candidates:
        validation_mode = "Optimisation légère et validation candidat activées."
    else:
        validation_mode = "Scan brut uniquement. Aucune optimisation, aucun walk-forward et aucun Monte Carlo candidat n'ont été lancés."

    improvement_table = _timeframe_improvements(frame)

    return f"""# Strategy Scanner V1.6

## Résumé global

- Mode: {validation_mode}
- Résultats CSV: `{output_csv}`
- Stratégies testées: {total}
- Rejetées: {rejected}
- À retravailler: {reworkable}
- Validables: {validable}

## Données

{chr(10).join(asset_lines)}

## Top 10 par robustesse

{_markdown_table(score_sorted, columns)}

## Top 10 par profit factor

{_markdown_table(pf_sorted, columns)}

## Top 10 par expectancy

{_markdown_table(expectancy_sorted, columns)}

## Améliorations M15 -> M30/H1

{improvement_table}

## Stratégies Devenues À Retravailler

{_markdown_table(reworkable_frame, columns)}

## Stratégies Toujours Rejetées

{_markdown_table(rejected_frame, columns)}

## Détails par actif

{chr(10).join(detail_parts) if detail_parts else "_Aucun détail disponible._"}

## Raisons de rejet

{_markdown_table(rejected_reasons, ["asset", "strategy", "rejection_reason"])}

## Artefacts candidats

{artifacts}

## Prochaine action recommandée

{_recommend_next_action(frame, optimize_candidates, diagnostic_full_sample)}
"""


def _candidate_scans(scans: list[RawScan]) -> list[RawScan]:
    return [scan for scan in scans if scan.row["verdict"] in {"VALIDABLE", "À RETRAVAILLER"}]


def _timeframe_improvements(frame: pd.DataFrame) -> str:
    if frame.empty or not {"base_asset", "timeframe", "strategy", "profit_factor", "expectancy"}.issubset(frame.columns):
        return "_Aucun comparatif timeframe disponible._"
    rows: list[dict[str, Any]] = []
    grouped = frame.groupby(["base_asset", "strategy"], dropna=False)
    for (base_asset, strategy), group in grouped:
        baseline = group[group["timeframe"] == "M15"]
        if baseline.empty:
            continue
        base_row = baseline.iloc[0]
        for _, row in group[group["timeframe"].isin(["M30", "H1"])].iterrows():
            rows.append(
                {
                    "base_asset": base_asset,
                    "strategy": strategy,
                    "timeframe": row["timeframe"],
                    "m15_profit_factor": base_row["profit_factor"],
                    "tf_profit_factor": row["profit_factor"],
                    "profit_factor_delta": _finite(row["profit_factor"]) - _finite(base_row["profit_factor"]),
                    "m15_expectancy": base_row["expectancy"],
                    "tf_expectancy": row["expectancy"],
                    "expectancy_delta": _finite(row["expectancy"]) - _finite(base_row["expectancy"]),
                    "verdict": row["verdict"],
                }
            )
    if not rows:
        return "_Aucun comparatif timeframe disponible._"
    improvements = pd.DataFrame(rows).sort_values(["profit_factor_delta", "expectancy_delta"], ascending=False).head(10)
    return _markdown_table(
        improvements,
        [
            "base_asset",
            "strategy",
            "timeframe",
            "m15_profit_factor",
            "tf_profit_factor",
            "profit_factor_delta",
            "m15_expectancy",
            "tf_expectancy",
            "expectancy_delta",
            "verdict",
        ],
    )


def _run_candidate_artifacts(scans: list[RawScan], output: Path, objective: str) -> list[str]:
    artifacts: list[str] = []
    candidates = _candidate_scans(scans)
    if not candidates:
        return artifacts

    optimization_frames: list[pd.DataFrame] = []
    for scan in candidates:
        asset = scan.row["asset"]
        strategy = scan.row["strategy"]
        prefix = output.with_suffix("")
        safe_name = f"{asset}_{strategy}"

        mc_result = run_monte_carlo(scan.trades, scan.backtest_config.initial_capital, simulations=500)
        mc_path = prefix.with_name(f"{prefix.name}_{safe_name}_monte_carlo.json")
        mc_path.write_text(json.dumps(asdict(mc_result), indent=2, default=_json_safe), encoding="utf-8")
        artifacts.append(str(mc_path))

        grid = DEFAULT_GRID.get(strategy)
        if not grid:
            continue

        optimization = run_grid_search(
            scan.data,
            scan.strategy_cls,
            scan.strategy_config,
            grid,
            scan.backtest_config,
            scan.asset_spec,
            objective=objective,
        )
        if not optimization.empty:
            optimization.insert(0, "strategy", strategy)
            optimization.insert(0, "asset", asset)
            optimization_frames.append(optimization)

        walk_forward = walk_forward_grid_search(
            scan.data,
            scan.strategy_cls,
            scan.strategy_config,
            grid,
            scan.backtest_config,
            scan.asset_spec,
            folds=3,
            objective=objective,
        )
        wf_path = prefix.with_name(f"{prefix.name}_{safe_name}_walk_forward.csv")
        walk_forward.to_csv(wf_path, index=False)
        artifacts.append(str(wf_path))

    if optimization_frames:
        opt_path = output.with_name(f"{output.stem}_optimization.csv")
        pd.concat(optimization_frames, ignore_index=True).to_csv(opt_path, index=False)
        artifacts.append(str(opt_path))

    return artifacts


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output_csv = output.with_suffix(".csv")

    assets_config = load_yaml(args.assets_config)
    strategies_config = load_yaml(args.strategies_config)
    risk_config = load_yaml(args.risk_config)
    asset_inputs = _parse_asset_inputs(args.assets)
    loaded_assets = _load_assets(asset_inputs, assets_config, args.timezone, args.timeframe)
    scans = _run_raw_scans(loaded_assets, strategies_config, risk_config, assets_config, args.diagnostic_full_sample)
    frame = pd.DataFrame([scan.row for scan in scans])
    if not frame.empty:
        frame = frame.sort_values(["verdict", "robustness_score"], ascending=[True, False]).reset_index(drop=True)
    frame.to_csv(
        output_csv,
        index=False,
        columns=[
            column
            for column in [
                *CSV_COLUMNS,
                "base_asset",
                "robustness_score",
                "monthly_stability",
                "stopped_reason",
                "diagnostic_full_sample",
                "data_rows",
                "missing_bars",
            ]
            if column in frame.columns
        ],
    )

    candidate_artifacts = _run_candidate_artifacts(scans, output, args.objective) if args.optimize_candidates and not args.diagnostic_full_sample else []
    report = _build_markdown_report(frame, loaded_assets, output_csv, args.optimize_candidates, candidate_artifacts, args.diagnostic_full_sample)
    output.write_text(report, encoding="utf-8")

    counts = frame["verdict"].value_counts().to_dict() if not frame.empty else {}
    print(f"Strategy scanner report: {output}")
    print(f"Strategy scanner CSV: {output_csv}")
    print(f"Strategies tested: {len(frame)}")
    print(f"VALIDABLE: {int(counts.get('VALIDABLE', 0))}")
    print(f"À RETRAVAILLER: {int(counts.get('À RETRAVAILLER', 0))}")
    print(f"REJETÉE: {int(counts.get('REJETÉE', 0))}")
    if args.diagnostic_full_sample:
        print("Mode diagnostic full sample: non tradable, max_total_drawdown ignored, VALIDABLE disabled.")
    if not frame.empty:
        columns = ["asset", "strategy", "trades", "profit_factor", "expectancy", "max_drawdown", "robustness_score", "verdict"]
        print(frame.sort_values("robustness_score", ascending=False).head(10)[columns].to_string(index=False))


if __name__ == "__main__":
    main()
