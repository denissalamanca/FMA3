//+------------------------------------------------------------------+
//| SwapEurq.mqh — LIVE swap / eurq generator (the MQL5 twin of       |
//| research/bpure/feed/swap_eurq_generator.py).                      |
//|                                                                   |
//| The exported b_h / CoreSim bundles carry PRE-BAKED eurq + swap    |
//| arrays. A live EA has none: it must GENERATE them each bar from   |
//| live quotes + the static tables below. This header is that        |
//| generator. NO trading calls, NO indicator calls — pure arithmetic |
//| + a causal per-bar state machine, so it is safe to include in a   |
//| script, an EA or a tester run.                                    |
//|                                                                   |
//| GATE (MEASURED, python twin): BIT-EQUAL (max|diff| = 0.0) vs the  |
//| pre-baked arrays over all 24 b_h quarters and CoreSim segments    |
//| 0/10/20/31 — research/bpure/feed/swap_eurq_gate.json.             |
//|                                                                   |
//| TWO PROFILES (they are NOT the same engine — measured, see the    |
//| python module docstring):                                         |
//|   CSwapEurqBH   (Satellite b_h, FMA2 account_engine_1m)           |
//|     * eurq  = 1/mid_close(EUR cross), the cross close CAST TO     |
//|       float FIRST ((float) — the record feed is float32-quantized;|
//|       feeding raw MT5 doubles gives a DIFFERENT eurq).            |
//|     * swap fires at the first bar >= SERVER MIDNIGHT of each day; |
//|       payload = pct/100/365*mult, ACCUMULATED (+=) when several   |
//|       day-midnights fall in one data gap (weekends: Sat+Sun+Mon   |
//|       all land on the Monday open bar).                           |
//|   CSwapEurqCore (Core a_h, NSF5 engine/backtest.prep_arrays)      |
//|     * eurq  = 1/mid_close(EUR cross), float64, NO float32 cast.   |
//|     * swap fires at the first bar >= 17:00 America/New_York       |
//|       (DST-correct); payload = flag += mult, long/short = pct/100 |
//|       (OVERWRITING; the /365 and the mult live in the kernel).    |
//|                                                                   |
//| Static tables are CODEGEN'd from the python module's tables       |
//| (config/settings.INSTRUMENTS + engine/costs.POLICY_RATES), which  |
//| a drift guard re-verifies against the live NSF5 source on every   |
//| gate run.                                                         |
//+------------------------------------------------------------------+
#ifndef __SWAPEURQ_MQH__
#define __SWAPEURQ_MQH__

#define SE_DAY 86400

#define SE_NCCY   16
#define SE_NSYM   33
#define SE_NCROSS 8
#define SE_MAXSTEP 23

//--- currency ids (policy-rate table rows)
#define SE_USD  0
#define SE_EUR  1
#define SE_GBP  2
#define SE_JPY  3
#define SE_CHF  4
#define SE_AUD  5
#define SE_NZD  6
#define SE_CAD  7
#define SE_NOK  8
#define SE_SEK  9
#define SE_XAU  10
#define SE_XAG  11
#define SE_XPT  12
#define SE_XTI  13
#define SE_XBR  14
#define SE_XNG  15

//--- asset classes
#define SE_FX 0
#define SE_METAL 1
#define SE_INDEX 2
#define SE_CRYPTO 3

//--- symbol table (name, asset class, base ccy, quote ccy, markup)
string SE_SYM[SE_NSYM]      = {"AUDCAD", "AUDJPY", "AUDNZD", "BTCUSD", "CADCHF", "CADJPY", "DAX", "ETHUSD", "EURCAD", "EURCHF", "EURGBP", "EURNOK", "EURNZD", "EURSEK", "EURUSD", "GBPJPY", "JP225", "NZDCAD", "NZDJPY", "SOLUSD", "UK100", "US30", "USA500", "USDCHF", "USDJPY", "USTEC", "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XTIUSD", "AUDUSD", "NZDUSD"};
int    SE_SYM_AC[SE_NSYM]   = {0, 0, 0, 3, 0, 0, 2, 3, 0, 0,
                               0, 0, 0, 0, 0, 0, 2, 0, 0, 3,
                               2, 2, 2, 0, 0, 2, 1, 1, 1, 1,
                               1, 0, 0};
int    SE_SYM_BASE[SE_NSYM] = {5, 5, 5, -1, 7, 7, -1, -1, 1, 1,
                               1, 1, 1, 1, 1, 2, -1, 6, 6, -1,
                               -1, -1, -1, 0, 0, -1, 11, 10, 14, 15,
                               13, 5, 6};
int    SE_SYM_QUOT[SE_NSYM] = {7, 3, 6, 0, 4, 3, 1, 0, 7, 4,
                               2, 8, 6, 9, 0, 3, 3, 7, 3, 0,
                               2, 0, 0, 4, 3, 0, 0, 0, 0, 0,
                               0, 0, 0};
double SE_SYM_MKUP[SE_NSYM] = {1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2,
                               1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2,
                               1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2,
                               1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 2,
                               1.2};

//--- EUR cross per quote ccy (-1 = EUR quote -> eurq == 1.0)
string SE_CROSS[SE_NCROSS]  = {"EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD"};
int    SE_QUOT_CROSS[SE_NCCY] = {7, -1, 2, 3, 1, -1, 5, 0, 4, 6,
                               -1, -1, -1, -1, -1, -1};

