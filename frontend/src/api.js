const API_BASE = "/api";

export async function fetchPoolSymbols(universe = "watchlist") {
  const res = await fetch(`${API_BASE}/pool/symbols?universe=${encodeURIComponent(universe)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function scanPool(universe = "watchlist", count = 700, workers = 3) {
  const params = new URLSearchParams({ universe, count, workers });
  const res = await fetch(`${API_BASE}/pool/scan?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchScore(symbol, count = 700) {
  const res = await fetch(`${API_BASE}/score/${encodeURIComponent(symbol)}?count=${count}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchKline(symbol, timeframe = "daily", limit = 300) {
  const params = new URLSearchParams({ timeframe, limit });
  const res = await fetch(`${API_BASE}/kline/${encodeURIComponent(symbol)}?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchKlineWithIndicators(symbol, timeframe = "daily", limit = 300) {
  const params = new URLSearchParams({ timeframe, limit });
  const res = await fetch(`${API_BASE}/kline/${encodeURIComponent(symbol)}/indicators?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function createWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/ws/intraday`;
  return new WebSocket(url);
}
