"""Live HTTP tests, not browser rendering tests. No model downloads or public tunnels."""
import socket
from urllib.parse import quote

import httpx
import pytest
from gradio_client import Client


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from longbook_harness.app import create_app, theme
    root = tmp_path_factory.mktemp("http-server")
    app, runtime = create_app(root)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app.launch(server_name="127.0.0.1", server_port=port, share=False,
               prevent_thread_lock=True, auth=("longbook", "test-password-123456"),
               quiet=True, ssr_mode=False, enable_monitoring=False,
               blocked_paths=[str(root)], theme=theme())
    try:
        yield f"http://127.0.0.1:{port}", root
    finally:
        runtime.cancel()
        app.close()


def test_auth_required(server):
    url, _ = server
    with httpx.Client(base_url=url, trust_env=False) as client:
        assert client.get("/config").status_code == 401
        assert client.post("/login", data={"username": "longbook", "password": "wrong"}).status_code == 400
        response = client.post("/login", data={"username": "longbook", "password": "test-password-123456"})
        assert response.status_code == 200
        assert client.get("/config").status_code == 200


def test_live_gradio_stream(server):
    url, _ = server
    client = Client(url, auth=("longbook", "test-password-123456"), verbose=False)
    # ChatInterface stores history in a State; callers do not pass a history argument here.
    reply, refs = client.predict("接続確認", 512, 0.6, 8192, True, "", api_name="/chat")
    assert "実際のLongBookモデルは動いていません" in reply
    assert "入力:" in refs
    client.close()


def test_private_data_not_downloadable(server):
    url, root = server
    canary = root / "private-canary.txt"
    canary.write_text("do-not-serve", encoding="utf-8")
    with httpx.Client(base_url=url, trust_env=False) as client:
        client.post("/login", data={"username": "longbook", "password": "test-password-123456"})
        response = client.get("/gradio_api/file=" + quote(str(canary), safe=""))
        assert response.status_code in {403, 404}
        assert "do-not-serve" not in response.text