//--- policy-rate step functions (effective date, percent/yr)
long   SE_RDATE[SE_NCCY][SE_MAXSTEP];
double SE_RRATE[SE_NCCY][SE_MAXSTEP];
int    SE_RN[SE_NCCY];
double SE_INDEX_MARKUP = 4.3;
double SE_USA500_DIV   = 0;
double SE_CRYPTO_LONG  = -20;
double SE_CRYPTO_SHORT = 0;

void SE_InitTables()
  {
   SE_RN[SE_USD] = 20;
   SE_RDATE[SE_USD][0] = (long)D'2019.11.01';  SE_RRATE[SE_USD][0] = 1.625;
   SE_RDATE[SE_USD][1] = (long)D'2020.03.03';  SE_RRATE[SE_USD][1] = 1.125;
   SE_RDATE[SE_USD][2] = (long)D'2020.03.15';  SE_RRATE[SE_USD][2] = 0.125;
   SE_RDATE[SE_USD][3] = (long)D'2022.03.17';  SE_RRATE[SE_USD][3] = 0.375;
   SE_RDATE[SE_USD][4] = (long)D'2022.05.05';  SE_RRATE[SE_USD][4] = 0.875;
   SE_RDATE[SE_USD][5] = (long)D'2022.06.16';  SE_RRATE[SE_USD][5] = 1.625;
   SE_RDATE[SE_USD][6] = (long)D'2022.07.28';  SE_RRATE[SE_USD][6] = 2.375;
   SE_RDATE[SE_USD][7] = (long)D'2022.09.22';  SE_RRATE[SE_USD][7] = 3.125;
   SE_RDATE[SE_USD][8] = (long)D'2022.11.03';  SE_RRATE[SE_USD][8] = 3.875;
   SE_RDATE[SE_USD][9] = (long)D'2022.12.15';  SE_RRATE[SE_USD][9] = 4.375;
   SE_RDATE[SE_USD][10] = (long)D'2023.02.02';  SE_RRATE[SE_USD][10] = 4.625;
   SE_RDATE[SE_USD][11] = (long)D'2023.03.23';  SE_RRATE[SE_USD][11] = 4.875;
   SE_RDATE[SE_USD][12] = (long)D'2023.05.04';  SE_RRATE[SE_USD][12] = 5.125;
   SE_RDATE[SE_USD][13] = (long)D'2023.07.27';  SE_RRATE[SE_USD][13] = 5.375;
   SE_RDATE[SE_USD][14] = (long)D'2024.09.19';  SE_RRATE[SE_USD][14] = 4.875;
   SE_RDATE[SE_USD][15] = (long)D'2024.11.08';  SE_RRATE[SE_USD][15] = 4.625;
   SE_RDATE[SE_USD][16] = (long)D'2024.12.19';  SE_RRATE[SE_USD][16] = 4.375;
   SE_RDATE[SE_USD][17] = (long)D'2025.09.18';  SE_RRATE[SE_USD][17] = 4.125;
   SE_RDATE[SE_USD][18] = (long)D'2025.10.30';  SE_RRATE[SE_USD][18] = 3.875;
   SE_RDATE[SE_USD][19] = (long)D'2025.12.11';  SE_RRATE[SE_USD][19] = 3.625;
   SE_RN[SE_EUR] = 18;
   SE_RDATE[SE_EUR][0] = (long)D'2019.09.18';  SE_RRATE[SE_EUR][0] = -0.5;
   SE_RDATE[SE_EUR][1] = (long)D'2022.07.27';  SE_RRATE[SE_EUR][1] = 0.0;
   SE_RDATE[SE_EUR][2] = (long)D'2022.09.14';  SE_RRATE[SE_EUR][2] = 0.75;
   SE_RDATE[SE_EUR][3] = (long)D'2022.11.02';  SE_RRATE[SE_EUR][3] = 1.5;
   SE_RDATE[SE_EUR][4] = (long)D'2022.12.21';  SE_RRATE[SE_EUR][4] = 2.0;
   SE_RDATE[SE_EUR][5] = (long)D'2023.02.08';  SE_RRATE[SE_EUR][5] = 2.5;
   SE_RDATE[SE_EUR][6] = (long)D'2023.03.22';  SE_RRATE[SE_EUR][6] = 3.0;
   SE_RDATE[SE_EUR][7] = (long)D'2023.05.10';  SE_RRATE[SE_EUR][7] = 3.25;
   SE_RDATE[SE_EUR][8] = (long)D'2023.06.21';  SE_RRATE[SE_EUR][8] = 3.5;
   SE_RDATE[SE_EUR][9] = (long)D'2023.09.20';  SE_RRATE[SE_EUR][9] = 4.0;
   SE_RDATE[SE_EUR][10] = (long)D'2024.06.12';  SE_RRATE[SE_EUR][10] = 3.75;
   SE_RDATE[SE_EUR][11] = (long)D'2024.09.18';  SE_RRATE[SE_EUR][11] = 3.5;
   SE_RDATE[SE_EUR][12] = (long)D'2024.10.23';  SE_RRATE[SE_EUR][12] = 3.25;
   SE_RDATE[SE_EUR][13] = (long)D'2024.12.18';  SE_RRATE[SE_EUR][13] = 3.0;
   SE_RDATE[SE_EUR][14] = (long)D'2025.02.05';  SE_RRATE[SE_EUR][14] = 2.75;
   SE_RDATE[SE_EUR][15] = (long)D'2025.03.12';  SE_RRATE[SE_EUR][15] = 2.5;
   SE_RDATE[SE_EUR][16] = (long)D'2025.04.23';  SE_RRATE[SE_EUR][16] = 2.25;
   SE_RDATE[SE_EUR][17] = (long)D'2025.06.11';  SE_RRATE[SE_EUR][17] = 2.0;
   SE_RN[SE_GBP] = 23;
   SE_RDATE[SE_GBP][0] = (long)D'2019.11.01';  SE_RRATE[SE_GBP][0] = 0.75;
   SE_RDATE[SE_GBP][1] = (long)D'2020.03.11';  SE_RRATE[SE_GBP][1] = 0.25;
   SE_RDATE[SE_GBP][2] = (long)D'2020.03.19';  SE_RRATE[SE_GBP][2] = 0.1;
   SE_RDATE[SE_GBP][3] = (long)D'2021.12.16';  SE_RRATE[SE_GBP][3] = 0.25;
   SE_RDATE[SE_GBP][4] = (long)D'2022.02.03';  SE_RRATE[SE_GBP][4] = 0.5;
   SE_RDATE[SE_GBP][5] = (long)D'2022.03.17';  SE_RRATE[SE_GBP][5] = 0.75;
   SE_RDATE[SE_GBP][6] = (long)D'2022.05.05';  SE_RRATE[SE_GBP][6] = 1.0;
   SE_RDATE[SE_GBP][7] = (long)D'2022.06.16';  SE_RRATE[SE_GBP][7] = 1.25;
   SE_RDATE[SE_GBP][8] = (long)D'2022.08.04';  SE_RRATE[SE_GBP][8] = 1.75;
   SE_RDATE[SE_GBP][9] = (long)D'2022.09.22';  SE_RRATE[SE_GBP][9] = 2.25;
   SE_RDATE[SE_GBP][10] = (long)D'2022.11.03';  SE_RRATE[SE_GBP][10] = 3.0;
   SE_RDATE[SE_GBP][11] = (long)D'2022.12.15';  SE_RRATE[SE_GBP][11] = 3.5;
   SE_RDATE[SE_GBP][12] = (long)D'2023.02.02';  SE_RRATE[SE_GBP][12] = 4.0;
   SE_RDATE[SE_GBP][13] = (long)D'2023.03.23';  SE_RRATE[SE_GBP][13] = 4.25;
   SE_RDATE[SE_GBP][14] = (long)D'2023.05.11';  SE_RRATE[SE_GBP][14] = 4.5;
   SE_RDATE[SE_GBP][15] = (long)D'2023.06.22';  SE_RRATE[SE_GBP][15] = 5.0;
   SE_RDATE[SE_GBP][16] = (long)D'2023.08.03';  SE_RRATE[SE_GBP][16] = 5.25;
   SE_RDATE[SE_GBP][17] = (long)D'2024.08.01';  SE_RRATE[SE_GBP][17] = 5.0;
   SE_RDATE[SE_GBP][18] = (long)D'2024.11.07';  SE_RRATE[SE_GBP][18] = 4.75;
   SE_RDATE[SE_GBP][19] = (long)D'2025.02.06';  SE_RRATE[SE_GBP][19] = 4.5;
   SE_RDATE[SE_GBP][20] = (long)D'2025.05.08';  SE_RRATE[SE_GBP][20] = 4.25;
   SE_RDATE[SE_GBP][21] = (long)D'2025.08.07';  SE_RRATE[SE_GBP][21] = 4.0;
   SE_RDATE[SE_GBP][22] = (long)D'2025.12.18';  SE_RRATE[SE_GBP][22] = 3.75;
   SE_RN[SE_JPY] = 4;
   SE_RDATE[SE_JPY][0] = (long)D'2019.11.01';  SE_RRATE[SE_JPY][0] = -0.1;
   SE_RDATE[SE_JPY][1] = (long)D'2024.03.19';  SE_RRATE[SE_JPY][1] = 0.1;
   SE_RDATE[SE_JPY][2] = (long)D'2024.07.31';  SE_RRATE[SE_JPY][2] = 0.25;
   SE_RDATE[SE_JPY][3] = (long)D'2025.01.24';  SE_RRATE[SE_JPY][3] = 0.5;
   SE_RN[SE_CHF] = 12;
   SE_RDATE[SE_CHF][0] = (long)D'2019.11.01';  SE_RRATE[SE_CHF][0] = -0.75;
   SE_RDATE[SE_CHF][1] = (long)D'2022.06.16';  SE_RRATE[SE_CHF][1] = -0.25;
   SE_RDATE[SE_CHF][2] = (long)D'2022.09.22';  SE_RRATE[SE_CHF][2] = 0.5;
   SE_RDATE[SE_CHF][3] = (long)D'2022.12.15';  SE_RRATE[SE_CHF][3] = 1.0;
   SE_RDATE[SE_CHF][4] = (long)D'2023.03.23';  SE_RRATE[SE_CHF][4] = 1.5;
   SE_RDATE[SE_CHF][5] = (long)D'2023.06.22';  SE_RRATE[SE_CHF][5] = 1.75;
   SE_RDATE[SE_CHF][6] = (long)D'2024.03.21';  SE_RRATE[SE_CHF][6] = 1.5;
   SE_RDATE[SE_CHF][7] = (long)D'2024.06.20';  SE_RRATE[SE_CHF][7] = 1.25;
   SE_RDATE[SE_CHF][8] = (long)D'2024.09.26';  SE_RRATE[SE_CHF][8] = 1.0;
   SE_RDATE[SE_CHF][9] = (long)D'2024.12.12';  SE_RRATE[SE_CHF][9] = 0.5;
   SE_RDATE[SE_CHF][10] = (long)D'2025.03.20';  SE_RRATE[SE_CHF][10] = 0.25;
   SE_RDATE[SE_CHF][11] = (long)D'2025.06.19';  SE_RRATE[SE_CHF][11] = 0.0;
   SE_RN[SE_AUD] = 20;
   SE_RDATE[SE_AUD][0] = (long)D'2019.11.01';  SE_RRATE[SE_AUD][0] = 0.75;
   SE_RDATE[SE_AUD][1] = (long)D'2020.03.03';  SE_RRATE[SE_AUD][1] = 0.5;
   SE_RDATE[SE_AUD][2] = (long)D'2020.03.19';  SE_RRATE[SE_AUD][2] = 0.25;
   SE_RDATE[SE_AUD][3] = (long)D'2020.11.03';  SE_RRATE[SE_AUD][3] = 0.1;
   SE_RDATE[SE_AUD][4] = (long)D'2022.05.03';  SE_RRATE[SE_AUD][4] = 0.35;
   SE_RDATE[SE_AUD][5] = (long)D'2022.06.07';  SE_RRATE[SE_AUD][5] = 0.85;
   SE_RDATE[SE_AUD][6] = (long)D'2022.07.05';  SE_RRATE[SE_AUD][6] = 1.35;
   SE_RDATE[SE_AUD][7] = (long)D'2022.08.02';  SE_RRATE[SE_AUD][7] = 1.85;
   SE_RDATE[SE_AUD][8] = (long)D'2022.09.06';  SE_RRATE[SE_AUD][8] = 2.35;
   SE_RDATE[SE_AUD][9] = (long)D'2022.10.04';  SE_RRATE[SE_AUD][9] = 2.6;
   SE_RDATE[SE_AUD][10] = (long)D'2022.11.01';  SE_RRATE[SE_AUD][10] = 2.85;
   SE_RDATE[SE_AUD][11] = (long)D'2022.12.06';  SE_RRATE[SE_AUD][11] = 3.1;
   SE_RDATE[SE_AUD][12] = (long)D'2023.02.07';  SE_RRATE[SE_AUD][12] = 3.35;
   SE_RDATE[SE_AUD][13] = (long)D'2023.03.07';  SE_RRATE[SE_AUD][13] = 3.6;
   SE_RDATE[SE_AUD][14] = (long)D'2023.05.02';  SE_RRATE[SE_AUD][14] = 3.85;
   SE_RDATE[SE_AUD][15] = (long)D'2023.06.06';  SE_RRATE[SE_AUD][15] = 4.1;
   SE_RDATE[SE_AUD][16] = (long)D'2023.11.07';  SE_RRATE[SE_AUD][16] = 4.35;
   SE_RDATE[SE_AUD][17] = (long)D'2025.02.18';  SE_RRATE[SE_AUD][17] = 4.1;
   SE_RDATE[SE_AUD][18] = (long)D'2025.05.20';  SE_RRATE[SE_AUD][18] = 3.85;
   SE_RDATE[SE_AUD][19] = (long)D'2025.08.12';  SE_RRATE[SE_AUD][19] = 3.6;
   SE_RN[SE_NZD] = 23;
   SE_RDATE[SE_NZD][0] = (long)D'2019.11.01';  SE_RRATE[SE_NZD][0] = 1.0;
   SE_RDATE[SE_NZD][1] = (long)D'2020.03.16';  SE_RRATE[SE_NZD][1] = 0.25;
   SE_RDATE[SE_NZD][2] = (long)D'2021.10.06';  SE_RRATE[SE_NZD][2] = 0.5;
   SE_RDATE[SE_NZD][3] = (long)D'2021.11.24';  SE_RRATE[SE_NZD][3] = 0.75;
   SE_RDATE[SE_NZD][4] = (long)D'2022.02.23';  SE_RRATE[SE_NZD][4] = 1.0;
   SE_RDATE[SE_NZD][5] = (long)D'2022.04.13';  SE_RRATE[SE_NZD][5] = 1.5;
   SE_RDATE[SE_NZD][6] = (long)D'2022.05.25';  SE_RRATE[SE_NZD][6] = 2.0;
   SE_RDATE[SE_NZD][7] = (long)D'2022.07.13';  SE_RRATE[SE_NZD][7] = 2.5;
   SE_RDATE[SE_NZD][8] = (long)D'2022.08.17';  SE_RRATE[SE_NZD][8] = 3.0;
   SE_RDATE[SE_NZD][9] = (long)D'2022.10.05';  SE_RRATE[SE_NZD][9] = 3.5;
   SE_RDATE[SE_NZD][10] = (long)D'2022.11.23';  SE_RRATE[SE_NZD][10] = 4.25;
   SE_RDATE[SE_NZD][11] = (long)D'2023.02.22';  SE_RRATE[SE_NZD][11] = 4.75;
   SE_RDATE[SE_NZD][12] = (long)D'2023.04.05';  SE_RRATE[SE_NZD][12] = 5.25;
   SE_RDATE[SE_NZD][13] = (long)D'2023.05.24';  SE_RRATE[SE_NZD][13] = 5.5;
   SE_RDATE[SE_NZD][14] = (long)D'2024.08.14';  SE_RRATE[SE_NZD][14] = 5.25;
   SE_RDATE[SE_NZD][15] = (long)D'2024.10.09';  SE_RRATE[SE_NZD][15] = 4.75;
   SE_RDATE[SE_NZD][16] = (long)D'2024.11.27';  SE_RRATE[SE_NZD][16] = 4.25;
   SE_RDATE[SE_NZD][17] = (long)D'2025.02.19';  SE_RRATE[SE_NZD][17] = 3.75;
   SE_RDATE[SE_NZD][18] = (long)D'2025.04.09';  SE_RRATE[SE_NZD][18] = 3.5;
   SE_RDATE[SE_NZD][19] = (long)D'2025.05.28';  SE_RRATE[SE_NZD][19] = 3.25;
   SE_RDATE[SE_NZD][20] = (long)D'2025.08.20';  SE_RRATE[SE_NZD][20] = 3.0;
   SE_RDATE[SE_NZD][21] = (long)D'2025.10.08';  SE_RRATE[SE_NZD][21] = 2.5;
   SE_RDATE[SE_NZD][22] = (long)D'2025.11.26';  SE_RRATE[SE_NZD][22] = 2.25;
   SE_RN[SE_CAD] = 21;
   SE_RDATE[SE_CAD][0] = (long)D'2019.11.01';  SE_RRATE[SE_CAD][0] = 1.75;
   SE_RDATE[SE_CAD][1] = (long)D'2020.03.04';  SE_RRATE[SE_CAD][1] = 1.25;
   SE_RDATE[SE_CAD][2] = (long)D'2020.03.16';  SE_RRATE[SE_CAD][2] = 0.75;
   SE_RDATE[SE_CAD][3] = (long)D'2020.03.27';  SE_RRATE[SE_CAD][3] = 0.25;
   SE_RDATE[SE_CAD][4] = (long)D'2022.03.02';  SE_RRATE[SE_CAD][4] = 0.5;
   SE_RDATE[SE_CAD][5] = (long)D'2022.04.13';  SE_RRATE[SE_CAD][5] = 1.0;
   SE_RDATE[SE_CAD][6] = (long)D'2022.06.01';  SE_RRATE[SE_CAD][6] = 1.5;
   SE_RDATE[SE_CAD][7] = (long)D'2022.07.13';  SE_RRATE[SE_CAD][7] = 2.5;
   SE_RDATE[SE_CAD][8] = (long)D'2022.09.07';  SE_RRATE[SE_CAD][8] = 3.25;
   SE_RDATE[SE_CAD][9] = (long)D'2022.10.26';  SE_RRATE[SE_CAD][9] = 3.75;
   SE_RDATE[SE_CAD][10] = (long)D'2022.12.07';  SE_RRATE[SE_CAD][10] = 4.25;
   SE_RDATE[SE_CAD][11] = (long)D'2023.01.25';  SE_RRATE[SE_CAD][11] = 4.5;
   SE_RDATE[SE_CAD][12] = (long)D'2023.06.07';  SE_RRATE[SE_CAD][12] = 4.75;
   SE_RDATE[SE_CAD][13] = (long)D'2023.07.12';  SE_RRATE[SE_CAD][13] = 5.0;
   SE_RDATE[SE_CAD][14] = (long)D'2024.06.05';  SE_RRATE[SE_CAD][14] = 4.75;
   SE_RDATE[SE_CAD][15] = (long)D'2024.07.24';  SE_RRATE[SE_CAD][15] = 4.5;
   SE_RDATE[SE_CAD][16] = (long)D'2024.09.04';  SE_RRATE[SE_CAD][16] = 4.25;
   SE_RDATE[SE_CAD][17] = (long)D'2024.10.23';  SE_RRATE[SE_CAD][17] = 3.75;
   SE_RDATE[SE_CAD][18] = (long)D'2024.12.11';  SE_RRATE[SE_CAD][18] = 3.25;
   SE_RDATE[SE_CAD][19] = (long)D'2025.01.29';  SE_RRATE[SE_CAD][19] = 3.0;
   SE_RDATE[SE_CAD][20] = (long)D'2025.03.12';  SE_RRATE[SE_CAD][20] = 2.75;
   SE_RN[SE_NOK] = 20;
   SE_RDATE[SE_NOK][0] = (long)D'2019.11.01';  SE_RRATE[SE_NOK][0] = 1.5;
   SE_RDATE[SE_NOK][1] = (long)D'2020.03.13';  SE_RRATE[SE_NOK][1] = 1.0;
   SE_RDATE[SE_NOK][2] = (long)D'2020.03.20';  SE_RRATE[SE_NOK][2] = 0.25;
   SE_RDATE[SE_NOK][3] = (long)D'2020.05.07';  SE_RRATE[SE_NOK][3] = 0.0;
   SE_RDATE[SE_NOK][4] = (long)D'2021.09.24';  SE_RRATE[SE_NOK][4] = 0.25;
   SE_RDATE[SE_NOK][5] = (long)D'2021.12.17';  SE_RRATE[SE_NOK][5] = 0.5;
   SE_RDATE[SE_NOK][6] = (long)D'2022.03.24';  SE_RRATE[SE_NOK][6] = 0.75;
   SE_RDATE[SE_NOK][7] = (long)D'2022.06.23';  SE_RRATE[SE_NOK][7] = 1.25;
   SE_RDATE[SE_NOK][8] = (long)D'2022.08.18';  SE_RRATE[SE_NOK][8] = 1.75;
   SE_RDATE[SE_NOK][9] = (long)D'2022.09.22';  SE_RRATE[SE_NOK][9] = 2.25;
   SE_RDATE[SE_NOK][10] = (long)D'2022.11.03';  SE_RRATE[SE_NOK][10] = 2.5;
   SE_RDATE[SE_NOK][11] = (long)D'2022.12.15';  SE_RRATE[SE_NOK][11] = 2.75;
   SE_RDATE[SE_NOK][12] = (long)D'2023.03.23';  SE_RRATE[SE_NOK][12] = 3.0;
   SE_RDATE[SE_NOK][13] = (long)D'2023.05.04';  SE_RRATE[SE_NOK][13] = 3.25;
   SE_RDATE[SE_NOK][14] = (long)D'2023.06.22';  SE_RRATE[SE_NOK][14] = 3.75;
   SE_RDATE[SE_NOK][15] = (long)D'2023.08.17';  SE_RRATE[SE_NOK][15] = 4.0;
   SE_RDATE[SE_NOK][16] = (long)D'2023.09.21';  SE_RRATE[SE_NOK][16] = 4.25;
   SE_RDATE[SE_NOK][17] = (long)D'2023.12.14';  SE_RRATE[SE_NOK][17] = 4.5;
   SE_RDATE[SE_NOK][18] = (long)D'2025.06.19';  SE_RRATE[SE_NOK][18] = 4.25;
   SE_RDATE[SE_NOK][19] = (long)D'2025.09.18';  SE_RRATE[SE_NOK][19] = 4.0;
   SE_RN[SE_SEK] = 17;
   SE_RDATE[SE_SEK][0] = (long)D'2019.11.01';  SE_RRATE[SE_SEK][0] = -0.25;
   SE_RDATE[SE_SEK][1] = (long)D'2020.01.08';  SE_RRATE[SE_SEK][1] = 0.0;
   SE_RDATE[SE_SEK][2] = (long)D'2022.05.04';  SE_RRATE[SE_SEK][2] = 0.25;
   SE_RDATE[SE_SEK][3] = (long)D'2022.07.06';  SE_RRATE[SE_SEK][3] = 0.75;
   SE_RDATE[SE_SEK][4] = (long)D'2022.09.21';  SE_RRATE[SE_SEK][4] = 1.75;
   SE_RDATE[SE_SEK][5] = (long)D'2022.11.30';  SE_RRATE[SE_SEK][5] = 2.5;
   SE_RDATE[SE_SEK][6] = (long)D'2023.02.09';  SE_RRATE[SE_SEK][6] = 3.0;
   SE_RDATE[SE_SEK][7] = (long)D'2023.04.26';  SE_RRATE[SE_SEK][7] = 3.5;
   SE_RDATE[SE_SEK][8] = (long)D'2023.07.05';  SE_RRATE[SE_SEK][8] = 3.75;
   SE_RDATE[SE_SEK][9] = (long)D'2023.09.21';  SE_RRATE[SE_SEK][9] = 4.0;
   SE_RDATE[SE_SEK][10] = (long)D'2024.05.08';  SE_RRATE[SE_SEK][10] = 3.75;
   SE_RDATE[SE_SEK][11] = (long)D'2024.08.20';  SE_RRATE[SE_SEK][11] = 3.5;
   SE_RDATE[SE_SEK][12] = (long)D'2024.09.25';  SE_RRATE[SE_SEK][12] = 3.25;
   SE_RDATE[SE_SEK][13] = (long)D'2024.11.07';  SE_RRATE[SE_SEK][13] = 2.75;
   SE_RDATE[SE_SEK][14] = (long)D'2024.12.19';  SE_RRATE[SE_SEK][14] = 2.5;
   SE_RDATE[SE_SEK][15] = (long)D'2025.01.29';  SE_RRATE[SE_SEK][15] = 2.25;
   SE_RDATE[SE_SEK][16] = (long)D'2025.06.18';  SE_RRATE[SE_SEK][16] = 2.0;
   SE_RN[SE_XAU] = 1;
   SE_RDATE[SE_XAU][0] = (long)D'2019.11.01';  SE_RRATE[SE_XAU][0] = 0.0;
   SE_RN[SE_XAG] = 1;
   SE_RDATE[SE_XAG][0] = (long)D'2019.11.01';  SE_RRATE[SE_XAG][0] = 0.0;
   SE_RN[SE_XPT] = 1;
   SE_RDATE[SE_XPT][0] = (long)D'2019.11.01';  SE_RRATE[SE_XPT][0] = 0.0;
   SE_RN[SE_XTI] = 1;
   SE_RDATE[SE_XTI][0] = (long)D'2019.11.01';  SE_RRATE[SE_XTI][0] = 0.0;
   SE_RN[SE_XBR] = 1;
   SE_RDATE[SE_XBR][0] = (long)D'2019.11.01';  SE_RRATE[SE_XBR][0] = 0.0;
   SE_RN[SE_XNG] = 1;
   SE_RDATE[SE_XNG][0] = (long)D'2019.11.01';  SE_RRATE[SE_XNG][0] = 0.0;
  }

