import pytest
from longbook_harness.config import BackendConfig, GenerationOptions
from longbook_harness.memory import SQLiteMemory
from longbook_harness.runtime import Runtime


def test_demo_labels_no_inference_and_provenance(tmp_path):
    memory = SQLiteMemory(tmp_path / "mem.sqlite3")
    memory.add_bytes("design.txt", b"memory uses sqlite")
    runtime = Runtime(memory)
    output = list(runtime.stream("memory", [], GenerationOptions()))
    assert "実際のLongBookモデルは動いていません" in output[-1][0]
    assert "design.txt" in output[-1][1]
    assert memory.stats()["documents"] == 1  # generated response is not auto-indexed
    assert not runtime.gate.locked()


def test_error_releases_gate(tmp_path):
    runtime = Runtime(SQLiteMemory(tmp_path / "mem.sqlite3"))
    with pytest.raises(ValueError):
        list(runtime.stream("x" * 20000, [], GenerationOptions()))
    assert not runtime.gate.locked()


def test_configure_during_generation_rejected(tmp_path):
    runtime = Runtime(SQLiteMemory(tmp_path / "mem.sqlite3"))
    stream = runtime.stream("hello", [], GenerationOptions())
    next(stream)
    with pytest.raises(ValueError):
        runtime.configure(BackendConfig())
    stream.close()
    assert not runtime.gate.locked()


def test_app_constructs_without_loading_model(tmp_path):
    from longbook_harness.app import create_app
    app, runtime = create_app(tmp_path)
    assert len(app.config["components"]) > 20
    assert runtime.config.kind == "demo"


def test_generation_option_validation():
    with pytest.raises(ValueError):
        GenerationOptions(max_new_tokens=4096, context_window=2048).validate()
