"""Loads and fills prompt text, preferring Langfuse-managed prompts (label
"production") and falling back to the local SYSTEM_PROMPT.md /
PROMPT_TEMPLATE.md files when Langfuse isn't configured or unreachable.
Kept free of heavy third-party imports at module level.
"""

from pathlib import Path

from src import tracing

NO_CONTEXT_MESSAGE = "No relevant content found in the ingested manual."

SYSTEM_PROMPT_NAME = "rag-tfm-system-prompt"
TEMPLATE_PROMPT_NAME = "rag-tfm-context-template"

_ROOT = Path(__file__).resolve().parent.parent
# Offline fallback only - the live source of truth is Langfuse's "production"
# label. Edits here don't reach production while Langfuse is reachable.
_SYSTEM_PROMPT_PATH = _ROOT / "SYSTEM_PROMPT.md"
_PROMPT_TEMPLATE_PATH = _ROOT / "PROMPT_TEMPLATE.md"

_warned_prompt_names: set[str] = set()


def _fetch_langfuse_prompt(name: str):
    """Returns the Langfuse prompt object, or None if unavailable for any
    reason (not configured, unreachable, prompt doesn't exist yet). A failed
    fetch prints a warning once per prompt name per process.
    """
    if not tracing.is_configured():
        return None
    try:
        from langfuse import get_client

        return get_client().get_prompt(name, label="production")
    except Exception as exc:
        if name not in _warned_prompt_names:
            _warned_prompt_names.add(name)
            print(
                f"Warning: couldn't fetch prompt '{name}' from Langfuse ({exc}); "
                "using the local file."
            )
        return None


def load_system_prompt() -> tuple[str, object | None]:
    """Returns (prompt text, Langfuse prompt object or None if it came
    from the local file fallback).
    """
    prompt = _fetch_langfuse_prompt(SYSTEM_PROMPT_NAME)
    if prompt is not None:
        return prompt.compile(), prompt
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip(), None


def build_context_prompt(question: str, context: str) -> tuple[str, object | None]:
    """Returns (filled prompt text, Langfuse prompt object or None if it
    came from the local file fallback).
    """
    prompt = _fetch_langfuse_prompt(TEMPLATE_PROMPT_NAME)
    if prompt is not None:
        return prompt.compile(context=context, question=question), prompt
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    filled = template.replace("{{context}}", context).replace("{{question}}", question)
    return filled, None