//+------------------------------------------------------------------+
//| scalar primitives (transcription of NSF5 engine/costs.py)         |
//+------------------------------------------------------------------+
int SE_SymId(const string s)
  {
   for(int i=0; i<SE_NSYM; i++)
      if(SE_SYM[i]==s)
         return i;
   return -1;
  }

int SE_CrossId(const string s)
  {
   for(int i=0; i<SE_NCROSS; i++)
      if(SE_CROSS[i]==s)
         return i;
   return -1;
  }

//--- Mon=0 .. Sun=6 for a midnight epoch (1970-01-01 was a Thursday)
int SE_WeekdayOf(const long day_sec)
  {
   return (int)(((day_sec/SE_DAY)+3)%7);
  }

long SE_MidnightOf(const long ts) { return (ts/SE_DAY)*SE_DAY; }

double SE_PolicyRate(const int ccy, const long ts)
  {
   double rate=SE_RRATE[ccy][0];
   for(int i=0; i<SE_RN[ccy]; i++)
     {
      if(SE_RDATE[ccy][i]<=ts)
         rate=SE_RRATE[ccy][i];
      else
         break;
     }
   return rate;
  }

//--- (long, short) annualized swap, percent of notional per year
void SE_SwapAnnualPct(const int k, const long day, double &lp, double &sp)
  {
   int ac=SE_SYM_AC[k];
   if(ac==SE_FX || ac==SE_METAL)
     {
      double rb=SE_PolicyRate(SE_SYM_BASE[k], day);
      double rq=SE_PolicyRate(SE_SYM_QUOT[k], day);
      double mk=SE_SYM_MKUP[k];
      lp=rb-rq-mk;
      sp=rq-rb-mk;
      return;
     }
   if(ac==SE_INDEX)
     {
      double rq=SE_PolicyRate(SE_SYM_QUOT[k], day);
      double div=(SE_SYM[k]=="USA500") ? SE_USA500_DIV : 0.0;
      lp=-(rq+SE_INDEX_MARKUP)+div;
      sp=rq-SE_INDEX_MARKUP-div;
      return;
     }
   lp=SE_CRYPTO_LONG;      // crypto
   sp=SE_CRYPTO_SHORT;
  }

