import json
import threading
import httpx
import pytest
from longbook_harness.backends import APIBackend, DemoBackend, sse_payloads
from longbook_harness.config import BackendConfig, GenerationOptions, normalize_api_url


def test_sse_records():
    lines = iter([":heartbeat", "data: {", 'data: "value":1}', "", "data: [DONE]"])
    assert list(sse_payloads(lines)) == ['{\n"value":1}', '[DONE]']


def test_api_stream_and_payload():
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            text='data: {"choices":[{"delta":{"content":"こん"}}]}\n\n'
                 'data: {"choices":[{"delta":{"content":"にちは"}}]}\n\n'
                 'data: [DONE]\n\n')
    backend = APIBackend(BackendConfig(kind="api", model="test"), httpx.MockTransport(handler))
    result = "".join(backend.stream([{"role": "user", "content": "hi"}],
                                   GenerationOptions(), threading.Event()))
    assert result == "こんにちは"
    assert seen[0]["stream"] is True and seen[0]["model"] == "test"
    backend.close()


def test_json_fallback():
    backend = APIBackend(BackendConfig(kind="api"), httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})))
    assert list(backend.stream([], GenerationOptions(), threading.Event())) == ["ok"]
    backend.close()


def test_error_does_not_leak_body():
    backend = APIBackend(BackendConfig(kind="api"), httpx.MockTransport(
        lambda request: httpx.Response(401, text="SECRET PROMPT AND KEY")))
    with pytest.raises(ValueError, match="HTTP 401") as exc:
        list(backend.stream([], GenerationOptions(), threading.Event()))
    assert "SECRET" not in str(exc.value)
    backend.close()


def test_cancel_before_generation():
    event = threading.Event()
    event.set()
    assert list(DemoBackend().stream([{"role": "user", "content": "x"}], GenerationOptions(), event)) == []


def test_config_redacts_key():
    assert "secret-value" not in repr(BackendConfig(api_key="secret-value"))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pw@host/v1",
                                 "https://host/v1?q=1", "http://remote.example/v1"])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        normalize_api_url(url)


def test_url_normalization():
    assert normalize_api_url("http://localhost:8080") == "http://localhost:8080/v1"
    assert normalize_api_url("https://server.example/v1/chat/completions") == "https://server.example/v1"
    assert normalize_api_url("http://192.168.1.2:8080/v1", True).endswith("/v1")


def test_no_redirect_following():
    backend = APIBackend(BackendConfig(kind="api", api_key="sensitive"), httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://untrusted.example"})))
    with pytest.raises(ValueError, match="HTTP 302"):
        list(backend.stream([], GenerationOptions(), threading.Event()))
    backend.close()
