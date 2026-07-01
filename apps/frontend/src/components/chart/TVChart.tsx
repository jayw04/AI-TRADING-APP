import { useEffect, useMemo, useRef, useState } from "react";
import { barsApi, type OHLCVBar } from "@/api/bars";
import { ApiError } from "@/api/client";

type Interval = "1" | "5" | "15" | "60" | "D";

interface Props {
  symbol: string;
  interval?: Interval;
}

// Chart-page interval id -> backend bar timeframe.
const TIMEFRAME: Record<Interval, string> = {
  "1": "1Min",
  "5": "5Min",
  "15": "15Min",
  "60": "1Hour",
  D: "1Day",
};

const PAD = { top: 12, right: 58, bottom: 22, left: 8 };
const UP = "#22c55e";
const DOWN = "#ef4444";

function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min)) return [min];
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let v = start; v <= max + 1e-9; v += step) out.push(v);
  return out;
}

function fmtPrice(n: number): string {
  return n >= 1000 ? n.toFixed(0) : n.toFixed(2);
}
function fmtTime(iso: string, intraday: boolean): string {
  const d = new Date(iso);
  return intraday
    ? d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZone: "America/New_York" })
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" });
}

/**
 * Local candlestick chart rendered from the backend bar cache
 * (GET /api/v1/bars/{symbol}). Replaces the former external TradingView embed,
 * which a third-party CDN dependency made unreliable behind SSL-inspecting
 * proxies (e.g. Norton); this path is same-origin and works fully offline.
 * Zero-dependency SVG — no charting lib (pnpm installs are blocked on this host).
 */
