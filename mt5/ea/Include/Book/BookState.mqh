//+------------------------------------------------------------------+
//| Book/BookState.mqh — CBookState: the safety-critical whole-book  |
//| state serializer (FABLEBOOKNATIVE_DESIGN v2 item 5(v)).          |
//|                                                                   |
//| WHY THIS EXISTS: the blend is a RATIO CHAIN (§3.6 of the design). |
//| Re-basing a/b independently to 1.0 (or truncating their state to  |
//| 4 decimals, like the legacy SaveState) changes the a/b ratio and  |
//| silently mis-weights EVERY trade while passing every <1e-12       |
//| self-check. This serializer therefore:                            |
//|   (a) serializes the COMPLETE live ledger — every component       |
//|       GetState (8 sleeves, CSatEquityNative, CCoreBookSim incl.   |
//|       seam carry + accumulated f_core rows + segment cursor/seed, |
//|       orchestrator glue: ffill[37], daily queues, prev rows,      |
//|       f_sat held ring, a/b hour samplers, emit bookkeeping) —     |
//|       every double at %.17g (binary64 round-trip), NEVER          |
//|       truncated;                                                  |
//|   (b) writes ATOMICALLY: stream to <file>.tmp in Common Files,    |
//|       then FileDelete(<file>) + FileMove(tmp -> file).            |
//|       FileMove-with-FILE_REWRITE maps to MoveFileEx and is        |
//|       rename-atomic on NTFS; under Wine it maps to rename(2).     |
//|       Because that atomicity is NOT certifiable from this repo    |
//|       (no terminal launch), the file carries a torn-write MARKER  |
//|       PROTOCOL that makes any partial/interleaved write           |
//|       detectable on load regardless of rename semantics:          |
//|       the payload ends with                                       |
//|           , "fnv64": "<16 lowercase hex>", "eof": true}           |
//|       where fnv64 = FNV-1a 64-bit over every payload byte before  |
//|       the trailer. A torn write loses the trailer; an interleaved |
//|       or bit-flipped write fails the checksum. Either -> REFUSE.  |
//|   (c) validates on load: schema/version field, component-count    |
//|       checks (every fixed-width array length is enforced),        |
//|       NaN/Infinity-aware number parsing (SatParseDouble);         |
//|   (d) CONTINUITY GUARD: after restore it recomputes               |
//|           j_restored = w*a_h + (1-w)*b_h                          |
//|       from the RESTORED samplers at the saved emission hour and   |
//|       compares against the j stored at save time. Any relative    |
//|       jump > BOOKSTATE_J_TOL (1e-9) — or any bit difference in    |
//|       a_first/b_first, or a j_hour mismatch — sets a              |
//|       REFUSE_TO_TRADE latch the EA MUST honor via                 |
//|       Ready()/RefuseToTrade()/RefuseReason().                     |
//|                                                                   |
//| ARCHITECTURE: this header is orchestrator-independent. CBookState |
//| talks to its peer through TEMPLATE methods — the peer (normally   |
//| CBookOrchestrator) must expose:                                   |
//|     bool BsWriteState(CBookStateWriter &w);   // aggregator (get) |
//|     bool BsSetState(CBookStateTok &tk);       // aggregator (set) |
//|     bool BsContinuity(SBookStateContinuity &c);                   |
//|     string LastError() const;                                     |
//| BookOrchestrator.mqh includes this header and implements the      |
//| three hooks ADDITIVELY (zero compute-path change — the S1 gate    |
//| stays intact).                                                    |
//|                                                                   |
//| The python statement-mirror of this schema lives in               |
//| research/bpure/book/book_state_mirror.py (same envelope, same     |
//| trailer, same continuity law); the split-run gate is              |
//| research/bpure/book/run_state_split_gate.py.                      |
//+------------------------------------------------------------------+
#ifndef BOOK_BOOKSTATE_MQH
#define BOOK_BOOKSTATE_MQH

#include <Sat/SatMath.mqh>

#define BOOKSTATE_SCHEMA   "fma3.bookstate"
#define BOOKSTATE_VERSION  1
#define BOOKSTATE_J_TOL    1e-9          // refuse-to-trade splice threshold
#define BOOKSTATE_FLUSH    262144        // writer part-flush threshold (chars)

