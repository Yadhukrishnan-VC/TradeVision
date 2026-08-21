# Edge Validation Report V2 — TradeVision

**Generated:** 2026-08-21T18:26:14.451737+00:00

**Symbols analyzed:** 41 (ADANIPORTS, APOLLOHOSP, ASIANPAINT, AXISBANK, BAJAJ-AUTO, BAJAJFINSV, BAJFINANCE, BHARTIARTL, BPCL, BRITANNIA, CIPLA, DIVISLAB, DRREDDY, EICHERMOT, GRASIM, HDFCBANK, HDFCLIFE, HEROMOTOCO, HINDALCO, HINDUNILVR, ICICIBANK, INDUSINDBK, INFY, JSWSTEEL, KOTAKBANK, LT, M&M, MARUTI, NESTLEIND, POWERGRID, RELIANCE, SBILIFE, SBIN, SUNPHARMA, TATACONSUM, TATASTEEL, TCS, TECHM, TITAN, ULTRACEMCO, WIPRO)
**Timeframe:** 1D
**Years of history:** 3
**Walk-forward window:** 252 days
**Walk-forward step:** 63 days
**In-sample ratio:** 0.70
**Realistic commission rate:** 0.0013 (0.13%)
**Realistic slippage:** 5.0 bps
**Significance test:** pooled shuffled baseline, n_shuffles=1000, alpha=0.05, min_trades=10

---

## Overall Verdicts

| Rule ID | Regime | Verdict | Symbols | Trades | Pooled Expectancy | p-value | Significant |
|---------|--------|---------|---------|--------|-------------------|---------|-------------|
| breakout_v1 | RANGING | **NO-GO** | 38 | 289 | 78.7286 | 0.0250 | YES |
| price_movement_v1 | RANGING | **NO-GO** | 37 | 428 | 6.0977 | 0.4336 | NO |
| volatility_breakout_v1 | RANGING | **INSUFFICIENT-DATA** | 35 | 131 | -47.6543 | 0.6633 | NO |
| volume_spike_v1 | RANGING | **INSUFFICIENT-DATA** | 1 | 1 | 2260.0014 | — | N/A |
| volume_spike_v1 | UNKNOWN | **INSUFFICIENT-DATA** | 1 | 0 | — | — | N/A |

---

## Per-Symbol Detail

