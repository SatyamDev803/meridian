# Meridian: pitch and demo script

## One line

Meridian is an adaptive market-making engine for the Delta Exchange testnet. It combines
reference-price quoting, inventory-aware pricing and automated risk controls. Its execution and
recovery paths are tested against injected failures, and its performance is measured honestly:
Delta's actual fees, spread captured, inventory exposure and adverse selection, reconciled
against the exchange wallet.

What we do not claim: that it is already a profitable market maker. We claim we can explain,
with exchange-verified numbers, why it made or lost money at each spread.

## Why a market maker

Most algo bots guess direction with an indicator. A market maker does not bet on direction. It
earns the spread and manages inventory risk, which is what exchanges pay real firms to do. This
is the loop I worked with in market-making operations: quote the venue, hedge or skew inventory,
reconcile everything, and stop on bad data.

## How it maps to the judging criteria

| Criterion | Weight | What to show |
|---|---|---|
| Strategy logic | 30% | Fair value from Delta's mark price plus Binance drift. Inventory skew (Avellaneda-Stoikov idea). Learned basis that ignores shocks. Spread chosen from a measured experiment, not a guess. |
| Risk management | 20% | Twelve live gates, each with a named action. Inventory limit goes reduce-only. Loss limit flattens and halts. |
| Technical code | 20% | Own signed Delta client, `ob_updates` book with sequence and CRC32 checksum, async engine, Decimal everywhere, 107 tests including a full engine test against a fake exchange, plus live end-to-end runs on the Delta demo account. |
| Automation | 15% | Hands-off: reconnects, resyncs, requotes, reconciles and heartbeats on its own. Optional auto-start. |
| Demo | 15% | Live dashboard, chaos buttons, kill switch, dead man's switch. |
| Bonus | | Dashboard, Render deployment, fail-safes. |

## Five-minute demo

**0:00 The problem (30s).** "A market maker always shows a buy and a sell. It earns the gap, but
every fill leaves it holding inventory it did not want. Meridian solves both halves."

**0:30 Fair value (45s).** Point at the big price. "This is Delta's own mark price, nudged by how
far Binance has moved since the last mark. The learned basis is the normal gap between the two.
Disagreement is how far we are from normal right now."

**1:15 Quotes and skew (60s).** Show the green and red pills and the dashed lines on the chart.
Open Settings and raise the inventory lean, or wait for a fill. "We are long 12 contracts, so
both quotes moved down. Our ask is now the more attractive one, so we are more likely to sell and
get back to flat. That is the whole strategy: earn the spread, never let inventory run."

**2:15 Safety checks (60s).** Open Settings, Test the fail-safes, Freeze Binance. Watch "Binance
reference fresh" turn red and the quotes vanish from the book, then come back by themselves.
Then Fake a price shock: "Prices agree" turns red. "We never quote on data we cannot trust."

**3:15 Reconcile (30s).** Corrupt the ledger. Within ten seconds the activity log shows the
reconcile break and the fix. "The exchange is the source of truth for position."

**3:45 Kill switch and dead man's switch (45s).** Press Kill: everything cancelled, status
Halted. Explain: "If the server itself dies, Delta cancels our orders for us within 30 seconds,
because we stop sending heartbeats."

**4:00 The economics (30s).** Open "Where the PnL comes from". "Every fill shows its edge and
where price went 5 and 30 seconds later. Fees are Delta's actual commission, taxes included, and
the net matches the exchange wallet to the cent." Then show the spread experiment: no setting
covered fees plus adverse selection on the testnet, and the panel shows exactly where each cent went.

**4:30 Close (30s).** Health rings: quoting time, inventory headroom, loss headroom. "Full rings
mean a healthy bot. Everything you saw is code paths, not a slide."

## Questions judges might ask

**Why use Delta's mark price instead of the order book mid?**
The testnet book is thin and full of other bots, so its mid can be pushed around. Mark price is
what Delta uses to value positions and liquidations, so it is the hardest price to manipulate.

**Why Binance at all if you trade on Delta?**
Two reasons. Mark updates every 2 seconds and Binance every 100 ms, so Binance tells us where the
mark is going next. And an independent source catches a broken feed: if the two disagree beyond
their normal gap, one of them is wrong and we stop.

**How do you avoid getting picked off?**
Requote when fair value moves 1.5 bps, pull on stale or disagreeing data, widen when agreement
weakens, and post-only orders so we never cross the spread by accident.

**What stops a runaway loss?**
Inventory limit (reduce-only beyond it), session loss limit (flatten and halt), and the
exchange-side dead man's switch if our process disappears.

**What happens on a disconnect?**
The socket watchdog reconnects with backoff and jitter. The book reloads from a fresh snapshot.
Quotes are pulled until every gate is green again.

**How do you know your position is right?**
Every fill updates our ledger, and every 10 seconds we compare it with `GET /v2/positions`. A
break is checked twice and then the exchange wins.

**How do you stay inside rate limits?**
A local mirror of Delta's 20,000-unit budget at 80%, a hysteresis threshold so tiny price changes
do not cause edits, and backing off on HTTP 429. Cancels are exempt, so we can always get out.

**Is it profitable?**
Not on the testnet, and we can show exactly why. We ran 2, 4, 8 and 12 bps for 15 minutes each,
twice, interleaved. At 2 and 4 bps Meridian traded 35 to 80 times an hour and lost money; at 8 bps
it never traded; at 12 bps it traded twice. Edge at fill was about zero and prices moved 0.4 to
0.7 bps further against us within 30 seconds, while a maker round trip costs about 4.2 bps in fees
with tax. The testnet's fills come from price moving through our quotes, not from traders paying
the spread. Full report: `docs/experiments/spread-experiment-20261024-2143.md`. The next lever is
a faster fair value, because near-zero edge at fill means ours lags the moves that fill it.

**How do you know the PnL is right?**
Fees start as estimates and are replaced by Delta's actual commission from `/v2/fills`. The
session's net PnL is checked against the change in the Delta wallet balance plus unrealized PnL.
In testing the two agree to the cent.

**What would you add with more time?**
A multi-level ladder, volatility-scaled spreads, hedging inventory on a second venue, and a
backtest harness that replays recorded `ob_updates`.
