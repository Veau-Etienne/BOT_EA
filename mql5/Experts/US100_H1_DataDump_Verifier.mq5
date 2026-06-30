#property strict
#property version "2.20"
#property description "US100 H1 data and indicator dump verifier for Python/MT5 parity debugging."

// DATA DUMP VERIFIER ONLY — DO NOT USE FOR LIVE TRADING
// This EA exports closed H1 bars and MT5 indicator values for parity analysis.
// It does not call OrderSend, CTrade.Buy, CTrade.Sell or any equivalent trade action.

input bool EnableTrading = false;
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_H1;
input int InpEMAFast = 20;
input int InpEMAMid = 50;
input int InpEMASlow = 200;
input int InpATRPeriod = 14;
input int InpEMASlopeLookback = 4;
input string InpOutputFile = "us100_h1_mt5_bars_indicators.csv";

int EmaFastHandle = INVALID_HANDLE;
int EmaMidHandle = INVALID_HANDLE;
int EmaSlowHandle = INVALID_HANDLE;
int AtrHandle = INVALID_HANDLE;
int FileHandle = INVALID_HANDLE;
datetime LastBarTime = 0;
datetime LastDumpedTime = 0;
int DumpedRows = 0;

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

double BarSpreadPoints(const MqlRates &bar)
{
   if(bar.spread > 0)
      return (double)bar.spread;
   long currentSpread = 0;
   if(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD, currentSpread))
      return (double)currentSpread;
   return 0.0;
}

void WriteHeader()
{
   FileWrite(
      FileHandle,
      "timestamp",
      "open",
      "high",
      "low",
      "close",
      "tick_volume",
      "spread",
      "ema_fast",
      "ema_slow",
      "ema200",
      "atr",
      "day_of_week",
      "hour",
      "ema_mid_slope",
      "ema_mid_past"
   );
}

void DumpClosedBar()
{
   MqlRates bars[];
   ArraySetAsSeries(bars, true);
   int needed = InpEMASlopeLookback + 2;
   if(needed < 2)
      needed = 2;
   if(CopyRates(_Symbol, InpTimeframe, 1, needed, bars) < needed)
      return;

   MqlRates row = bars[0];
   if(row.time == LastDumpedTime)
      return;

   double emaFast = 0.0;
   double emaMid = 0.0;
   double emaMidPast = 0.0;
   double emaSlow = 0.0;
   double atr = 0.0;
   bool hasEmaFast = BufferValue(EmaFastHandle, 1, emaFast);
   bool hasEmaMid = BufferValue(EmaMidHandle, 1, emaMid);
   bool hasEmaMidPast = BufferValue(EmaMidHandle, 1 + InpEMASlopeLookback, emaMidPast);
   bool hasEmaSlow = BufferValue(EmaSlowHandle, 1, emaSlow);
   bool hasAtr = BufferValue(AtrHandle, 1, atr);

   MqlDateTime t;
   TimeToStruct(row.time, t);
   double emaMidSlope = EMPTY_VALUE;
   if(hasEmaMid && hasEmaMidPast)
      emaMidSlope = emaMid - emaMidPast;

   string emaFastText = "";
   string emaMidText = "";
   string emaSlowText = "";
   string atrText = "";
   string emaMidSlopeText = "";
   string emaMidPastText = "";
   if(hasEmaFast)
      emaFastText = DoubleToString(emaFast, _Digits);
   if(hasEmaMid)
      emaMidText = DoubleToString(emaMid, _Digits);
   if(hasEmaSlow)
      emaSlowText = DoubleToString(emaSlow, _Digits);
   if(hasAtr)
      atrText = DoubleToString(atr, _Digits);
   if(emaMidSlope != EMPTY_VALUE)
      emaMidSlopeText = DoubleToString(emaMidSlope, _Digits);
   if(hasEmaMidPast)
      emaMidPastText = DoubleToString(emaMidPast, _Digits);

   FileWrite(
      FileHandle,
      TimeToString(row.time, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      DoubleToString(row.open, _Digits),
      DoubleToString(row.high, _Digits),
      DoubleToString(row.low, _Digits),
      DoubleToString(row.close, _Digits),
      (long)row.tick_volume,
      DoubleToString(BarSpreadPoints(row), 2),
      emaFastText,
      emaMidText,
      emaSlowText,
      atrText,
      t.day_of_week,
      t.hour,
      emaMidSlopeText,
      emaMidPastText
   );
   FileFlush(FileHandle);
   LastDumpedTime = row.time;
   DumpedRows++;
}

int OnInit()
{
   if(EnableTrading)
      Print("EnableTrading=true was requested, but this data verifier never sends orders.");
   if(!EnableTrading)
      Print("Data dump/export only: EnableTrading=false, no trading allowed.");

   EmaFastHandle = iMA(_Symbol, InpTimeframe, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE);
   EmaMidHandle = iMA(_Symbol, InpTimeframe, InpEMAMid, 0, MODE_EMA, PRICE_CLOSE);
   EmaSlowHandle = iMA(_Symbol, InpTimeframe, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE);
   AtrHandle = iATR(_Symbol, InpTimeframe, InpATRPeriod);
   if(EmaFastHandle == INVALID_HANDLE || EmaMidHandle == INVALID_HANDLE || EmaSlowHandle == INVALID_HANDLE || AtrHandle == INVALID_HANDLE)
      return INIT_FAILED;

   FileHandle = FileOpen(InpOutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(FileHandle == INVALID_HANDLE)
   {
      Print("Cannot open data dump output file: ", InpOutputFile, " error=", GetLastError());
      return INIT_FAILED;
   }
   WriteHeader();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Print("Data dump verifier exported rows: ", DumpedRows);
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
   DumpClosedBar();
}
