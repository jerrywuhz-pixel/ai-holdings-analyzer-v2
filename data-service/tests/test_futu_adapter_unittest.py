import sys
import types
import unittest
from unittest.mock import patch

from adapters import futu as futu_adapter


class FakeILoc:
    def __init__(self, row):
        self._row = row

    def __getitem__(self, index):
        if index != 0:
            raise IndexError(index)
        return self._row


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = len(rows) == 0
        self.iloc = FakeILoc(rows[0] if rows else {})

    def iterrows(self):
        for idx, row in enumerate(self._rows):
            yield idx, row


class FutuAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_symbol_mapping(self):
        self.assertEqual(futu_adapter.to_futu_symbol("AAPL"), "US.AAPL")
        self.assertEqual(futu_adapter.to_futu_symbol("HK00700"), "HK.00700")
        self.assertEqual(futu_adapter.to_futu_symbol("SH600519"), "SH.600519")
        self.assertEqual(futu_adapter.to_futu_symbol("SZ000001"), "SZ.000001")
        self.assertEqual(futu_adapter.to_business_symbol("US.AAPL"), "AAPL")
        self.assertEqual(futu_adapter.to_business_symbol("HK.00700"), "HK00700")
        self.assertEqual(futu_adapter.to_business_symbol("SH.600519"), "SH600519")
        self.assertEqual(futu_adapter.to_business_symbol("SZ.000001"), "SZ000001")

    async def test_unavailable_without_sdk(self):
        with patch("adapters.futu._HAS_FUTU", False):
            adapter = futu_adapter.FutuAdapter()

        with self.assertRaisesRegex(RuntimeError, "futu-api SDK not installed"):
            await adapter.fetch_quote("AAPL")

    async def test_fetch_quote_normalizes_snapshot(self):
        fake_module = types.SimpleNamespace(
            RET_OK=0,
            OpenQuoteContext=lambda host, port: FakeQuoteContext(
                rows=[
                    {
                        "code": "US.AAPL",
                        "stock_name": "Apple Inc.",
                        "last_price": 190.12,
                        "prev_close_price": 188.0,
                        "price_spread": 0.01,
                        "update_time": "2026-04-26 09:30:05",
                    }
                ]
            ),
        )

        with patch.dict(sys.modules, {"futu": fake_module}):
            with patch("adapters.futu._HAS_FUTU", True):
                with patch("adapters.futu._futu", fake_module):
                    adapter = futu_adapter.FutuAdapter(host="127.0.0.1", port=11111)
                    result = await adapter.fetch_quote("AAPL")

        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["market"], "US")
        self.assertEqual(result["exchange"], "US")
        self.assertEqual(result["name"], "Apple Inc.")
        self.assertEqual(result["price"], 190.12)
        self.assertEqual(result["change"], 2.12)
        self.assertEqual(result["change_rate"], 1.13)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["source"], "futu")
        self.assertFalse(result["delayed"])

    async def test_fetch_batch_quotes_uses_single_snapshot_call(self):
        context = FakeQuoteContext(
            rows=[
                {"code": "US.AAPL", "stock_name": "Apple Inc.", "last_price": 190.0, "prev_close_price": 188.0},
                {"code": "HK.00700", "stock_name": "Tencent", "last_price": 390.0, "prev_close_price": 380.0},
            ]
        )
        fake_module = types.SimpleNamespace(
            RET_OK=0,
            OpenQuoteContext=lambda host, port: context,
        )

        with patch.dict(sys.modules, {"futu": fake_module}):
            with patch("adapters.futu._HAS_FUTU", True):
                with patch("adapters.futu._futu", fake_module):
                    adapter = futu_adapter.FutuAdapter(host="127.0.0.1", port=11111)
                    results = await adapter.fetch_batch_quotes(["AAPL", "HK00700"])

        self.assertEqual(set(results.keys()), {"AAPL", "HK00700"})
        self.assertEqual(context.snapshot_calls, [["US.AAPL", "HK.00700"]])


class FakeQuoteContext:
    def __init__(self, rows):
        self.rows = rows
        self.snapshot_calls = []

    def get_market_snapshot(self, codes):
        self.snapshot_calls.append(codes)
        return 0, FakeFrame(self.rows)

    def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
