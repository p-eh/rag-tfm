"""Mocked tests for src.query: verify RAG/no-context orchestration logic
(prompt building, source extraction, no-context short-circuit) without
calling the real Anthropic API or needing chromadb/llama_index installed.

For a real end-to-end call against the Anthropic API, see test_ask_live.py.
"""

from src import query

FAKE_USAGE = {"input_tokens": 10, "output_tokens": 20}


class FakeUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def _fake_raw(input_tokens, output_tokens):
    return {"usage": FakeUsage(input_tokens, output_tokens)}


class FakeLLMResponse:
    def __init__(self, text, raw):
        self._text = text
        self.raw = raw

    def __str__(self):
        return self._text


class FakeChatMessage:
    def __init__(self, content):
        self.content = content


class FakeChatResponse:
    def __init__(self, text, raw):
        self.message = FakeChatMessage(text)
        self.raw = raw


class FakeLLM:
    """Fakes both llm.complete() (no-context mode) and llm.chat() (RAG/full-doc
    modes, which send a real system message - see query._ask_with_context)."""

    def __init__(self, text="mocked answer", input_tokens=10, output_tokens=20):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.prompts_seen = []
        self.messages_seen = []

    def complete(self, prompt):
        self.prompts_seen.append(prompt)
        return FakeLLMResponse(self.text, _fake_raw(self.input_tokens, self.output_tokens))

    def chat(self, messages):
        self.messages_seen.append(messages)
        return FakeChatResponse(self.text, _fake_raw(self.input_tokens, self.output_tokens))


class FakeNode:
    def __init__(self, content, file_name):
        self._content = content
        self.metadata = {"file_name": file_name}

    def get_content(self):
        return self._content


class FakeRetriever:
    def __init__(self, nodes):
        self._nodes = nodes

    def retrieve(self, question):
        return self._nodes


class FakeIndex:
    def __init__(self, nodes):
        self._nodes = nodes

    def as_retriever(self, similarity_top_k):
        return FakeRetriever(self._nodes)


def test_ask_no_context_returns_llm_answer(monkeypatch):
    fake_llm = FakeLLM("Paris is the capital of France.")
    monkeypatch.setattr(query, "_build_llm", lambda: fake_llm)

    result = query.ask_no_context("What is the capital of France?")

    assert result == {
        "answer": "Paris is the capital of France.",
        "sources": [],
        "usage": FAKE_USAGE,
    }
    assert fake_llm.prompts_seen == ["What is the capital of France?"]


def test_ask_rag_with_no_retrieved_nodes_skips_llm_call(tmp_path, monkeypatch):
    monkeypatch.setattr(query, "load_manuals_index", lambda manual_path: FakeIndex([]))

    def fail_if_called():
        raise AssertionError("LLM should not be called when no context is retrieved")

    monkeypatch.setattr(query, "_build_llm", fail_if_called)

    result = query.ask_rag("What is the warranty period?", tmp_path / "manual.pdf")

    assert result == {
        "answer": query.NO_CONTEXT_MESSAGE,
        "sources": [],
        "contexts": [],
        "usage": query.NO_USAGE,
    }


def test_ask_rag_builds_context_prompt_and_dedupes_sources(tmp_path, monkeypatch):
    nodes = [
        FakeNode("Soak the cartridge for 15 minutes.", "manual-a.pdf"),
        FakeNode("Rinse under running water.", "manual-a.pdf"),
    ]
    fake_llm = FakeLLM("Soak for 15 minutes, then rinse.")

    monkeypatch.setattr(query.tracing, "is_configured", lambda: False)
    monkeypatch.setattr(query, "load_manuals_index", lambda manual_path: FakeIndex(nodes))
    monkeypatch.setattr(query, "_build_llm", lambda: fake_llm)

    result = query.ask_rag("How do I set up a new filter?", tmp_path / "manual.pdf")

    assert result["answer"] == "Soak for 15 minutes, then rinse."
    assert result["sources"] == ["manual-a.pdf"]
    assert result["contexts"] == [
        "Soak the cartridge for 15 minutes.",
        "Rinse under running water.",
    ]
    assert result["usage"] == FAKE_USAGE
    assert len(fake_llm.messages_seen) == 1
    system_message, user_message = fake_llm.messages_seen[0]
    assert system_message.content == query.build_chat_messages("", "")[0]
    assert "How do I set up a new filter?" in user_message.content
    assert "Soak the cartridge for 15 minutes." in user_message.content
    assert "Rinse under running water." in user_message.content


def test_ask_full_doc_with_missing_manual_skips_llm_call(tmp_path, monkeypatch):
    def fail_if_called():
        raise AssertionError("LLM should not be called when the manual is missing")

    monkeypatch.setattr(query, "_build_llm", fail_if_called)

    result = query.ask_full_doc("What is the warranty period?", tmp_path / "missing.pdf")

    assert result == {
        "answer": query.NO_CONTEXT_MESSAGE,
        "sources": [],
        "contexts": [],
        "usage": query.NO_USAGE,
    }


def test_ask_full_doc_sends_the_manual_in_full(tmp_path, monkeypatch):
    manual_path = tmp_path / "manual-a.pdf"
    manual_path.touch()
    fake_llm = FakeLLM("Soak for 15 minutes, then rinse.")

    monkeypatch.setattr(query.tracing, "is_configured", lambda: False)
    monkeypatch.setattr(
        query, "_load_manual_text", lambda path: "Soak the cartridge for 15 minutes before use."
    )
    monkeypatch.setattr(query, "_build_llm", lambda: fake_llm)

    result = query.ask_full_doc("How do I care for the filter?", manual_path)

    assert result["answer"] == "Soak for 15 minutes, then rinse."
    assert result["sources"] == ["manual-a.pdf"]
    assert result["contexts"] == ["Soak the cartridge for 15 minutes before use."]
    assert result["usage"] == FAKE_USAGE
    assert len(fake_llm.messages_seen) == 1
    system_message, user_message = fake_llm.messages_seen[0]
    assert system_message.content == query.build_chat_messages("", "")[0]
    assert "How do I care for the filter?" in user_message.content
    assert "Soak the cartridge for 15 minutes before use." in user_message.content


def test_ask_full_doc_records_extraction_span_output(tmp_path, monkeypatch):
    manual_path = tmp_path / "manual-a.pdf"
    manual_path.touch()

    monkeypatch.setattr(query.tracing, "is_configured", lambda: False)
    monkeypatch.setattr(
        query, "_load_manual_text", lambda path: "Soak the cartridge for 15 minutes before use."
    )
    monkeypatch.setattr(query, "_build_llm", lambda: FakeLLM("ok"))

    span_updates = []

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def update(self, **kwargs):
            span_updates.append(kwargs)

    monkeypatch.setattr(query.tracing, "traced_span", lambda *a, **kw: FakeSpan())

    query.ask_full_doc("How do I care for the filter?", manual_path)

    assert span_updates == [
        {
            "output": {
                "char_count": len("Soak the cartridge for 15 minutes before use."),
                "preview": "Soak the cartridge for 15 minutes before use.",
            }
        }
    ]
