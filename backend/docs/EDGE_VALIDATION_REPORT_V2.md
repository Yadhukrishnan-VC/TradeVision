# Edge Validation Report V2 — TradeVision

**Generated:** 2026-08-21T00:36:51.298005+00:00

**Symbols analyzed:** 47 (ADANIENT, ADANIPORTS, APOLLOHOSP, ASIANPAINT, AXISBANK, BAJAJ-AUTO, BAJAJFINSV, BAJFINANCE, BHARTIARTL, BPCL, BRITANNIA, CIPLA, COALINDIA, DIVISLAB, DRREDDY, EICHERMOT, GRASIM, HDFCBANK, HDFCLIFE, HEROMOTOCO, HINDALCO, HINDUNILVR, ICICIBANK, INDUSINDBK, INFY, ITC, JSWSTEEL, KOTAKBANK, LT, M&M, MARUTI, NESTLEIND, NTPC, ONGC, POWERGRID, RELIANCE, SBILIFE, SBIN, SUNPHARMA, TATACONSUM, TATASTEEL, TCS, TECHM, TITAN, ULTRACEMCO, UPL, WIPRO)
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
| breakout_v1 | RANGING | **GO** | 45 | 369 | 132.8928 | 0.0010 | YES |
| high_beta_breakout_v1 | RANGING | **INSUFFICIENT-DATA** | 2 | 2 | 97.9473 | — | N/A |
| price_movement_v1 | RANGING | **NO-GO** | 45 | 585 | 9.2513 | 0.4016 | NO |
| volatility_breakout_v1 | RANGING | **INSUFFICIENT-DATA** | 42 | 155 | -28.3643 | 0.5804 | NO |
| volume_spike_v1 | RANGING | **INSUFFICIENT-DATA** | 2 | 3 | 106.1392 | — | N/A |
| volume_spike_v1 | UNKNOWN | **INSUFFICIENT-DATA** | 2 | 0 | — | — | N/A |

---

## Per-Symbol Detail

