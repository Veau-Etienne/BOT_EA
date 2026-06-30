from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from src.backtest.validation import ValidationResult


def _fmt(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value == float("inf"):
            return "inf"
        return f"{value:.{decimals}f}"
    return str(value)


def build_backtest_report(
    metrics: dict[str, Any],
    validation: ValidationResult,
    monte_carlo: dict[str, Any] | None = None,
    title: str = "Backtest Report",
    entry_mode: str | None = None,
    cost_multiplier: float = 1.0,
    diagnostic_full_sample: bool = False,
) -> str:
    monte_carlo = monte_carlo or {}
    lines = [
        f"# {title}",
        "",
    ]
    if diagnostic_full_sample:
        lines.extend(["> MODE DIAGNOSTIC — non tradable, drawdown limits ignored for analysis.", ""])
    if entry_mode or cost_multiplier != 1.0:
        lines.extend(
            [
                "## Execution",
                "",
                f"- Entry mode: `{entry_mode or 'bar_close'}`",
                f"- Cost multiplier: `x{cost_multiplier:.2f}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Verdict",
            "",
            f"- Verdict: **{validation.verdict}**",
            f"- Robustness score: `{validation.robustness_score}/100`",
            "",
            "## Core Metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Initial capital | {_fmt(metrics.get('initial_capital'))} |",
            f"| Final capital | {_fmt(metrics.get('final_capital'))} |",
            f"| Net profit | {_fmt(metrics.get('net_profit'))} |",
            f"| Profit factor | {_fmt(metrics.get('profit_factor'))} |",
            f"| Winrate | {_fmt(metrics.get('winrate_pct'))}% |",
            f"| Expectancy | {_fmt(metrics.get('expectancy'))} |",
            f"| Max drawdown | {_fmt(metrics.get('max_drawdown_pct'))}% |",
            f"| Max losing streak | {_fmt(metrics.get('max_loss_streak'), 0)} |",
            f"| Trades | {_fmt(metrics.get('trade_count'), 0)} |",
            f"| Avg trades/day | {_fmt(metrics.get('trades_per_day_avg'))} |",
            f"| Best month | {_fmt(metrics.get('best_month'))} |",
            f"| Worst month | {_fmt(metrics.get('worst_month'))} |",
            f"| Monthly stability | {_fmt(metrics.get('monthly_stability_pct'))}% |",
            f"| Profit from best month | {_fmt(metrics.get('monthly_profit_concentration_pct'))}% |",
        ]
    )

    lines.extend(["", "## Validation Checks", "", "| Rule | Pass |", "| --- | ---: |"])
    for key, passed in validation.checks.items():
        lines.append(f"| {key} | {'yes' if passed else 'no'} |")
    if validation.warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in validation.warnings:
            lines.append(f"- {warning}")

    lines.extend(["", "## Month By Month", "", "| Month | PnL |", "| --- | ---: |"])
    monthly = metrics.get("performance_by_month", {})
    if monthly:
        for month, pnl in monthly.items():
            lines.append(f"| {month} | {_fmt(pnl)} |")
    else:
        lines.append("| n/a | 0.00 |")

    lines.extend(["", "## Year By Year", "", "| Year | PnL |", "| --- | ---: |"])
    yearly = metrics.get("performance_by_year", {})
    if yearly:
        for year, pnl in yearly.items():
            lines.append(f"| {year} | {_fmt(pnl)} |")
    else:
        lines.append("| n/a | 0.00 |")

    lines.extend(["", "## R Multiple Distribution", "", "| Statistic | R |", "| --- | ---: |"])
    distribution = metrics.get("r_multiple_distribution", {})
    if distribution:
        for key, value in distribution.items():
            lines.append(f"| {key} | {_fmt(value)} |")
    else:
        lines.append("| n/a | 0.00 |")

    if monte_carlo:
        lines.extend(["", "## Monte Carlo", "", "| Metric | Value |", "| --- | ---: |"])
        for key, value in monte_carlo.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    lines.append(f"| {key}.{sub_key} | {_fmt(sub_value)} |")
            else:
                lines.append(f"| {key} | {_fmt(value)} |")

    return "\n".join(lines) + "\n"


def write_backtest_report(path: str | Path, report: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    return output


def latest_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