export default function TVChart({ symbol, interval = "5" }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [bars, setBars] = useState<OHLCVBar[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  // Track container size so the SVG fills the panel responsively.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // Fetch bars on symbol / interval change.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setHover(null);
    barsApi
      .getBars(symbol, { timeframe: TIMEFRAME[interval], limit: 160 })
      .then((r) => {
        if (!cancelled) setBars(r.bars);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? `Could not load bars (HTTP ${e.status})` : "Could not load bars",
          );
          setBars(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, interval]);

  const intraday = interval !== "D";

  const geom = useMemo(() => {
    if (!bars || bars.length === 0 || size.w < 40 || size.h < 40) return null;
    const plotW = size.w - PAD.left - PAD.right;
    const plotH = size.h - PAD.top - PAD.bottom;
    let lo = Infinity;
    let hi = -Infinity;
    for (const b of bars) {
      if (b.l < lo) lo = b.l;
      if (b.h > hi) hi = b.h;
    }
    const padY = (hi - lo) * 0.06 || hi * 0.01 || 1;
    lo -= padY;
    hi += padY;
    const y = (p: number) => PAD.top + plotH - ((p - lo) / (hi - lo)) * plotH;
    const slot = plotW / bars.length;
    const cw = Math.max(1, Math.min(slot * 0.7, 14));
    const x = (i: number) => PAD.left + slot * (i + 0.5);
    return { plotW, plotH, lo, hi, y, x, slot, cw };
  }, [bars, size]);

  return (
    <div ref={wrapRef} className="relative h-full w-full">
      <div className="absolute left-2 top-1.5 z-10 flex items-center gap-2 text-xs">
        <span className="font-mono font-medium text-neutral-200">{symbol}</span>
        <span className="text-neutral-500">
          {TIMEFRAME[interval]}
          {bars ? ` · ${bars.length} bars` : ""}
        </span>
        {loading && <span className="text-neutral-500">loading…</span>}
      </div>

      {error && (
        <div className="flex h-full w-full items-center justify-center text-sm text-neutral-500">
          {error}
        </div>
      )}
      {!error && bars && bars.length === 0 && !loading && (
        <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-sm text-neutral-500">
          <span>No bars cached for {symbol} at {TIMEFRAME[interval]}.</span>
          <span className="text-xs text-neutral-600">Try the 1D interval, or another symbol.</span>
        </div>
      )}

      {!error && geom && bars && (
        <svg
          width={size.w}
          height={size.h}
          className="block"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const i = Math.floor((mx - PAD.left) / geom.slot);
            setHover(i >= 0 && i < bars.length ? i : null);
          }}
        >
          {/* price grid + axis labels */}
          {niceTicks(geom.lo, geom.hi).map((p) => (
            <g key={p}>
              <line
                x1={PAD.left}
                x2={size.w - PAD.right}
                y1={geom.y(p)}
                y2={geom.y(p)}
                stroke="#262626"
                strokeWidth={1}
              />
              <text
                x={size.w - PAD.right + 4}
                y={geom.y(p) + 3}
                fill="#737373"
                fontSize={10}
                fontFamily="monospace"
              >
                {fmtPrice(p)}
              </text>
            </g>
          ))}

          {/* candles */}
          {bars.map((b, i) => {
            const up = b.c >= b.o;
            const color = up ? UP : DOWN;
            const cx = geom.x(i);
            const yo = geom.y(b.o);
            const yc = geom.y(b.c);
            const bodyTop = Math.min(yo, yc);
            const bodyH = Math.max(1, Math.abs(yc - yo));
            return (
              <g key={i}>
                <line x1={cx} x2={cx} y1={geom.y(b.h)} y2={geom.y(b.l)} stroke={color} strokeWidth={1} />
                <rect
                  x={cx - geom.cw / 2}
                  y={bodyTop}
                  width={geom.cw}
                  height={bodyH}
                  fill={color}
                />
              </g>
            );
          })}

          {/* last close marker */}
          {bars.length > 0 &&
            (() => {
              const last = bars[bars.length - 1];
              const yy = geom.y(last.c);
              return (
                <g>
                  <line
                    x1={PAD.left}
                    x2={size.w - PAD.right}
                    y1={yy}
                    y2={yy}
                    stroke="#525252"
                    strokeDasharray="3 3"
                    strokeWidth={1}
                  />
                  <rect x={size.w - PAD.right} y={yy - 7} width={PAD.right} height={14} fill="#404040" />
                  <text
                    x={size.w - PAD.right + 4}
                    y={yy + 3}
                    fill="#fafafa"
                    fontSize={10}
                    fontFamily="monospace"
                  >
                    {fmtPrice(last.c)}
                  </text>
                </g>
              );
            })()}

          {/* x-axis date labels (~5 evenly spaced) */}
          {bars
            .map((b, i) => ({ b, i }))
            .filter((_, i, arr) => i % Math.max(1, Math.floor(arr.length / 5)) === 0)
            .map(({ b, i }) => (
              <text
                key={`t${i}`}
                x={geom.x(i)}
                y={size.h - 8}
                fill="#737373"
                fontSize={10}
                fontFamily="monospace"
                textAnchor="middle"
              >
                {fmtTime(b.t, intraday)}
              </text>
            ))}

          {/* hover crosshair + OHLC readout */}
          {hover !== null && bars[hover] && (
            <g>
              <line
                x1={geom.x(hover)}
                x2={geom.x(hover)}
                y1={PAD.top}
                y2={size.h - PAD.bottom}
                stroke="#525252"
                strokeWidth={1}
              />
            </g>
          )}
        </svg>
      )}

      {hover !== null && bars && bars[hover] && (
        <div className="pointer-events-none absolute right-16 top-1.5 z-10 rounded border border-neutral-800 bg-neutral-950/90 px-2 py-1 font-mono text-[11px] text-neutral-300">
          <span className="text-neutral-500">{fmtTime(bars[hover].t, intraday)}</span>{" "}
          O {fmtPrice(bars[hover].o)} H {fmtPrice(bars[hover].h)} L {fmtPrice(bars[hover].l)} C{" "}
          <span className={bars[hover].c >= bars[hover].o ? "text-emerald-400" : "text-red-400"}>
            {fmtPrice(bars[hover].c)}
          </span>
        </div>
      )}
    </div>
  );
}
