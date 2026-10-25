# Meridian

An inventory-aware market maker for Delta Exchange perpetuals, built for the Fingrad Algo
Trading Hackathon. It quotes both sides of BTCUSD on the Delta India testnet, leans its prices
away from whatever it is holding, and stops itself the moment anything looks wrong.

Everything runs through the API. No order is ever placed by hand.

## What it does

A market maker keeps a buy price and a sell price on the book at all times and earns the gap
between them. Meridian repeats four steps, four times a second:

1. **Find fair value.** Delta's own mark price is the anchor. Between mark updates (every 2s)
   it adds how far Binance has moved, so quotes never sit stale.
2. **Quote around it.** A bid below and an ask above, `spread_bps` apart, rounded to the tick.
3. **Lean against inventory.** Long inventory lowers both prices so our ask fills first and we
   drift back to flat. Short inventory raises them. At the inventory limit only the reducing
   side is quoted.
4. **Check twelve safety gates.** Any failure widens, reduces, pulls or halts. Quotes rest on
   Delta only while every gate passes.

```
Binance bookTicker ─┐
                    ├─► FairValue ─► Quoter ─► OrderManager ─► Delta REST (signed)
Delta public WS ────┘   (mark + drift,  (spread,     (diff live vs
  mark_price, ob_updates,  basis guard)   skew, tick)  desired orders)
  ticker, system_status            ▲
                                   │ RiskEngine: 12 gates, 4 times a second
Delta private WS ─► Ledger ────────┘
  orders, positions,  (avg cost, realized, unrealized)
  v2/user_trades            │
                   Reconciler (vs GET /positions every 10s)
                   Dead man's switch (POST /heartbeat every 10s)
                            │
             FastAPI: /api/state, /api/stream (SSE), /api/control/*, /api/chaos/*
                            │
             Next.js dashboard, served as static files by the same process
```

## The strategy, in numbers

```
q    = clamp(position / max_position, -1, 1)
r    = fair * (1 - q * skew_bps / 10_000)        reservation price
bid  = floor_to_tick(r * (1 - half_spread))
ask  = ceil_to_tick (r * (1 + half_spread))
```

Fair value is `mark + (binance_now - binance_at_last_mark)`, with the drift capped. Delta perp and
Binance spot normally sit a few bps apart, so Meridian learns that gap as a slow moving average
and only reacts to sudden deviations from it.

## Measuring the economics

Quoting both sides does not guarantee profit. Every fill pays a fee, and the trader on the other
side often knows something: price tends to move against a market maker right after a fill. So
Meridian measures, per session:

- **Edge at fill**: how far inside fair value we traded.
- **Markout at 5s and 30s**: the same measure against where fair value went next.
- **Adverse selection**: edge minus the 30s markout, the part of the spread the market took back.
- **Fees**: estimated at fill time, then replaced with Delta's actual commission from
  `GET /v2/fills`. Delta adds tax on top of the published rate, so estimates alone run about 6% low.
- **Net PnL, twice**: from Meridian's ledger, and from the change in Delta's wallet balance plus
  unrealized PnL. The second includes funding, so any gap between them is visible on the dashboard.

A round trip at the maker rate costs about 4.2 bps with tax, which sets the floor for the spread.

### Spread experiment

```bash
.venv/bin/python scripts/experiment.py --spreads 2,4,8,12 --minutes 15 --rounds 2
```

Each run is a fresh session at one spread. At the end of a run Meridian stops, closes leftover
inventory at market (that cost is charged to the run), waits for Delta's actual fees and wallet,
then records the results. Spreads are interleaved across rounds so no setting gets only the calm
part of the day. Reports land in `docs/experiments/` as Markdown and JSON.

## Decision log

Every place, amend and cancel is recorded with the reason the order manager chose it (no resting
order, price moved past the requote threshold, partially filled, side not wanted because of a
pause or the inventory limit) and Delta's response. Every safety pause and resume is recorded
with the failing checks and their details, and every cancel-all with its trigger.

Each record carries a snapshot of the exact values that strategy tick used: fair value, Delta
mark, Binance mid, drift, basis and disagreement; current, target and maximum inventory;
configured spread, applied half spread, inventory skew, reservation price, disagreement widening;
all twelve risk checks; and the final bid and ask. Meridian has no volatility model, so the
volatility adjustment is recorded as 0 and labelled as not modelled.

The log is read-only: trading never reads it, and a failure inside it cannot block an order.
`GET /api/decisions?kind=orders|pause|resume|cancel_all`, the live stream, and the dashboard's
"Why Meridian did that" panel all serve it. Records are also stored in the `decisions` table.

