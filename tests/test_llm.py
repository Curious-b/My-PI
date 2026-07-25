"""Tests for LM configuration — in particular, that OLLAMA_NUM_CTX and
LLM_MAX_TOKENS actually reach dspy.LM(), since silently dropping either
was the root cause of large schemas producing garbled/truncated output.

dspy isn't a hard requirement for running this project's core tests, so we
inject a fake `dspy` module rather than depending on the real package.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.llm as llm_mod  # noqa: E402


def test_configure_lm_passes_num_ctx_and_max_tokens(monkeypatch):
    captured = {}

    class FakeLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_dspy = types.ModuleType("dspy")
    fake_dspy.LM = FakeLM
    fake_dspy.configure = lambda **kw: None

    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)
    monkeypatch.setattr(llm_mod, "_configured", False)
    monkeypatch.setattr(llm_mod, "_error", None)

    ok, err = llm_mod.configure_lm()

    assert ok is True
    assert err is None
    assert captured["num_ctx"] == llm_mod.settings.ollama_num_ctx
    assert captured["max_tokens"] == llm_mod.settings.llm_max_tokens
    assert captured["model"] == llm_mod.settings.llm_model
