import importlib
import unittest


models = importlib.import_module(
    "openclaw.skills.quant-options-strategy.sellput_models"
)
scorecard = importlib.import_module(
    "openclaw.skills.quant-options-strategy.sellput_scorecard"
)


OpenScoreInput = models.OpenScoreInput
HoldScoreInput = models.HoldScoreInput
ScoreEngine = scorecard.ScoreEngine


def strong_open_input(**overrides):
    data = {
        "symbol": "AAPL",
        "strike": 200.0,
        "expiry": "2026-06-19",
        "underlying_price": 235.0,
        "premium": 7.5,
        "dte": 40,
        "delta": -0.14,
        "iv_rank": 78,
        "iv_percentile": 85,
        "iv_hv_ratio": 1.35,
        "annualized_premium_yield": 32,
        "premium_to_max_loss_pct": 5.5,
        "premium_to_account_pct": 0.7,
        "bid_ask_spread_pct": 3,
        "contract_open_interest": 8000,
        "contract_volume": 900,
        "revenue_growth_yoy": 18,
        "eps_growth_yoy": 25,
        "fcf_positive": True,
        "fcf_growing": True,
        "debt_to_equity": 0.3,
        "price_vs_ma200_pct": 12,
        "ma_alignment": "bullish",
        "rsi14": 52,
        "max_drawdown_30d_pct": 4,
        "market_cap_b": 2800,
        "avg_volume_20d_m": 55,
        "chain_open_interest": 250000,
        "earnings_before_expiry": False,
        "earnings_days_before_expiry": None,
        "ex_dividend_before_expiry": False,
        "major_event_before_expiry": False,
        "theta_to_premium_pct": 3.5,
        "vega_pnl_impact_pct_per_iv_point": 1.0,
        "gamma_risk": "low",
        "vix": 20,
        "vix_term_structure": "contango",
        "spy_trend": "bullish",
        "market_breadth_pct_above_ma200": 65,
        "rate_environment": "stable",
    }
    data.update(overrides)
    return OpenScoreInput(**data)


def weak_open_input(**overrides):
    data = {
        "symbol": "XYZ",
        "strike": 98.0,
        "expiry": "2026-05-15",
        "underlying_price": 100.0,
        "premium": 1.0,
        "dte": 5,
        "delta": -0.46,
        "iv_rank": 20,
        "iv_percentile": 25,
        "iv_hv_ratio": 0.8,
        "annualized_premium_yield": 4,
        "premium_to_max_loss_pct": 0.8,
        "premium_to_account_pct": 0.1,
        "bid_ask_spread_pct": 25,
        "contract_open_interest": 50,
        "contract_volume": 3,
        "revenue_growth_yoy": -5,
        "eps_growth_yoy": -10,
        "fcf_positive": False,
        "fcf_growing": False,
        "debt_to_equity": 3.0,
        "price_vs_ma200_pct": -15,
        "ma_alignment": "bearish",
        "rsi14": 75,
        "max_drawdown_30d_pct": 16,
        "market_cap_b": 1.5,
        "avg_volume_20d_m": 0.05,
        "chain_open_interest": 5000,
        "earnings_before_expiry": True,
        "earnings_days_before_expiry": 3,
        "ex_dividend_before_expiry": True,
        "major_event_before_expiry": True,
        "theta_to_premium_pct": 0.4,
        "vega_pnl_impact_pct_per_iv_point": 4.5,
        "gamma_risk": "high",
        "vix": 42,
        "vix_term_structure": "backwardation",
        "spy_trend": "bearish",
        "market_breadth_pct_above_ma200": 30,
        "rate_environment": "aggressive_hiking",
    }
    data.update(overrides)
    return OpenScoreInput(**data)


class SellPutScorecardTests(unittest.TestCase):
    def setUp(self):
        self.engine = ScoreEngine()

    def test_strong_open_score_is_confident_sell(self):
        result = self.engine.score_open(strong_open_input())

        self.assertGreaterEqual(result.total_score, 90)
        self.assertEqual(result.grade, "A")
        self.assertEqual(result.action, "SELL_CONFIDENT")
        self.assertEqual(result.dimension_scores["underlying_quality"], 25)
        self.assertEqual(result.dimension_scores["option_value"], 30)

    def test_mid_open_score_is_limited_sell(self):
        result = self.engine.score_open(
            strong_open_input(
                iv_rank=45,
                iv_percentile=55,
                iv_hv_ratio=1.15,
                annualized_premium_yield=15,
                premium_to_max_loss_pct=3.2,
                otm_pct=None,
                delta=-0.24,
                dte=55,
                vix=13,
            )
        )

        self.assertGreaterEqual(result.total_score, 70)
        self.assertLess(result.total_score, 90)
        self.assertEqual(result.grade, "B")
        self.assertEqual(result.action, "SELL_LIMITED")

    def test_weak_open_score_is_avoid_with_warnings(self):
        result = self.engine.score_open(weak_open_input())

        self.assertLess(result.total_score, 70)
        self.assertEqual(result.grade, "C")
        self.assertEqual(result.action, "AVOID")
        self.assertIn("bid-ask spread too wide", result.warnings)
        self.assertIn("earnings before expiry", result.warnings)
        self.assertIn("delta assignment risk too high", result.warnings)

    def test_hold_score_take_profit(self):
        hold = HoldScoreInput(
            symbol="AAPL",
            strike=200.0,
            underlying_price=238.0,
            premium_collected=8.0,
            current_option_price=1.0,
            dte_remaining=12,
            dte_original=42,
            current_iv_rank=35,
            open_iv_rank=65,
            iv_change_pct=-25,
            vix_change="improved",
            trend_change="improved",
            has_new_negative_event=False,
            position_account_pct=4,
            margin_usage_pct=20,
            roll_quality="profitable",
            event_before_expiry=False,
        )

        result = self.engine.score_hold(hold)

        self.assertGreaterEqual(result.total_score, 90)
        self.assertEqual(result.grade, "A")
        self.assertEqual(result.action, "TAKE_PROFIT")

    def test_hold_score_below_70_requests_adjustment(self):
        hold = HoldScoreInput(
            symbol="XYZ",
            strike=100.0,
            underlying_price=96.0,
            premium_collected=4.0,
            current_option_price=8.5,
            dte_remaining=28,
            dte_original=42,
            current_iv_rank=80,
            open_iv_rank=45,
            iv_change_pct=35,
            vix_change="worse",
            trend_change="bearish",
            has_new_negative_event=True,
            position_account_pct=22,
            margin_usage_pct=70,
            roll_quality="not_available",
            event_before_expiry=True,
        )

        result = self.engine.score_hold(hold)

        self.assertLess(result.total_score, 70)
        self.assertEqual(result.grade, "C")
        self.assertEqual(result.action, "ADJUST_OR_HEDGE")

    def test_scan_chain_filters_and_sorts_candidates(self):
        candidates = self.engine.scan_chain(
            [
                weak_open_input(symbol="LOW"),
                strong_open_input(symbol="BEST", iv_rank=90),
                strong_open_input(symbol="OK", iv_rank=52, annualized_premium_yield=22),
            ],
            min_score=70,
        )

        self.assertEqual([item.symbol for item in candidates], ["BEST", "OK"])
        self.assertGreaterEqual(candidates[0].total_score, candidates[1].total_score)


if __name__ == "__main__":
    unittest.main()
