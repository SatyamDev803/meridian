"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, api } from "./api";
import type { Decision, MeridianEvent, PnlPoint, PricePoint, State } from "./types";

export type Link = "connecting" | "live" | "offline";

const MAX_POINTS = 900;
const MAX_EVENTS = 200;

function toPricePoint(s: State): PricePoint {
  return {
    t: s.ts,
    fair: s.market.fair,
    mark: s.market.mark,
    ref: s.market.ref,
    bestBid: s.market.bestBid,
    bestAsk: s.market.bestAsk,
    bid: s.quotes.bid,
    ask: s.quotes.ask,
    live: s.status === "running",
  };
}

export function useMeridian() {
  const [state, setState] = useState<State | null>(null);
  const [events, setEvents] = useState<MeridianEvent[]>([]);
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [pnl, setPnl] = useState<PnlPoint[]>([]);
  const [link, setLink] = useState<Link>("connecting");
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [decisionsAvailable, setDecisionsAvailable] = useState(true);
  const lastPoint = useRef(0);
  const lastState = useRef(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.history(), api.events()])
      .then(([h, ev]) => {
        if (cancelled) return;
        setPrices(h.prices.slice(-MAX_POINTS));
        setPnl(h.pnl.slice(-MAX_POINTS));
        setEvents(ev.slice(0, MAX_EVENTS));
      })
      .catch(() => {
        /* the stream will retry and fill in */
      });

    api
      .decisions()
      .then((d) => !cancelled && setDecisions(d))
      .catch(() => !cancelled && setDecisionsAvailable(false));

    const es = new EventSource(`${API_BASE}/api/stream`);
    es.onopen = () => setLink("live");
    // A brief reconnect should not flash the UI as offline: judge by data freshness instead.
    es.onerror = () => {
      if (Date.now() - lastState.current > 4000) {
        setLink(es.readyState === EventSource.CLOSED ? "offline" : "connecting");
      }
    };
    const watchdog = setInterval(() => {
      if (lastState.current && Date.now() - lastState.current > 6000) setLink("offline");
    }, 2000);
    es.addEventListener("state", (e) => {
      const s = JSON.parse((e as MessageEvent).data) as State;
      lastState.current = Date.now();
      setLink("live");
      setState(s);
      if (s.ts - lastPoint.current >= 1000) {
        lastPoint.current = s.ts;
        setPrices((p) => [...p, toPricePoint(s)].slice(-MAX_POINTS));
        setPnl((p) =>
          [
            ...p,
            {
              t: s.ts,
              realized: s.pnl.realized,
              unrealized: s.pnl.unrealized,
              total: s.pnl.session,
              position: s.position.contracts,
            },
          ].slice(-MAX_POINTS),
        );
      }
    });
    es.addEventListener("event", (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as MeridianEvent;
      setEvents((list) => (list.some((x) => x.id === ev.id) ? list : [ev, ...list].slice(0, MAX_EVENTS)));
    });
    es.addEventListener("decision", (e) => {
      const d = JSON.parse((e as MessageEvent).data) as Decision;
      setDecisionsAvailable(true);
      setDecisions((list) => (list.some((x) => x.id === d.id) ? list : [d, ...list].slice(0, 300)));
    });
    return () => {
      cancelled = true;
      clearInterval(watchdog);
      es.close();
    };
  }, []);

  const patchParams = useCallback((next: State["params"]) => {
    setState((s) => (s ? { ...s, params: next } : s));
  }, []);

  return { state, events, prices, pnl, link, patchParams, decisions, decisionsAvailable };
}
