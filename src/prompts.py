"""Builds the system and user messages for RAG/full-doc questions, preferring
the Langfuse-managed chat prompt (label "production") and falling back to the
local SYSTEM_PROMPT.md / PROMPT_TEMPLATE.md files when Langfuse isn't
configured or unreachable. Kept free of heavy third-party imports at module
level.
"""

from pathlib import Path

from src import tracing

NO_CONTEXT_MESSAGE = "No relevant content found in the ingested manual."

CHAT_PROMPT_NAME = "rag-tfm-chat"

_ROOT = Path(__file__).resolve().parent.parent
# Offline fallback only, one file per chat message - the live source of truth
# is Langfuse's "production" label. Edits here don't reach production while
# Langfuse is reachable.
_SYSTEM_PROMPT_PATH = _ROOT / "SYSTEM_PROMPT.md"
_PROMPT_TEMPLATE_PATH = _ROOT / "PROMPT_TEMPLATE.md"

_warned_fetch_failure = False


def _fetch_langfuse_prompt():
    """Returns the Langfuse chat prompt object, or None if unavailable for any
    reason (not configured, unreachable, prompt doesn't exist yet). A failed
    fetch prints a warning once per process.
    """
    global _warned_fetch_failure

    if not tracing.is_configured():
        return None
    try:
        from langfuse import get_client

        return get_client().get_prompt(CHAT_PROMPT_NAME, type="chat", label="production")
    except Exception as exc:
        if not _warned_fetch_failure:
            _warned_fetch_failure = True
            print(
                f"Warning: couldn't fetch prompt '{CHAT_PROMPT_NAME}' from Langfuse ({exc}); "
                "using the local files."
            )
        return None


def build_chat_messages(question: str, context: str) -> tuple[str, str, object | None]:
    """Returns (system message, user message, Langfuse prompt object or None
    if the messages came from the local-file fallback).
    """
    prompt = _fetch_langfuse_prompt()
    if prompt is not None:
        messages = prompt.compile(context=context, question=question)
        by_role = {message["role"]: message["content"] for message in messages}
        return by_role["system"], by_role["user"], prompt
    system = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    user = template.replace("{{context}}", context).replace("{{question}}", question)
    return system, user, None