### breakout_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| APOLLOHOSP | INSUFF | INSUFF | NO | 0 | 9 | — | -31.3057 | 0.7735 | 2.0151 | 0.0340 | 29 | 0 OOS windows had trades |
| ASIANPAINT | INSUFF | INSUFF | NO | 6 | 6 | 336.4498 | -6.3886 | 0.9720 | 7.1108 | 0.0113 | 23 | 0 OOS windows had trades |
| AXISBANK | INSUFF | INSUFF | NO | 2 | 2 | 1335.0000 | 834.2417 | 3.8694 | 13.3278 | 0.0000 | 6 | 0 OOS windows had trades |
| BAJAJ-AUTO | INSUFF | INSUFF | NO | 9 | 9 | -119.2280 | -365.4033 | 0.0634 | -11.1680 | 0.1994 | 17 | 0 OOS windows had trades |
| BAJAJFINSV | INSUFF | INSUFF | NO | 1 | 1 | 819.0000 | 331.2482 | 2.1697 | — | 0.0000 | 33 | 0 OOS windows had trades |
| BAJFINANCE | INSUFF | INSUFF | NO | 4 | 4 | -86.8388 | -542.4388 | 0.0827 | -7.9858 | 0.1521 | 14 | 0 OOS windows had trades |
| BHARTIARTL | GO | NO-GO | YES | 21 | 21 | 48.0208 | -61.7148 | 0.6237 | 0.4371 | 0.1791 | 29 | 0 OOS windows had trades |
| BRITANNIA | INSUFF | INSUFF | NO | 6 | 6 | 49.3249 | -72.1130 | 0.4692 | -0.1308 | 0.0391 | 23 | 0 OOS windows had trades |
| CIPLA | INSUFF | INSUFF | NO | 7 | 7 | 261.5500 | 98.3180 | 1.4559 | 6.6055 | 0.0622 | 30 | 0 OOS windows had trades |
| DIVISLAB | GO | NO-GO | YES | 13 | 13 | 185.2886 | -65.2321 | 0.6786 | 6.2658 | 0.0700 | 36 | 0 OOS windows had trades |
| DRREDDY | INSUFF | INSUFF | NO | 3 | 3 | 557.8833 | 243.9167 | 1.9839 | 7.4467 | 0.0118 | 18 | 0 OOS windows had trades |
| EICHERMOT | INSUFF | INSUFF | NO | 7 | 7 | 340.0205 | 172.3656 | 2.5050 | 11.2293 | 0.0107 | 24 | 0 OOS windows had trades |
| GRASIM | GO | NO-GO | YES | 10 | 10 | 91.6840 | -17.0281 | 0.8568 | 4.9650 | 0.0256 | 26 | 0 OOS windows had trades |
| HDFCBANK | INSUFF | INSUFF | NO | 7 | 7 | 338.4607 | -146.4542 | 0.8188 | 1.2489 | 0.3043 | 22 | 0 OOS windows had trades |
| HDFCLIFE | GO | NO-GO | YES | 13 | 13 | 81.4346 | -137.8931 | 0.5777 | 1.2525 | 0.1768 | 25 | 0 OOS windows had trades |
| HEROMOTOCO | NO-GO | NO-GO | NO | 17 | 17 | -9.4994 | -98.3818 | 0.3426 | -1.9642 | 0.0847 | 29 | 0 OOS windows had trades |
| HINDALCO | INSUFF | INSUFF | NO | 2 | 2 | 243.0750 | -147.3136 | 0.5589 | 3.0321 | 0.0250 | 9 | 0 OOS windows had trades |
| HINDUNILVR | INSUFF | INSUFF | NO | 2 | 2 | -637.0000 | -892.2544 | 0.0000 | -11.2250 | 0.0808 | 7 | 0 OOS windows had trades |
| ICICIBANK | GO | NO-GO | YES | 13 | 13 | 66.1092 | -70.9382 | 0.6913 | 0.5438 | 0.1815 | 25 | 0 OOS windows had trades |
| INDUSINDBK | INSUFF | INSUFF | NO | 1 | 1 | 201.6500 | 11.8260 | 1.1073 | — | 0.0000 | 13 | 0 OOS windows had trades |
| INFY | INSUFF | INSUFF | NO | 7 | 7 | 223.0571 | -163.0253 | 0.6632 | 1.3591 | 0.1295 | 24 | 0 OOS windows had trades |
| JSWSTEEL | INSUFF | INSUFF | NO | 7 | 7 | -74.4000 | -129.3187 | 0.4635 | -1.3564 | 0.0809 | 28 | 0 OOS windows had trades |
| KOTAKBANK | INSUFF | INSUFF | NO | 2 | 2 | 1305.0150 | 545.0820 | 2.2354 | 87.9543 | 0.0000 | 13 | 0 OOS windows had trades |
| LT | INSUFF | INSUFF | NO | 9 | 9 | 887.8289 | 652.2799 | 4.3690 | 7.9901 | 0.0499 | 26 | 0 OOS windows had trades |
| M&M | NO-GO | NO-GO | NO | 12 | 12 | -124.7863 | -212.2101 | 0.4170 | -1.9972 | 0.2867 | 30 | 0 OOS windows had trades |
| MARUTI | INSUFF | INSUFF | NO | 8 | 8 | 91.9591 | -107.1979 | 0.5287 | 0.8028 | 0.0409 | 20 | 0 OOS windows had trades |
| NESTLEIND | INSUFF | INSUFF | NO | 7 | 7 | 116.0639 | -127.0393 | 0.4289 | 0.9368 | 0.0635 | 13 | 0 OOS windows had trades |
| POWERGRID | INSUFF | INSUFF | NO | 6 | 6 | 829.1333 | 413.7179 | 2.1608 | 9.4635 | 0.0696 | 6 | 0 OOS windows had trades |
| SBILIFE | INSUFF | INSUFF | NO | 6 | 6 | -6.8000 | -246.6677 | 0.2150 | -4.0660 | 0.0396 | 23 | 0 OOS windows had trades |
| SBIN | INSUFF | INSUFF | NO | 5 | 5 | 270.7450 | -23.9729 | 0.9492 | 2.9624 | 0.0941 | 12 | 0 OOS windows had trades |
| SUNPHARMA | INSUFF | INSUFF | NO | 7 | 7 | 66.7786 | -82.7012 | 0.3210 | 0.5961 | 0.0181 | 26 | 0 OOS windows had trades |
| TATACONSUM | NO-GO | NO-GO | NO | 15 | 15 | -112.5848 | -208.0670 | 0.3210 | -2.3680 | 0.3134 | 30 | 0 OOS windows had trades |
| TATASTEEL | INSUFF | INSUFF | NO | 3 | 3 | 1329.7500 | 804.1929 | 3.1494 | 9.1444 | 0.0206 | 3 | 0 OOS windows had trades |
| TCS | NO-GO | NO-GO | NO | 10 | 10 | -69.3336 | -291.9699 | 0.2029 | -5.4404 | 0.1576 | 35 | 0 OOS windows had trades |
| TECHM | GO | NO-GO | YES | 11 | 11 | 159.9591 | -104.2175 | 0.6301 | 1.6815 | 0.1340 | 34 | 0 OOS windows had trades |
| TITAN | INSUFF | INSUFF | NO | 5 | 5 | 20.7014 | -446.5043 | 0.3266 | -3.2046 | 0.2262 | 19 | 0 OOS windows had trades |
| ULTRACEMCO | INSUFF | INSUFF | NO | 8 | 8 | 285.7442 | 6.2788 | 1.0299 | 5.5250 | 0.0275 | 20 | 0 OOS windows had trades |
| WIPRO | INSUFF | INSUFF | NO | 8 | 8 | 180.2050 | -158.8402 | 0.6519 | 0.7113 | 0.2311 | 24 | 0 OOS windows had trades |


