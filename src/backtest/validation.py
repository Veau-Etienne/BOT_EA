from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Verdict = Literal["VALIDABLE", "À RETRAVAILLER", "REJETÉE"]


@dataclass(frozen=True)
class ValidationResult:
    verdict: Verdict
    robustness_score: float
    checks: dict[str, bool]
    warnings: list[str]


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number == float("inf"):
        return 999.0
    if number == float("-inf"):
        return -999.0
    if number != number:
        return default
    return number


def robustness_score(metrics: dict[str, Any], monte_carlo_p95_dd: float | None = None) -> float:
    pf = _finite(metrics.get("profit_factor"))
    expectancy = _finite(metrics.get("expectancy"))
    trade_count = _finite(metrics.get("trade_count"))
    dd = _finite(metrics.get("max_drawdown_pct"))
    stability = _finite(metrics.get("monthly_stability_pct"))
    concentration = _finite(metrics.get("monthly_profit_concentration_pct"))
    mc_dd = _finite(monte_carlo_p95_dd, dd)

    score = 0.0
    score += min(25.0, max(0.0, (pf - 1.0) / 0.5 * 25.0))
    score += 20.0 if expectancy > 0 else 0.0
    score += min(20.0, trade_count / 100.0 * 20.0)
    score += max(0.0, 15.0 - min(15.0, dd / 8.0 * 15.0))
    score += min(10.0, stability / 100.0 * 10.0)
    score += max(0.0, 10.0 - max(0.0, concentration - 40.0) / 60.0 * 10.0)
    score -= max(0.0, mc_dd - 10.0)
    return round(max(0.0, min(100.0, score)), 2)


def validate_strategy(
    metrics: dict[str, Any],
    monte_carlo_p95_dd: float | None = None,
    diagnostic_full_sample: bool = False,
) -> ValidationResult:
    concentration = _finite(metrics.get("monthly_profit_concentration_pct"))
    checks = {
        "profit_factor_gt_1_20": _finite(metrics.get("profit_factor")) > 1.20,
        "min_100_trades": _finite(metrics.get("trade_count")) >= 100,
        "expectancy_positive": _finite(metrics.get("expectancy")) > 0,
        "max_drawdown_lt_8_pct": _finite(metrics.get("max_drawdown_pct")) < 8.0,
        "single_month_profit_lte_40_pct": concentration <= 40.0 if _finite(metrics.get("net_profit")) > 0 else False,
        "monte_carlo_p95_drawdown_lt_10_pct": _finite(monte_carlo_p95_dd, 999.0) < 10.0,
    }
    warnings: list[str] = []
    if not checks["min_100_trades"]:
        warnings.append("Too few trades for validation; require at least 100.")
    if not checks["single_month_profit_lte_40_pct"]:
        warnings.append("Profit concentration is too high; more than 40% comes from one month or strategy is not profitable.")
    if _finite(metrics.get("monthly_stability_pct")) < 50 and _finite(metrics.get("trade_count")) > 0:
        warnings.append("Monthly stability is weak; fewer than half of months are profitable.")
    if not checks["monte_carlo_p95_drawdown_lt_10_pct"]:
        warnings.append("Monte Carlo 95th percentile drawdown is above the 10% validation limit.")
    if diagnostic_full_sample:
        warnings.append("MODE DIAGNOSTIC — non tradable, drawdown limits ignored for analysis.")

    score = robustness_score(metrics, monte_carlo_p95_dd)
    if all(checks.values()):
        verdict: Verdict = "VALIDABLE"
    elif (
        _finite(metrics.get("profit_factor")) <= 1.0
        or _finite(metrics.get("expectancy")) <= 0
        or _finite(metrics.get("trade_count")) < 30
        or _finite(metrics.get("max_drawdown_pct")) >= 12.0
        or _finite(monte_carlo_p95_dd, 0.0) >= 15.0
    ):
        verdict = "REJETÉE"
    else:
        verdict = "À RETRAVAILLER"
    if diagnostic_full_sample and verdict == "VALIDABLE":
        verdict = "À RETRAVAILLER"

    return ValidationResult(verdict=verdict, robustness_score=score, checks=checks, warnings=warnings)
