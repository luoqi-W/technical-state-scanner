"""Multi-layer scoring system for technical state signals.

Implements AGENTS.md §18 scoring layers:
1. Base Signal Score
2. Timeframe Multiplier  
3. Factor Confluence Score
4. Cross-Timeframe All-Factor Coverage Multiplier

Final formula:
[
  sum(base_signal_score * timeframe_multiplier)
  +
  sum(best_factor_confluence_score_per_timeframe)
]
*
cross_timeframe_all_factor_coverage_multiplier
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BaseSignalScore:
    """Base score for each factor type."""

    F1_TIER_A: int = 4
    F1_TIER_B: int = 3
    F1_TIER_C: int = 2
    F2: int = 3
    F3: int = 4
    F4: int = 1
    F5: int = 4
    F6: int = 1

    def get_score(self, factor_id: str, tier: str | None = None) -> int:
        """Get base signal score for a factor.
        
        Args:
            factor_id: One of F1-F6
            tier: For F1, one of A/B/C (tier of Vegas Alignment)
            
        Returns:
            Base score value
        """
        if factor_id == "F1":
            if tier == "A":
                return self.F1_TIER_A
            elif tier == "B":
                return self.F1_TIER_B
            elif tier == "C":
                return self.F1_TIER_C
            else:
                return self.F1_TIER_A  # default to A
        elif factor_id == "F2":
            return self.F2
        elif factor_id == "F3":
            return self.F3
        elif factor_id == "F4":
            return self.F4
        elif factor_id == "F5":
            return self.F5
        elif factor_id == "F6":
            return self.F6
        return 0


@dataclass(frozen=True)
class TimeframeMultiplier:
    """Timeframe coverage multipliers.
    
    Higher multipliers apply when the same factor triggers
    across multiple timeframes.
    """

    WEEKLY_DAILY_4H: float = 6.0
    WEEKLY_DAILY: float = 4.5
    WEEKLY_4H: float = 3.5
    DAILY_4H: float = 3.0
    WEEKLY_ONLY: float = 2.5
    DAILY_ONLY: float = 1.5
    HOUR4_ONLY: float = 1.0

    def get_multiplier(self, timeframes_triggered: set[str]) -> float:
        """Get multiplier based on which timeframes triggered the factor.
        
        Args:
            timeframes_triggered: Set of timeframe strings (e.g., {'weekly', 'daily'})
            
        Returns:
            Multiplier value
        """
        timeframes_triggered = {t.lower().replace("4hour", "4h") for t in timeframes_triggered}
        
        if timeframes_triggered == {"weekly", "daily", "4h"}:
            return self.WEEKLY_DAILY_4H
        elif timeframes_triggered == {"weekly", "daily"}:
            return self.WEEKLY_DAILY
        elif timeframes_triggered == {"weekly", "4h"}:
            return self.WEEKLY_4H
        elif timeframes_triggered == {"daily", "4h"}:
            return self.DAILY_4H
        elif timeframes_triggered == {"weekly"}:
            return self.WEEKLY_ONLY
        elif timeframes_triggered == {"daily"}:
            return self.DAILY_ONLY
        elif timeframes_triggered == {"4h"}:
            return self.HOUR4_ONLY
        else:
            return 1.0


@dataclass(frozen=True)
class FactorConfluenceScore:
    """Factor Confluence Score tiers.
    
    Per-timeframe confluence scoring based on how many factors trigger together.
    Apply only the highest matched tier per timeframe.
    """

    S_TIER: int = 30      # F1 + F2 + F3 + F4 + F5 + F6
    A_PLUS_TIER: int = 24  # F3 + F4 + F5 + F6
    A_TIER: int = 22       # F3 + F5 + F6 OR F1A + F2 + F3 + F4 + F5
    B_PLUS_TIER: int = 18  # F1B + F2 + F3 + F4 + F5
    B_TIER: int = 15       # F1C + F2 + F3 + F4 + F5
    C_PLUS_TIER: int = 12  # F1A + F2 + F3 + F4
    C_TIER: int = 10       # F1B + F2 + F3 + F4
    C_MINUS_TIER: int = 8  # F1C + F2 + F3 + F4
    D_PLUS_TIER: int = 6   # F1A + F2 + F3 OR F1A + F2 + F4
    D_TIER: int = 5        # F1B + F2 + F3 OR F1B + F2 + F4
    D_MINUS_TIER: int = 4  # F1C + F2 + F3 OR F1C + F2 + F4
    EARLY_SIGNAL_TIER: int = 3  # F1A + F2 OR F1B + F2 OR F1C + F2

    def get_confluence_score(
        self,
        triggered_factors: set[str],
        factor_details: dict[str, Any],
    ) -> tuple[str | None, int]:
        """Determine confluence tier and score for a timeframe.
        
        Args:
            triggered_factors: Set of factor IDs that triggered (e.g., {'F1', 'F2', 'F3'})
            factor_details: Dict mapping factor ID to its details dict
            
        Returns:
            Tuple of (tier_name, score) or (None, 0) if no confluence
        """
        # Get F1 tier if F1 is triggered
        f1_tier = None
        if "F1" in triggered_factors and factor_details.get("F1", {}).get("details"):
            f1_tier = factor_details["F1"]["details"].get("mode_quality_tier")

        # Check each tier from highest to lowest
        # S Tier: all 6 factors
        if triggered_factors == {"F1", "F2", "F3", "F4", "F5", "F6"}:
            return ("S", self.S_TIER)

        # A+ Tier: F3 + F4 + F5 + F6 (without F1, F2)
        if triggered_factors == {"F3", "F4", "F5", "F6"}:
            return ("A+", self.A_PLUS_TIER)

        # A Tier: F3 + F5 + F6 (no F1, F2, F4)
        if triggered_factors == {"F3", "F5", "F6"}:
            return ("A", self.A_TIER)

        # A Tier: F1A + F2 + F3 + F4 + F5
        if (
            f1_tier == "A"
            and triggered_factors == {"F1", "F2", "F3", "F4", "F5"}
        ):
            return ("A", self.A_TIER)

        # B+ Tier: F1B + F2 + F3 + F4 + F5
        if (
            f1_tier == "B"
            and triggered_factors == {"F1", "F2", "F3", "F4", "F5"}
        ):
            return ("B+", self.B_PLUS_TIER)

        # B Tier: F1C + F2 + F3 + F4 + F5
        if (
            f1_tier == "C"
            and triggered_factors == {"F1", "F2", "F3", "F4", "F5"}
        ):
            return ("B", self.B_TIER)

        # C+ Tier: F1A + F2 + F3 + F4
        if (
            f1_tier == "A"
            and triggered_factors == {"F1", "F2", "F3", "F4"}
        ):
            return ("C+", self.C_PLUS_TIER)

        # C Tier: F1B + F2 + F3 + F4
        if (
            f1_tier == "B"
            and triggered_factors == {"F1", "F2", "F3", "F4"}
        ):
            return ("C", self.C_TIER)

        # C- Tier: F1C + F2 + F3 + F4
        if (
            f1_tier == "C"
            and triggered_factors == {"F1", "F2", "F3", "F4"}
        ):
            return ("C-", self.C_MINUS_TIER)

        # D+ Tier: F1A + F2 + F3 OR F1A + F2 + F4
        if f1_tier == "A" and "F2" in triggered_factors:
            if triggered_factors == {"F1", "F2", "F3"}:
                return ("D+", self.D_PLUS_TIER)
            elif triggered_factors == {"F1", "F2", "F4"}:
                return ("D+", self.D_PLUS_TIER)

        # D Tier: F1B + F2 + F3 OR F1B + F2 + F4
        if f1_tier == "B" and "F2" in triggered_factors:
            if triggered_factors == {"F1", "F2", "F3"}:
                return ("D", self.D_TIER)
            elif triggered_factors == {"F1", "F2", "F4"}:
                return ("D", self.D_TIER)

        # D- Tier: F1C + F2 + F3 OR F1C + F2 + F4
        if f1_tier == "C" and "F2" in triggered_factors:
            if triggered_factors == {"F1", "F2", "F3"}:
                return ("D-", self.D_MINUS_TIER)
            elif triggered_factors == {"F1", "F2", "F4"}:
                return ("D-", self.D_MINUS_TIER)

        # Early Signal Tier: F1A + F2 OR F1B + F2 OR F1C + F2
        if triggered_factors == {"F1", "F2"}:
            return ("Early", self.EARLY_SIGNAL_TIER)

        # No confluence tier matched
        return (None, 0)


@dataclass
class TimeframeScore:
    """Scoring results for a single timeframe."""

    timeframe: str
    triggered_factors: set[str]
    confluence_tier: str | None
    confluence_score: int
    base_timeframe_scores: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ScanScore:
    """Complete multi-layer scoring result for a ticker across all timeframes."""

    ticker: str
    base_timeframe_scores: dict[str, dict[str, Any]]  # Per-factor scores with multipliers
    factor_confluence_scores: dict[str, dict[str, Any]]  # Per-timeframe confluence
    cross_timeframe_all_factor_coverage_multiplier: float
    pre_multiplier_score: float
    total_score: float


def calculate_score(
    all_triggered_signals: dict[str, list[str]],  # timeframe -> list of signal names
    timeframe_signals_map: dict[str, dict[str, Any]],  # timeframe -> aggregator output
    base_score_config: BaseSignalScore | None = None,
    timeframe_multiplier_config: TimeframeMultiplier | None = None,
    confluence_config: FactorConfluenceScore | None = None,
) -> ScanScore:
    """Calculate multi-layer score for a stock across all timeframes.
    
    Args:
        all_triggered_signals: Dict mapping timeframe to list of signal names
        timeframe_signals_map: Dict mapping timeframe to aggregator result dict
            (containing 'triggered_factors', 'details', etc.)
        base_score_config: Optional custom BaseSignalScore config
        timeframe_multiplier_config: Optional custom TimeframeMultiplier config
        confluence_config: Optional custom FactorConfluenceScore config
        
    Returns:
        ScanScore with complete scoring breakdown
    """
    base_score = base_score_config or BaseSignalScore()
    tf_multiplier = timeframe_multiplier_config or TimeframeMultiplier()
    confluence = confluence_config or FactorConfluenceScore()

    # Step 1 & 2: Calculate base_timeframe_scores with multipliers
    # Map each factor to the timeframes where it was triggered
    factor_to_timeframes: dict[str, set[str]] = {}
    base_timeframe_scores_result: dict[str, dict[str, Any]] = {}

    for timeframe, signals_data in timeframe_signals_map.items():
        triggered_factors = signals_data.get("triggered_factors", [])
        details = signals_data.get("details", {})

        for factor_id in triggered_factors:
            if factor_id not in factor_to_timeframes:
                factor_to_timeframes[factor_id] = set()
            factor_to_timeframes[factor_id].add(timeframe)

    # For each factor that was triggered anywhere, calculate its score
    for factor_id, timeframes_set in factor_to_timeframes.items():
        multiplier = tf_multiplier.get_multiplier(timeframes_set)

        # Get F1 tier if applicable
        f1_tier = None
        if factor_id == "F1":
            # Find the F1 details from any timeframe where it triggered
            for tf in timeframes_set:
                f1_details = timeframe_signals_map.get(tf, {}).get("details", {}).get("F1", {})
                if f1_details.get("triggered"):
                    f1_tier = f1_details.get("details", {}).get("mode_quality_tier")
                    break

        base_sig_score = base_score.get_score(factor_id, f1_tier)
        final_score = base_sig_score * multiplier

        # Determine timeframe coverage label
        tf_sorted = sorted(timeframes_set)
        if tf_sorted == ["4hour"]:
            label = f"1-3天 + {_get_signal_name(factor_id, f1_tier)}"
        elif tf_sorted == ["daily"]:
            label = f"1-2周 + {_get_signal_name(factor_id, f1_tier)}"
        elif tf_sorted == ["weekly"]:
            label = f"长期 + {_get_signal_name(factor_id, f1_tier)}"
        elif tf_sorted == ["4hour", "daily"]:
            label = f"日线+4小时 共振 + {_get_signal_name(factor_id, f1_tier)}"
        elif tf_sorted == ["4hour", "weekly"]:
            label = f"周线+4小时 共振 + {_get_signal_name(factor_id, f1_tier)}"
        elif tf_sorted == ["daily", "weekly"]:
            label = f"周线+日线 共振 + {_get_signal_name(factor_id, f1_tier)}"
        elif tf_sorted == ["4hour", "daily", "weekly"]:
            label = f"周线+日线+4小时 共振 + {_get_signal_name(factor_id, f1_tier)}"
        else:
            label = f"{','.join(tf_sorted)} + {_get_signal_name(factor_id, f1_tier)}"

        base_timeframe_scores_result[factor_id] = {
            "triggered_timeframes": list(timeframes_set),
            "base_signal_score": base_sig_score,
            "timeframe_multiplier": multiplier,
            "score": final_score,
            "label": label,
        }

    # Step 3: Calculate factor_confluence_scores per timeframe
    factor_confluence_scores_result: dict[str, dict[str, Any]] = {}

    for timeframe, signals_data in timeframe_signals_map.items():
        triggered_factors = set(signals_data.get("triggered_factors", []))
        details = signals_data.get("details", {})

        tier_name, tier_score = confluence.get_confluence_score(triggered_factors, details)

        factor_confluence_scores_result[timeframe] = {
            "tier": tier_name,
            "score": tier_score,
            "matched_rule": _get_confluence_rule_name(tier_name, triggered_factors, details),
        }

    # Step 4: Calculate cross-timeframe all-factor coverage multiplier
    all_timeframe_factors = set()
    for signals_data in timeframe_signals_map.values():
        all_timeframe_factors.update(signals_data.get("triggered_factors", []))

    cross_tf_multiplier = 10.0 if all_timeframe_factors == {"F1", "F2", "F3", "F4", "F5", "F6"} else 1.0

    # Calculate pre-multiplier score
    pre_multiplier = sum(s["score"] for s in base_timeframe_scores_result.values())
    pre_multiplier += sum(s["score"] for s in factor_confluence_scores_result.values())

    # Calculate final score
    total = pre_multiplier * cross_tf_multiplier

    return ScanScore(
        ticker="",  # Will be set by caller
        base_timeframe_scores=base_timeframe_scores_result,
        factor_confluence_scores=factor_confluence_scores_result,
        cross_timeframe_all_factor_coverage_multiplier=cross_tf_multiplier,
        pre_multiplier_score=pre_multiplier,
        total_score=total,
    )


def _get_signal_name(factor_id: str, tier: str | None = None) -> str:
    """Get human-readable signal name for a factor."""
    if factor_id == "F1":
        return "Vegas Alignment"
    elif factor_id == "F2":
        return "EMA12 Lift-Off"
    elif factor_id == "F3":
        return "Round Bottom"
    elif factor_id == "F4":
        return "Triangle Consolidation"
    elif factor_id == "F5":
        return "Big Bullish Candle"
    elif factor_id == "F6":
        return "Volume Surge"
    return factor_id


def _get_confluence_rule_name(tier: str | None, triggered_factors: set[str], details: dict) -> str | None:
    """Get the confluence rule that matched this tier."""
    if tier is None:
        return None

    # Get F1 tier if available
    f1_tier = None
    if "F1" in triggered_factors and details.get("F1", {}).get("details"):
        f1_tier = details["F1"]["details"].get("mode_quality_tier")

    if tier == "S":
        return "F1 + F2 + F3 + F4 + F5 + F6"
    elif tier == "A+":
        return "F3 + F4 + F5 + F6"
    elif tier == "A":
        if f1_tier == "A":
            return "F1 Tier A + F2 + F3 + F4 + F5"
        return "F3 + F5 + F6"
    elif tier == "B+":
        return f"F1 Tier B + F2 + F3 + F4 + F5"
    elif tier == "B":
        return f"F1 Tier C + F2 + F3 + F4 + F5"
    elif tier == "C+":
        return "F1 Tier A + F2 + F3 + F4"
    elif tier == "C":
        return "F1 Tier B + F2 + F3 + F4"
    elif tier == "C-":
        return "F1 Tier C + F2 + F3 + F4"
    elif tier == "D+":
        return "F1 Tier A + F2 + F3/F4"
    elif tier == "D":
        return "F1 Tier B + F2 + F3/F4"
    elif tier == "D-":
        return "F1 Tier C + F2 + F3/F4"
    elif tier == "Early":
        return "F1 + F2"
    return None