> **Reliable subset (breakout_v1/RANGING):** Of the 47 symbols screened, only 6 symbols individually maintain a positive expectancy and profit factor > 1 at realistic NSE costs (commission=0.13%, slippage=5bps) in the deep 14-window walk-forward re-run: **BPCL, COALINDIA, ITC, NTPC, ONGC, UPL**. The pooled GO verdict for breakout_v1/RANGING is driven primarily by these names; the rule should not be interpreted as broadly effective across the full Nifty 50 universe. Deep re-run used 14 walk-forward windows (step=63d) with realistic costs; other symbols either flipped to NO-GO or had insufficient OOS trades.





### price_movement_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIPORTS | NO-GO | NO-GO | NO | 23 | 23 | -67.0759 | -436.9068 | 0.3045 | -4.5636 | 0.7429 | 25 | 0 OOS windows had trades |
| APOLLOHOSP | GO | NO-GO | YES | 20 | 14 | 13.3937 | -248.0309 | 0.1089 | -9.9751 | 0.2022 | 29 | 0 OOS windows had trades |
| ASIANPAINT | GO | NO-GO | YES | 14 | 14 | 115.0979 | -197.9599 | 0.5166 | 0.1869 | 0.1450 | 23 | 0 OOS windows had trades |
| AXISBANK | INSUFF | INSUFF | NO | 4 | 4 | 145.3125 | -146.9942 | 0.9537 | 2.5908 | 0.0986 | 6 | 0 OOS windows had trades |
| BAJAJ-AUTO | INSUFF | INSUFF | NO | 6 | 6 | 62.5500 | -2.7244 | 0.9409 | 9.2329 | 0.0037 | 17 | 0 OOS windows had trades |
| BAJAJFINSV | NO-GO | NO-GO | NO | 27 | 27 | -80.1732 | -289.9354 | 0.2948 | -4.3257 | 0.7094 | 33 | 0 OOS windows had trades |
| BAJFINANCE | INSUFF | INSUFF | NO | 9 | 9 | -74.2733 | -445.2228 | 0.4636 | -2.9139 | 0.6437 | 14 | 0 OOS windows had trades |
| BHARTIARTL | INSUFF | INSUFF | NO | 4 | 4 | -52.3375 | -47.9739 | 0.1809 | -6.7149 | 0.0166 | 29 | 0 OOS windows had trades |
| BRITANNIA | GO | NO-GO | YES | 11 | 11 | 7.5772 | -93.6095 | 0.1479 | -4.4683 | 0.0327 | 23 | 0 OOS windows had trades |
| CIPLA | GO | GO | NO | 18 | 18 | 233.3565 | 64.9380 | 1.2388 | 3.9754 | 0.1605 | 30 | 0 OOS windows had trades |
| DIVISLAB | NO-GO | NO-GO | NO | 20 | 20 | -107.6020 | -217.5346 | 0.3116 | -3.2667 | 0.3928 | 36 | 0 OOS windows had trades |
| DRREDDY | GO | GO | NO | 12 | 12 | 509.4843 | 153.0158 | 1.3547 | 3.2615 | 0.1795 | 18 | 0 OOS windows had trades |
| EICHERMOT | GO | GO | NO | 10 | 10 | 428.3945 | 88.5130 | 1.2748 | 5.9213 | 0.0921 | 24 | 0 OOS windows had trades |
| GRASIM | NO-GO | NO-GO | NO | 11 | 11 | -51.3320 | -181.3606 | 0.2187 | -6.2699 | 0.1634 | 26 | 0 OOS windows had trades |
| HDFCBANK | INSUFF | INSUFF | NO | 8 | 8 | 633.3750 | 289.7901 | 1.6556 | 6.2615 | 0.1663 | 22 | 0 OOS windows had trades |
| HDFCLIFE | NO-GO | NO-GO | NO | 10 | 10 | -174.1220 | -266.4799 | 0.0278 | -10.0091 | 0.2308 | 25 | 0 OOS windows had trades |
| HEROMOTOCO | GO | NO-GO | YES | 11 | 11 | 63.7770 | -26.9410 | 0.7278 | 3.9417 | 0.0198 | 29 | 0 OOS windows had trades |
| HINDALCO | INSUFF | INSUFF | NO | 7 | 7 | 710.1500 | 344.7975 | 1.3693 | 3.7051 | 0.5854 | 9 | 0 OOS windows had trades |
| HINDUNILVR | INSUFF | INSUFF | NO | 2 | 2 | 383.6250 | -241.4899 | 0.4936 | 3.9059 | 0.0234 | 7 | 0 OOS windows had trades |
| ICICIBANK | INSUFF | INSUFF | NO | 6 | 6 | 27.8125 | -142.6882 | 0.3224 | -1.2410 | 0.0523 | 25 | 0 OOS windows had trades |
| INDUSINDBK | NO-GO | NO-GO | NO | 11 | 11 | -5.1909 | -255.2488 | 0.2860 | -4.4064 | 0.2592 | 13 | 0 OOS windows had trades |
| INFY | NO-GO | NO-GO | NO | 13 | 13 | -102.0692 | -278.4948 | 0.2434 | -6.2118 | 0.2945 | 24 | 0 OOS windows had trades |
| JSWSTEEL | GO | GO | NO | 18 | 18 | 485.6069 | 268.5043 | 1.7222 | 3.8351 | 0.1651 | 28 | 0 OOS windows had trades |
| KOTAKBANK | INSUFF | INSUFF | NO | 9 | 9 | -255.8002 | -674.2253 | 0.1458 | -7.5219 | 0.4964 | 13 | 0 OOS windows had trades |
| LT | GO | GO | NO | 15 | 15 | 309.9530 | 220.4927 | 3.0963 | 6.2101 | 0.0631 | 26 | 0 OOS windows had trades |
| M&M | GO | NO-GO | YES | 15 | 15 | 28.6268 | -83.4416 | 0.4698 | -1.1536 | 0.0979 | 30 | 0 OOS windows had trades |
| MARUTI | INSUFF | INSUFF | NO | 9 | 9 | 36.2271 | -88.8243 | 0.2568 | -1.3954 | 0.0260 | 20 | 0 OOS windows had trades |
| NESTLEIND | INSUFF | INSUFF | NO | 4 | 4 | 123.2428 | -157.1517 | 0.2084 | 0.8562 | 0.0148 | 13 | 0 OOS windows had trades |
| SBILIFE | GO | NO-GO | YES | 14 | 14 | 3.3224 | -165.5803 | 0.3615 | -2.6447 | 0.1673 | 23 | 0 OOS windows had trades |
| SBIN | INSUFF | INSUFF | NO | 5 | 5 | -434.8200 | -727.7595 | 0.0000 | -20.0743 | 0.2593 | 12 | 0 OOS windows had trades |
| SUNPHARMA | GO | NO-GO | YES | 12 | 12 | 57.1240 | -70.9271 | 0.5581 | 0.7106 | 0.0459 | 26 | 0 OOS windows had trades |
| TATACONSUM | GO | GO | NO | 10 | 10 | 203.9700 | 128.7080 | 2.9018 | 7.3740 | 0.0192 | 30 | 0 OOS windows had trades |
| TCS | GO | NO-GO | YES | 16 | 16 | 84.1697 | -25.8111 | 0.8393 | 2.7116 | 0.1094 | 35 | 0 OOS windows had trades |
| TECHM | NO-GO | NO-GO | NO | 21 | 21 | -0.5071 | -59.6311 | 0.4895 | -1.9440 | 0.1310 | 34 | 0 OOS windows had trades |
| TITAN | NO-GO | NO-GO | NO | 10 | 10 | -80.7455 | -309.6949 | 0.2529 | -6.1555 | 0.3196 | 19 | 0 OOS windows had trades |
| ULTRACEMCO | INSUFF | INSUFF | NO | 7 | 7 | 120.0296 | -42.2949 | 0.6820 | 5.0515 | 0.0211 | 20 | 0 OOS windows had trades |
| WIPRO | GO | NO-GO | YES | 12 | 12 | 132.3812 | -70.8565 | 0.6639 | 2.9545 | 0.0434 | 24 | 0 OOS windows had trades |

