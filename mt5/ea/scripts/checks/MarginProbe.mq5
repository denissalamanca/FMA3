//+------------------------------------------------------------------+
//| MarginProbe.mq5 — what margin does THIS account actually charge?  |
//|                                                                    |
//| WHY: the record engine has NO account-leverage axis; its margin is |
//| a static per-symbol table (core.S.INSTRUMENTS[s]["leverage"], the  |
//| ESMA retail ladder 30/20/10/2). A live account charges whatever    |
//| ITS OWN broker says, and FTMO's own FAQ tells you to read it off   |
//| the platform. SYMBOL_MARGIN_INITIAL alone is NOT enough — on IC it |
//| is a bijective restatement of contract size and encodes no divisor.|
//| The load-bearing fields are ACCOUNT_LEVERAGE, SymbolInfoMarginRate |
//| and above all OrderCalcMargin(), which is the broker's own answer. |
//|                                                                    |
//| SELF-CONTAINED ON PURPOSE: no #include beyond the MQL5 stdlib, so  |
//| it compiles in a VIRGIN terminal (the FTMO one has none of our     |
//| Include\ tree — that is exactly why SymbolMetaProbe fails there).  |
//|                                                                    |
//| ZERO trading: no CTrade, no OrderSend, no position/history query.  |
//| OrderCalcMargin is a pure calculation — it places nothing.         |
//|                                                                    |
//| OUTPUT: Common\Files\FMA3_margin_probe_<login>.csv (login-suffixed |
//| so IC and FTMO can NEVER overwrite each other — the shared-folder  |
//| trap that already bit this project once).                          |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

// The model's 37-symbol universe in CANONICAL (model) names. Broker names may
// differ per broker (FTMO uses e.g. US30.cash / GER40.cash), so a miss here is
// itself a finding: it means the symbol map needs populating for that account.
string CANON[] = {
  "AUDCAD","AUDJPY","AUDNZD","AUDUSD","CADCHF","CADJPY","EURCAD","EURCHF","EURGBP",
  "EURJPY","EURNOK","EURNZD","EURSEK","EURUSD","GBPJPY","GBPUSD","NZDCAD","NZDJPY",
  "NZDUSD","USDCAD","USDCHF","USDCNH","USDJPY","USDSEK",
  "DAX","DE40","GER40","JP225","UK100","US30","US500","USA500","USTEC","NAS100",
  "XAUUSD","XAGUSD","XPTUSD","XBRUSD","XNGUSD","XTIUSD",
  "BTCUSD","ETHUSD","SOLUSD","XRPUSD"
};

input bool InpProbeMarketWatch = true;   // also probe every symbol in Market Watch

string CalcModeName(const int m)   // int: MQL5 switch() narrows a long anyway
  {
   switch(m)
     {
      case SYMBOL_CALC_MODE_FOREX:            return "FOREX";
      case SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE:return "FOREX_NO_LEVERAGE";
      case SYMBOL_CALC_MODE_CFD:              return "CFD";
      case SYMBOL_CALC_MODE_CFDINDEX:         return "CFDINDEX";
      case SYMBOL_CALC_MODE_CFDLEVERAGE:      return "CFDLEVERAGE";
      case SYMBOL_CALC_MODE_EXCH_STOCKS:      return "EXCH_STOCKS";
      case SYMBOL_CALC_MODE_EXCH_FUTURES:     return "EXCH_FUTURES";
      default:                                return StringFormat("MODE_%d", m);
     }
  }

