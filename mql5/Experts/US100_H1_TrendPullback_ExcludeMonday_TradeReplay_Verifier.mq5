#property strict
#property version "2.30"
#property description "US100 H1 trend pullback exclude Monday trade replay verifier. Simulates trades for Python parity; no live trading."

// TRADE REPLAY VERIFIER ONLY — DO NOT USE FOR LIVE TRADING
// This EA simulates closed-bar signals and next-bar-open execution.
// It does not call OrderSend, CTrade.Buy, CTrade.Sell or any equivalent trade action.

input bool EnableTrading = false;
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_H1;
input int InpEMAFast = 20;
input int InpEMAMid = 50;
input int InpEMASlow = 200;
input int InpEMASlopeLookback = 4;
input int InpATRPeriod = 14;
input double InpATRMinFilter = 20.0;
input double InpSLATRMultiplier = 1.5;
input double InpTPRMultiple = 1.5;
input int InpSwingLookback = 5;
input int InpMaxSpreadPoints = 250;
input double InpSpreadMultiplier = 1.0;
input double InpSlippagePoints = 5.0;
input double InpCommissionPerLotRoundTurn = 7.0;
input double InpInitialCapital = 100000.0;
input double InpRiskPerTradePct = 0.25;
input int InpMaxTradesPerDay = 2;
input string InpOutputFile = "us100_h1_mt5_trade_replay.csv";

int EmaFastHandle = INVALID_HANDLE;
int EmaMidHandle = INVALID_HANDLE;
int EmaSlowHandle = INVALID_HANDLE;
int AtrHandle = INVALID_HANDLE;
int FileHandle = INVALID_HANDLE;
datetime LastBarTime = 0;
double Equity = 0.0;
int TradesToday = 0;
int CurrentDayOfYear = -1;

bool HasPosition = false;
datetime PositionSignalTime = 0;
datetime PositionEntryTime = 0;
string PositionDirection = "";
double PositionEntry = 0.0;
double PositionStop = 0.0;
double PositionTarget = 0.0;
double PositionLots = 0.0;
double PositionRiskAmount = 0.0;
double PositionSpreadEntry = 0.0;

bool IsNewBar()
{
   datetime times[1];
   if(CopyTime(_Symbol, InpTimeframe, 0, 1, times) != 1)
      return false;
   if(times[0] == LastBarTime)
      return false;
   LastBarTime = times[0];
   return true;
}

bool BufferValue(int handle, int shift, double &value)
{
   double buffer[1];
   if(CopyBuffer(handle, 0, shift, 1, buffer) != 1)
      return false;
   value = buffer[0];
   return value != EMPTY_VALUE;
}

double SpreadPoints(const MqlRates &bar)
{
   double spread = 0.0;
   if(bar.spread > 0)
      spread = (double)bar.spread;
   else
   {
      long currentSpread = 0;
      if(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD, currentSpread))
         spread = (double)currentSpread;
   }
   return spread * InpSpreadMultiplier;
}

double EntryPrice(double mid, string direction, double spreadPoints)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double adjustment = spreadPoints * point / 2.0 + InpSlippagePoints * point;
   if(direction == "long")
      return mid + adjustment;
   return mid - adjustment;
}

double ExitPrice(double mid, string direction, double spreadPoints)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double adjustment = spreadPoints * point / 2.0 + InpSlippagePoints * point;
   if(direction == "long")
      return mid - adjustment;
   return mid + adjustment;
}

bool InSession(datetime ts)
{
   MqlDateTime t;
   TimeToStruct(ts, t);
   int minutes = t.hour * 60 + t.min;
   return minutes >= (15 * 60 + 45) && minutes <= (18 * 60);
}

bool IsMonday(datetime ts)
{
   MqlDateTime t;
   TimeToStruct(ts, t);
   return t.day_of_week == 1;
}

void WriteHeader()
{
   FileWrite(
      FileHandle,
      "signal_timestamp",
      "entry_timestamp",
      "direction",
      "entry_price",
      "stop_loss",
      "take_profit",
      "exit_timestamp",
      "exit_price",
      "exit_reason",
      "gross_pnl",
      "net_pnl",
      "r_multiple",
      "spread_entry",
      "spread_exit"
   );
}