int SE_SwapDayMultiplier(const int k, const long day)
  {
   int ac=SE_SYM_AC[k];
   int wd=SE_WeekdayOf(day);
   if(ac==SE_FX || ac==SE_METAL)
      return (wd==2) ? 3 : 1;      // triple Wednesday
   if(ac==SE_INDEX)
      return (wd==4) ? 3 : 1;      // triple Friday
   return 1;                       // crypto: every calendar day
  }

bool SE_IsSwapDay(const int k, const long day)
  {
   return (SE_SYM_AC[k]==SE_CRYPTO) || (SE_WeekdayOf(day)<5);
  }

//--- n-th Sunday of (year, month), epoch seconds at 00:00
long SE_NthSunday(const int year, const int month, const int n)
  {
   MqlDateTime st;
   st.year=year;
   st.mon=month;
   st.day=1;
   st.hour=0;
   st.min=0;
   st.sec=0;
   st.day_of_week=0;
   st.day_of_year=0;
   long t=(long)StructToTime(st);
   int wd=SE_WeekdayOf(t);          // Mon=0..Sun=6
   int off=(6-wd)%7;
   return t+(long)(off+7*(n-1))*SE_DAY;
  }

//--- 17:00 America/New_York on `day`, as a naive-UTC epoch second
//    (US rule: EDT from 2nd Sun Mar 02:00 local to 1st Sun Nov 02:00 local)
long SE_RolloverUtcSec(const long day)
  {
   MqlDateTime st;
   TimeToStruct((datetime)day, st);
   long ds=SE_NthSunday(st.year, 3, 2)+7*3600;    // 02:00 EST = 07:00 UTC
   long de=SE_NthSunday(st.year,11, 1)+6*3600;    // 02:00 EDT = 06:00 UTC
   long noon=day+12*3600;
   bool edt=(noon>=ds && noon<de);
   return day+17*3600+(edt ? 4*3600 : 5*3600);
  }

