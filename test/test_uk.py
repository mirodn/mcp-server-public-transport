import pytest
from fastmcp import FastMCP
from tools.uk import register_uk_tools, TransportAPIError

@pytest.fixture
def mcp():
    return FastMCP("test-uk")

@pytest.fixture(autouse=True)
def mock_fetch_json(monkeypatch):
    async def dummy(url, params):
        return {"dummy": True}
    monkeypatch.setattr("tools.uk.fetch_json", dummy)
    return dummy

def get_tool_by_name(mcp, name):
    return next(t for t in register_uk_tools(mcp) if t.name == name) # type: ignore

class TestUKTools:

    @pytest.mark.unit
    async def test_uk_live_departures_invalid_code(self, mcp):
        fn = get_tool_by_name(mcp, "uk_live_departures")
        with pytest.raises(ValueError):
            await fn.fn("AB")  # type: ignore # too short

    @pytest.mark.unit
    async def test_uk_live_departures_no_credentials(self, mcp, monkeypatch):
        monkeypatch.delenv("UK_TRANSPORT_APP_ID", raising=False)
        monkeypatch.delenv("UK_TRANSPORT_API_KEY", raising=False)
        fn = get_tool_by_name(mcp, "uk_live_departures")
        with pytest.raises(TransportAPIError):
            await fn.fn("PAD") # type: ignore

    @pytest.mark.unit
    async def test_uk_live_departures_success(self, mcp, monkeypatch):
        monkeypatch.setenv("UK_TRANSPORT_APP_ID", "app")
        monkeypatch.setenv("UK_TRANSPORT_API_KEY", "key")
        fn = get_tool_by_name(mcp, "uk_live_departures")
        result = await fn.fn("PAD") # type: ignore
        assert result == {"dummy": True}