void ClosePosition(datetime exitTime, double exitMid, string reason, double spreadExit)
{
   if(!HasPosition)
      return;
   double exitPrice = ExitPrice(exitMid, PositionDirection, spreadExit);
   double sign = PositionDirection == "long" ? 1.0 : -1.0;
   double grossPnl = (exitPrice - PositionEntry) * sign * PositionLots;
   double commission = InpCommissionPerLotRoundTurn * PositionLots;
   double netPnl = grossPnl - commission;
   double rMultiple = PositionRiskAmount > 0.0 ? netPnl / PositionRiskAmount : 0.0;
   Equity += netPnl;
   FileWrite(
      FileHandle,
      TimeToString(PositionSignalTime, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      TimeToString(PositionEntryTime, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      PositionDirection,
      DoubleToString(PositionEntry, _Digits),
      DoubleToString(PositionStop, _Digits),
      DoubleToString(PositionTarget, _Digits),
      TimeToString(exitTime, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      DoubleToString(exitPrice, _Digits),
      reason,
      DoubleToString(grossPnl, 8),
      DoubleToString(netPnl, 8),
      DoubleToString(rMultiple, 8),
      DoubleToString(PositionSpreadEntry, 2),
      DoubleToString(spreadExit, 2)
   );
   FileFlush(FileHandle);
   HasPosition = false;
}

void EvaluateExit(const MqlRates &bar)
{
   if(!HasPosition)
      return;
   double exitMid = 0.0;
   string reason = "";
   if(PositionDirection == "long")
   {
      if(bar.low <= PositionStop)
      {
         exitMid = PositionStop;
         reason = "stop_loss";
      }
      else if(bar.high >= PositionTarget)
      {
         exitMid = PositionTarget;
         reason = "take_profit";
      }
   }
   else
   {
      if(bar.high >= PositionStop)
      {
         exitMid = PositionStop;
         reason = "stop_loss";
      }
      else if(bar.low <= PositionTarget)
      {
         exitMid = PositionTarget;
         reason = "take_profit";
      }
   }
   MqlDateTime t;
   TimeToStruct(bar.time, t);
   if(reason == "" && t.hour >= 18)
   {
      exitMid = bar.close;
      reason = "force_flat";
   }
   if(reason != "")
      ClosePosition(bar.time, exitMid, reason, SpreadPoints(bar));
}

void TryOpenFromClosedSignal(const MqlRates &entryBar, const MqlRates &signalBar, const MqlRates &prevBar, const MqlRates &bars[])
{
   if(HasPosition)
      return;
   MqlDateTime t;
   TimeToStruct(signalBar.time, t);
   if(CurrentDayOfYear != t.day_of_year)
   {
      CurrentDayOfYear = t.day_of_year;
      TradesToday = 0;
   }
   if(TradesToday >= InpMaxTradesPerDay)
      return;
   if(IsMonday(signalBar.time) || !InSession(signalBar.time) || t.hour >= 18)
      return;
   double spreadSignal = SpreadPoints(signalBar);
   if(spreadSignal > InpMaxSpreadPoints)
      return;

   double emaFast = 0.0;
   double emaFastPrev = 0.0;
   double emaMid = 0.0;
   double emaMidPast = 0.0;
   double emaSlow = 0.0;
   double atr = 0.0;
   if(!BufferValue(EmaFastHandle, 1, emaFast)) return;
   if(!BufferValue(EmaFastHandle, 2, emaFastPrev)) return;
   if(!BufferValue(EmaMidHandle, 1, emaMid)) return;
   if(!BufferValue(EmaMidHandle, 1 + InpEMASlopeLookback, emaMidPast)) return;
   if(!BufferValue(EmaSlowHandle, 1, emaSlow)) return;
   if(!BufferValue(AtrHandle, 1, atr)) return;
   if(atr <= 0.0 || atr < InpATRMinFilter) return;

   double emaMidSlope = emaMid - emaMidPast;
   bool longOk = signalBar.close > emaSlow && emaMidSlope > 0.0;
   bool shortOk = signalBar.close < emaSlow && emaMidSlope < 0.0;
   bool pullbackLong = prevBar.low <= emaFastPrev;
   bool pullbackShort = prevBar.high >= emaFastPrev;
   bool resumeLong = signalBar.close > signalBar.open && signalBar.close > prevBar.high;
   bool resumeShort = signalBar.close < signalBar.open && signalBar.close < prevBar.low;

   string direction = "";
   double stopLoss = 0.0;
   double takeProfit = 0.0;
   if(longOk && pullbackLong && resumeLong)
   {
      direction = "long";
      stopLoss = bars[1].low;
      for(int i = 2; i <= InpSwingLookback + 1 && i < ArraySize(bars); i++)
         stopLoss = MathMin(stopLoss, bars[i].low);
      if(stopLoss >= signalBar.close || signalBar.close - stopLoss < 0.25 * atr)
         stopLoss = signalBar.close - InpSLATRMultiplier * atr;
      double risk = signalBar.close - stopLoss;
      takeProfit = signalBar.close + risk * InpTPRMultiple;
   }
   else if(shortOk && pullbackShort && resumeShort)
   {
      direction = "short";
      stopLoss = bars[1].high;
      for(int i = 2; i <= InpSwingLookback + 1 && i < ArraySize(bars); i++)
         stopLoss = MathMax(stopLoss, bars[i].high);
      if(stopLoss <= signalBar.close || stopLoss - signalBar.close < 0.25 * atr)
         stopLoss = signalBar.close + InpSLATRMultiplier * atr;
      double risk = stopLoss - signalBar.close;
      takeProfit = signalBar.close - risk * InpTPRMultiple;
   }
   if(direction == "")
      return;

   double spreadEntry = SpreadPoints(entryBar);
   double entry = EntryPrice(entryBar.open, direction, spreadEntry);
   double priceRisk = MathAbs(entry - stopLoss);
   if(priceRisk <= 0.0)
      return;
   double riskAmount = Equity * InpRiskPerTradePct / 100.0;
   double lots = riskAmount / priceRisk;
   if(lots <= 0.0)
      return;

   HasPosition = true;
   PositionSignalTime = signalBar.time;
   PositionEntryTime = entryBar.time;
   PositionDirection = direction;
   PositionEntry = entry;
   PositionStop = stopLoss;
   PositionTarget = takeProfit;
   PositionLots = lots;
   PositionRiskAmount = riskAmount;
   PositionSpreadEntry = spreadEntry;
   TradesToday++;
}

int OnInit()
{
   Equity = InpInitialCapital;
   if(EnableTrading)
      Print("EnableTrading=true was requested, but this trade replay verifier never sends orders.");
   if(!EnableTrading)
      Print("Trade replay/export only: EnableTrading=false, no trading allowed.");
   EmaFastHandle = iMA(_Symbol, InpTimeframe, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE);
   EmaMidHandle = iMA(_Symbol, InpTimeframe, InpEMAMid, 0, MODE_EMA, PRICE_CLOSE);
   EmaSlowHandle = iMA(_Symbol, InpTimeframe, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE);
   AtrHandle = iATR(_Symbol, InpTimeframe, InpATRPeriod);
   if(EmaFastHandle == INVALID_HANDLE || EmaMidHandle == INVALID_HANDLE || EmaSlowHandle == INVALID_HANDLE || AtrHandle == INVALID_HANDLE)
      return INIT_FAILED;
   FileHandle = FileOpen(InpOutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(FileHandle == INVALID_HANDLE)
      return INIT_FAILED;
   WriteHeader();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(HasPosition)
   {
      MqlRates lastBar[1];
      if(CopyRates(_Symbol, InpTimeframe, 1, 1, lastBar) == 1)
         ClosePosition(lastBar[0].time, lastBar[0].close, "end_of_backtest", SpreadPoints(lastBar[0]));
   }
   if(FileHandle != INVALID_HANDLE) FileClose(FileHandle);
   if(EmaFastHandle != INVALID_HANDLE) IndicatorRelease(EmaFastHandle);
   if(EmaMidHandle != INVALID_HANDLE) IndicatorRelease(EmaMidHandle);
   if(EmaSlowHandle != INVALID_HANDLE) IndicatorRelease(EmaSlowHandle);
   if(AtrHandle != INVALID_HANDLE) IndicatorRelease(AtrHandle);
}

void OnTick()
{
   if(!IsNewBar())
      return;
   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   int needed = MathMax(InpSwingLookback + 2, InpEMASlopeLookback + 3);
   if(CopyRates(_Symbol, InpTimeframe, 0, needed, bars) < needed)
      return;
   EvaluateExit(bars[1]);
   TryOpenFromClosedSignal(bars[0], bars[1], bars[2], bars);
}