### breakout_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| APOLLOHOSP | INSUFF | INSUFF | NO | 0 | 9 | — | -31.3057 | 0.7735 | 2.0151 | 0.0340 | 29 | — |
| ASIANPAINT | INSUFF | INSUFF | NO | 6 | 6 | 336.4498 | -6.3886 | 0.9720 | 7.1108 | 0.0113 | 23 | — |
| AXISBANK | INSUFF | INSUFF | NO | 2 | 2 | 1335.0000 | 834.2417 | 3.8694 | 13.3278 | 0.0000 | 6 | — |
| BAJAJ-AUTO | INSUFF | INSUFF | NO | 9 | 9 | -119.2280 | -365.4033 | 0.0634 | -11.1680 | 0.1994 | 17 | — |
| BAJAJFINSV | INSUFF | INSUFF | NO | 1 | 1 | 819.0000 | 331.2482 | 2.1697 | — | 0.0000 | 33 | — |
| BAJFINANCE | INSUFF | INSUFF | NO | 4 | 4 | -86.8388 | -542.4388 | 0.0827 | -7.9858 | 0.1521 | 14 | — |
| BHARTIARTL | GO | NO-GO | YES | 21 | 21 | 48.0208 | -61.7148 | 0.6237 | 0.4371 | 0.1791 | 29 | — |
| BPCL | GO | GO | NO | 15 | 15 | 288.7170 | 155.9323 | 2.2548 | 6.6202 | 0.0387 | 31 | — |
| BRITANNIA | INSUFF | INSUFF | NO | 6 | 6 | 49.3249 | -72.1130 | 0.4692 | -0.1308 | 0.0391 | 23 | — |
| CIPLA | INSUFF | INSUFF | NO | 7 | 7 | 261.5500 | 98.3180 | 1.4559 | 6.6055 | 0.0622 | 30 | — |
| COALINDIA | GO | GO | NO | 19 | 19 | 259.2658 | 121.2590 | 2.4132 | 11.2779 | 0.0046 | 31 | — |
| DIVISLAB | GO | NO-GO | YES | 13 | 13 | 185.2886 | -65.2321 | 0.6786 | 6.2658 | 0.0700 | 36 | — |
| DRREDDY | INSUFF | INSUFF | NO | 3 | 3 | 557.8833 | 243.9167 | 1.9839 | 7.4467 | 0.0118 | 18 | — |
| EICHERMOT | INSUFF | INSUFF | NO | 7 | 7 | 340.0205 | 172.3656 | 2.5050 | 11.2293 | 0.0107 | 24 | — |
| GRASIM | GO | NO-GO | YES | 10 | 10 | 91.6840 | -17.0281 | 0.8568 | 4.9650 | 0.0256 | 26 | — |
| HDFCBANK | INSUFF | INSUFF | NO | 7 | 7 | 338.4607 | -146.4542 | 0.8188 | 1.2489 | 0.3043 | 22 | — |
| HDFCLIFE | GO | NO-GO | YES | 13 | 13 | 81.4346 | -137.8931 | 0.5777 | 1.2525 | 0.1768 | 25 | — |
| HEROMOTOCO | NO-GO | NO-GO | NO | 17 | 17 | -9.4994 | -98.3818 | 0.3426 | -1.9642 | 0.0847 | 29 | — |
| HINDALCO | INSUFF | INSUFF | NO | 2 | 2 | 243.0750 | -147.3136 | 0.5589 | 3.0321 | 0.0250 | 9 | — |
| HINDUNILVR | INSUFF | INSUFF | NO | 2 | 2 | -637.0000 | -892.2544 | 0.0000 | -11.2250 | 0.0808 | 7 | — |
| ICICIBANK | GO | NO-GO | YES | 13 | 13 | 66.1092 | -70.9382 | 0.6913 | 0.5438 | 0.1815 | 25 | — |
| INDUSINDBK | INSUFF | INSUFF | NO | 1 | 1 | 201.6500 | 11.8260 | 1.1073 | — | 0.0000 | 13 | — |
| INFY | INSUFF | INSUFF | NO | 7 | 7 | 223.0571 | -163.0253 | 0.6632 | 1.3591 | 0.1295 | 24 | — |
| ITC | GO | GO | NO | 10 | 10 | 523.2733 | 263.5384 | 2.4331 | 8.1798 | 0.0260 | 32 | — |
| JSWSTEEL | INSUFF | INSUFF | NO | 7 | 7 | -74.4000 | -129.3187 | 0.4635 | -1.3564 | 0.0809 | 28 | — |
| KOTAKBANK | INSUFF | INSUFF | NO | 2 | 2 | 1305.0150 | 545.0820 | 2.2354 | 87.9543 | 0.0000 | 13 | — |
| LT | INSUFF | INSUFF | NO | 9 | 9 | 887.8289 | 652.2799 | 4.3690 | 7.9901 | 0.0499 | 26 | — |
| M&M | NO-GO | NO-GO | NO | 12 | 12 | -124.7863 | -212.2101 | 0.4170 | -1.9972 | 0.2867 | 30 | — |
| MARUTI | INSUFF | INSUFF | NO | 8 | 8 | 91.9591 | -107.1979 | 0.5287 | 0.8028 | 0.0409 | 20 | — |
| NESTLEIND | INSUFF | INSUFF | NO | 7 | 7 | 116.0639 | -127.0393 | 0.4289 | 0.9368 | 0.0635 | 13 | — |
| NTPC | GO | GO | NO | 13 | 13 | 362.4526 | 229.4996 | 2.1728 | 4.9373 | 0.1073 | 29 | — |
| ONGC | GO | GO | NO | 11 | 11 | 516.5091 | 311.8643 | 3.2021 | 9.7026 | 0.0169 | 36 | — |
| POWERGRID | INSUFF | INSUFF | NO | 6 | 6 | 829.1333 | 413.7179 | 2.1608 | 9.4635 | 0.0696 | 6 | — |
| RELIANCE | INSUFF | INSUFF | NO | 2 | 1 | 407.0500 | 248.7559 | 2.0745 | — | 0.0000 | 33 | — |
| SBILIFE | INSUFF | INSUFF | NO | 6 | 6 | -6.8000 | -246.6677 | 0.2150 | -4.0660 | 0.0396 | 23 | — |
| SBIN | INSUFF | INSUFF | NO | 5 | 5 | 270.7450 | -23.9729 | 0.9492 | 2.9624 | 0.0941 | 12 | — |
| SUNPHARMA | INSUFF | INSUFF | NO | 7 | 7 | 66.7786 | -82.7012 | 0.3210 | 0.5961 | 0.0181 | 26 | — |
| TATACONSUM | NO-GO | NO-GO | NO | 15 | 15 | -112.5848 | -208.0670 | 0.3210 | -2.3680 | 0.3134 | 30 | — |
| TATASTEEL | INSUFF | INSUFF | NO | 3 | 3 | 1329.7500 | 804.1929 | 3.1494 | 9.1444 | 0.0206 | 3 | — |
| TCS | NO-GO | NO-GO | NO | 10 | 10 | -69.3336 | -291.9699 | 0.2029 | -5.4404 | 0.1576 | 35 | — |
| TECHM | GO | NO-GO | YES | 11 | 11 | 159.9591 | -104.2175 | 0.6301 | 1.6815 | 0.1340 | 34 | — |
| TITAN | INSUFF | INSUFF | NO | 5 | 5 | 20.7014 | -446.5043 | 0.3266 | -3.2046 | 0.2262 | 19 | — |
| ULTRACEMCO | INSUFF | INSUFF | NO | 8 | 8 | 285.7442 | 6.2788 | 1.0299 | 5.5250 | 0.0275 | 20 | — |
| UPL | GO | GO | NO | 11 | 11 | 616.7182 | 301.1358 | 2.3275 | 15.3847 | 0.0432 | 30 | — |
| WIPRO | INSUFF | INSUFF | NO | 8 | 8 | 180.2050 | -158.8402 | 0.6519 | 0.7113 | 0.2311 | 24 | — |

