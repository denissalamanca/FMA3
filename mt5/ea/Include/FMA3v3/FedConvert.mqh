//+------------------------------------------------------------------+
//| FMA3v3/FedConvert.mqh - EUR-per-quote conversion (unconditional). |
//|                                                                    |
//| The v2 F3_EurPerQuoteV34 PROMOTED to ALL 33 symbols (MODEL_SPEC    |
//| par.6): eurq = 1 if quote==EUR else 1/mid(EUR-cross) with the FULL |
//| currency map {USD,JPY,GBP,CHF,NZD,CAD,NOK,SEK}. Terminal           |
//| tick-value primitive as a fallback; else 0.0 -> DesiredLots' guard |
//| skips the leg LOUDLY (never a silent mis-size). ALWAYS on - there  |
//| is no InpV34EurQuoteFix gate in v3 (it is unconditional by design).|
//|                                                                    |
//| Requires (defined in the .mq5): InpEURUSD, InpEURJPY, InpEURGBP,   |
//| InpEURCHF, InpEURNZD, InpEURCAD, InpEURNOK, InpEURSEK.             |
//+------------------------------------------------------------------+

//--- best available mid of a (conversion) symbol
double FED_MidOf(string sym)
  {
   double b=SymbolInfoDouble(sym,SYMBOL_BID);
   double a=SymbolInfoDouble(sym,SYMBOL_ASK);
   return (b>0.0 && a>0.0)?0.5*(a+b):0.0;
  }

//--- EUR-cross symbol for a quote currency (conversion only; not traded).
string FED_EurCrossFor(string q)
  {
   if(q=="USD") return InpEURUSD;
   if(q=="JPY") return InpEURJPY;
   if(q=="GBP") return InpEURGBP;
   if(q=="CHF") return InpEURCHF;
   if(q=="NZD") return InpEURNZD;
   if(q=="CAD") return InpEURCAD;
   if(q=="NOK") return InpEURNOK;
   if(q=="SEK") return InpEURSEK;
   return "";
  }

//--- EUR per one unit of the symbol's PROFIT currency. Full map, always on.
//--- PRIMARY = 1/MidOf(EUR-cross) to match record_engine_ext._eurq_chunk.
//--- FALLBACK = terminal tick-value primitive (unit_eur = px*tick_value/tick_size
//--- identity; deposit ccy EUR). 0.0 => caller skips the leg loudly.
double FED_Eurq(string sym)
  {
   string q=SymbolInfoString(sym,SYMBOL_CURRENCY_PROFIT);
   if(q=="EUR") return 1.0;                              // DE40 etc: quote==EUR, no cross
   string cross=FED_EurCrossFor(q);                      // PRIMARY: model-faithful EUR-cross MID
   if(cross!=""){ double m=FED_MidOf(cross); if(m>0.0) return 1.0/m; }
   double tvp=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE_PROFIT);   // FALLBACK: tick-value primitive
   double tvl=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE_LOSS);
   double tv =(tvp>0.0 && tvl>0.0)?0.5*(tvp+tvl):tvp;    // avg PROFIT/LOSS ~ mid; else PROFIT-side
   double ts =SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   double cs =SymbolInfoDouble(sym,SYMBOL_TRADE_CONTRACT_SIZE);
   if(tv>0.0 && ts>0.0 && cs>0.0) return tv/(ts*cs);     // eurq=(tv/ts)/contract => unit_eur=px*tv/ts
   return 0.0;                                           // skip-loud in DesiredLots
  }
//+------------------------------------------------------------------+
