import { useEffect, useRef } from "react";

type Interval = "1" | "5" | "15" | "60" | "D";

interface Props {
  symbol: string;
  interval?: Interval;
}

// Best-effort ticker → TradingView-symbol map. Falls back to the raw upper-cased
// ticker; TradingView will resolve "AAPL" on its own for most cases but adding
// the exchange prefix makes the widget load faster and avoids ambiguity.
const SYMBOL_MAP: Record<string, string> = {
  AAPL: "NASDAQ:AAPL",
  MSFT: "NASDAQ:MSFT",
  NVDA: "NASDAQ:NVDA",
  TSLA: "NASDAQ:TSLA",
  AMD: "NASDAQ:AMD",
  GOOGL: "NASDAQ:GOOGL",
  AMZN: "NASDAQ:AMZN",
  META: "NASDAQ:META",
  SPY: "AMEX:SPY",
  QQQ: "NASDAQ:QQQ",
  F: "NYSE:F",
};

export default function TVChart({ symbol, interval = "5" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const tvSymbol = SYMBOL_MAP[symbol.toUpperCase()] ?? symbol.toUpperCase();
    containerRef.current.innerHTML = "";

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval,
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      hide_side_toolbar: false,
      allow_symbol_change: true,
      withdateranges: true,
      details: true,
      studies: ["MASimple@tv-basicstudies"],
      container_id: "tv-chart",
    });

    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container h-full w-full";
    wrapper.innerHTML = `<div id="tv-chart" style="height: 100%; width: 100%;"></div>`;
    wrapper.appendChild(script);
    containerRef.current.appendChild(wrapper);

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
  }, [symbol, interval]);

  return <div ref={containerRef} className="h-full w-full" />;
}