// One row. `implied_leverage` is the ONLY number that answers the question:
// notional_in_account_ccy / margin_for_1_lot. OrderCalcMargin gives the
// denominator straight from the broker, so no assumption is needed.
string Row(const string sym, const long acct_lev, bool &ok)
  {
   ok = false;
   if(!SymbolSelect(sym, true))
      return StringFormat("%s,,,,,,,,,,,0,NOT_ON_THIS_BROKER\n", sym);

   double ask      = SymbolInfoDouble(sym, SYMBOL_ASK);
   double contract = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   double margin_i = SymbolInfoDouble(sym, SYMBOL_MARGIN_INITIAL);
   long   cmode    = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);
   string cprof = "", cmarg = "";
   SymbolInfoString(sym, SYMBOL_CURRENCY_PROFIT, cprof);
   SymbolInfoString(sym, SYMBOL_CURRENCY_MARGIN, cmarg);

   double rate_ini = 0.0, rate_mnt = 0.0;
   bool rate_ok = SymbolInfoMarginRate(sym, ORDER_TYPE_BUY, rate_ini, rate_mnt);

   // the broker's OWN margin for exactly 1.0 lot, in ACCOUNT currency
   double mgn = 0.0;
   bool mok = OrderCalcMargin(ORDER_TYPE_BUY, sym, 1.0, ask, mgn);

   // notional (profit ccy) — NOT converted; the judge converts if needed.
   double notional = contract * ask;
   // implied leverage is only exact when profit ccy == account ccy; otherwise
   // it is off by the FX rate and MUST be treated as indicative. Flagged below.
   double implied = (mok && mgn > 0.0) ? notional / mgn : 0.0;

   ok = true;
   // split: MQL5's StringFormat caps its argument count (the original
   // SymbolMetaProbe hit the same wall and says so at its own format call)
   string a = StringFormat("%s,%.17g,%.17g,%s,%s,%s,",
                           sym, ask, contract, CalcModeName((int)cmode), cprof, cmarg);
   string b = StringFormat("%.17g,%.17g,%d,%.17g,%.17g,1,\n",
                           rate_ok ? rate_ini : -1.0, rate_ok ? rate_mnt : -1.0,
                           mok ? 1 : 0, mgn, implied);
   return a + b;
  }

void OnStart()
  {
   long   acct_lev  = AccountInfoInteger(ACCOUNT_LEVERAGE);
   long   login     = AccountInfoInteger(ACCOUNT_LOGIN);
   long   mmode     = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   long   demo      = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   // AccountInfoString RETURNS the string (no 2-arg form, unlike SymbolInfoString)
   string server  = AccountInfoString(ACCOUNT_SERVER);
   string ccy     = AccountInfoString(ACCOUNT_CURRENCY);
   string company = AccountInfoString(ACCOUNT_COMPANY);

   string mm = (mmode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) ? "RETAIL_HEDGING"
             : (mmode == ACCOUNT_MARGIN_MODE_RETAIL_NETTING) ? "RETAIL_NETTING"
             : "EXCHANGE";
   string dm = (demo == ACCOUNT_TRADE_MODE_DEMO) ? "DEMO"
             : (demo == ACCOUNT_TRADE_MODE_CONTEST) ? "CONTEST" : "REAL";

   // login-suffixed: IC and FTMO share Common\Files
   string out = StringFormat("FMA3_margin_probe_%I64d.csv", login);
   int oh = FileOpen(out, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(oh == INVALID_HANDLE)
     { PrintFormat("MarginProbe FAIL: cannot open %s err=%d", out, GetLastError()); return; }

   PrintFormat("MarginProbe: login=%I64d server=%s company=%s ccy=%s",
               login, server, company, ccy);
   PrintFormat("MarginProbe: ACCOUNT_LEVERAGE=1:%I64d  margin_mode=%s  trade_mode=%s",
               acct_lev, mm, dm);
   if(mmode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      Print("MarginProbe *** WARNING ***: NOT retail-hedging — FableBookNative REFUSES to run on this account.");
   if(demo == ACCOUNT_TRADE_MODE_REAL)
      Print("MarginProbe *** WARNING ***: this is a REAL account.");

   FileWriteString(oh, StringFormat(
      "# login=%I64d server=%s company=%s currency=%s account_leverage=%I64d margin_mode=%s trade_mode=%s\n",
      login, server, company, ccy, acct_lev, mm, dm));
   FileWriteString(oh,
      "symbol,ask,contract_size,calc_mode,ccy_profit,ccy_margin,"
      "margin_rate_initial,margin_rate_maintenance,order_calc_margin_ok,"
      "margin_1lot_acct_ccy,implied_leverage_if_profit_ccy_eq_acct_ccy,found,note\n");

   int n=0, miss=0;
   for(int i = 0; i < ArraySize(CANON); i++)
     {
      bool ok=false;
      FileWriteString(oh, Row(CANON[i], acct_lev, ok));
      if(ok) n++; else miss++;
     }

   if(InpProbeMarketWatch)
     {
      int tot = SymbolsTotal(true);
      for(int i = 0; i < tot; i++)
        {
         string s = SymbolName(i, true);
         bool dup=false;
         for(int j=0;j<ArraySize(CANON);j++) if(CANON[j]==s){dup=true;break;}
         if(dup) continue;
         bool ok=false;
         FileWriteString(oh, Row(s, acct_lev, ok));
        }
     }

   FileClose(oh);
   PrintFormat("MarginProbe: %d canonical symbols found, %d NOT on this broker -> %s", n, miss, out);
   Print("MarginProbe: DONE. Zero orders placed.");
  }
