import unittest
import sys
import types
from unittest.mock import AsyncMock, patch

fake_redis_asyncio = types.SimpleNamespace(
    Redis=object,
    from_url=lambda *args, **kwargs: None,
)
sys.modules.setdefault("redis", types.SimpleNamespace(asyncio=fake_redis_asyncio))
sys.modules.setdefault("redis.asyncio", fake_redis_asyncio)

from services.registry import DataSourceRegistry


class RegistryFutuPriorityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = DataSourceRegistry()

    def test_futu_is_top_realtime_priority_for_portfolio_markets(self):
        self.assertEqual(self.registry._get_priority("AAPL")[0], "futu")
        self.assertEqual(self.registry._get_priority("HK00700")[0], "futu")
        self.assertEqual(self.registry._get_priority("SH600519")[0], "futu")

    def test_prefer_source_still_overrides_priority(self):
        self.assertEqual(self.registry._get_priority("AAPL", prefer="yahoo"), ["yahoo"])

    async def test_get_quote_falls_back_when_futu_unavailable(self):
        yahoo_quote = {"symbol": "AAPL", "price": 191.24, "market": "US"}

        with patch.object(self.registry._cache, "get", new_callable=AsyncMock, return_value=None):
            with patch.object(
                self.registry._adapters["futu"],
                "fetch_quote",
                new_callable=AsyncMock,
                side_effect=RuntimeError("futu unavailable"),
            ) as mock_futu:
                with patch.object(
                    self.registry._adapters["yahoo"],
                    "fetch_quote",
                    new_callable=AsyncMock,
                    return_value=yahoo_quote,
                ) as mock_yahoo:
                    with patch.object(self.registry._cache, "set", new_callable=AsyncMock):
                        result = await self.registry.get_quote("AAPL")

        self.assertEqual(result["symbol"], "AAPL")
        self.assertTrue(result["source_fallback"])
        mock_futu.assert_awaited_once_with("AAPL")
        mock_yahoo.assert_awaited_once_with("AAPL")

    async def test_batch_uses_futu_batch_then_batch_fallbacks(self):
        batch_quote = {"AAPL": {"symbol": "AAPL", "price": 191.24, "market": "US"}}
        fallback_quote = {"symbol": "MSFT", "price": 420.0, "market": "US"}

        with patch.object(self.registry._cache, "get", new_callable=AsyncMock, return_value=None):
            with patch.object(self.registry._cache, "set", new_callable=AsyncMock) as mock_cache_set:
                with patch.object(
                    self.registry._adapters["futu"],
                    "fetch_batch_quotes",
                    new_callable=AsyncMock,
                    return_value=batch_quote,
                ) as mock_futu_batch:
                    with patch.object(
                        self.registry._adapters["yahoo"],
                        "fetch_batch_quotes",
                        new_callable=AsyncMock,
                        return_value={"MSFT": fallback_quote},
                    ) as mock_yahoo_batch:
                        result = await self.registry.fetch_batch_quotes(["AAPL", "MSFT"])

        self.assertEqual(set(result.keys()), {"AAPL", "MSFT"})
        mock_futu_batch.assert_awaited_once_with(["AAPL", "MSFT"])
        mock_yahoo_batch.assert_awaited_once_with(["MSFT"])
        self.assertGreaterEqual(mock_cache_set.await_count, 1)


if __name__ == "__main__":
    unittest.main()