//+------------------------------------------------------------------+
//| causal ffill of one EUR cross's bar-close mid                     |
//+------------------------------------------------------------------+
class CSECross
  {
public:
   double            bid_c, ask_c;
   bool              seeded;
   bool              f32;
                     CSECross() { bid_c=0.0; ask_c=0.0; seeded=false; f32=true; }
   void              Update(const double b, const double a)
     {
      //--- the b_h record feed is float32-quantized: the (float) cast is
      //--- LOAD-BEARING (BH_ENGINE_SPEC section 3 / the CSV reader contract)
      bid_c = f32 ? (double)(float)b : b;
      ask_c = f32 ? (double)(float)a : a;
      seeded=true;
     }
   double            EurPerQuote() const
     {
      return 1.0/(0.5*(bid_c+ask_c));
     }
  };

//+------------------------------------------------------------------+
//| CSwapEurqBH — Satellite profile (31 book symbols, 8 EUR crosses)  |
//+------------------------------------------------------------------+
class CSwapEurqBH
  {
private:
   int               m_k[SE_NSYM];        // slot -> symbol id
   int               m_n;                 // slots in use
   CSECross          m_cross[SE_NCROSS];
   long              m_next_day;
   long              m_last_day;
   bool              m_started;
public:
   int               pre_first_bar_hits;
   int               rollovers_fired;

                     CSwapEurqBH() { m_n=0; m_started=false; m_next_day=0; m_last_day=0;
                                     pre_first_bar_hits=0; rollovers_fired=0; }

   //--- symbol slots, in the caller's own (book) order
   bool              AddSymbol(const string s)
     {
      int id=SE_SymId(s);
      if(id<0 || m_n>=SE_NSYM)
         return false;
      m_k[m_n++]=id;
      return true;
     }
   int               NSlots() const { return m_n; }

   void              Start(const long first_ts, const long last_ts)
     {
      SE_InitTables();
      for(int c=0; c<SE_NCROSS; c++)
         m_cross[c].f32=true;
      m_next_day=SE_MidnightOf(first_ts);
      m_last_day=SE_MidnightOf(last_ts)+SE_DAY;   // exporter day range +1D
      m_started=true;
     }

   //--- push a completed cross bar (stamp <= the bar being stepped)
   void              OnCrossBar(const string cross, const double bid_c, const double ask_c)
     {
      int c=SE_CrossId(cross);
      if(c>=0)
         m_cross[c].Update(bid_c, ask_c);
     }
   //--- `pre` rule: value used for grid bars BEFORE the cross's first bar
   void              SeedCross(const string cross, const double bid_c, const double ask_c)
     {
      int c=SE_CrossId(cross);
      if(c>=0 && !m_cross[c].seeded)
        {
         m_cross[c].Update(bid_c, ask_c);
         pre_first_bar_hits++;
        }
     }
   bool              CrossReady() const
     {
      for(int i=0; i<m_n; i++)
        {
         int x=SE_QUOT_CROSS[SE_SYM_QUOT[m_k[i]]];
         if(x>=0 && !m_cross[x].seeded)
            return false;
        }
      return true;
     }

   //--- one union-grid minute -> eurq[], swap_l[], swap_s[] (slot order)
   bool              Step(const long ts, double &eurq[], double &swap_l[], double &swap_s[])
     {
      if(!m_started || !CrossReady())
         return false;
      for(int i=0; i<m_n; i++)
        {
         int x=SE_QUOT_CROSS[SE_SYM_QUOT[m_k[i]]];
         eurq[i]   = (x<0) ? 1.0 : m_cross[x].EurPerQuote();
         swap_l[i] = 0.0;
         swap_s[i] = 0.0;
        }
      while(m_next_day<=m_last_day && m_next_day<=ts)
        {
         bool fired=false;
         for(int i=0; i<m_n; i++)
           {
            int k=m_k[i];
            if(!SE_IsSwapDay(k, m_next_day))
               continue;
            int mult=SE_SwapDayMultiplier(k, m_next_day);
            double lp, sp;
            SE_SwapAnnualPct(k, m_next_day, lp, sp);
            swap_l[i] += lp/100.0/365.0*mult;      // ACCUMULATING +=
            swap_s[i] += sp/100.0/365.0*mult;
            fired=true;
           }
         if(fired)
            rollovers_fired++;
         m_next_day+=SE_DAY;
        }
      return true;
     }
  };

