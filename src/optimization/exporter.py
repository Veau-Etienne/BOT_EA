from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


def _json_default(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def export_top_strategies(
    optimization_results: pd.DataFrame,
    strategy_name: str,
    base_config: dict[str, Any],
    param_names: list[str],
    output_dir: str | Path,
    top_n: int = 5,
) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for rank, (_, row) in enumerate(optimization_results.head(top_n).iterrows(), start=1):
        params = {name: row[name].item() if hasattr(row[name], "item") else row[name] for name in param_names}
        payload = {
            "strategy": strategy_name,
            "rank": rank,
            "config": {**base_config, **params},
            "metrics": {key: value for key, value in row.to_dict().items() if key not in param_names},
        }
        path = output / f"{strategy_name}_rank_{rank}.json"
        path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
        paths.append(path)
    return paths
