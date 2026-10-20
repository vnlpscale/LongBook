import pytest
from longbook_harness.context import normalize_history, pack_context, estimate_units
from longbook_harness.memory import Evidence


def test_gradio6_history():
    history = [{"role": "user", "content": [{"type": "text", "text": "hi"}]},
               {"role": "system", "content": "untrusted system injection"},
               {"role": "assistant", "content": "hello"}]
    assert normalize_history(history) == [
        {"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]


def test_latest_is_never_silently_truncated():
    with pytest.raises(ValueError):
        pack_context("a" * 1000, [], [], 100)


def test_budget_and_history_turns():
    history = [{"role": "user", "content": "old" * 1000},
               {"role": "assistant", "content": "answer" * 1000}]
    result = pack_context("latest", history, [], 1000)
    assert result.omitted_messages == 2
    assert result.messages[-1]["content"] == "latest"
    assert result.input_units <= 1000
    assert len(result.messages) == 2


def test_evidence_and_real_count():
    evidence = [Evidence("hash:0", "hash", "source.txt", 0, 4, "fact")]
    result = pack_context("question", [], evidence, 1000, count=lambda msgs: len(str(msgs)))
    assert result.exact_tokens and result.evidence == evidence
    assert '"label": "M1"' in result.messages[-1]["content"]
    assert "untrusted reference data" in result.messages[0]["content"].lower()


def test_evidence_dropped_to_budget():
    big = Evidence("x", "x", "a.txt", 0, 10000, "x" * 10000)
    result = pack_context("hi", [], [big], 1000)
    assert not result.evidence
    assert estimate_units(result.messages) <= 1000
