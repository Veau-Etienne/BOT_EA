from __future__ import annotations


DEFAULT_GRID = {
    "xau_trend_breakout": {"sl_atr": [1.2, 1.5, 1.8], "tp_atr": [2.0, 2.5, 3.0], "donchian_period": [20, 30]},
    "xau_failed_breakout_reversal": {
        "donchian_period": [20, 30],
        "reentry_bars": [2, 3],
        "tp_r_multiple": [1.5, 2.0],
        "tp_mode": ["range_mid"],
    },
    "xau_pullback_trend": {
        "ema_fast": [20, 50],
        "tp_r_multiple": [1.5, 2.0, 2.5],
        "sl_atr_multiplier": [1.2, 1.5],
    },
    "nas_opening_breakout": {
        "opening_range_minutes": [15, 30, 45, 60],
        "tp_r_multiple": [1.0, 1.5, 2.0],
        "min_atr_filter": [20, 40],
        "min_range_atr_ratio": [0.5, 0.8],
        "max_range_atr_ratio": [2.5, 3.0],
        "break_even_at_r": [None, 1.0],
        "max_trades_per_day": [1, 2],
    },
    "nas_post_open_mean_reversion": {
        "initial_window_minutes": [30, 45, 60],
        "min_initial_move_atr": [0.8, 1.0, 1.2],
        "tp_r_multiple": [0.75, 1.0],
        "max_trades_per_day": [1, 2],
    },
    "nas_trend_pullback": {
        "pullback_ema": [20, 50],
        "tp_r_multiple": [1.0, 1.5, 2.0],
        "sl_atr_multiplier": [1.2, 1.5],
    },
    "nas_opening_range_retest": {
        "opening_range_minutes": [30, 45],
        "retest_tolerance_atr": [0.15, 0.25, 0.35],
        "tp_r_multiple": [1.0, 1.5, 2.0],
    },
    "eur_london_breakout": {"tp_r": [1.2, 1.8, 2.2], "min_atr": [0.0003, 0.0005, 0.0007]},
    "eur_london_mean_reversion": {"tp_r_multiple": [0.75, 1.0, 1.25], "atr_min_filter": [0.0002, 0.0003, 0.0005]},
}
