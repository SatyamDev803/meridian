"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { onThemeChange } from "@/lib/theme";
import type { PricePoint } from "@/lib/types";

type Key = "fair" | "ref" | "bestBid" | "bestAsk" | "bid" | "ask";

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function PriceChart({ points }: { points: PricePoint[] }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<Partial<Record<Key, ISeriesApi<"Line">>>>({});
  const latest = useRef<PricePoint[]>(points);
  latest.current = points;

  useEffect(() => {
    if (!host.current) return;
    const build = () => {
      chart.current?.remove();
      series.current = {};
      const c = createChart(host.current!, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: cssVar("--label-2"),
          fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Inter, sans-serif",
          fontSize: 11,
          attributionLogo: false,
        },
        grid: { vertLines: { visible: false }, horzLines: { color: cssVar("--hairline") } },
        rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.12 } },
        timeScale: { borderVisible: false, timeVisible: true, secondsVisible: true, rightOffset: 4 },
        crosshair: { horzLine: { labelBackgroundColor: cssVar("--blue") }, vertLine: { labelBackgroundColor: cssVar("--blue") } },
        handleScroll: false,
        handleScale: false,
      });
      const add = (key: Key, color: string, width: 1 | 2 | 3, style: LineStyle, title: string) => {
        series.current[key] = c.addSeries(LineSeries, {
          color,
          lineWidth: width,
          lineStyle: style,
          title,
          priceLineVisible: false,
          lastValueVisible: key === "fair" || key === "bid" || key === "ask",
          crosshairMarkerVisible: key === "fair",
        });
      };
      const fade = (hex: string, pct: number) => {
        const n = parseInt(hex.replace("#", ""), 16);
        return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${pct / 100})`;
      };
      add("bestBid", fade(cssVar("--green"), 35), 1, LineStyle.Solid, "");
      add("bestAsk", fade(cssVar("--red"), 35), 1, LineStyle.Solid, "");
      add("ref", cssVar("--teal"), 1, LineStyle.Dotted, "Binance");
      add("bid", cssVar("--green"), 2, LineStyle.Dashed, "Our bid");
      add("ask", cssVar("--red"), 2, LineStyle.Dashed, "Our ask");
      add("fair", cssVar("--blue"), 3, LineStyle.Solid, "Fair");
      chart.current = c;
      applyData(series.current, latest.current); // a theme switch rebuilds the chart
    };
    build();
    const stop = onThemeChange(build);
    return () => {
      stop();
      chart.current?.remove();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    applyData(series.current, points);
  }, [points]);

  return <div ref={host} className="h-[300px] w-full sm:h-[340px]" />;
}

const KEYS: Key[] = ["fair", "ref", "bestBid", "bestAsk", "bid", "ask"];

function applyData(series: Partial<Record<Key, ISeriesApi<"Line">>>, points: PricePoint[]) {
  for (const key of KEYS) {
    const s = series[key];
    if (!s) continue;
    const seen = new Set<number>();
    const data = [];
    for (const p of points) {
      const t = Math.floor(p.t / 1000);
      const v = p[key];
      if (v == null || seen.has(t)) continue;
      seen.add(t);
      data.push({ time: t as UTCTimestamp, value: v });
    }
    s.setData(data);
  }
}
