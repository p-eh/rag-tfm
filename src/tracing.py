"""Langfuse tracing setup. LlamaIndex operations (retrieval, LLM calls) are
captured automatically by OpenTelemetry instrumentation once `init_tracing()`
has run; `traced_span` is only for steps that aren't LlamaIndex operations,
such as the full-doc mode's pypdf text extraction.

Heavy imports are kept inside the functions that need them, not at module
level, matching the rest of `src/`.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from src import config

_instrumented = False

_linked_prompt: ContextVar = ContextVar("linked_prompt", default=None)


def is_configured() -> bool:
    return bool(config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY)


def init_tracing() -> None:
    """No-op if Langfuse credentials aren't configured."""
    global _instrumented

    if not is_configured():
        return

    from langfuse import Langfuse

    Langfuse(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST,
    )

    if not _instrumented:
        # instrument() registers a listener on LlamaIndex's own event
        # dispatcher, wired to the Langfuse client's TracerProvider above -
        # not a monkeypatch. Already idempotent internally; this flag just
        # skips its repeat-call warning print.
        from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

        LlamaIndexInstrumentor().instrument()
        _register_prompt_linker()
        _instrumented = True


def _register_prompt_linker() -> None:
    from opentelemetry import trace

    trace.get_tracer_provider().add_span_processor(_prompt_link_processor())


def _prompt_link_processor():
    """Span processor that tags each span started inside `linked_prompt(...)`
    with that prompt's name and version.
    """
    from opentelemetry.sdk.trace import SpanProcessor

    class _PromptLinkProcessor(SpanProcessor):
        def on_start(self, span, parent_context=None):
            prompt = _linked_prompt.get()
            if prompt is not None:
                span.set_attribute("langfuse.observation.prompt.name", prompt.name)
                span.set_attribute("langfuse.observation.prompt.version", prompt.version)

    return _PromptLinkProcessor()


@contextmanager
def linked_prompt(prompt):
    """Links the LLM generation started inside this block to Langfuse `prompt`
    (None links nothing), via `_prompt_link_processor` as the span starts.
    """
    token = _linked_prompt.set(prompt)
    try:
        yield
    finally:
        _linked_prompt.reset(token)


def flush_tracing() -> None:
    """Force-export pending traces before the CLI process exits. Swallows
    any failure (e.g. Langfuse unreachable) so the answer already printed
    to the user is never retracted by a tracing problem.
    """
    if not is_configured():
        return

    from langfuse import get_client

    try:
        get_client().flush()
    except Exception as exc:
        print(f"Warning: tracing flush failed ({exc}); the answer above is unaffected.")


def traced_span(name: str, **input_kwargs):
    """Context manager for a manual span outside LlamaIndex's own
    instrumentation. A no-op when tracing was never configured, so callers
    don't need to check `is_configured()` themselves.
    """
    if not is_configured():
        from contextlib import nullcontext

        return nullcontext()

    from langfuse import get_client

    return get_client().start_as_current_observation(
        name=name, as_type="span", input=input_kwargs or None
    )
