"""
Futu OpenD real-time quote adapter.

The adapter is optional: if ``futu-api`` is not installed or Futu OpenD is not
running/configured, calls fail fast and the registry falls back to other data
sources.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from adapters.base import DataSourceAdapter

try:
    import futu as _futu

    _HAS_FUTU = True
except ImportError:
    _futu = None
    _HAS_FUTU = False


def to_futu_symbol(symbol: str) -> str:
    """
    Convert business symbol to Futu OpenD code.

    Examples:
        AAPL -> US.AAPL
        HK00700 -> HK.00700
        SH600519 -> SH.600519
        SZ000001 -> SZ.000001
    """
    s = symbol.strip().upper()
    if s.startswith("HK"):
        return f"HK.{s[2:]}"
    if s.startswith("SH"):
        return f"SH.{s[2:]}"
    if s.startswith("SZ"):
        return f"SZ.{s[2:]}"
    if "." in s:
        return s
    return f"US.{s}"


def to_business_symbol(futu_symbol: str) -> str:
    """Convert Futu OpenD code to business symbol."""
    code = futu_symbol.strip().upper()
    if code.startswith("US."):
        return code[3:]
    if code.startswith("HK."):
        return f"HK{code[3:].zfill(5)}"
    if code.startswith("SH."):
        return f"SH{code[3:]}"
    if code.startswith("SZ."):
        return f"SZ{code[3:]}"
    return code


def _infer_market(futu_symbol: str) -> str:
    code = futu_symbol.strip().upper()
    if code.startswith("HK."):
        return "HK"
    if code.startswith(("SH.", "SZ.")):
        return "CN"
    return "US"


def _exchange_for(futu_symbol: str) -> str:
    code = futu_symbol.strip().upper()
    if code.startswith("HK."):
        return "HKEX"
    if code.startswith("SH."):
        return "SSE"
    if code.startswith("SZ."):
        return "SZSE"
    return "US"


def _currency_for(futu_symbol: str) -> str:
    market = _infer_market(futu_symbol)
    if market == "HK":
        return "HKD"
    if market == "CN":
        return "CNY"
    return "USD"


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _parse_update_timestamp(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value) if value < 1e11 else int(value / 1000)
    if isinstance(value, str) and value:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return int(datetime.strptime(value, fmt).timestamp())
            except ValueError:
                continue
    return int(time.time())


def _normalize_snapshot_row(row: Any) -> Dict[str, Any]:
    futu_symbol = str(_row_get(row, "code", ""))
    price = _row_get(row, "last_price")
    prev_close = _row_get(row, "prev_close_price")

    price_float = float(price) if price is not None else None
    prev_close_float = float(prev_close) if prev_close not in (None, 0) else None
    change = None
    change_rate = None
    if price_float is not None and prev_close_float:
        change = round(price_float - prev_close_float, 4)
        change_rate = round(change / prev_close_float * 100, 2)

    return {
        "symbol": to_business_symbol(futu_symbol),
        "name": _row_get(row, "stock_name", "") or _row_get(row, "name", "") or "",
        "market": _infer_market(futu_symbol),
        "exchange": _exchange_for(futu_symbol),
        "price": round(price_float, 4) if price_float is not None else None,
        "change": change,
        "change_rate": change_rate,
        "currency": _currency_for(futu_symbol),
        "timestamp": _parse_update_timestamp(_row_get(row, "update_time")),
        "source": "futu",
        "realtime": True,
        "delayed": False,
    }


class FutuAdapter(DataSourceAdapter):
    """Futu OpenD adapter for CN/HK/US real-time portfolio quotes."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        batch_size: Optional[int] = None,
    ):
        self.host = host or os.getenv("FUTU_OPEND_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("FUTU_OPEND_PORT", "11111"))
        self.batch_size = int(batch_size or os.getenv("FUTU_BATCH_SIZE", "200"))
        self._available = _HAS_FUTU
        self._ctx: Optional[Any] = None

    def _get_context(self) -> Any:
        if not self._available or _futu is None:
            raise RuntimeError("futu-api SDK not installed")
        if self._ctx is None:
            self._ctx = _futu.OpenQuoteContext(host=self.host, port=self.port)
        return self._ctx

    async def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        results = await self.fetch_batch_quotes([symbol])
        quote = results.get(symbol.strip().upper())
        if not quote:
            raise RuntimeError(f"No Futu quote returned for {symbol}")
        return quote

    async def fetch_batch_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        if not self._available or _futu is None:
            raise RuntimeError("futu-api SDK not installed")
        if not symbols:
            return {}

        ctx = self._get_context()
        results: Dict[str, Dict[str, Any]] = {}
        normalized_symbols = [sym.strip().upper() for sym in symbols]
        futu_symbols = [to_futu_symbol(sym) for sym in normalized_symbols]

        for start in range(0, len(futu_symbols), self.batch_size):
            chunk = futu_symbols[start:start + self.batch_size]
            ret_code, frame = await asyncio.to_thread(ctx.get_market_snapshot, chunk)
            if ret_code != getattr(_futu, "RET_OK", 0):
                raise RuntimeError(f"Futu snapshot error: {frame}")
            if getattr(frame, "empty", False):
                continue

            for _idx, row in frame.iterrows():
                quote = _normalize_snapshot_row(row)
                results[quote["symbol"]] = quote

        return results

    async def search_symbols(self, keyword: str, market: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def close(self) -> None:
        if self._ctx is not None:
            try:
                self._ctx.close()
            finally:
                self._ctx = None