//------------------------------------------------------------------//
// %.17g with python-json non-strict tokens (NaN/Infinity/-Infinity) //
// — the same convention every component GetState already uses.      //
//------------------------------------------------------------------//
string BookStateNum(const double x)
  {
   if(x != x)
      return "NaN";
   double inf = SatInf();
   if(x == inf)
      return "Infinity";
   if(x == -inf)
      return "-Infinity";
   return StringFormat("%.17g", x);
  }

//------------------------------------------------------------------//
// FNV-1a 64-bit over a uchar block (torn-write / corruption marker) //
//------------------------------------------------------------------//
// 14695981039346656037 / 1099511628211 (hex: decimal literals above
// LONG_MAX are not portable in MQL5; hex is well-defined to 64 bits)
#define BOOKSTATE_FNV_OFFSET  ((ulong)0xCBF29CE484222325)
#define BOOKSTATE_FNV_PRIME   ((ulong)0x00000100000001B3)

ulong BookStateFnv1a(const uchar &b[], const int n, const ulong h0)
  {
   ulong h = h0;
   for(int i = 0; i < n; i++)
     {
      h ^= (ulong)b[i];
      h *= BOOKSTATE_FNV_PRIME;
     }
   return h;
  }

//==================================================================//
// CBookStateWriter — chunked JSON emitter.  Avoids O(n^2) string   //
// growth by flushing to a parts[] array; the whole payload is only //
// materialized as bytes at file-write time.  ASCII-only content.   //
//==================================================================//
class CBookStateWriter
  {
private:
   string            m_parts[];
   int               m_np;
   string            m_buf;

   void              FlushIf()
     {
      if(StringLen(m_buf) < BOOKSTATE_FLUSH)
         return;
      int cap = ArraySize(m_parts);
      if(m_np >= cap)
         ArrayResize(m_parts, cap + 64);
      m_parts[m_np] = m_buf;
      m_np++;
      m_buf = "";
     }

public:
                     CBookStateWriter() { Clear(); }

   void              Clear()
     {
      ArrayResize(m_parts, 0);
      m_np  = 0;
      m_buf = "";
     }

   void              Raw(const string s) { m_buf += s; FlushIf(); }
   void              K(const string name)   { Raw("\"" + name + "\": "); }
   void              CK(const string name)  { Raw(", \"" + name + "\": "); }
   void              D(const double v)      { Raw(BookStateNum(v)); }
   void              I(const long v)        { Raw(StringFormat("%I64d", v)); }
   void              B(const bool v)        { Raw(v ? "true" : "false"); }
   void              Q(const string s)      { Raw("\"" + s + "\""); }

   void              KD(const string name, const double v) { CK(name); D(v); }
   void              KI(const string name, const long v)   { CK(name); I(v); }
   void              KB(const string name, const bool v)   { CK(name); B(v); }

   void              ArrD(const double &v[], const int n)
     {
      Raw("[");
      for(int i = 0; i < n; i++)
        {
         if(i > 0)
            Raw(", ");
         D(v[i]);
        }
      Raw("]");
     }

   void              ArrL(const long &v[], const int n)
     {
      Raw("[");
      for(int i = 0; i < n; i++)
        {
         if(i > 0)
            Raw(", ");
         I(v[i]);
        }
      Raw("]");
     }

   void              KArrD(const string name, const double &v[], const int n)
     {
      CK(name);
      ArrD(v, n);
     }

   void              KArrL(const string name, const long &v[], const int n)
     {
      CK(name);
      ArrL(v, n);
     }

   //--- harvest -----------------------------------------------------
   int               Parts()
     {
      FlushFinal();
      return m_np;
     }
   string            Part(const int i) const
     {
      return (i >= 0 && i < m_np) ? m_parts[i] : "";
     }

private:
   void              FlushFinal()
     {
      if(StringLen(m_buf) == 0)
         return;
      int cap = ArraySize(m_parts);
      if(m_np >= cap)
         ArrayResize(m_parts, cap + 4);
      m_parts[m_np] = m_buf;
      m_np++;
      m_buf = "";
     }
  };

