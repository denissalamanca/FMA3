//+------------------------------------------------------------------+
//| TestV34Native.mq5 — FMA3 v34 in-terminal replay harness          |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions — pure FileOpen /       |
//| FileReadString / compute.  Adopts the Gemini TestBrain2 PATTERN  |
//| (CSV in Common Files -> step every union-grid hour -> CSV out)   |
//| with the corrected input contract:                               |
//|   * input = timestamp (epoch seconds) + RAW close per 37 symbols |
//|     (core.ALL order), EMPTY field where the symbol printed no    |
//|     bar that hour.  NO injected vols / has_bar / day_valid — the |
//|     steppers own ALL ffill / return / daily-grid / NaN semantics.|
//|   * output doubles printed %.17g (not the TestBrain2 8dp).       |
//|                                                                  |
//| Files (FILE_COMMON — the terminal Common\Files directory):       |
//|   in : FMA3_v34_inputs.csv         (export_master_inputs.py)     |
//|   out: FMA3_v34_native_actual.csv  (timestamp + 31 book columns) |
//|                                                                  |
//| Derivations this harness performs from the raw closes — each     |
//| recipe PROVEN BITWISE in Python by export_master_inputs.py       |
//| against the frozen U["close"]/U["ret"]/daily_closes matrices:    |
//|   * streaming ffill per symbol;                                  |
//|   * xau_ret = clip(ffill_t/ffill_{t-1} - 1, +-0.30), 0.0 while   |
//|     prev is NaN (== core.universe_frames ret, never NaN);        |
//|   * daily rows: a calendar day closes when the FIRST bar of the  |
//|     next grid day arrives; its closes = the ffilled values as of |
//|     the PREVIOUS bar (== resample('1D').last() on grid days);    |
//|     - trend_v2 steps EVERY grid day; held row of closed day d    |
//|       becomes effective at the first bar >= (d+1) 05:00          |
//|       (EXEC_HOUR 5, to_hourly lag 6h; latest effective wins);    |
//|     - crisis steps WEEKDAYS only ((epoch_day+3)%7 < 5); target   |
//|       effective at res.effective = d + 1d + 13h with pandas      |
//|       ffill semantics (NaN target never overwrites; 0.0 before   |
//|       the first finite target) == V34CrisisExpandToHourly;       |
//|     - the trailing (still-open) last grid day is never closed:   |
//|       its daily targets stamp beyond the grid (no output effect, |
//|       identical to the Python drivers' final rows).              |
//|   * seasonal/crypto deferred emit: CV34SeasonalCryptoStepper     |
//|     Step() at bar t returns the finalized row of bar t-1, so the |
//|     other 7 sleeve rows are buffered one bar and the book row of |
//|     bar t-1 is assembled when bar t is stepped; Finalize()       |
//|     flushes the last row (seasonal leg forced 0).                |
//|                                                                  |
//| Ensemble shell: AddSleeve with EXACTLY the golden sleeve parquet |
//| columns (carry_breakout keeps 21 of the stepper's 32 outputs;    |
//| the 11 dropped columns are identically zero — proven in          |
//| research/bpure/parity/book_parity.json).  Book columns = sorted  |
//| union = the 31 golden book.parquet columns.                      |
//|                                                                  |
//| Run: attach to any chart (or Navigator > Scripts); progress is   |
//| printed every 5000 bars; final line starts with "DONE".          |
//+------------------------------------------------------------------+
#property version   "1.00"
#property description "FMA3 v34 native replay: FMA3_v34_inputs.csv -> FMA3_v34_native_actual.csv (Common Files)"

#include <FMA3v34/MagXau.mqh>
#include <FMA3v34/Intraday.mqh>
#include <FMA3v34/MeanRev.mqh>
#include <FMA3v34/SeasonalCrypto.mqh>
#include <FMA3v34/CarryBreakout.mqh>
#include <FMA3v34/Crisis.mqh>
#include <FMA3v34/TrendV2.mqh>
#include <FMA3v34/Ensemble.mqh>

