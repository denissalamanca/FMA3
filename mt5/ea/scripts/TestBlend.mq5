//+------------------------------------------------------------------+
//| TestBlend.mq5 - FMA3 static_blend in-terminal replay harness     |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions - pure FileOpen /       |
//| FileReadString / CBookBlend::Step / FileWriteString.             |
//|                                                                  |
//| Replays the FROZEN blend inputs through Book/BookBlend.mqh and   |
//| emits the netted book_frac stream with EXACTLY the exporter's    |
//| emission semantics (scripts/export_book_frac_v3.py::build_rows): |
//|   * per hour, rows for every |net_frac| > 1e-12 leg, broker-     |
//|     mapped (USA500->US500, DAX->DE40), broker-name ordinal       |
//|     ascending within the hour;                                   |
//|   * one "epoch,__GRID__,0" sentinel per all-flat hour;           |
//|   * values %.17g (binary64 round-trip; the 12dp golden is        |
//|     compared numerically by validate_blend.py).                  |
//|                                                                  |
//| Files (FILE_COMMON - the terminal Common\Files directory):       |
//|   in : FMA3_blend_inputs.csv   (research/bpure/blend/            |
//|                                 export_blend_inputs.py)          |
//|   out: FMA3_blend_actual.csv                                     |
//|                                                                  |
//| PARSE-LOSS GATE: the input header carries sumcheck = the plain   |
//| left-to-right IEEE double sum of every value in file order. This |
//| script accumulates the same sum from its StringToDouble results  |
//| and requires a BITWISE match - any parse loss (e.g. exponent     |
//| notation mishandling) fails loudly instead of poisoning the      |
//| diff. The python statement mirror of this file is               |
//| research/bpure/blend/mirror_blend.py; the diff judge is          |
//| research/bpure/blend/validate_blend.py (target <= 1e-12 vs the   |
//| 12dp golden, 0 vs the %.17g golden).                             |
//|                                                                  |
//| Run: attach to any chart (or Navigator > Scripts); progress      |
//| every 5000 hours; final line starts with "DONE".                 |
//+------------------------------------------------------------------+
#property version     "1.00"
#property description "FMA3 blend replay: FMA3_blend_inputs.csv -> FMA3_blend_actual.csv (Common Files)"
#property script_show_inputs false

#include <Book/BookBlend.mqh>

#define TBL_EPS       1e-12       // exporter emission threshold (build_rows EPS)
#define TBL_PROGRESS  5000

const string TBL_IN_FILE  = "FMA3_blend_inputs.csv";
const string TBL_OUT_FILE = "FMA3_blend_actual.csv";
const string TBL_CONFIG_HASH = "51a7541cc2aaa593";

// repo(model) -> broker symbol map, applied at EMIT (exporter SYMMAP)
const string TBL_MAP_MODEL[2]  = {"USA500", "DAX"};
const string TBL_MAP_BROKER[2] = {"US500", "DE40"};

//--- broker name of a model symbol (identity when unmapped)
string TBL_BrokerSym(const string model_sym)
  {
   for(int i = 0; i < 2; i++)
      if(TBL_MAP_MODEL[i] == model_sym)
         return TBL_MAP_BROKER[i];
   return model_sym;
  }

//--- strip one trailing CR (files written with \n; belt and braces)
string TBL_Chomp(string line)
  {
   int n = StringLen(line);
   if(n > 0 && StringGetCharacter(line, n - 1) == 13)
      return StringSubstr(line, 0, n - 1);
   return line;
  }