### volatility_breakout_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIPORTS | INSUFF | INSUFF | NO | 2 | 1 | -5143.3000 | -11172.0859 | 0.0000 | — | 1.2071 | 25 | 0 OOS windows had trades |
| APOLLOHOSP | INSUFF | INSUFF | NO | 7 | 6 | 17.1352 | -76.5916 | 0.5091 | -0.2480 | 0.0475 | 29 | 0 OOS windows had trades |
| ASIANPAINT | INSUFF | INSUFF | NO | 3 | 3 | -1.4333 | -471.2517 | 0.2644 | -3.9983 | 0.1323 | 23 | 0 OOS windows had trades |
| BAJAJ-AUTO | INSUFF | INSUFF | NO | 2 | 2 | 123.6504 | 20.3698 | 1.3042 | 9.5613 | 0.0014 | 17 | 0 OOS windows had trades |
| BAJAJFINSV | INSUFF | INSUFF | NO | 5 | 5 | 1049.7899 | 660.1942 | 3.6920 | 14.8512 | 0.0000 | 33 | 0 OOS windows had trades |
| BAJFINANCE | INSUFF | INSUFF | NO | 1 | 1 | 1245.9750 | 820.3068 | 4.3186 | — | 0.0000 | 14 | 0 OOS windows had trades |
| BHARTIARTL | INSUFF | INSUFF | NO | 4 | 4 | 193.8250 | 85.3529 | 2.2841 | 7.8738 | 0.0012 | 29 | 0 OOS windows had trades |
| BRITANNIA | INSUFF | INSUFF | NO | 6 | 6 | -91.0677 | -240.0806 | 0.1583 | -4.7116 | 0.0979 | 23 | 0 OOS windows had trades |
| CIPLA | INSUFF | INSUFF | NO | 5 | 5 | 352.7600 | 230.4460 | 3.3276 | 9.7407 | 0.0143 | 30 | 0 OOS windows had trades |
| DIVISLAB | INSUFF | INSUFF | NO | 3 | 3 | 138.4011 | -284.9574 | 0.0926 | -4.8465 | 0.0214 | 36 | 0 OOS windows had trades |
| DRREDDY | INSUFF | INSUFF | NO | 3 | 3 | 1421.7333 | 1101.9126 | 6.9338 | 14.8785 | 0.0000 | 18 | 0 OOS windows had trades |
| EICHERMOT | INSUFF | INSUFF | NO | 7 | 7 | 97.0009 | -71.7165 | 0.4337 | 3.9207 | 0.0103 | 24 | 0 OOS windows had trades |
| GRASIM | INSUFF | INSUFF | NO | 5 | 5 | 456.6525 | 186.7161 | 1.8890 | 11.2013 | 0.0257 | 26 | 0 OOS windows had trades |
| HDFCBANK | INSUFF | INSUFF | NO | 7 | 7 | 194.3893 | -162.2535 | 0.7252 | 1.6423 | 0.1450 | 22 | 0 OOS windows had trades |
| HDFCLIFE | INSUFF | INSUFF | NO | 2 | 2 | 108.5500 | -509.3112 | 0.3689 | -2.2620 | 0.1139 | 25 | 0 OOS windows had trades |
| HEROMOTOCO | INSUFF | INSUFF | NO | 1 | 1 | -1.0996 | -35.3000 | 0.0000 | — | 0.0015 | 29 | 0 OOS windows had trades |
| HINDUNILVR | INSUFF | INSUFF | NO | 3 | 3 | 924.7333 | 288.4853 | 1.7809 | 18.7649 | 0.0000 | 7 | 0 OOS windows had trades |
| ICICIBANK | INSUFF | INSUFF | NO | 6 | 6 | 177.9000 | -30.9890 | 0.8634 | 3.3347 | 0.0431 | 25 | 0 OOS windows had trades |
| INDUSINDBK | INSUFF | INSUFF | NO | 1 | 1 | 426.3000 | 32.3229 | 1.1413 | — | 0.0000 | 13 | 0 OOS windows had trades |
| INFY | INSUFF | INSUFF | NO | 4 | 4 | -1923.0375 | -2460.4634 | 0.0000 | -13.9797 | 1.1056 | 24 | 0 OOS windows had trades |
| JSWSTEEL | INSUFF | INSUFF | NO | 3 | 3 | -10.5667 | -82.3602 | 0.0000 | -23.9402 | 0.0115 | 28 | 0 OOS windows had trades |
| KOTAKBANK | INSUFF | INSUFF | NO | 2 | 2 | -190.7550 | -730.6588 | 0.0000 | -45.0698 | 0.0949 | 13 | 0 OOS windows had trades |
| LT | INSUFF | INSUFF | NO | 2 | 2 | 1034.4262 | 588.2927 | 3.2712 | 17.7024 | 0.0000 | 26 | 0 OOS windows had trades |
| M&M | INSUFF | INSUFF | NO | 3 | 3 | -17.5336 | -55.9545 | 0.1861 | -8.0959 | 0.0139 | 30 | 0 OOS windows had trades |
| MARUTI | INSUFF | INSUFF | NO | 3 | 3 | 196.4502 | 158.9449 | 8.2985 | 21.5793 | 0.0000 | 20 | 0 OOS windows had trades |
| NESTLEIND | INSUFF | INSUFF | NO | 2 | 2 | 680.7000 | 287.7896 | 1.9314 | 8.5464 | 0.0180 | 13 | 0 OOS windows had trades |
| SBILIFE | INSUFF | INSUFF | NO | 3 | 3 | 264.0833 | 14.2956 | 1.0805 | 6.9987 | 0.0097 | 23 | 0 OOS windows had trades |
| SBIN | INSUFF | INSUFF | NO | 2 | 2 | -29.1000 | -213.4071 | 0.0000 | -11.2250 | 0.0128 | 12 | 0 OOS windows had trades |
| SUNPHARMA | INSUFF | INSUFF | NO | 7 | 7 | 186.0500 | -195.8204 | 0.6649 | 0.3769 | 0.1767 | 26 | 0 OOS windows had trades |
| TATACONSUM | INSUFF | INSUFF | NO | 5 | 5 | 248.0100 | 141.7610 | 2.3739 | 7.0877 | 0.0207 | 30 | 0 OOS windows had trades |
| TCS | INSUFF | INSUFF | NO | 9 | 9 | -83.0610 | -193.2490 | 0.2546 | -5.6295 | 0.1673 | 35 | 0 OOS windows had trades |
| TECHM | INSUFF | INSUFF | NO | 2 | 2 | -312.0500 | -501.4614 | 0.0000 | -45.7225 | 0.0784 | 34 | 0 OOS windows had trades |
| TITAN | INSUFF | INSUFF | NO | 4 | 4 | -958.3135 | -1256.4983 | 0.0000 | -23.7863 | 0.5008 | 19 | 0 OOS windows had trades |
| ULTRACEMCO | INSUFF | INSUFF | NO | 5 | 5 | 134.1480 | -24.7826 | 0.7431 | 14.6578 | 0.0021 | 20 | 0 OOS windows had trades |
| WIPRO | INSUFF | INSUFF | NO | 4 | 4 | 198.2062 | -329.8619 | 0.5361 | -0.3959 | 0.1798 | 24 | 0 OOS windows had trades |

