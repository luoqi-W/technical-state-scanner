import React, { useEffect, useRef } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";

const EMA_COLORS = {
  EMA12: "#ffffff",
  EMA144: "#f2cc60",
  EMA169: "#d29922",
  EMA576: "#3fb950",
  EMA676: "#238636",
};

export default function KlineChart({ candles, emaData }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#0d1117" },
        textColor: "#8b949e",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: {
        borderColor: "#30363d",
        timeVisible: true,
        secondsVisible: false,
      },
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#3fb950",
      downColor: "#f85149",
      borderUpColor: "#3fb950",
      borderDownColor: "#f85149",
      wickUpColor: "#3fb950",
      wickDownColor: "#f85149",
    });

    if (candles && candles.length > 0) {
      const chartData = candles.map((c) => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      candleSeries.setData(chartData);
    }

    if (emaData) {
      for (const [name, values] of Object.entries(emaData)) {
        if (!values || values.length === 0) continue;
        const color = EMA_COLORS[name] || "#8b949e";
        const lineSeries = chart.addLineSeries({
          color,
          lineWidth: name === "EMA12" ? 2 : 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        const lineData = values
          .filter((v) => v.value != null && !isNaN(v.value))
          .map((v) => ({
            time: Math.floor(new Date(v.timestamp).getTime() / 1000),
            value: v.value,
          }));
        if (lineData.length > 0) {
          lineSeries.setData(lineData);
        }
      }
    }

    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, emaData]);

  return <div ref={containerRef} className="chart-container" />;
}
