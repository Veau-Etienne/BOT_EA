#property strict
#property version "2.00"
#property description "US100 H1 trend pullback exclude Monday verifier. Exports MT5 signals for Python parity; trading disabled by default."

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
input int InpSlippagePoints = 5;
input string InpOutputFile = "us100_h1_mt5_signals.csv";

int EmaFastHandle = INVALID_HANDLE;
int EmaMidHandle = INVALID_HANDLE;
int EmaSlowHandle = INVALID_HANDLE;
int AtrHandle = INVALID_HANDLE;
int FileHandle = INVALID_HANDLE;
datetime LastBarTime = 0;
int SignalCount = 0;

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

string DayName(datetime ts)
{
   MqlDateTime t;
   TimeToStruct(ts, t);
   if(t.day_of_week == 0) return "Sunday";
   if(t.day_of_week == 1) return "Monday";
   if(t.day_of_week == 2) return "Tuesday";
   if(t.day_of_week == 3) return "Wednesday";
   if(t.day_of_week == 4) return "Thursday";
   if(t.day_of_week == 5) return "Friday";
   return "Saturday";
}

bool BufferValue(int handle, int shift, double &value)
{
   double buffer[1];
   if(CopyBuffer(handle, 0, shift, 1, buffer) != 1)
      return false;
   value = buffer[0];
   return value != EMPTY_VALUE;
}

double SignalSpreadPoints(const MqlRates &bar)
{
   if(bar.spread > 0)
      return (double)bar.spread;
   long currentSpread = 0;
   if(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD, currentSpread))
      return (double)currentSpread;
   return 0.0;
}

double TheoreticalEntry(double close, string direction, double spreadPoints)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double halfSpread = spreadPoints * point / 2.0;
   double slippage = InpSlippagePoints * point;
   if(direction == "long")
      return close + halfSpread + slippage;
   return close - halfSpread - slippage;
}