### high_beta_breakout_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIENT | INSUFF | INSUFF | NO | 0 | 1 | — | 84.6973 | 1.6871 | — | 0.0000 | 43 | — |
| RELIANCE | INSUFF | INSUFF | NO | 0 | 1 | — | -57.0085 | 0.0000 | — | 0.0012 | 33 | — |

### price_movement_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIENT | GO | GO | NO | 39 | 39 | 94.3460 | 71.9863 | 1.1530 | 1.9673 | 0.6590 | 43 | — |
| ADANIPORTS | NO-GO | NO-GO | NO | 23 | 23 | -67.0759 | -436.9068 | 0.3045 | -4.5636 | 0.7429 | 25 | — |
| APOLLOHOSP | GO | NO-GO | YES | 20 | 14 | 13.3937 | -248.0309 | 0.1089 | -9.9751 | 0.2022 | 29 | — |
| ASIANPAINT | GO | NO-GO | YES | 14 | 14 | 115.0979 | -197.9599 | 0.5166 | 0.1869 | 0.1450 | 23 | — |
| AXISBANK | INSUFF | INSUFF | NO | 4 | 4 | 145.3125 | -146.9942 | 0.9537 | 2.5908 | 0.0986 | 6 | — |
| BAJAJ-AUTO | INSUFF | INSUFF | NO | 6 | 6 | 62.5500 | -2.7244 | 0.9409 | 9.2329 | 0.0037 | 17 | — |
| BAJAJFINSV | NO-GO | NO-GO | NO | 27 | 27 | -80.1732 | -289.9354 | 0.2948 | -4.3257 | 0.7094 | 33 | — |
| BAJFINANCE | INSUFF | INSUFF | NO | 9 | 9 | -74.2733 | -445.2228 | 0.4636 | -2.9139 | 0.6437 | 14 | — |
| BHARTIARTL | INSUFF | INSUFF | NO | 4 | 4 | -52.3375 | -47.9739 | 0.1809 | -6.7149 | 0.0166 | 29 | — |
| BPCL | NO-GO | NO-GO | NO | 14 | 14 | -74.9618 | -189.0420 | 0.1846 | -5.7176 | 0.1884 | 31 | — |
| BRITANNIA | GO | NO-GO | YES | 11 | 11 | 7.5772 | -93.6095 | 0.1479 | -4.4683 | 0.0327 | 23 | — |
| CIPLA | GO | GO | NO | 18 | 18 | 233.3565 | 64.9380 | 1.2388 | 3.9754 | 0.1605 | 30 | — |
| COALINDIA | GO | NO-GO | YES | 12 | 12 | 103.5167 | -23.1270 | 0.8710 | 1.6521 | 0.0956 | 31 | — |
| DIVISLAB | NO-GO | NO-GO | NO | 20 | 20 | -107.6020 | -217.5346 | 0.3116 | -3.2667 | 0.3928 | 36 | — |
| DRREDDY | GO | GO | NO | 12 | 12 | 509.4843 | 153.0158 | 1.3547 | 3.2615 | 0.1795 | 18 | — |
| EICHERMOT | GO | GO | NO | 10 | 10 | 428.3945 | 88.5130 | 1.2748 | 5.9213 | 0.0921 | 24 | — |
| GRASIM | NO-GO | NO-GO | NO | 11 | 11 | -51.3320 | -181.3606 | 0.2187 | -6.2699 | 0.1634 | 26 | — |
| HDFCBANK | INSUFF | INSUFF | NO | 8 | 8 | 633.3750 | 289.7901 | 1.6556 | 6.2615 | 0.1663 | 22 | — |
| HDFCLIFE | NO-GO | NO-GO | NO | 10 | 10 | -174.1220 | -266.4799 | 0.0278 | -10.0091 | 0.2308 | 25 | — |
| HEROMOTOCO | GO | NO-GO | YES | 11 | 11 | 63.7770 | -26.9410 | 0.7278 | 3.9417 | 0.0198 | 29 | — |
| HINDALCO | INSUFF | INSUFF | NO | 7 | 7 | 710.1500 | 344.7975 | 1.3693 | 3.7051 | 0.5854 | 9 | — |
| HINDUNILVR | INSUFF | INSUFF | NO | 2 | 2 | 383.6250 | -241.4899 | 0.4936 | 3.9059 | 0.0234 | 7 | — |
| ICICIBANK | INSUFF | INSUFF | NO | 6 | 6 | 27.8125 | -142.6882 | 0.3224 | -1.2410 | 0.0523 | 25 | — |
| INDUSINDBK | NO-GO | NO-GO | NO | 11 | 11 | -5.1909 | -255.2488 | 0.2860 | -4.4064 | 0.2592 | 13 | — |
| INFY | NO-GO | NO-GO | NO | 13 | 13 | -102.0692 | -278.4948 | 0.2434 | -6.2118 | 0.2945 | 24 | — |
| ITC | NO-GO | NO-GO | NO | 15 | 15 | -47.3588 | -106.0266 | 0.4095 | -2.6487 | 0.1810 | 32 | — |
| JSWSTEEL | GO | GO | NO | 18 | 18 | 485.6069 | 268.5043 | 1.7222 | 3.8351 | 0.1651 | 28 | — |
| KOTAKBANK | INSUFF | INSUFF | NO | 9 | 9 | -255.8002 | -674.2253 | 0.1458 | -7.5219 | 0.4964 | 13 | — |
| LT | GO | GO | NO | 15 | 15 | 309.9530 | 220.4927 | 3.0963 | 6.2101 | 0.0631 | 26 | — |
| M&M | GO | NO-GO | YES | 15 | 15 | 28.6268 | -83.4416 | 0.4698 | -1.1536 | 0.0979 | 30 | — |
| MARUTI | INSUFF | INSUFF | NO | 9 | 9 | 36.2271 | -88.8243 | 0.2568 | -1.3954 | 0.0260 | 20 | — |
| NESTLEIND | INSUFF | INSUFF | NO | 4 | 4 | 123.2428 | -157.1517 | 0.2084 | 0.8562 | 0.0148 | 13 | — |
| NTPC | GO | GO | NO | 14 | 14 | 99.1393 | 47.8803 | 1.4282 | 4.3088 | 0.0740 | 29 | — |
| ONGC | GO | NO-GO | YES | 22 | 22 | 23.5505 | -120.4344 | 0.5070 | -1.2275 | 0.2371 | 36 | — |
| RELIANCE | GO | NO-GO | YES | 25 | 25 | 83.6813 | -17.9570 | 0.8444 | 1.9565 | 0.0723 | 33 | — |
| SBILIFE | GO | NO-GO | YES | 14 | 14 | 3.3224 | -165.5803 | 0.3615 | -2.6447 | 0.1673 | 23 | — |
| SBIN | INSUFF | INSUFF | NO | 5 | 5 | -434.8200 | -727.7595 | 0.0000 | -20.0743 | 0.2593 | 12 | — |
| SUNPHARMA | GO | NO-GO | YES | 12 | 12 | 57.1240 | -70.9271 | 0.5581 | 0.7106 | 0.0459 | 26 | — |
| TATACONSUM | GO | GO | NO | 10 | 10 | 203.9700 | 128.7080 | 2.9018 | 7.3740 | 0.0192 | 30 | — |
| TCS | GO | NO-GO | YES | 16 | 16 | 84.1697 | -25.8111 | 0.8393 | 2.7116 | 0.1094 | 35 | — |
| TECHM | NO-GO | NO-GO | NO | 21 | 21 | -0.5071 | -59.6311 | 0.4895 | -1.9440 | 0.1310 | 34 | — |
| TITAN | NO-GO | NO-GO | NO | 10 | 10 | -80.7455 | -309.6949 | 0.2529 | -6.1555 | 0.3196 | 19 | — |
| ULTRACEMCO | INSUFF | INSUFF | NO | 7 | 7 | 120.0296 | -42.2949 | 0.6820 | 5.0515 | 0.0211 | 20 | — |
| UPL | NO-GO | NO-GO | NO | 16 | 16 | -310.0547 | -430.7320 | 0.0440 | -8.5728 | 0.5487 | 30 | — |
| WIPRO | GO | NO-GO | YES | 12 | 12 | 132.3812 | -70.8565 | 0.6639 | 2.9545 | 0.0434 | 24 | — |

