import pytest

from core import base
from core.base import TransportAPIError, clear_cache, fetch_json, post_json


class FakeResponse:
    def __init__(self, status, body=None, text=""):
        self.status = status
        self._body = body
        self._text = text

    async def text(self):
        return self._text

    async def json(self, content_type=None):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)


@pytest.fixture
def session(monkeypatch):
    holder = {}

    def install(*responses):
        holder["s"] = FakeSession(responses)
        return holder["s"]

    async def get_session():
        return holder["s"]

    async def no_backoff(attempt):
        return None

    monkeypatch.setattr(base, "get_session", get_session)
    monkeypatch.setattr(base, "_backoff", no_backoff)
    clear_cache()
    yield install
    clear_cache()


class TestFetchJson:

    @pytest.mark.unit
    async def test_http_error_keeps_message(self, session):
        session(FakeResponse(404, text="not found"))
        with pytest.raises(TransportAPIError) as exc:
            await fetch_json("https://example.test/x")
        # must not be re-wrapped as "Unexpected error: ..."
        assert str(exc.value) == "HTTP 404: not found"

    @pytest.mark.unit
    async def test_retries_on_rate_limit(self, session):
        s = session(FakeResponse(429), FakeResponse(503), FakeResponse(200, {"ok": True}))
        assert await fetch_json("https://example.test/x", {"a": 1}) == {"ok": True}
        assert len(s.requests) == 3
        assert s.requests[0][1] == "https://example.test/x?a=1"

    @pytest.mark.unit
    async def test_gives_up_after_tries(self, session):
        s = session(FakeResponse(500, text="e1"), FakeResponse(500, text="e2"))
        with pytest.raises(TransportAPIError, match="HTTP 500: e2"):
            await fetch_json("https://example.test/x", tries=2)
        assert len(s.requests) == 2

    @pytest.mark.unit
    async def test_no_retry_on_client_error(self, session):
        s = session(FakeResponse(400, text="bad"), FakeResponse(200, {"ok": True}))
        with pytest.raises(TransportAPIError, match="HTTP 400"):
            await fetch_json("https://example.test/x")
        assert len(s.requests) == 1

    @pytest.mark.unit
    async def test_post_json_sends_body(self, session):
        s = session(FakeResponse(200, {"data": {}}))
        await post_json("https://example.test/gql", {"query": "q"}, headers={"X": "1"})
        method, _, kwargs = s.requests[0]
        assert method == "POST"
        assert kwargs["json"] == {"query": "q"}
        assert kwargs["headers"]["X"] == "1"


class TestCache:

    @pytest.mark.unit
    async def test_no_cache_by_default(self, session):
        s = session(FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2}))
        assert await fetch_json("https://example.test/x") == {"n": 1}
        assert await fetch_json("https://example.test/x") == {"n": 2}
        assert len(s.requests) == 2

    @pytest.mark.unit
    async def test_cache_hit_within_ttl(self, session):
        s = session(FakeResponse(200, {"n": 1}))
        first = await fetch_json("https://example.test/x", {"q": "a"}, cache_ttl=60)
        first["n"] = 99  # callers must not be able to corrupt the cache
        assert await fetch_json("https://example.test/x", {"q": "a"}, cache_ttl=60) == {"n": 1}
        assert len(s.requests) == 1

    @pytest.mark.unit
    async def test_cache_keyed_by_params_and_body(self, session):
        s = session(*(FakeResponse(200, {"n": i}) for i in range(3)))
        await fetch_json("https://example.test/x", {"q": "a"}, cache_ttl=60)
        await fetch_json("https://example.test/x", {"q": "b"}, cache_ttl=60)
        await post_json("https://example.test/x", {"q": "a"}, cache_ttl=60)
        assert len(s.requests) == 3

    @pytest.mark.unit
    async def test_cache_expires(self, session, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(base.time, "monotonic", lambda: now[0])
        s = session(FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2}))
        await fetch_json("https://example.test/x", cache_ttl=30)
        now[0] += 31
        assert await fetch_json("https://example.test/x", cache_ttl=30) == {"n": 2}
        assert len(s.requests) == 2

    @pytest.mark.unit
    async def test_errors_not_cached(self, session):
        s = session(FakeResponse(404, text="nope"), FakeResponse(200, {"ok": True}))
        with pytest.raises(TransportAPIError):
            await fetch_json("https://example.test/x", cache_ttl=60)
        assert await fetch_json("https://example.test/x", cache_ttl=60) == {"ok": True}
        assert len(s.requests) == 2
