"use client";

import type { State } from "@/lib/types";
import { cn, fmtBps, fmtPrice } from "@/lib/format";
import { Card } from "./ui/card";

type Row = { price: number; size: number; side: "bid" | "ask"; ours?: boolean };

export function Ladder({ state }: { state: State | null }) {
  const book = state?.market.book ?? { bids: [], asks: [] };
  const live = state?.orders?.live;
  const ourBid = live?.buy?.order_id ? Number(live.buy.price) : null;
  const ourAsk = live?.sell?.order_id ? Number(live.sell.price) : null;

  const asks: Row[] = book.asks.slice(0, 6).map(([p, s]) => ({ price: Number(p), size: Number(s), side: "ask" }));
  const bids: Row[] = book.bids.slice(0, 6).map(([p, s]) => ({ price: Number(p), size: Number(s), side: "bid" }));
  const mark = (rows: Row[], price: number | null, side: "bid" | "ask", size: number) => {
    if (price == null) return rows;
    const hit = rows.find((r) => r.price === price);
    if (hit) {
      hit.ours = true;
      return rows;
    }
    return [...rows, { price, size, side, ours: true }];
  };
  const askRows = mark(asks, ourAsk, "ask", live?.sell?.unfilled ?? 0).sort((a, b) => b.price - a.price);
  const bidRows = mark(bids, ourBid, "bid", live?.buy?.unfilled ?? 0).sort((a, b) => b.price - a.price);
  const maxSize = Math.max(1, ...[...askRows, ...bidRows].map((r) => r.size));

  return (
    <Card
      title="Order book"
      aside={state?.market.bookSynced ? (state.market.checksumVerified ? "Checksum verified" : "Sequence verified") : "Syncing"}
    >
      <div className="px-3 pb-4 pt-3" role="table" aria-label="Delta order book">
        <div className="grid grid-cols-[1fr_1fr] px-2 pb-1 text-[12px] text-label-2" role="row">
          <span role="columnheader">Price</span>
          <span role="columnheader" className="text-right">Contracts</span>
        </div>
        {withGaps(askRows).map((r) =>
          "gap" in r ? <GapRow key={`ag${r.at}`} gap={r.gap} /> : <LadderRow key={`a${r.price}`} row={r} maxSize={maxSize} />,
        )}
        <div className="my-1.5 flex items-center justify-between rounded-xl bg-fill px-3 py-1.5 text-[13px]">
          <span className="text-label-2">Spread</span>
          <span className="num font-medium">{fmtBps(state?.market.spreadBps, 2)}</span>
        </div>
        {withGaps(bidRows).map((r) =>
          "gap" in r ? <GapRow key={`bg${r.at}`} gap={r.gap} /> : <LadderRow key={`b${r.price}`} row={r} maxSize={maxSize} />,
        )}
        {!askRows.length && !bidRows.length && (
          <p className="px-2 py-8 text-center text-[15px] text-label-2">Waiting for the first snapshot from Delta.</p>
        )}
      </div>
    </Card>
  );
}

// Our quotes usually sit outside the top levels. Show the distance instead of hiding it.
function withGaps(rows: Row[]): (Row | { gap: number; at: number })[] {
  const out: (Row | { gap: number; at: number })[] = [];
  rows.forEach((r, i) => {
    const prev = rows[i - 1];
    if (prev && (prev.ours || r.ours) && Math.abs(prev.price - r.price) > 2) {
      out.push({ gap: Math.abs(prev.price - r.price), at: r.price });
    }
    out.push(r);
  });
  return out;
}

function GapRow({ gap }: { gap: number }) {
  return (
    <div className="flex items-center gap-2 px-2 py-1 text-[12px] text-label-2" role="row">
      <span className="h-px flex-1 border-t border-dashed border-hairline" />
      <span role="cell" className="num">{gap.toFixed(1)} away from the book</span>
      <span className="h-px flex-1 border-t border-dashed border-hairline" />
    </div>
  );
}

function LadderRow({ row, maxSize }: { row: Row; maxSize: number }) {
  const bid = row.side === "bid";
  return (
    <div
      role="row"
      className={cn(
        "relative grid grid-cols-[1fr_1fr] items-center overflow-hidden rounded-lg px-2 py-[5px] text-[14px]",
        row.ours && "ring-2 ring-inset ring-blue",
      )}
    >
      <span
        aria-hidden="true"
        className={cn("absolute inset-y-0.5 right-0 rounded-md", bid ? "bg-green/12" : "bg-red/12")}
        style={{ width: `${Math.max(3, (row.size / maxSize) * 100)}%` }}
      />
      <span role="cell" className={cn("num relative font-medium", bid ? "text-green" : "text-red")}>
        {fmtPrice(row.price)}
        {row.ours && <span className="ml-2 rounded-full bg-blue px-1.5 py-px text-[11px] font-semibold text-white">You</span>}
      </span>
      <span role="cell" className="num relative text-right text-label">
        {row.size.toLocaleString()}
      </span>
    </div>
  );
}
