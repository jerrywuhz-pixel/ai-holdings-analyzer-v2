"""
数据源注册与健康检测服务

统一管理多个行情数据源（Futu OpenD / Yahoo Finance / Tushare / AkShare），
实现智能路由、Redis 缓存集成和健康检查。
"""

import asyncio
from typing import Any, Dict, List, Optional

from adapters.yahoo import YahooFinanceAdapter
from adapters.tushare import TushareAdapter
from adapters.akshare import AkShareAdapter
from adapters.longbridge import LongbridgeAdapter
from adapters.futu import FutuAdapter
from services.cache import QuoteCache


class DataSourceRegistry:
    """
    数据源注册表。

    维护多个适配器实例，根据股票代码自动推断市场并选择最优数据源，
    同时集成 QuoteCache 实现查询结果缓存。
    """

    # 各市场的默认数据源优先级（越靠前越优先）。
    # Futu OpenD 具备实时行情和高批量快照能力，适合持仓页/持仓分析的多标的刷新；
    # 未安装 SDK、OpenD 未运行或权限不足时，会自动 fallback 到原有数据源。
    _CN_PRIORITY = ["futu", "tushare", "yahoo", "akshare"]
    _HK_PRIORITY = ["futu", "longbridge", "yahoo", "tushare", "akshare"]
    _US_PRIORITY = ["futu", "yahoo", "longbridge", "tushare", "akshare"]

    def __init__(self):
        self._adapters = {
            "yahoo": YahooFinanceAdapter(),
            "tushare": TushareAdapter(),
            "akshare": AkShareAdapter(),
            "longbridge": LongbridgeAdapter(),
            "futu": FutuAdapter(),
        }
        self._cache = QuoteCache()

    @staticmethod
    def _infer_market(symbol: str) -> str:
        """根据业务层 symbol 前缀推断市场。"""
        s = symbol.strip().upper()
        if s.startswith(("SH", "SZ")):
            return "CN"
        if s.startswith("HK"):
            return "HK"
        return "US"

    def _get_priority(self, symbol: str, prefer: Optional[str] = None) -> List[str]:
        """确定数据源尝试优先级。"""
        if prefer and prefer in self._adapters:
            return [prefer]

        market = self._infer_market(symbol)
        if market == "CN":
            return self._CN_PRIORITY
        if market == "HK":
            return self._HK_PRIORITY
        return self._US_PRIORITY

    async def get_quote(self, symbol: str, prefer: Optional[str] = None) -> Dict[str, Any]:
        """
        获取单只股票实时行情，优先读缓存，未命中按优先级请求数据源。

        新增字段说明：
            - source_fallback: bool  是否使用了非首选数据源
            - cached: bool            是否来自缓存（含 stale）
            - stale: bool             是否来自 stale 缓存兜底

        Args:
            symbol: 业务层股票代码，如 "SH600519"、"AAPL"
            prefer: 强制指定数据源（"futu" / "yahoo" / "tushare" / "akshare" / "longbridge"），可选

        Returns:
            标准化行情字典（可能携带 source_fallback / cached / stale 字段）

        Raises:
            RuntimeError: 所有数据源及 stale 缓存均失败
        """
        # 1. 读缓存
        cache_key = QuoteCache.build_key(symbol)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            cached["cached"] = True
            cached["stale"] = False
            return cached

        # 2. 按优先级尝试各数据源
        priority = self._get_priority(symbol, prefer)
        last_error = ""
        first_source = priority[0] if priority else None

        for source in priority:
            adapter = self._adapters.get(source)
            if adapter is None:
                continue
            try:
                quote = await adapter.fetch_quote(symbol)
                # 复制后再添加元数据，避免副作用
                quote = dict(quote)
                quote["source_fallback"] = source != first_source
                quote["cached"] = False
                quote["stale"] = False
                # 写入缓存后返回
                await self._cache.set(cache_key, quote, ttl=60)
                await self.record_source_health(source, success=True)
                return quote
            except Exception as exc:
                last_error = f"{source}: {exc}"
                await self.record_source_health(source, success=False, error=str(exc))
                continue

        # 3. 所有数据源失败，尝试 stale 缓存兜底
        stale_data, is_stale = await self._cache.get_with_stale(cache_key)
        if stale_data is not None:
            stale_data = dict(stale_data)
            stale_data["cached"] = True
            stale_data["stale"] = True
            stale_data["source"] = stale_data.get("source", "unknown") + "_stale"
            return stale_data

        raise RuntimeError(f"All data sources failed for {symbol}. Last error: {last_error}")

    async def fetch_batch_quotes(
        self, symbols: List[str], prefer: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量获取行情。

        先批量读缓存，未命中的 symbol 再并发请求数据源。

        Args:
            symbols: 业务层股票代码列表
            prefer:  强制指定数据源，可选

        Returns:
            {业务层 symbol: 标准化行情字典} 的映射，失败的 symbol 不包含在内
        """
        results: Dict[str, Dict[str, Any]] = {}
        uncached: List[str] = []

        # 批量读缓存
        for sym in symbols:
            cache_key = QuoteCache.build_key(sym)
            cached = await self._cache.get(cache_key)
            if cached is not None:
                enriched = dict(cached)
                enriched.setdefault("cached", True)
                enriched.setdefault("stale", False)
                results[sym] = enriched
            else:
                uncached.append(sym)

        # 先按首选数据源分组批量请求。Futu/Longbridge 这类源的批量能力对持仓页
        # 多标的刷新更重要；失败或缺失的 symbol 按下一优先级继续批量降级，
        # 避免在 Futu 不可用时对每个持仓重复尝试 Futu 单查。
        remaining = {sym.upper(): sym for sym in uncached}
        attempted: Dict[str, set[str]] = {sym.upper(): set() for sym in uncached}

        while remaining:
            grouped: Dict[str, List[str]] = {}
            for sym_key, original_sym in list(remaining.items()):
                next_source = None
                for source in self._get_priority(original_sym, prefer):
                    if source not in attempted[sym_key]:
                        next_source = source
                        break
                if next_source is not None:
                    grouped.setdefault(next_source, []).append(original_sym)

            if not grouped:
                break

            for source, group_symbols in grouped.items():
                adapter = self._adapters.get(source)
                for sym in group_symbols:
                    attempted[sym.upper()].add(source)
                if adapter is None:
                    continue

                try:
                    batch_quotes = await adapter.fetch_batch_quotes(group_symbols)
                except Exception as exc:
                    await self.record_source_health(source, success=False, error=str(exc))
                    continue

                await self.record_source_health(source, success=True)
                normalized_batch = {key.upper(): value for key, value in batch_quotes.items()}
                for sym in group_symbols:
                    sym_key = sym.upper()
                    quote = normalized_batch.get(sym_key)
                    if quote is None:
                        continue
                    enriched = dict(quote)
                    first_source = self._get_priority(sym, prefer)[0]
                    enriched["source_fallback"] = source != first_source
                    enriched["cached"] = False
                    enriched["stale"] = False
                    results[sym] = enriched
                    remaining.pop(sym_key, None)
                    cache_key = QuoteCache.build_key(sym)
                    await self._cache.set(cache_key, enriched, ttl=60)

        # 批量源全部失败后，尝试 stale 缓存兜底。
        for sym_key, sym in list(remaining.items()):
            cache_key = QuoteCache.build_key(sym)
            stale_data, is_stale = await self._cache.get_with_stale(cache_key)
            if stale_data is not None:
                stale_data = dict(stale_data)
                stale_data["cached"] = True
                stale_data["stale"] = is_stale
                stale_data["source"] = stale_data.get("source", "unknown") + "_stale"
                results[sym] = stale_data

        return results

    async def search_symbols(self, keyword: str, market: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜索股票代码。

        优先使用 Yahoo Finance 搜索，失败返回空列表。
        """
        try:
            return await self._adapters["yahoo"].search_symbols(keyword, market=market)
        except Exception:
            return []

    async def record_source_health(self, source: str, success: bool, error: str = "") -> None:
        """
        记录数据源健康状态。

        当前仅打印日志，后续可扩展为写入数据库或时序存储。

        Args:
            source:  数据源标识（如 "yahoo" / "longbridge"）
            success: 本次请求是否成功
            error:   失败时的错误信息
        """
        status_str = "OK" if success else "FAIL"
        print(f"[DataSourceHealth] source={source} status={status_str} error={error}")

    async def health_check(self) -> Dict[str, bool]:
        """
        检测各数据源可用性。

        对每个数据源并行尝试一次真实请求，返回布尔状态映射。
        """
        async def _check_one(name: str, sym: str) -> tuple[str, bool]:
            try:
                await self._adapters[name].fetch_quote(sym)
                return name, True
            except Exception:
                return name, False

        checks = [
            _check_one("yahoo", "AAPL"),
            _check_one("tushare", "SH600519"),
            _check_one("akshare", "SH600519"),
            _check_one("longbridge", "HK00700"),
            _check_one("futu", "AAPL"),
        ]
        results = await asyncio.gather(*checks)
        return {name: ok for name, ok in results}
