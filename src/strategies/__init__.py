"""Strategy implementations."""

from src.strategies.base import BaseStrategy
from src.strategies.eur_london_breakout import EURLondonBreakout
from src.strategies.eur_london_mean_reversion import EURLondonMeanReversion
from src.strategies.nas_opening_breakout import NASOpeningBreakout
from src.strategies.nas_opening_range_retest import NASOpeningRangeRetest
from src.strategies.nas_post_open_mean_reversion import NASPostOpenMeanReversion
from src.strategies.nas_trend_pullback import NASTrendPullback
from src.strategies.xau_failed_breakout_reversal import XAUFailedBreakoutReversal
from src.strategies.xau_pullback_trend import XAUPullbackTrend
from src.strategies.xau_trend_breakout import XAUTrendBreakout


STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    XAUTrendBreakout.name: XAUTrendBreakout,
    XAUFailedBreakoutReversal.name: XAUFailedBreakoutReversal,
    XAUPullbackTrend.name: XAUPullbackTrend,
    NASOpeningBreakout.name: NASOpeningBreakout,
    NASPostOpenMeanReversion.name: NASPostOpenMeanReversion,
    NASTrendPullback.name: NASTrendPullback,
    NASOpeningRangeRetest.name: NASOpeningRangeRetest,
    EURLondonBreakout.name: EURLondonBreakout,
    EURLondonMeanReversion.name: EURLondonMeanReversion,
}