### volume_spike_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIPORTS | INSUFF | INSUFF | NO | 0 | 1 | — | 2120.7378 | 16.2282 | — | 0.0000 | 25 | 0 OOS windows had trades |

#### Regime: UNKNOWN

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| APOLLOHOSP | INSUFF | INSUFF | NO | 2 | 0 | -226.4298 | — | — | — | — | 0 | 0 OOS windows had trades |

---

## Notes

- **GO**: Rule has positive expectancy, profit factor > 1, and statistically significant edge at realistic costs.
- **NO-GO**: Rule fails the edge criterion at realistic costs.
- **INSUFFICIENT-DATA**: Not enough trades to make a determination (less than min_trades).
- Significance test is a one-sided sign-flip permutation test on the pooled per-trade net P&L sequence, costs applied.
- Observed regimes from the intelligence pipeline: RANGING, UNKNOWN.
- Regime detection currently falls back to RANGING for 1D-only replay: the replayed payloads carry ema_20/atr_14/rsi_14/bb_upper (no ema_50/ema_200/macd/bb_lower/avg_atr_20d/VIX), so the deterministic detect_regime classifier labels most bars RANGING. Full PatternEngine regime labels remain an outstanding item.
- This report does NOT write to RuleConfig.validated_regimes. That step requires human review.
