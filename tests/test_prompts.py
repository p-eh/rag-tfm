import sys
import types

from src import prompts, tracing
from src.prompts import NO_CONTEXT_MESSAGE, build_chat_messages


def test_no_context_message_is_non_empty():
    assert NO_CONTEXT_MESSAGE


def test_build_chat_messages_from_local_files(monkeypatch):
    monkeypatch.setattr(tracing, "is_configured", lambda: False)

    system, user, langfuse_prompt = build_chat_messages(
        "How do I clean it?", "Unplug before cleaning."
    )

    assert system == prompts._SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    assert "How do I clean it?" in user
    assert "Unplug before cleaning." in user
    assert langfuse_prompt is None


def test_build_chat_messages_from_langfuse(monkeypatch):
    monkeypatch.setattr(tracing, "is_configured", lambda: True)

    class _FakeChatPrompt:
        def compile(self, **variables):
            return [
                {"role": "system", "content": "system text"},
                {"role": "user", "content": f"{variables['question']} | {variables['context']}"},
            ]

    fake_prompt = _FakeChatPrompt()

    class _Client:
        def get_prompt(self, name, type, label):
            assert (name, type, label) == (prompts.CHAT_PROMPT_NAME, "chat", "production")
            return fake_prompt

    monkeypatch.setitem(sys.modules, "langfuse", types.SimpleNamespace(get_client=_Client))

    system, user, langfuse_prompt = build_chat_messages("Q?", "ctx")

    assert (system, user) == ("system text", "Q? | ctx")
    assert langfuse_prompt is fake_prompt


def _make_langfuse_unreachable(monkeypatch):
    monkeypatch.setattr(tracing, "is_configured", lambda: True)
    monkeypatch.setattr(prompts, "_warned_fetch_failure", False)

    class _UnreachableClient:
        def get_prompt(self, *args, **kwargs):
            raise ConnectionError("Langfuse unreachable")

    fake_langfuse_module = types.SimpleNamespace(get_client=lambda: _UnreachableClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse_module)


def test_build_chat_messages_falls_back_when_langfuse_unreachable(monkeypatch):
    _make_langfuse_unreachable(monkeypatch)

    system, user, langfuse_prompt = build_chat_messages("Q?", "ctx")

    assert system
    assert "Q?" in user
    assert langfuse_prompt is None


def test_fallback_warns_once(monkeypatch, capsys):
    _make_langfuse_unreachable(monkeypatch)

    build_chat_messages("Q?", "ctx")
    build_chat_messages("Q?", "ctx")

    output = capsys.readouterr().out
    assert output.count("Warning: couldn't fetch prompt 'rag-tfm-chat'") == 1
    assert "Langfuse unreachable" in output


def test_no_warning_when_langfuse_not_configured(monkeypatch, capsys):
    monkeypatch.setattr(tracing, "is_configured", lambda: False)

    build_chat_messages("Q?", "ctx")

    assert "Warning" not in capsys.readouterr().out
