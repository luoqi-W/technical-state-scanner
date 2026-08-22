import React, { useState } from "react";

const COLUMNS = [
  { key: "ticker", label: "Ticker", align: "left" },
  { key: "total_score", label: "Score", align: "right" },
  { key: "signals", label: "Signals", align: "left" },
];

export default function PoolTable({ results, selectedTicker, onSelect }) {
  const [sortKey, setSortKey] = useState("total_score");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...results].sort((a, b) => {
    let va = a[sortKey];
    let vb = b[sortKey];
    if (typeof va === "number" && typeof vb === "number") {
      return sortAsc ? va - vb : vb - va;
    }
    va = String(va ?? "");
    vb = String(vb ?? "");
    return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
  });

  function handleSort(key) {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  return (
    <div className="pool-table">
      <table>
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                style={{ textAlign: col.align }}
                onClick={() => handleSort(col.key)}
              >
                {col.label}
                {sortKey === col.key ? (sortAsc ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={row.ticker}
              className={row.ticker === selectedTicker ? "selected" : ""}
              onClick={() => onSelect(row.ticker)}
            >
              <td>{row.ticker}</td>
              <td className="score-cell">{row.total_score?.toFixed(1) ?? "—"}</td>
              <td>
                {(row.all_triggered_signals || []).length > 0
                  ? row.all_triggered_signals.map((s) => (
                      <span key={s} className="signal-badge active">
                        {s}
                      </span>
                    ))
                  : <span className="signal-badge">None</span>}
                {row.error && <span className="error-text"> {row.error}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length === 0 && (
        <div className="empty-state">No results. Run a pool scan to get started.</div>
      )}
    </div>
  );
}
