import importlib
import unittest
from unittest.mock import AsyncMock


models = importlib.import_module(
    "openclaw.skills.quant-options-strategy.sellput_models"
)
service_mod = importlib.import_module(
    "openclaw.skills.quant-options-strategy.hermes_sellput"
)


OpenScoreInput = models.OpenScoreInput
HoldScoreInput = models.HoldScoreInput
HermesSellPutService = service_mod.HermesSellPutService
FutuSellPutDataSource = service_mod.FutuSellPutDataSource


class HermesSellPutServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = HermesSellPutService()

    def test_evaluate_open_returns_structured_payload_and_report(self):
        payload = {
            "symbol": "AAPL",
            "strike": 200,
            "expiry": "2026-06-19",
            "underlying_price": 235,
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

        result = self.service.evaluate_open(payload)

        self.assertTrue(result["ok"])
        self.assertEqual(result["strategy"], "sell_put_open")
        self.assertEqual(result["score"]["action"], "SELL_CONFIDENT")
        self.assertIn("## Hermes Sell Put Open Score", result["formatted_report"])
        self.assertIn("AAPL", result["formatted_report"])

    def test_evaluate_open_records_futu_market_data_when_supplied(self):
        payload = self._base_open_payload()
        market_data = {
            "source": "futu",
            "underlying_quote": {
                "symbol": "AAPL",
                "price": 240.5,
                "timestamp": 1777138205,
                "source": "futu",
            },
        }

        result = self.service.evaluate_open(payload, market_data=market_data)

        self.assertTrue(result["ok"])
        self.assertEqual(result["market_data"]["source"], "futu")
        self.assertEqual(result["market_data"]["underlying_quote"]["price"], 240.5)
        self.assertIn("Market Data", result["formatted_report"])
        self.assertIn("futu", result["formatted_report"])

    def test_scan_candidates_accepts_dicts_and_sorts_scores(self):
        strong = self._base_open_payload(symbol="BEST", iv_rank=90)
        okay = self._base_open_payload(symbol="OK", iv_rank=52, annualized_premium_yield=22)
        weak = self._base_open_payload(
            symbol="LOW",
            iv_rank=15,
            iv_percentile=20,
            iv_hv_ratio=0.75,
            annualized_premium_yield=4,
            premium_to_max_loss_pct=0.5,
            premium_to_account_pct=0.1,
            delta=-0.5,
            dte=5,
            bid_ask_spread_pct=30,
            contract_open_interest=40,
            contract_volume=2,
            revenue_growth_yoy=-8,
            eps_growth_yoy=-20,
            fcf_positive=False,
            fcf_growing=False,
            debt_to_equity=3.5,
            price_vs_ma200_pct=-20,
            ma_alignment="bearish",
            rsi14=76,
            max_drawdown_30d_pct=18,
            market_cap_b=1,
            avg_volume_20d_m=0.03,
            chain_open_interest=3000,
            earnings_before_expiry=True,
            earnings_days_before_expiry=4,
            ex_dividend_before_expiry=True,
            major_event_before_expiry=True,
            theta_to_premium_pct=0.5,
            vega_pnl_impact_pct_per_iv_point=5,
            gamma_risk="high",
            vix=45,
            vix_term_structure="backwardation",
            spy_trend="bearish",
            market_breadth_pct_above_ma200=25,
            rate_environment="aggressive_hiking",
        )

        result = self.service.scan_candidates([weak, okay, strong], min_score=70)

        self.assertTrue(result["ok"])
        self.assertEqual([item["symbol"] for item in result["candidates"]], ["BEST", "OK"])
        self.assertIn("## Hermes Sell Put Candidate Scan", result["formatted_report"])

    def test_evaluate_hold_returns_take_profit_report(self):
        payload = {
            "symbol": "AAPL",
            "strike": 200,
            "underlying_price": 238,
            "premium_collected": 8,
            "current_option_price": 1,
            "dte_remaining": 12,
            "dte_original": 42,
            "current_iv_rank": 35,
            "open_iv_rank": 65,
            "iv_change_pct": -25,
            "vix_change": "improved",
            "trend_change": "improved",
            "has_new_negative_event": False,
            "position_account_pct": 4,
            "margin_usage_pct": 20,
            "roll_quality": "profitable",
            "event_before_expiry": False,
        }

        result = self.service.evaluate_hold(payload)

        self.assertTrue(result["ok"])
        self.assertEqual(result["strategy"], "sell_put_hold")
        self.assertEqual(result["score"]["action"], "TAKE_PROFIT")
        self.assertIn("## Hermes Sell Put Hold Score", result["formatted_report"])

    def test_futu_data_source_fetches_underlying_quote_from_data_service(self):
        client = FakeHttpClient(
            {
                "ok": True,
                "data": {
                    "symbol": "AAPL",
                    "price": 240.5,
                    "source": "futu",
                    "timestamp": 1777138205,
                },
            }
        )
        data_source = FutuSellPutDataSource(
            data_service_url="http://data-service:8000",
            http_client_factory=lambda: client,
        )

        result = self._run(data_source.fetch_underlying_quote("AAPL"))

        self.assertEqual(result["price"], 240.5)
        self.assertEqual(client.calls, [("http://data-service:8000/api/quote/AAPL", {"source": "futu"})])

    def test_evaluate_open_with_futu_fills_missing_underlying_price(self):
        payload = self._base_open_payload()
        payload.pop("underlying_price")
        data_source = FakeFutuDataSource(
            {"symbol": "AAPL", "price": 240.5, "source": "futu", "timestamp": 1777138205}
        )
        service = HermesSellPutService(futu_data_source=data_source)

        result = self._run(service.evaluate_open_with_futu(payload))

        self.assertTrue(result["ok"])
        self.assertEqual(result["market_data"]["source"], "futu")
        self.assertEqual(result["market_data"]["underlying_quote"]["price"], 240.5)
        self.assertEqual(data_source.symbols, ["AAPL"])

    @staticmethod
    def _base_open_payload(**overrides):
        payload = {
            "symbol": "AAPL",
            "strike": 200,
            "expiry": "2026-06-19",
            "underlying_price": 235,
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
        payload.update(overrides)
        return payload

    @staticmethod
    def _run(coro):
        import asyncio

        return asyncio.run(coro)


class FakeFutuDataSource:
    def __init__(self, quote):
        self.quote = quote
        self.symbols = []

    async def fetch_underlying_quote(self, symbol):
        self.symbols.append(symbol)
        return self.quote


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self.calls.append((url, params))
        return FakeHttpResponse(self.payload)


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


if __name__ == "__main__":
    unittest.main()
