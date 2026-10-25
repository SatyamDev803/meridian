# Spread experiment

Testnet BTCUSD, 2 contracts per side, 15.0 minutes per run, 2 interleaved rounds. Every run ends flat: leftover inventory is closed at market and that cost is charged to the run. Fees are Delta's actual commission.

Edge at fill is how far inside fair value we traded. Markout is the same measure 5s and 30s later. Adverse selection is edge minus the 30s markout.

| Spread bps | Round | Minutes | Fills | Fills per hour | Maker share | Edge at fill bps | Markout 5s bps | Markout 30s bps | Adverse selection bps | Gross PnL | Fees | Net PnL (ledger) | Net PnL (wallet) | Max inventory | Max drawdown | Quoting % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2.000 | 1 | 15.200 | 21 | 82.700 | 1.000 | -0.035 | -0.668 | -0.661 | 0.626 | -0.366 | 0.683 | -1.049 | -1.049 | 4 | 1.049 | 94.792 |
| 4.000 | 1 | 15.200 | 10 | 39.400 | 1.000 | 0.024 | -0.607 | -0.529 | 0.553 | -0.040 | 0.342 | -0.382 | -0.382 | 2 | 0.382 | 97.801 |
| 8.000 | 1 | 15.200 | 0 | 0.000 | - | - | - | - | - | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0.000 | 99.798 |
| 12.000 | 1 | 15.200 | 0 | 0.000 | - | - | - | - | - | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0.000 | 99.972 |
| 2.000 | 2 | 15.100 | 16 | 63.400 | 0.938 | -0.114 | -0.354 | -0.426 | 0.312 | -0.223 | 0.565 | -0.787 | -0.787 | 3 | 0.697 | 99.205 |
| 4.000 | 2 | 15.200 | 9 | 35.400 | 0.889 | -0.071 | -0.690 | -0.740 | 0.668 | -0.050 | 0.300 | -0.349 | -0.349 | 2 | 0.314 | 98.673 |
| 8.000 | 2 | 15.200 | 0 | 0.000 | - | - | - | - | - | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0.000 | 99.972 |
| 12.000 | 2 | 15.100 | 2 | 7.900 | 0.500 | -0.315 | 0.076 | 1.128 | -1.443 | 0.001 | 0.120 | -0.120 | -0.120 | 2 | 0.238 | 99.904 |

## Totals by spread

| Spread bps | Runs | Fills | Gross PnL | Fees | Net PnL (wallet) | Net per fill |
|---|---|---|---|---|---|---|
| 2 | 2 | 37 | -0.5887 | 1.2474 | -1.8361 | -0.0496 |
| 4 | 2 | 19 | -0.0900 | 0.6413 | -0.7313 | -0.0385 |
| 8 | 2 | 0 | +0.0000 | 0.0000 | +0.0000 | +0.0000 |
| 12 | 2 | 2 | +0.0006 | 0.1202 | -0.1196 | -0.0598 |

## Findings

Run on 25 October 2026, 03:13 to 05:15 IST, Delta India testnet, BTCUSD perpetual.
Eight 15-minute runs, two interleaved rounds. 58 fills in total. Total cost: 2.69 USD of demo funds.

**Accounting is exact.** In all eight runs, Meridian's ledger net PnL matched the change in
Delta's wallet to the cent, using Delta's actual commission (taxes included) per fill.

**No spread made money.**

- At 2 and 4 bps Meridian traded regularly (35 to 80 fills an hour) and lost money. Spread
  captured was already slightly negative before fees, and fees were roughly twice that again.
- At 8 bps there were no fills at all in 30 minutes.
- At 12 bps there were two fills in 30 minutes: one maker fill, and the taker order that closed
  the leftover position at the end of the run.

**Why: the fills are adverse selection, not spread capture.** Edge at fill sits around zero
(between −0.3 and +0.02 bps). Meridian's quotes only trade when fair value has already moved to
them, so the counterparty is the market moving, not a trader paying the spread. Thirty seconds
later the price has moved a further 0.4 to 0.7 bps against the position. Against that, a maker
round trip costs about 4.2 bps in fees with tax. There is no setting in this range where the
captured spread covers both.

**What this says about the testnet.** Flow on the testnet book appears to be dominated by other
bots and price-tracking activity rather than by traders crossing the spread. A spread wide enough
to cover fees is not reached by anyone; a spread narrow enough to trade is only reached when the
price is moving through it.

**What would have to change for positive expectancy** (not yet tested):

1. A better fair value. Near-zero edge at fill means Meridian's fair value lags the moves that
   fill it. Compare runs with the Binance drift on and off, and try a short-horizon momentum term.
2. Asymmetric quoting: lean the quotes with short-term direction, not only with inventory.
3. Lower costs: maker rebates or a fee tier where a round trip costs less than the spread captured.
4. Real flow: the same measurement on a venue or product where uninformed traders cross the spread.

Sample size caveat: 58 fills over two hours on one testnet afternoon. The direction of the result
is clear for 2 and 4 bps; the 8 and 12 bps rows say only that they rarely trade.