//==================================================================//
// CBookStateTok — strict fixed-schema cursor tokenizer.  Numbers   //
// parse through SatParseDouble (NaN/Infinity aware); every array   //
// reader ENFORCES the expected element count (component-count      //
// checks).  First failure latches m_err with a position message.   //
//==================================================================//
class CBookStateTok
  {
private:
   string            m_s;
   int               m_p;
   int               m_n;
   bool              m_err;
   string            m_msg;

   void              Fail(const string what)
     {
      if(m_err)
         return;
      m_err = true;
      m_msg = what + StringFormat(" (at char %d)", m_p);
     }

   void              SkipWs()
     {
      while(m_p < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_p);
         if(c != ' ' && c != '\t' && c != '\n' && c != '\r')
            break;
         m_p++;
        }
     }

public:
                     CBookStateTok() { Attach(""); }

   void              Attach(const string s)
     {
      m_s   = s;
      m_p   = 0;
      m_n   = StringLen(s);
      m_err = false;
      m_msg = "";
     }

   bool              Ok()  const { return !m_err; }
   string            Err() const { return m_msg;  }
   int               Pos() const { return m_p;    }

   bool              Eat(const ushort ch)
     {
      if(m_err)
         return false;
      SkipWs();
      if(m_p >= m_n || StringGetCharacter(m_s, m_p) != ch)
        {
         Fail(StringFormat("expected '%c'", ch));
         return false;
        }
      m_p++;
      return true;
     }

   bool              TryEat(const ushort ch)
     {
      if(m_err)
         return false;
      SkipWs();
      if(m_p < m_n && StringGetCharacter(m_s, m_p) == ch)
        {
         m_p++;
         return true;
        }
      return false;
     }

   // expects  "name":   exactly (fixed schema — order is normative)
   bool              Key(const string name)
     {
      if(m_err)
         return false;
      SkipWs();
      int len = StringLen(name);
      if(m_p + len + 2 > m_n
         || StringGetCharacter(m_s, m_p) != '"'
         || StringSubstr(m_s, m_p + 1, len) != name
         || StringGetCharacter(m_s, m_p + 1 + len) != '"')
        {
         Fail("expected key \"" + name + "\"");
         return false;
        }
      m_p += len + 2;
      return Eat(':');
     }

   bool              CommaKey(const string name)
     {
      return Eat(',') && Key(name);
     }

   // quoted string, no escape handling (all our strings are plain)
   bool              StrVal(string &out)
     {
      if(!Eat('"'))
         return false;
      int q = StringFind(m_s, "\"", m_p);
      if(q < 0)
        {
         Fail("unterminated string");
         return false;
        }
      out = StringSubstr(m_s, m_p, q - m_p);
      m_p = q + 1;
      return true;
     }

   // raw number/word token up to , ] } or whitespace
   bool              TokVal(string &out)
     {
      if(m_err)
         return false;
      SkipWs();
      int st = m_p;
      while(m_p < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_p);
         if(c == ',' || c == ']' || c == '}' || c == ' '
            || c == '\n' || c == '\r' || c == '\t')
            break;
         m_p++;
        }
      if(m_p == st)
        {
         Fail("expected value token");
         return false;
        }
      out = StringSubstr(m_s, st, m_p - st);
      return true;
     }

   bool              NumVal(double &v)
     {
      string t;
      if(!TokVal(t))
         return false;
      v = SatParseDouble(t);
      return true;
     }

   bool              IntVal(long &v)
     {
      string t;
      if(!TokVal(t))
         return false;
      v = StringToInteger(t);
      return true;
     }

   bool              BoolVal(bool &v)
     {
      string t;
      if(!TokVal(t))
         return false;
      if(t == "true")  { v = true;  return true; }
      if(t == "false") { v = false; return true; }
      Fail("expected true/false");
      return false;
     }

   // [ d, d, ... ] with ENFORCED element count (component-count check)
   bool              ArrD(double &out[], const int expect)
     {
      if(!Eat('['))
         return false;
      if(ArraySize(out) < expect)
         ArrayResize(out, expect);
      if(TryEat(']'))
        {
         if(expect != 0)
            Fail(StringFormat("array count 0 != %d", expect));
         return !m_err;
        }
      int i = 0;
      while(true)
        {
         double v = 0.0;
         if(!NumVal(v))
            return false;
         if(i >= expect)
           {
            Fail(StringFormat("array count > %d", expect));
            return false;
           }
         out[i] = v;
         i++;
         if(TryEat(','))
            continue;
         if(!Eat(']'))
            return false;
         break;
        }
      if(i != expect)
        {
         Fail(StringFormat("array count %d != %d", i, expect));
         return false;
        }
      return true;
     }

   bool              ArrL(long &out[], const int expect)
     {
      if(!Eat('['))
         return false;
      if(ArraySize(out) < expect)
         ArrayResize(out, expect);
      if(TryEat(']'))
        {
         if(expect != 0)
            Fail(StringFormat("array count 0 != %d", expect));
         return !m_err;
        }
      int i = 0;
      while(true)
        {
         long v = 0;
         if(!IntVal(v))
            return false;
         if(i >= expect)
           {
            Fail(StringFormat("array count > %d", expect));
            return false;
           }
         out[i] = v;
         i++;
         if(TryEat(','))
            continue;
         if(!Eat(']'))
            return false;
         break;
        }
      if(i != expect)
        {
         Fail(StringFormat("array count %d != %d", i, expect));
         return false;
        }
      return true;
     }

   // variable-length variants (queues): return the parsed count
   bool              ArrDVar(double &out[], int &count)
     {
      if(!Eat('['))
         return false;
      count = 0;
      if(TryEat(']'))
         return true;
      while(true)
        {
         double v = 0.0;
         if(!NumVal(v))
            return false;
         int cap = ArraySize(out);
         if(count >= cap)
            ArrayResize(out, cap + 256);
         out[count] = v;
         count++;
         if(TryEat(','))
            continue;
         if(!Eat(']'))
            return false;
         break;
        }
      return true;
     }

   bool              ArrLVar(long &out[], int &count)
     {
      if(!Eat('['))
         return false;
      count = 0;
      if(TryEat(']'))
         return true;
      while(true)
        {
         long v = 0;
         if(!IntVal(v))
            return false;
         int cap = ArraySize(out);
         if(count >= cap)
            ArrayResize(out, cap + 256);
         out[count] = v;
         count++;
         if(TryEat(','))
            continue;
         if(!Eat(']'))
            return false;
         break;
        }
      return true;
     }

   // capture one balanced {...} object as a raw substring (handed to a
   // component's own SetState parser: SC / CB / TV2 / b-engine)
   bool              ObjRaw(string &out)
     {
      if(m_err)
         return false;
      SkipWs();
      if(m_p >= m_n || StringGetCharacter(m_s, m_p) != '{')
        {
         Fail("expected '{' (raw object)");
         return false;
        }
      int st = m_p;
      int depth = 0;
      bool instr = false;
      while(m_p < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_p);
         if(instr)
           {
            if(c == '\\')
               m_p++;                      // skip escaped char
            else if(c == '"')
               instr = false;
           }
         else
           {
            if(c == '"')
               instr = true;
            else if(c == '{')
               depth++;
            else if(c == '}')
              {
               depth--;
               if(depth == 0)
                 {
                  m_p++;
                  out = StringSubstr(m_s, st, m_p - st);
                  return true;
                 }
              }
           }
         m_p++;
        }
      Fail("unterminated raw object");
      return false;
     }
  };

