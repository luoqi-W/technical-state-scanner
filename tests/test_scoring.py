"""Tests for multi-layer scoring system."""

from __future__ import annotations

import pytest

from technical_state_scanner.core.scoring import (
    BaseSignalScore,
    TimeframeMultiplier,
    FactorConfluenceScore,
    calculate_score,
)


class TestBaseSignalScore:
    """Test base signal score assignment."""

    def test_f1_tier_a_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F1", "A") == 4

    def test_f1_tier_b_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F1", "B") == 3

    def test_f1_tier_c_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F1", "C") == 2

    def test_f2_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F2") == 3

    def test_f3_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F3") == 4

    def test_f4_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F4") == 1

    def test_f5_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F5") == 4

    def test_f6_score(self):
        scores = BaseSignalScore()
        assert scores.get_score("F6") == 1


class TestTimeframeMultiplier:
    """Test timeframe multiplier calculation."""

    def test_all_three_timeframes(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"weekly", "daily", "4h"})
        assert result == 6.0

    def test_weekly_daily_only(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"weekly", "daily"})
        assert result == 4.5

    def test_weekly_4h_only(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"weekly", "4h"})
        assert result == 3.5

    def test_daily_4h_only(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"daily", "4h"})
        assert result == 3.0

    def test_weekly_only(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"weekly"})
        assert result == 2.5

    def test_daily_only(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"daily"})
        assert result == 1.5

    def test_4h_only(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"4h"})
        assert result == 1.0

    def test_case_insensitive_timeframe(self):
        mult = TimeframeMultiplier()
        # Test with different case variations
        result = mult.get_multiplier({"Weekly", "Daily", "4h"})
        assert result == 6.0

    def test_4hour_normalized_to_4h(self):
        mult = TimeframeMultiplier()
        result = mult.get_multiplier({"4hour"})
        assert result == 1.0