//+------------------------------------------------------------------+
//| CSwapEurqCore — Core a_h profile (per-leg, NY-17:00 rollover)     |
//+------------------------------------------------------------------+
class CSwapEurqCore
  {
private:
   int               m_k[SE_NSYM];
   int               m_n;
   CSECross          m_cross[SE_NCROSS];
   long              m_next_day;
   long              m_last_day;
   bool              m_started;
public:
   int               pre_first_bar_hits;
   int               rollovers_fired;

                     CSwapEurqCore() { m_n=0; m_started=false; m_next_day=0; m_last_day=0;
                                       pre_first_bar_hits=0; rollovers_fired=0; }
   bool              AddSymbol(const string s)
     {
      int id=SE_SymId(s);
      if(id<0 || m_n>=SE_NSYM)
         return false;
      m_k[m_n++]=id;
      return true;
     }
   int               NSlots() const { return m_n; }

   void              Start(const long first_ts, const long last_ts)
     {
      SE_InitTables();
      for(int c=0; c<SE_NCROSS; c++)
         m_cross[c].f32=false;               // a_h feed is float64 — NO cast
      m_next_day=SE_MidnightOf(first_ts);
      m_last_day=SE_MidnightOf(last_ts);     // NSF5 day range: no +1D
      m_started=true;
     }
   void              OnCrossBar(const string cross, const double bid_c, const double ask_c)
     {
      int c=SE_CrossId(cross);
      if(c>=0)
         m_cross[c].Update(bid_c, ask_c);
     }
   void              SeedCross(const string cross, const double bid_c, const double ask_c)
     {
      int c=SE_CrossId(cross);
      if(c>=0 && !m_cross[c].seeded)
        {
         m_cross[c].Update(bid_c, ask_c);
         pre_first_bar_hits++;
        }
     }

   bool              Step(const long ts, double &eurq[], double &flag[],
                          double &sw_long[], double &sw_short[])
     {
      if(!m_started)
         return false;
      for(int i=0; i<m_n; i++)
        {
         int x=SE_QUOT_CROSS[SE_SYM_QUOT[m_k[i]]];
         if(x>=0 && !m_cross[x].seeded)
            return false;
         eurq[i]     = (x<0) ? 1.0 : m_cross[x].EurPerQuote();
         flag[i]     = 0.0;
         sw_long[i]  = 0.0;
         sw_short[i] = 0.0;
        }
      while(m_next_day<=m_last_day && SE_RolloverUtcSec(m_next_day)<=ts)
        {
         bool fired=false;
         for(int i=0; i<m_n; i++)
           {
            int k=m_k[i];
            if(!SE_IsSwapDay(k, m_next_day))
               continue;
            double lp, sp;
            SE_SwapAnnualPct(k, m_next_day, lp, sp);
            flag[i]     += (double)SE_SwapDayMultiplier(k, m_next_day);  // +=
            sw_long[i]   = lp/100.0;                                     // =
            sw_short[i]  = sp/100.0;
            fired=true;
           }
         if(fired)
            rollovers_fired++;
         m_next_day+=SE_DAY;
        }
      return true;
     }

   //--- LIVE warm-start additive accessors (Book/CoreLiveDrive.mqh) ---
   //--- pure reads/setters over EXISTING fields; the generator law    ---
   //--- (Start/OnCrossBar/Step) is untouched.                        ---
   long              NextDay(void)   const { return m_next_day; }
   bool              StartedGen(void) const { return m_started;  }
   void              RestoreClock(const long next_day) { m_next_day=next_day; }
   bool              CrossGet(const int c, double &b, double &a, bool &seeded) const
     {
      if(c<0 || c>=SE_NCROSS)
         return false;
      b=m_cross[c].bid_c;
      a=m_cross[c].ask_c;
      seeded=m_cross[c].seeded;
      return true;
     }
   bool              CrossRestore(const int c, const double b, const double a, const bool seeded)
     {
      if(c<0 || c>=SE_NCROSS)
         return false;
      m_cross[c].bid_c=b;
      m_cross[c].ask_c=a;
      m_cross[c].seeded=seeded;
      return true;
     }
  };

#endif // __SWAPEURQ_MQH__
