#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.execution import entry_price
from src.data.loader import load_mt5_ohlcv
from src.strategies import STRATEGY_REGISTRY
from src.utils.config import build_backtest_config, load_yaml, resolve_asset_spec, strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export theoretical Python strategy signals for MT5 parity checks.")
    parser.add_argument("--data", required=True, help="Clean or MT5 CSV used by Python.")
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_REGISTRY))
    parser.add_argument("--asset", required=True, help="Label used in output metadata, for example US100_H1.")
    parser.add_argument("--output", required=True, help="CSV output path.")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--assets-config", default=str(ROOT / "config/assets.yaml"))
    parser.add_argument("--risk-config", default=str(ROOT / "config/risk.yaml"))
    parser.add_argument("--strategies-config", default=str(ROOT / "config/strategies.yaml"))
    return parser.parse_args()


def _number(row: pd.Series, column: str) -> float | None:
    if column not in row or pd.isna(row[column]):
        return None
    return float(row[column])


def main() -> None:
    args = parse_args()
    strategies_cfg = load_yaml(args.strategies_config)
    risk_cfg = load_yaml(args.risk_config)
    assets_cfg = load_yaml(args.assets_config)
    strat_cfg = strategy_config(strategies_cfg, args.strategy)
    asset = resolve_asset_spec(assets_cfg, strat_cfg["symbol"])
    backtest_cfg = build_backtest_config(risk_cfg, strat_cfg)

    data, cleaning = load_mt5_ohlcv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    strategy = STRATEGY_REGISTRY[args.strategy](strat_cfg)
    prepared = strategy.prepare(data)

    rows: list[dict[str, object]] = []
    for i, (ts, row) in enumerate(prepared.iterrows()):
        signal = strategy.generate_signal(i, prepared)
        if signal is None:
            continue
        spread_points = float(row["spread"]) if "spread" in prepared.columns and pd.notna(row.get("spread")) else backtest_cfg.spread_points
        theoretical_entry = entry_price(float(row["close"]), signal.direction, spread_points, backtest_cfg.slippage_points, asset.point)
        rows.append(
            {
                "signal_id": f"{args.asset}_{args.strategy}_{len(rows) + 1:05d}",
                "timestamp": pd.Timestamp(ts).tz_localize(None).strftime("%Y-%m-%d %H:%M:%S"),
                "direction": signal.direction,
                "entry_price": theoretical_entry,
                "stop_loss": float(signal.stop_loss),
                "take_profit": float(signal.take_profit),
                "risk_r": abs(theoretical_entry - float(signal.stop_loss)),
                "spread": spread_points,
                "atr": _number(row, "atr"),
                "ema_fast": _number(row, "ema_fast"),
                "ema_slow": _number(row, "ema_mid"),
                "ema200": _number(row, "ema_slow"),
                "reason": str(signal.metadata.get("strategy", args.strategy)),
                "day_of_week": pd.Timestamp(ts).day_name(),
                "hour": int(pd.Timestamp(ts).hour),
                "allowed_by_filters": True,
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        rows,
        columns=[
            "signal_id",
            "timestamp",
            "direction",
            "entry_price",
            "stop_loss",
            "take_profit",
            "risk_r",
            "spread",
            "atr",
            "ema_fast",
            "ema_slow",
            "ema200",
            "reason",
            "day_of_week",
            "hour",
            "allowed_by_filters",
        ],
    ).to_csv(output, index=False)

    print(f"Rows loaded: {cleaning.rows_out}")
    print(f"Signals exported: {len(rows)}")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