#define TV34_NIN        37
#define TV34_NKEEP      21
#define TV34_PROGRESS   5000

const string TV34_IN_FILE  = "FMA3_v34_inputs.csv";
const string TV34_OUT_FILE = "FMA3_v34_native_actual.csv";

// input CSV symbol order == core.ALL (FX 21, CRYPTO 4, INDICES 6,
// COMMODITIES 6) — verified against the file header at run time
const string TV34_IN_SYMS[TV34_NIN] =
  {
   "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
   "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
   "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY",
   "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
   "DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
   "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"
  };

// carry_breakout golden parquet columns (21 KEPT of the 32 stepper
// outputs) — column ORDER is the golden carry_breakout_pos.parquet order
const string TV34_CB_KEPT[TV34_NKEEP] =
  {
   "AUDJPY", "CADCHF", "CADJPY", "EURCAD", "EURNZD", "EURUSD", "GBPJPY",
   "NZDJPY", "USDCHF", "USDJPY", "DAX", "JP225", "UK100", "US30",
   "USA500", "USTEC", "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XTIUSD"
  };

// remaining golden sleeve columns (crisis/trend/crypto/intraday orders
// come from the include-level constants; these mirror the parquets)
const string TV34_SEA_SYMS[1] = {"XAUUSD"};
const string TV34_MAG_SYMS[1] = {"XAUUSD"};
const string TV34_ID_SYMS[2]  = {"USA500", "USTEC"};

//------------------------------------------------------------------//
// helpers                                                          //
//------------------------------------------------------------------//
int TV34SymIndex(const string name)
  {
   for(int i = 0; i < TV34_NIN; i++)
      if(TV34_IN_SYMS[i] == name)
         return i;
   return -1;
  }

// map sleeve symbol names -> input-column indices; false on any miss
bool TV34MapSyms(const string &names[], int &ix[])
  {
   int n = ArraySize(names);
   ArrayResize(ix, n);
   for(int i = 0; i < n; i++)
     {
      ix[i] = TV34SymIndex(names[i]);
      if(ix[i] < 0)
        {
         Print("TestV34Native: unknown symbol '", names[i], "'");
         return false;
        }
     }
   return true;
  }

// pop the front entry of a (eff[], flat w[] stride-per-entry) queue
void TV34QPop(long &eff[], double &w[], const int stride)
  {
   int n = ArraySize(eff);
   for(int i = 1; i < n; i++)
      eff[i - 1] = eff[i];
   ArrayResize(eff, n - 1);
   int m = ArraySize(w);
   for(int i = stride; i < m; i++)
      w[i - stride] = w[i];
   ArrayResize(w, m - stride);
  }

// push one entry onto a (eff[], flat w[]) queue
void TV34QPush(long &eff[], double &w[], const long e,
               const double &row[], const int stride)
  {
   int n = ArraySize(eff);
   ArrayResize(eff, n + 1);
   eff[n] = e;
   int m = ArraySize(w);
   ArrayResize(w, m + stride);
   for(int j = 0; j < stride; j++)
      w[m + j] = row[j];
  }

// %.17g cell (IEEE-754 binary64 round-trip)
string TV34Cell(const double v)
  {
   return StringFormat("%.17g", v);
  }

