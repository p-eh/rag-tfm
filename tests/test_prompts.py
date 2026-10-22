import sys
import types

from src import prompts, tracing
from src.prompts import NO_CONTEXT_MESSAGE, build_context_prompt, load_system_prompt


def test_no_context_message_is_non_empty():
    assert NO_CONTEXT_MESSAGE


def test_load_system_prompt_is_non_empty(monkeypatch):
    monkeypatch.setattr(tracing, "is_configured", lambda: False)

    text, langfuse_prompt = load_system_prompt()

    assert text
    assert langfuse_prompt is None


def test_build_context_prompt_includes_question_and_context(monkeypatch):
    monkeypatch.setattr(tracing, "is_configured", lambda: False)

    prompt, langfuse_prompt = build_context_prompt("How do I clean it?", "Unplug before cleaning.")

    assert "How do I clean it?" in prompt
    assert "Unplug before cleaning." in prompt
    assert langfuse_prompt is None


def _make_langfuse_unreachable(monkeypatch):
    monkeypatch.setattr(tracing, "is_configured", lambda: True)
    monkeypatch.setattr(prompts, "_warned_prompt_names", set())

    class _UnreachableClient:
        def get_prompt(self, *args, **kwargs):
            raise ConnectionError("Langfuse unreachable")

    fake_langfuse_module = types.SimpleNamespace(get_client=lambda: _UnreachableClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse_module)


def test_load_system_prompt_falls_back_when_langfuse_unreachable(monkeypatch):
    _make_langfuse_unreachable(monkeypatch)

    text, langfuse_prompt = load_system_prompt()

    assert text
    assert langfuse_prompt is None


def test_fallback_warns_once_per_prompt(monkeypatch, capsys):
    _make_langfuse_unreachable(monkeypatch)

    load_system_prompt()
    load_system_prompt()

    output = capsys.readouterr().out
    assert output.count("Warning: couldn't fetch prompt 'rag-tfm-system-prompt'") == 1
    assert "Langfuse unreachable" in output


def test_no_warning_when_langfuse_not_configured(monkeypatch, capsys):
    monkeypatch.setattr(tracing, "is_configured", lambda: False)

    load_system_prompt()

    assert "Warning" not in capsys.readouterr().out