### volatility_breakout_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIENT | INSUFF | INSUFF | NO | 1 | 1 | 680.4054 | 253.2875 | 2.0214 | — | 0.0000 | 43 | — |
| ADANIPORTS | INSUFF | INSUFF | NO | 2 | 1 | -5143.3000 | -11172.0859 | 0.0000 | — | 1.2071 | 25 | — |
| APOLLOHOSP | INSUFF | INSUFF | NO | 7 | 6 | 17.1352 | -76.5916 | 0.5091 | -0.2480 | 0.0475 | 29 | — |
| ASIANPAINT | INSUFF | INSUFF | NO | 3 | 3 | -1.4333 | -471.2517 | 0.2644 | -3.9983 | 0.1323 | 23 | — |
| BAJAJ-AUTO | INSUFF | INSUFF | NO | 2 | 2 | 123.6504 | 20.3698 | 1.3042 | 9.5613 | 0.0014 | 17 | — |
| BAJAJFINSV | INSUFF | INSUFF | NO | 5 | 5 | 1049.7899 | 660.1942 | 3.6920 | 14.8512 | 0.0000 | 33 | — |
| BAJFINANCE | INSUFF | INSUFF | NO | 1 | 1 | 1245.9750 | 820.3068 | 4.3186 | — | 0.0000 | 14 | — |
| BHARTIARTL | INSUFF | INSUFF | NO | 4 | 4 | 193.8250 | 85.3529 | 2.2841 | 7.8738 | 0.0012 | 29 | — |
| BPCL | INSUFF | INSUFF | NO | 2 | 2 | 1271.5875 | 972.3340 | 6.4496 | 11.1343 | 0.0009 | 31 | — |
| BRITANNIA | INSUFF | INSUFF | NO | 6 | 6 | -91.0677 | -240.0806 | 0.1583 | -4.7116 | 0.0979 | 23 | — |
| CIPLA | INSUFF | INSUFF | NO | 5 | 5 | 352.7600 | 230.4460 | 3.3276 | 9.7407 | 0.0143 | 30 | — |
| DIVISLAB | INSUFF | INSUFF | NO | 3 | 3 | 138.4011 | -284.9574 | 0.0926 | -4.8465 | 0.0214 | 36 | — |
| DRREDDY | INSUFF | INSUFF | NO | 3 | 3 | 1421.7333 | 1101.9126 | 6.9338 | 14.8785 | 0.0000 | 18 | — |
| EICHERMOT | INSUFF | INSUFF | NO | 7 | 7 | 97.0009 | -71.7165 | 0.4337 | 3.9207 | 0.0103 | 24 | — |
| GRASIM | INSUFF | INSUFF | NO | 5 | 5 | 456.6525 | 186.7161 | 1.8890 | 11.2013 | 0.0257 | 26 | — |
| HDFCBANK | INSUFF | INSUFF | NO | 7 | 7 | 194.3893 | -162.2535 | 0.7252 | 1.6423 | 0.1450 | 22 | — |
| HDFCLIFE | INSUFF | INSUFF | NO | 2 | 2 | 108.5500 | -509.3112 | 0.3689 | -2.2620 | 0.1139 | 25 | — |
| HEROMOTOCO | INSUFF | INSUFF | NO | 1 | 1 | -1.0996 | -35.3000 | 0.0000 | — | 0.0015 | 29 | — |
| HINDUNILVR | INSUFF | INSUFF | NO | 3 | 3 | 924.7333 | 288.4853 | 1.7809 | 18.7649 | 0.0000 | 7 | — |
| ICICIBANK | INSUFF | INSUFF | NO | 6 | 6 | 177.9000 | -30.9890 | 0.8634 | 3.3347 | 0.0431 | 25 | — |
| INDUSINDBK | INSUFF | INSUFF | NO | 1 | 1 | 426.3000 | 32.3229 | 1.1413 | — | 0.0000 | 13 | — |
| INFY | INSUFF | INSUFF | NO | 4 | 4 | -1923.0375 | -2460.4634 | 0.0000 | -13.9797 | 1.1056 | 24 | — |
| ITC | INSUFF | INSUFF | NO | 7 | 7 | 236.6226 | -10.3984 | 0.9286 | 13.5724 | 0.0015 | 32 | — |
| JSWSTEEL | INSUFF | INSUFF | NO | 3 | 3 | -10.5667 | -82.3602 | 0.0000 | -23.9402 | 0.0115 | 28 | — |
| KOTAKBANK | INSUFF | INSUFF | NO | 2 | 2 | -190.7550 | -730.6588 | 0.0000 | -45.0698 | 0.0949 | 13 | — |
| LT | INSUFF | INSUFF | NO | 2 | 2 | 1034.4262 | 588.2927 | 3.2712 | 17.7024 | 0.0000 | 26 | — |
| M&M | INSUFF | INSUFF | NO | 3 | 3 | -17.5336 | -55.9545 | 0.1861 | -8.0959 | 0.0139 | 30 | — |
| MARUTI | INSUFF | INSUFF | NO | 3 | 3 | 196.4502 | 158.9449 | 8.2985 | 21.5793 | 0.0000 | 20 | — |
| NESTLEIND | INSUFF | INSUFF | NO | 2 | 2 | 680.7000 | 287.7896 | 1.9314 | 8.5464 | 0.0180 | 13 | — |
| NTPC | INSUFF | INSUFF | NO | 2 | 2 | -195.2250 | -314.7300 | 0.0000 | -33.1974 | 0.0482 | 29 | — |
| ONGC | INSUFF | INSUFF | NO | 3 | 3 | -126.3700 | -292.8559 | 0.0658 | -7.9023 | 0.0592 | 36 | — |
| RELIANCE | INSUFF | INSUFF | NO | 4 | 6 | 687.5438 | 225.3976 | 2.4900 | 6.2117 | 0.0094 | 33 | — |
| SBILIFE | INSUFF | INSUFF | NO | 3 | 3 | 264.0833 | 14.2956 | 1.0805 | 6.9987 | 0.0097 | 23 | — |
| SBIN | INSUFF | INSUFF | NO | 2 | 2 | -29.1000 | -213.4071 | 0.0000 | -11.2250 | 0.0128 | 12 | — |
| SUNPHARMA | INSUFF | INSUFF | NO | 7 | 7 | 186.0500 | -195.8204 | 0.6649 | 0.3769 | 0.1767 | 26 | — |
| TATACONSUM | INSUFF | INSUFF | NO | 5 | 5 | 248.0100 | 141.7610 | 2.3739 | 7.0877 | 0.0207 | 30 | — |
| TCS | INSUFF | INSUFF | NO | 9 | 9 | -83.0610 | -193.2490 | 0.2546 | -5.6295 | 0.1673 | 35 | — |
| TECHM | INSUFF | INSUFF | NO | 2 | 2 | -312.0500 | -501.4614 | 0.0000 | -45.7225 | 0.0784 | 34 | — |
| TITAN | INSUFF | INSUFF | NO | 4 | 4 | -958.3135 | -1256.4983 | 0.0000 | -23.7863 | 0.5008 | 19 | — |
| ULTRACEMCO | INSUFF | INSUFF | NO | 5 | 5 | 134.1480 | -24.7826 | 0.7431 | 14.6578 | 0.0021 | 20 | — |
| UPL | INSUFF | INSUFF | NO | 3 | 3 | -918.5833 | -1083.8275 | 0.0269 | -9.0997 | 0.3271 | 30 | — |
| WIPRO | INSUFF | INSUFF | NO | 4 | 4 | 198.2062 | -329.8619 | 0.5361 | -0.3959 | 0.1798 | 24 | — |