//--- %.17g cell (IEEE-754 binary64 round-trip)
string TBL_Cell(const double v)
  {
   return StringFormat("%.17g", v);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   Print("TestBlend: FMA3 static_blend replay starting ...");

   //--- input file ---------------------------------------------------
   int fh = FileOpen(TBL_IN_FILE, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      Print("TestBlend: cannot open ", TBL_IN_FILE, " in Common Files, error ",
            GetLastError());
      return;
     }

   //--- header 1: key=value tokens ------------------------------------
   string hdr = TBL_Chomp(FileReadString(fh));
   string toks[];
   int nt = StringSplit(hdr, ',', toks);
   double w = 0.0;
   string hashv = "", fmtv = "", sumcheck_str = "";
   int n_core = 0, n_sat = 0;
   long n_rows = 0;
   for(int i = 0; i < nt; i++)
     {
      string kv[];
      if(StringSplit(toks[i], '=', kv) != 2)
         continue;
      if(kv[0] == "w")                w = StringToDouble(kv[1]);
      else if(kv[0] == "config_hash") hashv = kv[1];
      else if(kv[0] == "fmt")         fmtv = kv[1];
      else if(kv[0] == "n_core")      n_core = (int)StringToInteger(kv[1]);
      else if(kv[0] == "n_sat")       n_sat = (int)StringToInteger(kv[1]);
      else if(kv[0] == "rows")        n_rows = StringToInteger(kv[1]);
      else if(kv[0] == "sumcheck")    sumcheck_str = kv[1];
     }
   if(hashv != TBL_CONFIG_HASH)
     {
      Print("TestBlend: config_hash mismatch - file '", hashv, "' vs compiled '",
            TBL_CONFIG_HASH, "'. Refusing a drifted input.");
      FileClose(fh);
      return;
     }
   if(fmtv != "blendin1" || n_core <= 0 || n_sat <= 0 || n_rows <= 0 ||
      StringLen(sumcheck_str) == 0)
     {
      Print("TestBlend: bad header: ", hdr);
      FileClose(fh);
      return;
     }
   double sumcheck_ref = StringToDouble(sumcheck_str);

   //--- header 2: epoch,a,b,<core syms>,<sat syms> ---------------------
   string cols[];
   int nc = StringSplit(TBL_Chomp(FileReadString(fh)), ',', cols);
   if(nc != 3 + n_core + n_sat || cols[0] != "epoch" || cols[1] != "a" ||
      cols[2] != "b")
     {
      Print("TestBlend: bad column header (", nc, " cols, expected ",
            3 + n_core + n_sat, ")");
      FileClose(fh);
      return;
     }
   string core_syms[], sat_syms[];
   ArrayResize(core_syms, n_core);
   ArrayResize(sat_syms, n_sat);
   for(int i = 0; i < n_core; i++)
      core_syms[i] = cols[3 + i];
   for(int i = 0; i < n_sat; i++)
      sat_syms[i] = cols[3 + n_core + i];

   //--- the blender -----------------------------------------------------
   CBookBlend blend;
   if(!blend.Init(w, core_syms, sat_syms))
     {
      Print("TestBlend: CBookBlend.Init failed");
      FileClose(fh);
      return;
     }
   int nnet = blend.NetCount();
   PrintFormat("TestBlend: w=%s  n_core=%d  n_sat=%d  net_cols=%d  rows=%I64d",
               TBL_Cell(w), n_core, n_sat, nnet, n_rows);

   //--- emission order: net columns sorted by BROKER name (ordinal),
   //--- matching build_rows' sort by (epoch, broker_symbol) -------------
   int perm[];
   string bsym[];
   ArrayResize(perm, nnet);
   ArrayResize(bsym, nnet);
   for(int k = 0; k < nnet; k++)
     {
      perm[k] = k;
      bsym[k] = TBL_BrokerSym(blend.NetSymbol(k));
     }
   for(int i = 1; i < nnet; i++)              // insertion sort on broker name
     {
      int pk = perm[i];
      int j = i - 1;
      while(j >= 0 && CBookBlend::CmpOrdinal(bsym[perm[j]], bsym[pk]) > 0)
        {
         perm[j + 1] = perm[j];
         j--;
        }
      perm[j + 1] = pk;
     }

   //--- output file ------------------------------------------------------
   int oh = FileOpen(TBL_OUT_FILE, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(oh == INVALID_HANDLE)
     {
      Print("TestBlend: cannot open ", TBL_OUT_FILE, " for writing, error ",
            GetLastError());
      FileClose(fh);
      return;
     }
   FileWriteString(oh, "w_v7=" + TBL_Cell(w) + ",config_hash=" + hashv +
                   ",fmt=3,prec=17,src=TestBlend\n");

   //--- main loop ----------------------------------------------------------
   double f_core[], f_sat[], out[];
   ArrayResize(f_core, n_core);
   ArrayResize(f_sat, n_sat);
   double acc = 0.0;                      // left-to-right parse sumcheck
   long hours = 0, data_rows = 0, sentinels = 0;
   bool failed = false;
   while(!FileIsEnding(fh))
     {
      string line = TBL_Chomp(FileReadString(fh));
      if(StringLen(line) == 0)
         continue;
      string f[];
      int nf = StringSplit(line, ',', f);
      if(nf != 3 + n_core + n_sat)
        {
         Print("TestBlend: bad row (", nf, " fields) at hour ", hours, ": ",
               StringSubstr(line, 0, 60));
         failed = true;
         break;
        }
      long   ep = StringToInteger(f[0]);
      double a  = StringToDouble(f[1]);
      double b  = StringToDouble(f[2]);
      acc += a;
      acc += b;
      for(int i = 0; i < n_core; i++)
        {
         f_core[i] = StringToDouble(f[3 + i]);
         acc += f_core[i];
        }
      for(int i = 0; i < n_sat; i++)
        {
         f_sat[i] = StringToDouble(f[3 + n_core + i]);
         acc += f_sat[i];
        }

      if(!blend.Step(f_core, f_sat, a, b, out))
        {
         Print("TestBlend: Step failed at hour ", hours);
         failed = true;
         break;
        }

      //--- emit: |v| > EPS legs in broker order, else __GRID__ ------------
      bool any_leg = false;
      for(int k = 0; k < nnet; k++)
        {
         double v = out[perm[k]];
         if(MathAbs(v) > TBL_EPS)
           {
            FileWriteString(oh, IntegerToString(ep) + "," + bsym[perm[k]] + "," +
                            TBL_Cell(v) + "\n");
            data_rows++;
            any_leg = true;
           }
        }
      if(!any_leg)
        {
         FileWriteString(oh, IntegerToString(ep) + ",__GRID__,0\n");
         sentinels++;
        }

      hours++;
      if(hours % TBL_PROGRESS == 0)
        {
         Print("TestBlend: hour ", hours, " (", TimeToString((datetime)ep),
               "), rows ", data_rows, " + ", sentinels, " sentinels");
         FileFlush(oh);
        }
     }
   FileClose(fh);
   FileFlush(oh);
   FileClose(oh);

   //--- parse-loss gate: BITWISE sumcheck match ---------------------------
   bool sum_ok = (acc == sumcheck_ref) && (TBL_Cell(acc) == sumcheck_str);
   PrintFormat("TestBlend: sumcheck computed %s vs header %s -> %s",
               TBL_Cell(acc), sumcheck_str, sum_ok ? "BITWISE MATCH" : "*** MISMATCH ***");

   PrintFormat("DONE TestBlend: hours=%I64d (header %I64d) data_rows=%I64d "
               "sentinels=%I64d out=%s (Common Files)%s%s",
               hours, n_rows, data_rows, sentinels, TBL_OUT_FILE,
               (hours == n_rows && !failed) ? "" : "  *** ROW COUNT / PARSE FAILURE ***",
               sum_ok ? "" : "  *** SUMCHECK FAILURE ***");
  }
//+------------------------------------------------------------------+
