#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import calculate_metrics
from src.backtest.validation import robustness_score
from src.data.loader import load_mt5_ohlcv
from src.indicators.atr import atr
from src.indicators.ema import ema
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


SEGMENTS = {
    "A_2023_2024": ("2023-02-27", "2024-02-29"),
    "B_2024_2025": ("2024-03-01", "2025-02-28"),
    "C_2025_2026": ("2025-03-01", "2026-02-25"),
}
RESEARCH_START = "2023-02-27"
RESEARCH_END = "2025-02-28"
HOLDOUT_START = "2025-03-01"
HOLDOUT_END = "2026-02-25"


@dataclass(frozen=True)
class FilterSpec:
    name: str
    category: str
    description: str
    predicate: Callable[[pd.DataFrame], pd.Series]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded regime filter lab for one candidate strategy.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--asset", required=True)
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


def _profit_factor(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses > 0:
        return float(wins / losses)
    return float("inf") if wins > 0 else 0.0


def _max_loss_streak(pnl: pd.Series) -> int:
    streak = 0
    max_streak = 0
    for value in pnl:
        if value < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _max_drawdown_pct(pnl: pd.Series, initial_capital: float = 100000.0) -> float:
    if pnl.empty:
        return 0.0
    equity = initial_capital + pnl.cumsum()
    peaks = equity.cummax()
    drawdowns = (peaks - equity) / peaks * 100
    return float(drawdowns.max()) if len(drawdowns) else 0.0


def _month_stats(trades: pd.DataFrame) -> tuple[float, float, int, int, float, float]:
    if trades.empty:
        return 0.0, 0.0, 0, 0, 0.0, 0.0
    monthly = trades.groupby("month")["net_pnl"].sum()
    positive = monthly[monthly > 0]
    net_profit = float(trades["net_pnl"].sum())
    best_month = float(monthly.max()) if len(monthly) else 0.0
    worst_month = float(monthly.min()) if len(monthly) else 0.0
    concentration_best = float(positive.max() / net_profit * 100) if net_profit > 0 and len(positive) else 0.0
    concentration_top3 = float(positive.nlargest(3).sum() / net_profit * 100) if net_profit > 0 and len(positive) else 0.0
    return best_month, worst_month, int((monthly > 0).sum()), int((monthly < 0).sum()), concentration_best, concentration_top3


def _metrics_from_trades(trades: pd.DataFrame, total_trades: int, initial_capital: float = 100000.0) -> dict[str, Any]:
    pnl = trades["net_pnl"].astype(float) if not trades.empty else pd.Series(dtype=float)
    best_month, worst_month, pos_months, neg_months, concentration_best, concentration_top3 = _month_stats(trades)
    yearly = trades.groupby("year")["net_pnl"].sum().to_dict() if not trades.empty else {}
    trade_count = int(len(trades))
    pf = _profit_factor(pnl)
    expectancy = float(pnl.mean()) if trade_count else 0.0
    max_dd = _max_drawdown_pct(pnl, initial_capital)
    metrics = {
        "trades": trade_count,
        "trades_removed_pct": float((total_trades - trade_count) / total_trades * 100) if total_trades else 0.0,
        "profit_net": float(pnl.sum()) if trade_count else 0.0,
        "profit_factor": pf,
        "winrate": float((pnl > 0).mean() * 100) if trade_count else 0.0,
        "expectancy": expectancy,
        "max_drawdown": max_dd,
        "max_losing_streak": _max_loss_streak(pnl),
        "best_month": best_month,
        "worst_month": worst_month,
        "concentration_best_month": concentration_best,
        "concentration_top3_months": concentration_top3,
        "positive_months": pos_months,
        "negative_months": neg_months,
        "performance_by_year": ";".join(f"{k}:{v:.2f}" for k, v in yearly.items()),
    }
    score_input = {
        "profit_factor": pf,
        "expectancy": expectancy,
        "trade_count": trade_count,
        "max_drawdown_pct": max_dd,
        "monthly_stability_pct": float(pos_months / (pos_months + neg_months) * 100) if pos_months + neg_months else 0.0,
        "monthly_profit_concentration_pct": concentration_best,
        "net_profit": metrics["profit_net"],
    }
    score = robustness_score(score_input)
    if concentration_best > 35:
        score -= min(15.0, (concentration_best - 35) / 65 * 15)
    if concentration_top3 > 75:
        score -= min(15.0, (concentration_top3 - 75) / 100 * 15)
    if metrics["trades_removed_pct"] > 60:
        score -= 10.0
    if trade_count < 100:
        score -= 25.0
    metrics["robustness_score"] = round(max(0.0, min(100.0, score)), 2)
    return metrics


def _period_slice(trades: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    start_ts = pd.Timestamp(start, tz=trades["exit_time"].dt.tz)
    end_ts = pd.Timestamp(end, tz=trades["exit_time"].dt.tz) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return trades[(trades["exit_time"] >= start_ts) & (trades["exit_time"] <= end_ts)].copy()


def _segment_rows(name: str, trades: pd.DataFrame, total_trades: int) -> dict[str, Any]:
    metrics = _metrics_from_trades(trades, total_trades)
    return {
        "filter": name,
        "segment_trades": metrics["trades"],
        "segment_profit_factor": metrics["profit_factor"],
        "segment_expectancy": metrics["expectancy"],
        "segment_drawdown": metrics["max_drawdown"],
        "segment_profit_net": metrics["profit_net"],
    }


def _segment_analysis(name: str, trades: pd.DataFrame) -> tuple[dict[str, Any], str]:
    row: dict[str, Any] = {"filter": name}
    bad_segments = 0
    negative_segments = 0
    for segment_name, (start, end) in SEGMENTS.items():
        part = _period_slice(trades, start, end)
        metrics = _metrics_from_trades(part, len(part))
        row[f"{segment_name}_trades"] = metrics["trades"]
        row[f"{segment_name}_pf"] = metrics["profit_factor"]
        row[f"{segment_name}_expectancy"] = metrics["expectancy"]
        row[f"{segment_name}_drawdown"] = metrics["max_drawdown"]
        if metrics["trades"] < 20 or metrics["profit_factor"] < 0.9:
            bad_segments += 1
        if metrics["expectancy"] < 0:
            negative_segments += 1
    if bad_segments == 0 and negative_segments <= 1:
        verdict = "OK"
    elif bad_segments <= 1 and negative_segments <= 1:
        verdict = "mitigé"
    else:
        verdict = "fragile"
    row["segment_verdict"] = verdict
    row["bad_segments"] = bad_segments
    row["negative_segments"] = negative_segments
    return row, verdict


def _holdout_analysis(name: str, trades: pd.DataFrame) -> tuple[dict[str, Any], str]:
    research = _period_slice(trades, RESEARCH_START, RESEARCH_END)
    holdout = _period_slice(trades, HOLDOUT_START, HOLDOUT_END)
    research_metrics = _metrics_from_trades(research, len(research))
    holdout_metrics = _metrics_from_trades(holdout, len(holdout))
    research_pf = float(research_metrics["profit_factor"])
    holdout_pf = float(holdout_metrics["profit_factor"])
    degradation = max(0.0, (research_pf - holdout_pf) / research_pf * 100) if research_pf > 0 and math.isfinite(research_pf) else 0.0
    if holdout_metrics["trades"] < 30 or holdout_pf < 1.0 or holdout_metrics["expectancy"] < 0:
        verdict = "rejeté"
    elif holdout_pf > 1.05 and degradation <= 50:
        verdict = "OK"
    else:
        verdict = "fragile"
    return (
        {
            "filter": name,
            "research_trades": research_metrics["trades"],
            "research_profit_factor": research_metrics["profit_factor"],
            "research_expectancy": research_metrics["expectancy"],
            "research_drawdown": research_metrics["max_drawdown"],
            "holdout_trades": holdout_metrics["trades"],
            "holdout_profit_factor": holdout_metrics["profit_factor"],
            "holdout_expectancy": holdout_metrics["expectancy"],
            "holdout_drawdown": holdout_metrics["max_drawdown"],
            "pf_degradation_pct": degradation,
            "holdout_verdict": verdict,
        },
        verdict,
    )


def _filter_verdict(metrics: dict[str, Any], segment_verdict: str, holdout_verdict: str) -> tuple[str, str]:
    reasons: list[str] = []
    if metrics["trades"] < 100:
        reasons.append("too_few_trades")
    if metrics["trades_removed_pct"] > 60:
        reasons.append("removed_more_than_60_pct")
    if metrics["profit_factor"] < 1.0:
        reasons.append("profit_factor_below_1")
    if metrics["expectancy"] < 0:
        reasons.append("negative_expectancy")
    if metrics["concentration_best_month"] > 35:
        reasons.append("best_month_concentration_above_35")
    if metrics["concentration_top3_months"] > 75:
        reasons.append("top3_concentration_above_75")
    if holdout_verdict == "rejeté":
        reasons.append("holdout_bad")
    if segment_verdict == "fragile":
        reasons.append("segments_fragile")

    promising = (
        metrics["profit_factor"] > 1.15
        and metrics["expectancy"] > 0
        and metrics["max_drawdown"] < 5
        and metrics["trades"] >= 100
        and metrics["concentration_best_month"] < 35
        and metrics["concentration_top3_months"] < 75
        and holdout_verdict == "OK"
        and segment_verdict in {"OK", "mitigé"}
    )
    if promising:
        return "PROMETTEUR", "passes_filter_lab_rules"
    reworkable = (
        1.05 <= metrics["profit_factor"] <= 1.15
        and metrics["expectancy"] > 0
        and metrics["trades"] >= 100
        and metrics["concentration_best_month"] <= 53.7
        and holdout_verdict != "rejeté"
        and segment_verdict != "fragile"
    )
    if reworkable:
        return "À RETRAVAILLER", ";".join(reasons or ["needs_more_validation"])
    return "REJETÉ", ";".join(reasons or ["does_not_meet_filter_rules"])


def _adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    close = data["close"].astype(float)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    true_range = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_smoothed = true_range.rolling(period, min_periods=period).mean()
    plus_di = 100 * plus_dm.rolling(period, min_periods=period).mean() / atr_smoothed
    minus_di = 100 * minus_dm.rolling(period, min_periods=period).mean() / atr_smoothed
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100
    return dx.rolling(period, min_periods=period).mean()


def _enrich_trades(trades: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    market = data.copy()
    market["atr_14"] = atr(market, 14)
    market["ema20"] = ema(market["close"], 20)
    market["ema50"] = ema(market["close"], 50)
    market["ema200"] = ema(market["close"], 200)
    market["ema50_slope"] = market["ema50"] - market["ema50"].shift(4)
    market["distance_ema200_atr"] = (market["close"] - market["ema200"]).abs() / market["atr_14"]
    market["adx14"] = _adx(market, 14)
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True).dt.tz_convert(data.index.tz)
    out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True).dt.tz_convert(data.index.tz)
    out = out.sort_values("exit_time").reset_index(drop=True)
    out = out.join(market[["atr_14", "spread", "ema20", "ema50", "ema200", "ema50_slope", "distance_ema200_atr", "adx14"]], on="entry_time")
    out["month"] = out["exit_time"].dt.tz_localize(None).dt.to_period("M").astype(str)
    out["year"] = out["exit_time"].dt.tz_localize(None).dt.to_period("Y").astype(str)
    out["weekday"] = out["entry_time"].dt.day_name()
    out["entry_hour"] = out["entry_time"].dt.hour
    out["atr_rank"] = out["atr_14"].rank(method="first", pct=True)
    out["atr_regime"] = pd.cut(out["atr_rank"], bins=[0, 1 / 3, 2 / 3, 1], labels=["low", "mid", "high"], include_lowest=True)
    out["ema_slope_ok"] = ((out["side"] == "long") & (out["ema50_slope"] > 0)) | ((out["side"] == "short") & (out["ema50_slope"] < 0))
    out["ema_alignment_ok"] = (
        ((out["side"] == "long") & (out["ema20"] > out["ema50"]) & (out["ema50"] > out["ema200"]))
        | ((out["side"] == "short") & (out["ema20"] < out["ema50"]) & (out["ema50"] < out["ema200"]))
    )
    return out


def _build_filters(trades: pd.DataFrame) -> list[FilterSpec]:
    spread_p75 = float(trades["spread"].quantile(0.75))
    spread_p90 = float(trades["spread"].quantile(0.90))
    spread_mean_std = float(trades["spread"].mean() + trades["spread"].std(ddof=0))
    distance_threshold = float(trades["distance_ema200_atr"].median())
    worst_hours = trades.groupby("entry_hour")["net_pnl"].sum().sort_values().head(2).index.tolist()
    filters = [
        FilterSpec("baseline", "baseline", "No filter", lambda df: pd.Series(True, index=df.index)),
        FilterSpec("exclude_monday", "weekday", "Exclude Monday", lambda df: df["weekday"] != "Monday"),
        FilterSpec("exclude_tuesday", "weekday", "Exclude Tuesday", lambda df: df["weekday"] != "Tuesday"),
        FilterSpec("exclude_wednesday", "weekday", "Exclude Wednesday", lambda df: df["weekday"] != "Wednesday"),
        FilterSpec("exclude_thursday", "weekday", "Exclude Thursday", lambda df: df["weekday"] != "Thursday"),
        FilterSpec("exclude_friday", "weekday", "Exclude Friday", lambda df: df["weekday"] != "Friday"),
        FilterSpec("keep_tuesday_thursday", "weekday", "Keep Tuesday to Thursday", lambda df: df["weekday"].isin(["Tuesday", "Wednesday", "Thursday"])),
        FilterSpec("keep_tuesday_friday", "weekday", "Keep Tuesday to Friday", lambda df: df["weekday"].isin(["Tuesday", "Wednesday", "Thursday", "Friday"])),
        FilterSpec("exclude_17h", "time", "Exclude 17h entries", lambda df: df["entry_hour"] != 17),
        FilterSpec("keep_15_18", "time", "Keep 15h-18h entries", lambda df: df["entry_hour"].between(15, 18)),
        FilterSpec("keep_16_19", "time", "Keep 16h-19h entries", lambda df: df["entry_hour"].between(16, 19)),
        FilterSpec("keep_15_20", "time", "Keep 15h-20h entries", lambda df: df["entry_hour"].between(15, 20)),
        FilterSpec("exclude_two_worst_hours", "time", f"Exclude worst hours {worst_hours}", lambda df, hours=worst_hours: ~df["entry_hour"].isin(hours)),
        FilterSpec("exclude_low_atr", "atr", "Exclude low ATR regime", lambda df: df["atr_regime"] != "low"),
        FilterSpec("exclude_mid_atr", "atr", "Exclude mid ATR regime", lambda df: df["atr_regime"] != "mid"),
        FilterSpec("exclude_high_atr", "atr", "Exclude high ATR regime", lambda df: df["atr_regime"] != "high"),
        FilterSpec("keep_mid_high_atr", "atr", "Keep mid + high ATR", lambda df: df["atr_regime"].isin(["mid", "high"])),
        FilterSpec("keep_low_mid_atr", "atr", "Keep low + mid ATR", lambda df: df["atr_regime"].isin(["low", "mid"])),
        FilterSpec("spread_lte_p75", "spread", f"Spread <= p75 ({spread_p75:.2f})", lambda df, x=spread_p75: df["spread"] <= x),
        FilterSpec("spread_lte_p90", "spread", f"Spread <= p90 ({spread_p90:.2f})", lambda df, x=spread_p90: df["spread"] <= x),
        FilterSpec("spread_lte_mean_std", "spread", f"Spread <= mean+std ({spread_mean_std:.2f})", lambda df, x=spread_mean_std: df["spread"] <= x),
        FilterSpec("ema_slope_ok", "momentum", "EMA50 slope agrees with trade direction", lambda df: df["ema_slope_ok"]),
        FilterSpec("distance_ema200_min", "momentum", f"Distance to EMA200 >= median ATR units ({distance_threshold:.2f})", lambda df, x=distance_threshold: df["distance_ema200_atr"] >= x),
        FilterSpec("ema_alignment_ok", "momentum", "EMA20/50/200 alignment agrees with side", lambda df: df["ema_alignment_ok"]),
        FilterSpec("adx_gt_15", "momentum", "ADX14 > 15", lambda df: df["adx14"] > 15),
        FilterSpec("adx_gt_20", "momentum", "ADX14 > 20", lambda df: df["adx14"] > 20),
        FilterSpec("adx_gt_25", "momentum", "ADX14 > 25", lambda df: df["adx14"] > 25),
        FilterSpec("longs_only", "direction", "Long trades only", lambda df: df["side"] == "long"),
        FilterSpec("shorts_only", "direction", "Short trades only", lambda df: df["side"] == "short"),
        FilterSpec("exclude_monday_adx_gt_20", "combo", "Exclude Monday + ADX > 20", lambda df: (df["weekday"] != "Monday") & (df["adx14"] > 20)),
        FilterSpec("exclude_monday_spread_lte_p75", "combo", "Exclude Monday + spread <= p75", lambda df, x=spread_p75: (df["weekday"] != "Monday") & (df["spread"] <= x)),
        FilterSpec("adx_gt_20_spread_lte_p75", "combo", "ADX > 20 + spread <= p75", lambda df, x=spread_p75: (df["adx14"] > 20) & (df["spread"] <= x)),
        FilterSpec("ema_slope_spread_lte_p75", "combo", "EMA slope filter + spread <= p75", lambda df, x=spread_p75: df["ema_slope_ok"] & (df["spread"] <= x)),
        FilterSpec("ema_slope_exclude_monday", "combo", "EMA slope filter + exclude Monday", lambda df: df["ema_slope_ok"] & (df["weekday"] != "Monday")),
        FilterSpec("best_broad_time_adx_gt_20", "combo", "Exclude 17h + ADX > 20", lambda df: (df["entry_hour"] != 17) & (df["adx14"] > 20)),
    ]
    return filters


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
                if column in {"trades", "max_losing_streak", "positive_months", "negative_months", "bad_segments", "negative_segments"}:
                    values.append(str(int(value)))
                elif "factor" in column or column.endswith("_pf"):
                    values.append(_fmt(value, 3))
                else:
                    values.append(_fmt(value, 2))
            else:
                values.append("" if pd.isna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _build_report(results: pd.DataFrame, segments: pd.DataFrame, holdout: pd.DataFrame, output_csv: Path, segments_csv: Path, holdout_csv: Path) -> str:
    columns = [
        "filter",
        "category",
        "trades",
        "trades_removed_pct",
        "profit_net",
        "profit_factor",
        "expectancy",
        "max_drawdown",
        "concentration_best_month",
        "concentration_top3_months",
        "robustness_score",
        "verdict",
        "reason",
    ]
    top_robust = results.sort_values("robustness_score", ascending=False).head(10)
    top_pf = results.sort_values("profit_factor", ascending=False).head(10)
    top_exp = results.sort_values("expectancy", ascending=False).head(10)
    rejected = results[results["verdict"] == "REJETÉ"].sort_values("robustness_score", ascending=False)
    rework = results[results["verdict"] == "À RETRAVAILLER"].sort_values("robustness_score", ascending=False)
    promising = results[results["verdict"] == "PROMETTEUR"].sort_values("robustness_score", ascending=False)
    baseline = results[results["filter"] == "baseline"]
    conclusion = _conclusion(results)
    return f"""# US100 H1 Filter Lab

## Résumé Du Candidat Brut

{_markdown_table(baseline, columns)}

## Fichiers

- Résultats: `{output_csv}`
- Segments: `{segments_csv}`
- Holdout: `{holdout_csv}`

## Top 10 Par Robustesse

{_markdown_table(top_robust, columns)}

## Top 10 Par Profit Factor

{_markdown_table(top_pf, columns)}

## Top 10 Par Expectancy

{_markdown_table(top_exp, columns)}

## Filtres Prometteurs

{_markdown_table(promising, columns)}

## Filtres À Retravailler

{_markdown_table(rework, columns)}

## Filtres Rejetés

{_markdown_table(rejected, columns)}

## Analyse Segments

{_markdown_table(segments.sort_values("filter"), ["filter", "A_2023_2024_pf", "A_2023_2024_expectancy", "A_2023_2024_drawdown", "B_2024_2025_pf", "B_2024_2025_expectancy", "B_2024_2025_drawdown", "C_2025_2026_pf", "C_2025_2026_expectancy", "C_2025_2026_drawdown", "segment_verdict", "bad_segments", "negative_segments"])}

## Analyse Holdout

{_markdown_table(holdout.sort_values("filter"), ["filter", "research_trades", "research_profit_factor", "research_expectancy", "research_drawdown", "holdout_trades", "holdout_profit_factor", "holdout_expectancy", "holdout_drawdown", "pf_degradation_pct", "holdout_verdict"])}

## Conclusion Froide

{conclusion}
"""


def _conclusion(results: pd.DataFrame) -> str:
    promising = results[results["verdict"] == "PROMETTEUR"]
    if not promising.empty:
        best = promising.sort_values("robustness_score", ascending=False).iloc[0]
        return (
            f"Un filtre prometteur existe: {best['filter']} avec PF {_fmt(best['profit_factor'], 3)}, "
            f"expectancy {_fmt(best['expectancy'])}, {int(best['trades'])} trades. "
            "Il mérite une validation avancée séparée, sans le considérer tradable."
        )
    rework = results[results["verdict"] == "À RETRAVAILLER"]
    if not rework.empty:
        best = rework.sort_values("robustness_score", ascending=False).iloc[0]
        return (
            f"Aucun filtre ne passe les règles prometteuses. Le meilleur filtre à retravailler est {best['filter']} "
            f"avec PF {_fmt(best['profit_factor'], 3)}, expectancy {_fmt(best['expectancy'])}, "
            f"concentration meilleur mois {_fmt(best['concentration_best_month'])}%. "
            "La stratégie reste non validée."
        )
    return "Aucun filtre ne mérite de suite. Le candidat doit être rejeté ou reformulé."


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output_csv = output.with_suffix(".csv")
    segments_csv = output.with_name(f"{output.stem}_segments.csv")
    holdout_csv = output.with_name(f"{output.stem}_holdout.csv")

    strategies_cfg = load_yaml(ROOT / "config/strategies.yaml")
    risk_cfg = load_yaml(ROOT / "config/risk.yaml")
    assets_cfg = load_yaml(ROOT / "config/assets.yaml")
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset_spec = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    data, cleaning = load_mt5_ohlcv(data_path, timezone=args.timezone, timeframe=args.timeframe)
    result = BacktestEngine(backtest_cfg, asset_spec).run(data, STRATEGY_REGISTRY[args.strategy](strat_cfg))
    raw_metrics = calculate_metrics(result.trades, result.equity_curve, backtest_cfg.initial_capital)
    trades = _enrich_trades(result.trades, data)
    filters = _build_filters(trades)

    result_rows: list[dict[str, Any]] = []
    segment_rows: list[dict[str, Any]] = []
    holdout_rows: list[dict[str, Any]] = []
    for spec in filters:
        mask = spec.predicate(trades).fillna(False)
        filtered = trades[mask].copy()
        metrics = _metrics_from_trades(filtered, len(trades), backtest_cfg.initial_capital)
        segment_row, segment_verdict = _segment_analysis(spec.name, filtered)
        holdout_row, holdout_verdict = _holdout_analysis(spec.name, filtered)
        verdict, reason = _filter_verdict(metrics, segment_verdict, holdout_verdict)
        result_rows.append(
            {
                "filter": spec.name,
                "category": spec.category,
                "description": spec.description,
                **metrics,
                "segment_verdict": segment_verdict,
                "holdout_verdict": holdout_verdict,
                "verdict": verdict,
                "reason": reason,
            }
        )
        segment_rows.append(segment_row)
        holdout_rows.append(holdout_row)

    results = pd.DataFrame(result_rows).sort_values(["verdict", "robustness_score"], ascending=[True, False]).reset_index(drop=True)
    segments = pd.DataFrame(segment_rows)
    holdout = pd.DataFrame(holdout_rows)
    results.to_csv(output_csv, index=False)
    segments.to_csv(segments_csv, index=False)
    holdout.to_csv(holdout_csv, index=False)
    output.write_text(_build_report(results, segments, holdout, output_csv, segments_csv, holdout_csv), encoding="utf-8")

    counts = results["verdict"].value_counts().to_dict()
    print(f"Filter lab report: {output}")
    print(f"Filter lab CSV: {output_csv}")
    print(f"Segments CSV: {segments_csv}")
    print(f"Holdout CSV: {holdout_csv}")
    print(f"Baseline trades: {int(raw_metrics['trade_count'])} | PF: {raw_metrics['profit_factor']:.3f} | Expectancy: {raw_metrics['expectancy']:.2f}")
    print(f"PROMETTEUR: {counts.get('PROMETTEUR', 0)}")
    print(f"À RETRAVAILLER: {counts.get('À RETRAVAILLER', 0)}")
    print(f"REJETÉ: {counts.get('REJETÉ', 0)}")
    print(results.sort_values("robustness_score", ascending=False).head(10)[["filter", "trades", "profit_factor", "expectancy", "max_drawdown", "concentration_best_month", "concentration_top3_months", "robustness_score", "verdict", "holdout_verdict", "segment_verdict"]].to_string(index=False))


if __name__ == "__main__":
    main()