//------------------------------------------------------------------//
// SBookStateContinuity — the ratio-chain anchor snapshot written at //
// save time and RECOMPUTED from the restored state at load time.    //
//------------------------------------------------------------------//
struct SBookStateContinuity
  {
   bool              have;       // any hour emitted yet
   long              j_hour;     // last emitted blend hour (-1 if none)
   double            a_h;        // AH(j_hour) — asof multiple, model fillna 1.0
   double            b_h;        // BH(j_hour)
   double            w;          // blend Core capital share
   double            j;          // w*a_h + (1-w)*b_h
   double            a_first;    // the iloc[0] anchors (bit-exact or refuse)
   double            b_first;
  };

//==================================================================//
// CBookState — atomic save / validating load / refuse-to-trade     //
// latch.  All file paths are Common Files (FILE_COMMON) relative.  //
//==================================================================//
class CBookState
  {
private:
   string            m_err;             // last operation error (save or load)
   bool              m_loaded;          // last Load fully validated
   bool              m_refuse;          // REFUSE_TO_TRADE latch
   string            m_refuse_reason;
   // last-load continuity metrics (diagnostics)
   double            m_j_saved, m_j_restored, m_rel_jump;
   long              m_j_hour;

   void              Refuse(const string why)
     {
      m_refuse        = true;
      m_loaded        = false;
      m_refuse_reason = why;
      m_err           = why;
     }

public:
                     CBookState() { ResetLatch(); }

   // NOTE: ResetLatch is for TESTS ONLY — a live EA must never clear
   // the latch without a successful validated Load().
   void              ResetLatch()
     {
      m_err           = "";
      m_loaded        = false;
      m_refuse        = false;
      m_refuse_reason = "";
      m_j_saved    = 0.0;
      m_j_restored = 0.0;
      m_rel_jump   = 0.0;
      m_j_hour     = -1;
     }

   bool              Ready()         const { return m_loaded && !m_refuse; }
   bool              RefuseToTrade() const { return m_refuse;              }
   string            RefuseReason()  const { return m_refuse_reason;       }
   string            LastError()     const { return m_err;                 }
   double            JSaved()        const { return m_j_saved;             }
   double            JRestored()     const { return m_j_restored;          }
   double            RelJump()       const { return m_rel_jump;            }
   long              JHour()         const { return m_j_hour;              }

   //---------------------------------------------------------------//
   // Save — stream the peer's complete ledger + continuity block to //
   // <fname>.tmp (Common Files), append the fnv64/eof trailer, then //
   // FileDelete(fname) + FileMove(tmp -> fname).                    //
   //---------------------------------------------------------------//
   template<typename TPeer>
   bool              Save(TPeer &peer, const string fname)
     {
      m_err = "";
      CBookStateWriter w;
      w.Raw("{\"schema\": \"" + BOOKSTATE_SCHEMA + "\", \"version\": "
            + IntegerToString(BOOKSTATE_VERSION) + ", ");
      if(!peer.BsWriteState(w))
        {
         m_err = "BsWriteState: " + peer.LastError();
         return false;
        }
      SBookStateContinuity c;
      if(!peer.BsContinuity(c))
        {
         m_err = "BsContinuity: " + peer.LastError();
         return false;
        }
      w.Raw(", \"continuity\": {\"have\": ");
      w.B(c.have);
      w.KI("j_hour", c.j_hour);
      w.KD("a_h", c.a_h);
      w.KD("b_h", c.b_h);
      w.KD("w", c.w);
      w.KD("j", c.j);
      w.KD("a_first", c.a_first);
      w.KD("b_first", c.b_first);
      w.Raw("}");

      // ---- stream to tmp, fnv over every payload byte -------------
      string tmp = fname + ".tmp";
      int fh = FileOpen(tmp, FILE_WRITE | FILE_BIN | FILE_COMMON);
      if(fh == INVALID_HANDLE)
        {
         m_err = StringFormat("FileOpen('%s') failed (%d)", tmp, GetLastError());
         return false;
        }
      ulong h = BOOKSTATE_FNV_OFFSET;
      int np = w.Parts();
      for(int i = 0; i < np; i++)
        {
         string part = w.Part(i);
         uchar bytes[];
         int nb = StringToCharArray(part, bytes, 0, WHOLE_ARRAY, CP_UTF8) - 1;
         if(nb < 0)
            nb = 0;
         h = BookStateFnv1a(bytes, nb, h);
         if(nb > 0 && FileWriteArray(fh, bytes, 0, nb) != (uint)nb)
           {
            FileClose(fh);
            m_err = "FileWriteArray short write";
            return false;
           }
        }
      string trailer = StringFormat(", \"fnv64\": \"%016I64x\", \"eof\": true}", h);
      uchar tb[];
      int ntb = StringToCharArray(trailer, tb, 0, WHOLE_ARRAY, CP_UTF8) - 1;
      if(FileWriteArray(fh, tb, 0, ntb) != (uint)ntb)
        {
         FileClose(fh);
         m_err = "trailer short write";
         return false;
        }
      FileClose(fh);

      // ---- publish: delete old, rename tmp into place -------------
      if(FileIsExist(fname, FILE_COMMON) && !FileDelete(fname, FILE_COMMON))
        {
         m_err = StringFormat("FileDelete('%s') failed (%d)", fname, GetLastError());
         return false;
        }
      if(!FileMove(tmp, FILE_COMMON, fname, FILE_COMMON | FILE_REWRITE))
        {
         m_err = StringFormat("FileMove('%s'->'%s') failed (%d)",
                              tmp, fname, GetLastError());
         return false;
        }
      return true;
     }

   //---------------------------------------------------------------//
   // Load — read + trailer/checksum validate + schema validate +    //
   // restore into peer + CONTINUITY GUARD.  Any failure sets the    //
   // REFUSE_TO_TRADE latch (and the peer may be partially restored: //
   // the caller must re-Init it before any other use).              //
   //---------------------------------------------------------------//
   template<typename TPeer>
   bool              Load(TPeer &peer, const string fname)
     {
      ResetLatch();

      // ---- read raw bytes -----------------------------------------
      int fh = FileOpen(fname, FILE_READ | FILE_BIN | FILE_COMMON);
      if(fh == INVALID_HANDLE)
        {
         Refuse(StringFormat("state file '%s' missing/unreadable (%d)",
                             fname, GetLastError()));
         return false;
        }
      int n = (int)FileSize(fh);
      uchar bytes[];
      if(n <= 0 || FileReadArray(fh, bytes, 0, n) != (uint)n)
        {
         FileClose(fh);
         Refuse("state file empty / short read");
         return false;
        }
      FileClose(fh);
      string s = CharArrayToString(bytes, 0, n, CP_UTF8);

      // ---- torn-write marker protocol ------------------------------
      string eof_mark = "\"eof\": true}";
      int elen = StringLen(eof_mark);
      if(StringLen(s) < elen
         || StringSubstr(s, StringLen(s) - elen, elen) != eof_mark)
        {
         Refuse("TORN WRITE: eof marker missing (partial/failed save)");
         return false;
        }
      string fnv_mark = ", \"fnv64\": \"";
      // last occurrence (payload cannot legally contain the marker, but
      // scan-to-last is the robust direction)
      int mp = -1, sp = 0;
      while(true)
        {
         int q = StringFind(s, fnv_mark, sp);
         if(q < 0)
            break;
         mp = q;
         sp = q + 1;
        }
      if(mp < 0)
        {
         Refuse("TORN WRITE: fnv64 trailer missing");
         return false;
        }
      int hex_at = mp + StringLen(fnv_mark);
      string hex = StringSubstr(s, hex_at, 16);
      ulong want = 0;
      for(int i = 0; i < 16; i++)
        {
         ushort c = StringGetCharacter(hex, i);
         int d;
         if(c >= '0' && c <= '9')
            d = (int)(c - '0');
         else if(c >= 'a' && c <= 'f')
            d = (int)(c - 'a') + 10;
         else
           {
            Refuse("TORN WRITE: fnv64 trailer malformed");
            return false;
           }
         want = (want << 4) | (ulong)d;
        }
      // payload bytes = [0, mp) in CHARACTER positions == byte positions
      // (ASCII payload; enforced by the writers)
      ulong got = BookStateFnv1a(bytes, mp, BOOKSTATE_FNV_OFFSET);
      if(got != want)
        {
         Refuse(StringFormat("CHECKSUM MISMATCH: fnv64 %016I64x != stored %016I64x "
                             "(torn/corrupted state file)", got, want));
         return false;
        }

      // ---- schema envelope -----------------------------------------
      CBookStateTok tk;
      tk.Attach(s);
      string schema;
      long   version = 0;
      if(!tk.Eat('{') || !tk.Key("schema") || !tk.StrVal(schema)
         || !tk.CommaKey("version") || !tk.IntVal(version))
        {
         Refuse("schema envelope malformed: " + tk.Err());
         return false;
        }
      if(schema != BOOKSTATE_SCHEMA)
        {
         Refuse("schema '" + schema + "' != '" + BOOKSTATE_SCHEMA + "'");
         return false;
        }
      if(version != BOOKSTATE_VERSION)
        {
         Refuse(StringFormat("state version %I64d != %d", version,
                             BOOKSTATE_VERSION));
         return false;
        }

      // ---- restore the ledger ---------------------------------------
      if(!tk.Eat(','))
        {
         Refuse("envelope: " + tk.Err());
         return false;
        }
      if(!peer.BsSetState(tk))
        {
         Refuse("RESTORE FAILED: " + peer.LastError()
                + (tk.Ok() ? "" : (" | tok: " + tk.Err())));
         return false;
        }

      // ---- saved continuity block ------------------------------------
      SBookStateContinuity cs;
      bool okc = tk.CommaKey("continuity") && tk.Eat('{');
      okc = okc && tk.Key("have") && tk.BoolVal(cs.have);
      okc = okc && tk.CommaKey("j_hour") && tk.IntVal(cs.j_hour);
      okc = okc && tk.CommaKey("a_h") && tk.NumVal(cs.a_h);
      okc = okc && tk.CommaKey("b_h") && tk.NumVal(cs.b_h);
      okc = okc && tk.CommaKey("w") && tk.NumVal(cs.w);
      okc = okc && tk.CommaKey("j") && tk.NumVal(cs.j);
      okc = okc && tk.CommaKey("a_first") && tk.NumVal(cs.a_first);
      okc = okc && tk.CommaKey("b_first") && tk.NumVal(cs.b_first);
      okc = okc && tk.Eat('}');
      if(!okc)
        {
         Refuse("continuity block malformed: " + tk.Err());
         return false;
        }

      // ---- CONTINUITY GUARD: recompute from the RESTORED state -------
      SBookStateContinuity cr;
      if(!peer.BsContinuity(cr))
        {
         Refuse("BsContinuity(restored): " + peer.LastError());
         return false;
        }
      m_j_hour  = cs.j_hour;
      m_j_saved = cs.j;
      // a_first/b_first: BIT-EXACT or refuse (the ratio-chain anchors;
      // NaN-safe compare — 0-vs-0 passes, NaN never does)
      if(!(cr.a_first == cs.a_first))
        {
         Refuse(StringFormat("A-ANCHOR MISMATCH: restored a_first %.17g != "
                             "saved %.17g — state re-based/corrupted",
                             cr.a_first, cs.a_first));
         return false;
        }
      if(!(cr.b_first == cs.b_first))
        {
         Refuse(StringFormat("B-ANCHOR MISMATCH: restored b_first %.17g != "
                             "saved %.17g — state re-based/corrupted",
                             cr.b_first, cs.b_first));
         return false;
        }
      if(cr.have != cs.have || cr.j_hour != cs.j_hour)
        {
         Refuse(StringFormat("J-HOUR MISMATCH: restored %I64d != saved %I64d",
                             cr.j_hour, cs.j_hour));
         return false;
        }
      if(!(cr.w == cs.w))
        {
         Refuse(StringFormat("W MISMATCH: restored %.17g != saved %.17g",
                             cr.w, cs.w));
         return false;
        }
      m_j_restored = cr.j;
      double den = MathAbs(cs.j);
      if(den < 1e-300)
         den = 1e-300;
      m_rel_jump = MathAbs(cr.j - cs.j) / den;
      if(!(m_rel_jump <= BOOKSTATE_J_TOL))       // NaN-safe: NaN refuses
        {
         Refuse(StringFormat("J-SPLICE DISCONTINUITY: j_restored %.17g vs "
                             "j_saved %.17g (rel %.3g > %g) — REFUSE TO TRADE",
                             cr.j, cs.j, m_rel_jump, BOOKSTATE_J_TOL));
         return false;
        }

      m_loaded = true;
      return true;
     }
  };

#endif // BOOK_BOOKSTATE_MQH
