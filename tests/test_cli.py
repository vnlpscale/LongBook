import pytest
from longbook_harness.cli import launch_ui


def test_weak_password_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("LONGBOOK_PASSWORD", "short")
    with pytest.raises(ValueError, match="12文字"):
        launch_ui(data_dir=tmp_path, inbrowser=False)


def test_public_link_gets_generated_auth(monkeypatch, tmp_path, capsys):
    import longbook_harness.app as module
    calls = []
    class FakeApp:
        def launch(self, **kwargs):
            calls.append(kwargs)
    class FakeRuntime:
        def cancel(self):
            pass
    monkeypatch.delenv("LONGBOOK_PASSWORD", raising=False)
    monkeypatch.setattr(module, "create_app", lambda root: (FakeApp(), FakeRuntime()))
    launch_ui(share=True, data_dir=tmp_path, inbrowser=False)
    auth = calls[0]["auth"]
    assert auth[0] == "longbook" and len(auth[1]) >= 24
    assert calls[0]["strict_cors"] is True
    assert calls[0]["enable_monitoring"] is False
    assert str(tmp_path) in calls[0]["blocked_paths"]
    assert auth[1] in capsys.readouterr().out  # shown locally, not silently lost