### volume_spike_v1

#### Regime: RANGING

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| ADANIENT | INSUFF | INSUFF | NO | 3 | 2 | 2285.6499 | -1199.2656 | 0.0000 | -29.1604 | 0.2113 | 43 | — |
| ADANIPORTS | INSUFF | INSUFF | NO | 0 | 1 | — | 2120.7378 | 16.2282 | — | 0.0000 | 25 | — |

#### Regime: UNKNOWN

| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | Trades (Real) | Expectancy (Base) | Expectancy (Real) | Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | Regime Trades | WF OOS Mean |
|--------|---------------|----------------|---------|---------------|---------------|-------------------|-------------------|---------------------|---------------|---------------|--------------|--------------|
| APOLLOHOSP | INSUFF | INSUFF | NO | 2 | 0 | -226.4298 | — | — | — | — | 0 | — |
| RELIANCE | INSUFF | INSUFF | NO | 2 | 0 | -131.9500 | — | — | — | — | 0 | — |

---

## Notes

- **GO**: Rule has positive expectancy, profit factor > 1, and statistically significant edge at realistic costs.
- **NO-GO**: Rule fails the edge criterion at realistic costs.
- **INSUFFICIENT-DATA**: Not enough trades to make a determination (less than min_trades).
- Significance test is a one-sided sign-flip permutation test on the pooled per-trade net P&L sequence, costs applied.
- Observed regimes from the intelligence pipeline: RANGING, UNKNOWN.
- Regime detection currently falls back to RANGING for 1D-only replay: the replayed payloads carry ema_20/atr_14/rsi_14/bb_upper (no ema_50/ema_200/macd/bb_lower/avg_atr_20d/VIX), so the deterministic detect_regime classifier labels most bars RANGING. Full PatternEngine regime labels remain an outstanding item.
- This report does NOT write to RuleConfig.validated_regimes. That step requires human review.