//------------------------------------------------------------------//
// stage the 8 sleeve rows for ONE bar and write the book row       //
//------------------------------------------------------------------//
bool TV34StageAndWrite(CV34EnsembleStepper &shell, const int out_handle,
                       const long ts_sec,
                       const double &mr[],   // 16, V34MR_SYMBOLS order
                       const double &cbk[],  // 21, TV34_CB_KEPT order
                       const double &id[],   // 2,  USA500 USTEC
                       const double &cr[],   // 4,  V34CrisisSym order
                       const double &tv[],   // 5,  V34TV2_SYMS order
                       const double &mg[],   // 1,  XAUUSD
                       const double &emit4[])// 4,  XAU BTC ETH SOL
  {
   double se[1], cs3[3];
   se[0]  = emit4[0];
   cs3[0] = emit4[1];
   cs3[1] = emit4[2];
   cs3[2] = emit4[3];
   bool ok = true;
   ok = ok && shell.SetSleeveRow("meanrev",        mr);
   ok = ok && shell.SetSleeveRow("carry_breakout", cbk);
   ok = ok && shell.SetSleeveRow("seasonal",       se);
   ok = ok && shell.SetSleeveRow("intraday",       id);
   ok = ok && shell.SetSleeveRow("crisis",         cr);
   ok = ok && shell.SetSleeveRow("trend_v2",       tv);
   ok = ok && shell.SetSleeveRow("crypto_smart",   cs3);
   ok = ok && shell.SetSleeveRow("mag",            mg);
   if(!ok)
      return false;
   double out[];
   if(!shell.Step((datetime)ts_sec, out))
      return false;
   string line = IntegerToString(ts_sec);
   int n = ArraySize(out);
   for(int i = 0; i < n; i++)
      line += "," + TV34Cell(out[i]);
   FileWriteString(out_handle, line + "\n");
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   Print("TestV34Native: FMA3 v34 native replay starting ...");
   double nan = V34Nan();

   //--- input file -------------------------------------------------
   int fh = FileOpen(TV34_IN_FILE, FILE_READ | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      Print("TestV34Native: cannot open ", TV34_IN_FILE,
            " in Common Files, error ", GetLastError());
      return;
     }

   //--- header check (must be exactly timestamp + core.ALL) --------
   string header = FileReadString(fh);
   if(StringLen(header) > 0 &&
      StringGetCharacter(header, StringLen(header) - 1) == 13)
      header = StringSubstr(header, 0, StringLen(header) - 1);
   string hcols[];
   int nh = StringSplit(header, ',', hcols);
   if(nh != TV34_NIN + 1 || hcols[0] != "timestamp")
     {
      Print("TestV34Native: bad header (", nh, " cols)");
      FileClose(fh);
      return;
     }
   for(int i = 0; i < TV34_NIN; i++)
      if(hcols[i + 1] != TV34_IN_SYMS[i])
        {
         Print("TestV34Native: header col ", i + 1, " '", hcols[i + 1],
               "' != '", TV34_IN_SYMS[i], "'");
         FileClose(fh);
         return;
        }

   //--- input-column maps for every sleeve --------------------------
   int mr_ix[], cb_ix[], id_ix[], tv_ix[];
   bool ok = true;
   ok = ok && TV34MapSyms(V34MR_SYMBOLS, mr_ix);      // 16
   ok = ok && TV34MapSyms(V34CB_SYMBOLS, cb_ix);      // 32
   ok = ok && TV34MapSyms(TV34_ID_SYMS,  id_ix);      // 2
   ok = ok && TV34MapSyms(V34TV2_SYMS,   tv_ix);      // 5
   int cr_in_ix[V34CRISIS_NIN];
   for(int i = 0; ok && i < V34CRISIS_NIN; i++)
     {
      cr_in_ix[i] = TV34SymIndex(V34CrisisInputSym(i));
      if(cr_in_ix[i] < 0)
         ok = false;
     }
   // carry kept columns -> index into the 32-wide stepper output
   int cb_keep_ix[TV34_NKEEP];
   for(int k = 0; ok && k < TV34_NKEEP; k++)
     {
      cb_keep_ix[k] = -1;
      for(int j = 0; j < V34CB_N_SYM; j++)
         if(V34CB_SYMBOLS[j] == TV34_CB_KEPT[k])
           {
            cb_keep_ix[k] = j;
            break;
           }
      if(cb_keep_ix[k] < 0)
         ok = false;
     }
   int ix_xau = TV34SymIndex("XAUUSD");
   int ix_btc = TV34SymIndex("BTCUSD");
   int ix_eth = TV34SymIndex("ETHUSD");
   int ix_sol = TV34SymIndex("SOLUSD");
   if(!ok || ix_xau < 0 || ix_btc < 0 || ix_eth < 0 || ix_sol < 0)
     {
      Print("TestV34Native: symbol mapping failed");
      FileClose(fh);
      return;
     }

   //--- steppers -----------------------------------------------------
   CV34MagXauStepper         mag;
   CV34IntradayStepper       intr;
   CV34MeanRevStepper        mr;
   CV34SeasonalCryptoStepper sc;
   CV34CarryBreakoutStepper  cb;
   CV34CrisisStepper         crisis;
   CV34TrendV2Stepper        tv;
   intr.InitDefault();

   //--- ensemble shell: EXACT golden sleeve parquet columns ----------
   string cr_syms[V34CRISIS_NOUT];
   for(int j = 0; j < V34CRISIS_NOUT; j++)
      cr_syms[j] = V34CrisisSym(j);
   CV34EnsembleStepper shell;
   ok = true;
   ok = ok && shell.AddSleeve("meanrev",        V34MR_SYMBOLS);
   ok = ok && shell.AddSleeve("carry_breakout", TV34_CB_KEPT);
   ok = ok && shell.AddSleeve("seasonal",       TV34_SEA_SYMS);
   ok = ok && shell.AddSleeve("intraday",       TV34_ID_SYMS);
   ok = ok && shell.AddSleeve("crisis",         cr_syms);
   ok = ok && shell.AddSleeve("trend_v2",       V34TV2_SYMS);
   ok = ok && shell.AddSleeve("crypto_smart",   V34_SC_CR_SYMBOLS);
   ok = ok && shell.AddSleeve("mag",            TV34_MAG_SYMS);
   ok = ok && shell.Finalize();
   if(!ok || shell.SymbolCount() != 31)
     {
      Print("TestV34Native: shell build failed (symbols=",
            shell.SymbolCount(), ", expected 31)");
      FileClose(fh);
      return;
     }

   //--- output file ---------------------------------------------------
   int oh = FileOpen(TV34_OUT_FILE, FILE_WRITE | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   if(oh == INVALID_HANDLE)
     {
      Print("TestV34Native: cannot open ", TV34_OUT_FILE,
            " for writing, error ", GetLastError());
      FileClose(fh);
      return;
     }
   string oheader = "timestamp";
   for(int i = 0; i < shell.SymbolCount(); i++)
      oheader += "," + shell.SymbolAt(i);
   FileWriteString(oh, oheader + "\n");

   //--- per-bar state ---------------------------------------------------
   double ffill[TV34_NIN];
   for(int i = 0; i < TV34_NIN; i++)
      ffill[i] = nan;
   bool   has_day = false;
   long   cur_day = 0;
   // pending daily targets (effective-stamp queues, seconds)
   long   tvq_eff[];
   double tvq_w[];                          // stride 5
   long   crq_eff[];
   double crq_w[];                          // stride 4
   double trend_cur[V34TV2_NSYM];
   double crisis_cur[V34CRISIS_NOUT];       // NaN until first finite target
   for(int j = 0; j < V34TV2_NSYM; j++)
      trend_cur[j] = 0.0;
   for(int j = 0; j < V34CRISIS_NOUT; j++)
      crisis_cur[j] = nan;
   // one-bar buffers for the deferred seasonal/crypto emission
   bool   have_prev = false;
   long   prev_ts = 0;
   double prev_mr[V34MR_NSYM], prev_cbk[TV34_NKEEP], prev_id[2];
   double prev_cr[V34CRISIS_NOUT], prev_tv[V34TV2_NSYM], prev_mg[1];
   // scratch
   double raw[TV34_NIN];
   double mrcl[V34MR_NSYM],  cbcl[V34CB_N_SYM], idcl[2];
   double crcl[V34CRISIS_NIN], tvcl[V34TV2_NSYM];
   double cur_mr[], cur_id[], cb32[V34CB_N_SYM];
   double cur_cbk[TV34_NKEEP], cur_cr[V34CRISIS_NOUT];
   double cur_tv[V34TV2_NSYM], cur_mg[1], held[];
   double emit4[];
   long   bars = 0, rows = 0;

   //--- main loop ----------------------------------------------------
   while(!FileIsEnding(fh))
     {
      string line = FileReadString(fh);
      if(StringLen(line) > 0 &&
         StringGetCharacter(line, StringLen(line) - 1) == 13)
         line = StringSubstr(line, 0, StringLen(line) - 1);
      if(StringLen(line) == 0)
         continue;
      string parts[];
      int np = StringSplit(line, ',', parts);
      if(np < 1)
         continue;
      long ts = StringToInteger(parts[0]);
      long ts_ns = ts * (long)1000000000;
      for(int j = 0; j < TV34_NIN; j++)
        {
         // trailing empty fields may be dropped by StringSplit — pad
         string s = (j + 1 < np) ? parts[j + 1] : "";
         raw[j] = (StringLen(s) == 0) ? nan : StringToDouble(s);
        }

      //--- daily rollover: close the previous grid day -----------------
      long day = ts / 86400;
      if(!has_day)
        {
         has_day = true;
         cur_day = day;
        }
      else if(day != cur_day)
        {
         // day closes = ffilled values as of the PREVIOUS bar (ffill[]
         // not yet updated with this bar) == resample('1D').last()
         for(int j = 0; j < V34TV2_NSYM; j++)
            tvcl[j] = ffill[tv_ix[j]];
         tv.Step(tvcl, held);
         TV34QPush(tvq_eff, tvq_w,
                   (cur_day + 1) * 86400 + V34TV2_EXEC_HOUR * 3600,
                   held, V34TV2_NSYM);
         if(((cur_day + 3) % 7) < 5)              // Mon..Fri only
           {
            for(int j = 0; j < V34CRISIS_NIN; j++)
               crcl[j] = ffill[cr_in_ix[j]];
            SV34CrisisResult res;
            if(!crisis.Step((datetime)(cur_day * 86400), crcl, res))
              {
               Print("TestV34Native: crisis step failed at day ", cur_day);
               break;
              }
            TV34QPush(crq_eff, crq_w, (long)res.effective, res.w,
                      V34CRISIS_NOUT);
           }
         cur_day = day;
        }

      //--- xau ret (prev ffill) then streaming ffill --------------------
      double prev_x = ffill[ix_xau];
      for(int j = 0; j < TV34_NIN; j++)
         if(raw[j] == raw[j])
            ffill[j] = raw[j];
      double xret = 0.0;
      if(prev_x == prev_x)
        {
         double r = ffill[ix_xau] / prev_x - 1.0;
         if(r < -0.30)
            r = -0.30;
         else if(r > 0.30)
            r = 0.30;
         xret = r;
        }

      //--- activate pending daily targets -------------------------------
      while(ArraySize(tvq_eff) > 0 && tvq_eff[0] <= ts)
        {
         for(int j = 0; j < V34TV2_NSYM; j++)
            trend_cur[j] = tvq_w[j];
         TV34QPop(tvq_eff, tvq_w, V34TV2_NSYM);
        }
      while(ArraySize(crq_eff) > 0 && crq_eff[0] <= ts)
        {
         for(int j = 0; j < V34CRISIS_NOUT; j++)
           {
            double v = crq_w[j];
            if(v == v)                    // NaN never overwrites (ffill)
               crisis_cur[j] = v;
           }
         TV34QPop(crq_eff, crq_w, V34CRISIS_NOUT);
        }

      //--- current-bar rows for the 7 non-deferred sleeves --------------
      cur_mg[0] = mag.StepNs(ts_ns, raw[ix_xau]);
      idcl[0] = raw[id_ix[0]];
      idcl[1] = raw[id_ix[1]];
      intr.StepNs(ts_ns, idcl, cur_id);
      for(int j = 0; j < V34MR_NSYM; j++)
         mrcl[j] = raw[mr_ix[j]];
      mr.Step((datetime)ts, mrcl, cur_mr);
      for(int j = 0; j < V34CB_N_SYM; j++)
         cbcl[j] = raw[cb_ix[j]];
      cb.Step(ts / 86400, cbcl, cb32);
      for(int k = 0; k < TV34_NKEEP; k++)
         cur_cbk[k] = cb32[cb_keep_ix[k]];
      for(int j = 0; j < V34TV2_NSYM; j++)
         cur_tv[j] = trend_cur[j];
      for(int j = 0; j < V34CRISIS_NOUT; j++)     // 0.0 before first target
         cur_cr[j] = (crisis_cur[j] == crisis_cur[j]) ? crisis_cur[j] : 0.0;

      //--- seasonal/crypto: deferred one-bar emission --------------------
      long emit_ts_ns = 0;
      bool emitted = sc.StepNs(ts_ns, xret, ffill[ix_btc], ffill[ix_eth],
                               ffill[ix_sol], emit_ts_ns, emit4);
      if(emitted)
        {
         if(!have_prev || emit_ts_ns != prev_ts * (long)1000000000)
           {
            Print("TestV34Native: emission misaligned at bar ", bars);
            break;
           }
         if(!TV34StageAndWrite(shell, oh, prev_ts, prev_mr, prev_cbk,
                               prev_id, prev_cr, prev_tv, prev_mg, emit4))
           {
            Print("TestV34Native: stage/step failed at bar ", bars);
            break;
           }
         rows++;
        }
      else if(bars > 0)
        {
         Print("TestV34Native: expected emission at bar ", bars);
         break;
        }

      //--- buffer this bar's rows for the next emission -------------------
      for(int j = 0; j < V34MR_NSYM; j++)
         prev_mr[j] = cur_mr[j];
      for(int k = 0; k < TV34_NKEEP; k++)
         prev_cbk[k] = cur_cbk[k];
      prev_id[0] = cur_id[0];
      prev_id[1] = cur_id[1];
      for(int j = 0; j < V34CRISIS_NOUT; j++)
         prev_cr[j] = cur_cr[j];
      for(int j = 0; j < V34TV2_NSYM; j++)
         prev_tv[j] = cur_tv[j];
      prev_mg[0] = cur_mg[0];
      prev_ts = ts;
      have_prev = true;

      bars++;
      if(bars % TV34_PROGRESS == 0)
        {
         Print("TestV34Native: bar ", bars, " (", TimeToString((datetime)ts),
               "), rows written ", rows);
         FileFlush(oh);
        }
     }
   FileClose(fh);

   //--- flush the last deferred row -------------------------------------
   long emit_ts_ns = 0;
   if(sc.Finalize(emit_ts_ns, emit4))
     {
      if(!have_prev || emit_ts_ns != prev_ts * (long)1000000000)
         Print("TestV34Native: FINAL emission misaligned");
      else if(TV34StageAndWrite(shell, oh, prev_ts, prev_mr, prev_cbk,
                                prev_id, prev_cr, prev_tv, prev_mg, emit4))
         rows++;
      else
         Print("TestV34Native: FINAL stage/step failed");
     }
   FileFlush(oh);
   FileClose(oh);

   PrintFormat("DONE TestV34Native: bars=%I64d rows=%I64d out=%s (Common Files)%s",
               bars, rows, TV34_OUT_FILE,
               (bars == rows && bars > 0) ? "" : "  *** ROW COUNT MISMATCH ***");
  }
//+------------------------------------------------------------------+
