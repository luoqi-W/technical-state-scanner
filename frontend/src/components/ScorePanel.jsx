import React from "react";

export default function ScorePanel({ scoreData }) {
  if (!scoreData) {
    return (
      <div className="signal-cards">
        <div className="signal-card">
          <div className="card-title">Total Score</div>
          <div className="card-value">—</div>
        </div>
      </div>
    );
  }

  const {
    ticker,
    total_score,
    scoring_breakdown,
    all_triggered_signals,
    factor_confluence,
  } = scoreData;

  const preMulti = scoring_breakdown?.pre_multiplier_score ?? 0;
  const coverageMul =
    scoring_breakdown?.cross_timeframe_all_factor_coverage_multiplier ?? 1;

  const confluenceTiers = {};
  if (factor_confluence) {
    for (const [tf, info] of Object.entries(factor_confluence)) {
      if (info?.tier) {
        confluenceTiers[tf] = `${info.tier} (${info.score})`;
      }
    }
  }

  return (
    <div className="signal-cards">
      <div className="signal-card">
        <div className="card-title">Total Score</div>
        <div className="card-value">{total_score?.toFixed(1) ?? "—"}</div>
        <div className="card-detail">{ticker}</div>
      </div>
      <div className="signal-card">
        <div className="card-title">Pre-multiplier</div>
        <div className="card-value">{preMulti?.toFixed(1) ?? "—"}</div>
        <div className="card-detail">
          Coverage ×{coverageMul}
        </div>
      </div>
      <div className="signal-card">
        <div className="card-title">Signals</div>
        <div className="card-value">{(all_triggered_signals || []).length}</div>
        <div className="card-detail">
          {(all_triggered_signals || []).join(", ") || "None"}
        </div>
      </div>
      {Object.entries(confluenceTiers).map(([tf, label]) => (
        <div className="signal-card" key={tf}>
          <div className="card-title">{tf} Confluence</div>
          <div className="card-value" style={{ fontSize: 14 }}>{label}</div>
        </div>
      ))}
    </div>
  );
}