class TestFactorConfluenceScore:
    """Test factor confluence score tiers."""

    def test_s_tier_all_six_factors(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score(
            {"F1", "F2", "F3", "F4", "F5", "F6"},
            {"F1": {"details": {"mode_quality_tier": "A"}}},
        )
        assert tier == "S"
        assert score == 30

    def test_a_plus_tier_f3_f4_f5_f6(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score(
            {"F3", "F4", "F5", "F6"},
            {},
        )
        assert tier == "A+"
        assert score == 24

    def test_a_tier_f3_f5_f6(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score(
            {"F3", "F5", "F6"},
            {},
        )
        assert tier == "A"
        assert score == 22

    def test_a_tier_f1a_f2_f3_f4_f5(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score(
            {"F1", "F2", "F3", "F4", "F5"},
            {"F1": {"details": {"mode_quality_tier": "A"}}},
        )
        assert tier == "A"
        assert score == 22

    def test_early_signal_tier_f1_f2(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score(
            {"F1", "F2"},
            {"F1": {"details": {"mode_quality_tier": "A"}}},
        )
        assert tier == "Early"
        assert score == 3

    def test_no_confluence_empty_factors(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score(set(), {})
        assert tier is None
        assert score == 0

    def test_no_confluence_single_factor(self):
        conf = FactorConfluenceScore()
        tier, score = conf.get_confluence_score({"F1"}, {})
        assert tier is None
        assert score == 0


class TestCalculateScore:
    """Test complete multi-layer scoring."""

    def test_single_factor_single_timeframe(self):
        """F3 triggered on daily only."""
        all_signals = {"daily": ["Round Bottom"]}
        tf_map = {
            "daily": {
                "triggered_factors": ["F3"],
                "triggered_signals": ["Round Bottom"],
                "details": {"F3": {"triggered": True, "details": {}}},
            },
            "weekly": {"triggered_factors": [], "details": {}},
            "4hour": {"triggered_factors": [], "details": {}},
        }

        score = calculate_score(all_signals, tf_map)

        # F3 base score: 4, multiplier: 1.5 (daily only) = 6
        # Confluence: no tier per daily (only 1 factor) = 0
        # Pre-multiplier: 6 + 0 = 6
        # Cross-timeframe coverage: not all 6 factors, multiplier = 1
        # Total: 6 * 1 = 6
        assert score.total_score == 6.0

    def test_multiple_factors_same_timeframe(self):
        """F1A + F2 + F3 on daily = C+ confluence tier."""
        all_signals = {"daily": ["Vegas Alignment", "EMA12 Lift-Off", "Round Bottom"]}
        tf_map = {
            "daily": {
                "triggered_factors": ["F1", "F2", "F3"],
                "triggered_signals": ["Vegas Alignment", "EMA12 Lift-Off", "Round Bottom"],
                "details": {
                    "F1": {"triggered": True, "details": {"mode_quality_tier": "A"}},
                    "F2": {"triggered": True, "details": {}},
                    "F3": {"triggered": True, "details": {}},
                },
            },
            "weekly": {"triggered_factors": [], "details": {}},
            "4hour": {"triggered_factors": [], "details": {}},
        }

        score = calculate_score(all_signals, tf_map)

        # Base timeframe scores:
        # F1 Tier A: base 4, multiplier 1.5 (daily only) = 6
        # F2: base 3, multiplier 1.5 (daily only) = 4.5
        # F3: base 4, multiplier 1.5 (daily only) = 6
        # Total base: 6 + 4.5 + 6 = 16.5

        # Confluence for daily: F1A + F2 + F3 + (F4 missing) = no tier match
        # Actually, F1A + F2 + F3 is D+ tier = 6
        # Pre-multiplier: 16.5 + 6 = 22.5
        # Cross-timeframe: not all 6 factors = 1
        # Total: 22.5
        assert score.base_timeframe_scores["F1"]["score"] == 6.0
        assert score.base_timeframe_scores["F2"]["score"] == 4.5
        assert score.base_timeframe_scores["F3"]["score"] == 6.0
        # Confluence is D+ (F1A + F2 + F3)
        assert score.factor_confluence_scores["daily"]["tier"] == "D+"

    def test_all_six_factors_across_timeframes(self):
        """All 6 factors triggered across 3 timeframes."""
        all_signals = {
            "weekly": ["Vegas Alignment", "Round Bottom"],
            "daily": ["EMA12 Lift-Off", "Big Bullish Candle"],
            "4hour": ["Triangle Consolidation", "Volume Surge"],
        }
        tf_map = {
            "weekly": {
                "triggered_factors": ["F1", "F3"],
                "triggered_signals": ["Vegas Alignment", "Round Bottom"],
                "details": {
                    "F1": {"triggered": True, "details": {"mode_quality_tier": "A"}},
                    "F3": {"triggered": True, "details": {}},
                },
            },
            "daily": {
                "triggered_factors": ["F2", "F5"],
                "triggered_signals": ["EMA12 Lift-Off", "Big Bullish Candle"],
                "details": {
                    "F2": {"triggered": True, "details": {}},
                    "F5": {"triggered": True, "details": {}},
                },
            },
            "4hour": {
                "triggered_factors": ["F4", "F6"],
                "triggered_signals": ["Triangle Consolidation", "Volume Surge"],
                "details": {
                    "F4": {"triggered": True, "details": {}},
                    "F6": {"triggered": True, "details": {}},
                },
            },
        }

        score = calculate_score(all_signals, tf_map)

        # Each factor triggered on 1 timeframe only:
        # F1: 4 * 2.5 = 10
        # F3: 4 * 2.5 = 10
        # F2: 3 * 1.5 = 4.5
        # F5: 4 * 1.5 = 6
        # F4: 1 * 1.0 = 1
        # F6: 1 * 1.0 = 1
        # Total base: 10 + 10 + 4.5 + 6 + 1 + 1 = 32.5

        # No confluence tiers (each timeframe has only 2 factors)
        # Pre-multiplier: 32.5 + 0 = 32.5

        # Cross-timeframe coverage: all 6 factors present = 10x multiplier
        # Total: 32.5 * 10 = 325
        assert score.cross_timeframe_all_factor_coverage_multiplier == 10.0
        assert score.total_score == 325.0

    def test_factor_triggered_multiple_timeframes(self):
        """F3 triggered on both weekly and daily."""
        all_signals = {
            "weekly": ["Round Bottom"],
            "daily": ["Round Bottom"],
            "4hour": [],
        }
        tf_map = {
            "weekly": {
                "triggered_factors": ["F3"],
                "details": {"F3": {"triggered": True, "details": {}}},
            },
            "daily": {
                "triggered_factors": ["F3"],
                "details": {"F3": {"triggered": True, "details": {}}},
            },
            "4hour": {
                "triggered_factors": [],
                "details": {},
            },
        }

        score = calculate_score(all_signals, tf_map)

        # F3 triggered on weekly + daily
        # Base score: 4, multiplier: 4.5 (weekly + daily) = 18
        assert score.base_timeframe_scores["F3"]["score"] == 18.0
        assert score.base_timeframe_scores["F3"]["timeframe_multiplier"] == 4.5
