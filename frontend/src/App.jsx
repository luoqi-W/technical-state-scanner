import React, { useState, useCallback, useEffect } from "react";
import PoolTable from "./components/PoolTable";
import KlineChart from "./components/KlineChart";
import ScorePanel from "./components/ScorePanel";
import useWebSocket from "./hooks/useWebSocket";
import { scanPool, fetchScore, fetchKlineWithIndicators } from "./api";

const TIMEFRAMES = ["weekly", "daily", "4hour", "15min"];
const TF_LABELS = { weekly: "Weekly", daily: "Daily", "4hour": "4H", "15min": "15m" };

export default function App() {
  const [universe, setUniverse] = useState("watchlist");
  const [poolResults, setPoolResults] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [scoreData, setScoreData] = useState(null);
  const [timeframe, setTimeframe] = useState("daily");
  const [candles, setCandles] = useState([]);
  const [emaData, setEmaData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("Ready");

  const { connected, lastMessage, send } = useWebSocket();

  useEffect(() => {
    if (lastMessage?.type === "intraday_update" && lastMessage.symbol === selectedTicker) {
      setStatus(`Intraday update for ${lastMessage.symbol}`);
    }
    if (lastMessage?.type === "scan_result" && lastMessage.data) {
      setScoreData(lastMessage.data);
    }
  }, [lastMessage, selectedTicker]);

  const handleScanPool = useCallback(async () => {
    setLoading(true);
    setStatus("Scanning pool...");
    try {
      const data = await scanPool(universe);
      setPoolResults(data.results || []);
      setStatus(`Scanned ${data.count} symbols`);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
    setLoading(false);
  }, [universe]);

  const handleSelectTicker = useCallback(
    async (ticker) => {
      setSelectedTicker(ticker);
      setStatus(`Loading ${ticker}...`);
      try {
        const [score, kline] = await Promise.all([
          fetchScore(ticker),
          fetchKlineWithIndicators(ticker, timeframe),
        ]);
        setScoreData(score);
        setCandles(kline.candles || []);
        setEmaData(kline.ema || null);
        setStatus(`${ticker}: score=${score.total_score?.toFixed(1)}`);
        if (connected) {
          send({ subscribe: [ticker] });
        }
      } catch (err) {
        setStatus(`Error loading ${ticker}: ${err.message}`);
      }
    },
    [timeframe, connected, send]
  );

  const handleTimeframeChange = useCallback(
    async (tf) => {
      setTimeframe(tf);
      if (!selectedTicker) return;
      setStatus(`Loading ${tf} chart...`);
      try {
        const kline = await fetchKlineWithIndicators(selectedTicker, tf);
        setCandles(kline.candles || []);
        setEmaData(kline.ema || null);
        setStatus(`${selectedTicker} ${tf}: ${kline.count} bars`);
      } catch (err) {
        setStatus(`Error: ${err.message}`);
      }
    },
    [selectedTicker]
  );

  return (
    <>
      {/* Header */}
      <div className="app-header">
        <h1>Technical State Scanner</h1>
        <div className="controls">
          <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Universe</label>
          <input
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            style={{ width: 140 }}
            placeholder="watchlist"
          />
          <button onClick={handleScanPool} disabled={loading}>
            {loading ? "Scanning..." : "Scan Pool"}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="app-body">
        {/* Left: Stock Pool */}
        <div className="pool-panel">
          <div className="panel-header">
            Stock Pool — {poolResults.length} symbols
          </div>
          <PoolTable
            results={poolResults}
            selectedTicker={selectedTicker}
            onSelect={handleSelectTicker}
          />
        </div>

        {/* Right: Chart Area */}
        <div className="chart-panel">
          <div className="chart-toolbar">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                className={`tf-button ${timeframe === tf ? "active" : ""}`}
                onClick={() => handleTimeframeChange(tf)}
              >
                {TF_LABELS[tf]}
              </button>
            ))}
            {selectedTicker && (
              <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--text-secondary)" }}>
                {selectedTicker}
              </span>
            )}
          </div>

          {selectedTicker ? (
            <>
              <KlineChart candles={candles} emaData={emaData} />
              <ScorePanel scoreData={scoreData} />
            </>
          ) : (
            <div className="empty-state">
              Select a ticker from the pool to view charts and signals.
            </div>
          )}
        </div>
      </div>

      {/* Status Bar */}
      <div className="status-bar">
        <span>{status}</span>
        <span>
          <span className={`ws-indicator ${connected ? "connected" : "disconnected"}`} />
          {connected ? "WebSocket connected" : "WebSocket disconnected"}
        </span>
      </div>
    </>
  );
}