void WriteSignal(datetime ts, string direction, double entry, double stopLoss, double takeProfit, double spreadPoints, double atr, double emaFast, double emaMid, double emaSlow)
{
   if(FileHandle == INVALID_HANDLE)
      return;
   SignalCount++;
   MqlDateTime t;
   TimeToStruct(ts, t);
   string signalId = StringFormat("US100_H1_nas_trend_pullback_exclude_monday_%05d", SignalCount);
   string timestamp = TimeToString(ts, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
   double riskR = MathAbs(entry - stopLoss);
   FileWrite(
      FileHandle,
      signalId,
      timestamp,
      direction,
      DoubleToString(entry, _Digits),
      DoubleToString(stopLoss, _Digits),
      DoubleToString(takeProfit, _Digits),
      DoubleToString(riskR, _Digits),
      DoubleToString(spreadPoints, 2),
      DoubleToString(atr, _Digits),
      DoubleToString(emaFast, _Digits),
      DoubleToString(emaMid, _Digits),
      DoubleToString(emaSlow, _Digits),
      "nas_trend_pullback_exclude_monday",
      DayName(ts),
      t.hour,
      "true"
   );
   FileFlush(FileHandle);
   Print("Verifier signal exported: ", timestamp, " ", direction, " entry=", entry, " sl=", stopLoss, " tp=", takeProfit);
}

int OnInit()
{
   if(EnableTrading)
      Print("EnableTrading=true was requested, but this verifier EA is for parity only. No orders are sent by this EA.");

   EmaFastHandle = iMA(_Symbol, InpTimeframe, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE);
   EmaMidHandle = iMA(_Symbol, InpTimeframe, InpEMAMid, 0, MODE_EMA, PRICE_CLOSE);
   EmaSlowHandle = iMA(_Symbol, InpTimeframe, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE);
   AtrHandle = iATR(_Symbol, InpTimeframe, InpATRPeriod);
   if(EmaFastHandle == INVALID_HANDLE || EmaMidHandle == INVALID_HANDLE || EmaSlowHandle == INVALID_HANDLE || AtrHandle == INVALID_HANDLE)
      return INIT_FAILED;

   FileHandle = FileOpen(InpOutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(FileHandle == INVALID_HANDLE)
   {
      Print("Cannot open signal output file: ", InpOutputFile, " error=", GetLastError());
      return INIT_FAILED;
   }
   FileWrite(
      FileHandle,
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
      "allowed_by_filters"
   );
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(FileHandle != INVALID_HANDLE)
      FileClose(FileHandle);
   if(EmaFastHandle != INVALID_HANDLE)
      IndicatorRelease(EmaFastHandle);
   if(EmaMidHandle != INVALID_HANDLE)
      IndicatorRelease(EmaMidHandle);
   if(EmaSlowHandle != INVALID_HANDLE)
      IndicatorRelease(EmaSlowHandle);
   if(AtrHandle != INVALID_HANDLE)
      IndicatorRelease(AtrHandle);
}

void OnTick()
{
   if(!IsNewBar())
      return;

   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   int needed = MathMax(InpSwingLookback + 1, InpEMASlopeLookback + 2);
   if(CopyRates(_Symbol, InpTimeframe, 1, needed, bars) < needed)
      return;

   MqlRates row = bars[0];
   MqlRates prev = bars[1];
   datetime ts = row.time;

   if(IsMonday(ts))
      return;
   if(!InSession(ts))
      return;

   double spreadPoints = SignalSpreadPoints(row);
   if(spreadPoints > InpMaxSpreadPoints)
      return;

   double emaFast = 0.0;
   double emaMid = 0.0;
   double emaMidPast = 0.0;
   double emaSlow = 0.0;
   double atr = 0.0;
   if(!BufferValue(EmaFastHandle, 1, emaFast))
      return;
   if(!BufferValue(EmaMidHandle, 1, emaMid))
      return;
   if(!BufferValue(EmaMidHandle, 1 + InpEMASlopeLookback, emaMidPast))
      return;
   if(!BufferValue(EmaSlowHandle, 1, emaSlow))
      return;
   if(!BufferValue(AtrHandle, 1, atr))
      return;
   if(atr <= 0.0 || atr < InpATRMinFilter)
      return;

   double emaMidSlope = emaMid - emaMidPast;
   bool longOk = row.close > emaSlow && emaMidSlope > 0.0;
   bool shortOk = row.close < emaSlow && emaMidSlope < 0.0;
   bool pullbackLong = prev.low <= emaFast;
   bool pullbackShort = prev.high >= emaFast;
   bool resumeLong = row.close > row.open && row.close > prev.high;
   bool resumeShort = row.close < row.open && row.close < prev.low;

   if(longOk && pullbackLong && resumeLong)
   {
      double stopLoss = bars[0].low;
      for(int i = 1; i <= InpSwingLookback && i < ArraySize(bars); i++)
         stopLoss = MathMin(stopLoss, bars[i].low);
      if(stopLoss >= row.close || row.close - stopLoss < 0.25 * atr)
         stopLoss = row.close - InpSLATRMultiplier * atr;
      double risk = row.close - stopLoss;
      double takeProfit = row.close + risk * InpTPRMultiple;
      double entry = TheoreticalEntry(row.close, "long", spreadPoints);
      WriteSignal(ts, "long", entry, stopLoss, takeProfit, spreadPoints, atr, emaFast, emaMid, emaSlow);
      return;
   }

   if(shortOk && pullbackShort && resumeShort)
   {
      double stopLoss = bars[0].high;
      for(int i = 1; i <= InpSwingLookback && i < ArraySize(bars); i++)
         stopLoss = MathMax(stopLoss, bars[i].high);
      if(stopLoss <= row.close || stopLoss - row.close < 0.25 * atr)
         stopLoss = row.close + InpSLATRMultiplier * atr;
      double risk = stopLoss - row.close;
      double takeProfit = row.close - risk * InpTPRMultiple;
      double entry = TheoreticalEntry(row.close, "short", spreadPoints);
      WriteSignal(ts, "short", entry, stopLoss, takeProfit, spreadPoints, atr, emaFast, emaMid, emaSlow);
   }
}
