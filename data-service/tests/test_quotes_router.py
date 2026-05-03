from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from main import app
from services.symbol_resolver import SymbolInfo

client = TestClient(app)


def test_get_quote_success():
    mock_quote = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "market": "US",
        "exchange": "NASDAQ",
        "price": 191.24,
        "change": 1.4,
        "change_rate": 0.74,
        "currency": "USD",
        "timestamp": 1713806400,
    }

    with patch(
        "routers.quotes._registry.get_quote", new_callable=AsyncMock, return_value=mock_quote
    ):
        response = client.get("/api/quote/AAPL")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["symbol"] == "AAPL"
    assert data["data"]["price"] == 191.24


def test_get_quote_error():
    with patch(
        "routers.quotes._registry.get_quote",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Yahoo API error"),
    ):
        response = client.get("/api/quote/INVALID")

    assert response.status_code == 500
    data = response.json()
    assert data["detail"]["ok"] is False
    assert "Failed to fetch quote" in data["detail"]["message"]


def test_post_batch_quotes_success():
    mock_results = {
        "AAPL": {"symbol": "AAPL", "price": 191.24},
        "MSFT": {"symbol": "MSFT", "price": 418.97},
    }

    with patch(
        "routers.quotes._registry.fetch_batch_quotes",
        new_callable=AsyncMock,
        return_value=mock_results,
    ):
        response = client.post("/api/quote/batch", json={"symbols": ["AAPL", "MSFT", "INVALID"]})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "AAPL" in data["data"]
    assert "MSFT" in data["data"]
    assert "INVALID" in data["failed"]


def test_post_batch_quotes_empty():
    response = client.post("/api/quote/batch", json={"symbols": []})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["ok"] is False
    assert "empty" in data["detail"]["message"].lower()


def test_search_success():
    mock_results = [
        {"symbol": "AAPL", "name": "Apple Inc.", "market": "US", "exchange": "NASDAQ"},
    ]

    with patch(
        "routers.quotes._registry.search_symbols",
        new_callable=AsyncMock,
        return_value=mock_results,
    ):
        response = client.get("/api/search?q=apple&market=US")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["results"]) == 1
    assert data["results"][0]["symbol"] == "AAPL"


def test_search_error():
    with patch(
        "routers.quotes._registry.search_symbols",
        new_callable=AsyncMock,
        side_effect=RuntimeError("search failed"),
    ):
        response = client.get("/api/search?q=test")

    assert response.status_code == 500
    data = response.json()
    assert data["detail"]["ok"] is False


def test_resolve_endpoint_success():
    """Mock services.symbol_resolver.resolve_symbol returning a SymbolInfo, verify 200 response."""
    mock_info = SymbolInfo(
        symbol="SH600519",
        name_zh="贵州茅台",
        name_en="Kweichow Moutai Co.,Ltd.",
        market="CN",
        exchange="SH",
        provider_symbols={"tushare": "600519.SH", "yahoo": "600519.SS"},
        aliases=["茅台"],
    )

    with patch(
        "routers.quotes.resolve_symbol", new_callable=AsyncMock, return_value=mock_info
    ):
        response = client.get("/api/resolve/600519")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["symbol"] == "SH600519"
    assert data["data"]["name_zh"] == "贵州茅台"
    assert data["data"]["name_en"] == "Kweichow Moutai Co.,Ltd."
    assert data["data"]["market"] == "CN"
    assert data["data"]["exchange"] == "SH"
    assert data["data"]["provider_symbols"] == {"tushare": "600519.SH", "yahoo": "600519.SS"}


def test_resolve_endpoint_not_found():
    """Mock returning None, verify 404 response."""
    with patch(
        "routers.quotes.resolve_symbol", new_callable=AsyncMock, return_value=None
    ):
        response = client.get("/api/resolve/invalid123")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["ok"] is False
    assert "Could not resolve" in data["detail"]["message"]


def test_search_fallback_to_registry():
    """Mock _registry.search_symbols returning empty, mock resolver_search returning results."""
    mock_registry_results = []
    mock_resolver_results = [
        SymbolInfo(
            symbol="SH600519",
            name_zh="贵州茅台",
            market="CN",
            exchange="SH",
            provider_symbols={},
            aliases=["茅台"],
        ),
    ]

    with patch(
        "routers.quotes._registry.search_symbols",
        new_callable=AsyncMock,
        return_value=mock_registry_results,
    ):
        with patch(
            "routers.quotes.resolver_search",
            new_callable=AsyncMock,
            return_value=mock_resolver_results,
        ):
            response = client.get("/api/search?q=茅台")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["results"]) == 1
    assert data["results"][0]["symbol"] == "SH600519"
    assert data["results"][0]["name"] == "贵州茅台"
    assert data["results"][0]["market"] == "CN"
    assert data["results"][0]["exchange"] == "SH"
    assert data["results"][0]["type"] == "EQUITY"