## Safety gates

| Gate | Fails when | Action |
|---|---|---|
| Kill switch | someone pressed it | halt |
| Delta market feed | socket down or silent for 35s | pull |
| Delta account feed | not authenticated | pull |
| Mark price fresh | no mark for 6s | pull |
| Order book in sync | `ob_updates` sequence gap or CRC32 checksum mismatch | pull and resubscribe |
| Binance reference fresh | no update for 3s | pull |
| Prices agree | Binance and Delta deviate from their normal gap by more than 25 bps | widen above 10 bps, pull above 25 |
| Inventory in limits | position at the limit | reduce only |
| Session loss limit | session PnL below the loss limit | cancel, flatten, halt |
| Rate limit headroom | local budget nearly used, or Delta returned 429 | pull |
| Exchange API healthy | five consecutive transport or 5xx errors | pull for 30s |
| Exchange operational | maintenance, or market not operational | pull |

Lifecycle fail-safes on top of the gates:

- Cancel all on start, stop, kill and any strategy error.
- **Delta's dead man's switch** (`/v2/heartbeat`): if Meridian dies, Delta cancels our orders
  within 30 seconds on its own.
- **Reconcile** every 10 seconds against `GET /v2/positions`. A disagreement is checked twice,
  then the exchange's position wins and the break is logged.
- Order book integrity from `ob_updates` sequence numbers and CRC32 checksums.
- Exponential backoff with jitter on every reconnect. Server heartbeats with a 35 second watchdog.

## Run it

You need Python 3.12 or newer and Node 22 with pnpm.

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env            # add your Delta testnet API key and secret

(cd web && pnpm install && NEXT_PUBLIC_API_BASE= pnpm build)
.venv/bin/python -m meridian    # http://127.0.0.1:8000
```

Without keys Meridian still streams live market data and previews the quotes it would place.

To work on the dashboard with hot reload, run the API as above and `pnpm dev` in `web/`; it
talks to `http://localhost:8000` through `web/.env.development`.

### Testnet keys

1. Sign up at [testnet.delta.exchange](https://testnet.delta.exchange) and fund the demo wallet.
2. Create an API key with trading permission. Leave IP whitelisting off if you deploy.
3. Put the key and secret in `.env`.

## Deploy

Vercel runs the same Dockerfile as a container service; `vercel.json` routes all traffic to it.
Set `DELTA_API_KEY`, `DELTA_API_SECRET` and a `CONTROL_API_KEY` as project env vars, then
`vercel --prod`. Instances can suspend when idle; an open dashboard stream keeps the bot live,
and the dead man's switch pulls the orders if the process dies.

Alternatively, `render.yaml` defines one Docker web service in Singapore plus a Postgres
database. Set `DELTA_API_KEY` and `DELTA_API_SECRET` in the Render dashboard. A
`CONTROL_API_KEY` is generated for you; enter it in the dashboard under Settings, Access, so
only you can start or stop the bot.

## Test it

```bash
.venv/bin/python -m pytest tests/test_quoter.py   # one file while iterating
scripts/checkCI.sh                                # everything, once, before pushing
```

The suite covers fee correction and markouts, the order book and checksum, quoting, every risk gate, the ledger,
the rate budget, the order manager, the REST client against a mock transport, the API, and the
whole engine against a fake exchange (start, fills, skew, stale feed, loss halt, kill).

## Test the fail-safes live

Settings, Test the fail-safes, or `POST /api/chaos/{name}`:

| Action | What you should see |
|---|---|
| `stale_ref` | Binance freezes for 10s, "Binance reference fresh" turns red, quotes disappear, then return |
| `price_shock` | Binance shifts 60 bps, "Prices agree" turns red, quotes pulled for 12s |
| `drop_feed` | Delta socket drops, book resyncs from a fresh snapshot, quoting resumes |
| `ledger_drift` | the ledger books a fake fill; within 10s reconcile catches it and adopts the exchange |

And the real one: kill the process with `kill -9` while quoting. Delta cancels the orders within
30 seconds through the dead man's switch.

## Layout

```
meridian/
  config.py          settings from env, runtime-editable strategy params
  delta/             auth (HMAC signing), rest (async client), ws (reconnecting socket), book (ob_updates)
  feeds/binance.py   reference price
  core/              fair_value, quoter, risk, oms, ledger, ratelimit, engine
  api/routes.py      state, SSE stream, control, chaos
  storage/db.py      fills, events, PnL points (SQLite or Postgres)
web/                 Next.js dashboard (static export)
tests/               pytest suite
docs/PITCH.md        five-minute demo script and judge Q&A
```
