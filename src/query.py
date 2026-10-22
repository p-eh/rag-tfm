"""Answer questions about a single ingested manual via Claude, in one of three
modes: RAG (retrieved chunks), full-doc (the entire manual, no retrieval), or
no-context (bare question, no manual content at all - baseline).

Heavy third-party imports are kept inside the functions that need them, not
at module level, so this module stays importable without the full stack.
"""

from src import config, tracing, vector_store
from src.prompts import NO_CONTEXT_MESSAGE, build_context_prompt, load_system_prompt

# Number of top-ranked chunks retrieved per question and passed to the LLM
# as context in RAG mode (see ask_rag's similarity_top_k usage below).
SIMILARITY_TOP_K = 4


def load_manuals_index(manual_path):
    """Open the Chroma collection built by `src.ingest` for this manual.

    Raises if that manual hasn't been ingested yet.
    """
    from llama_index.core import VectorStoreIndex

    with tracing.traced_span("load_embedding_model"):
        vector_store.configure_embed_model()
    store = vector_store.get_existing_collection(manual_path)
    if store is None:
        raise SystemExit(
            f"No index found for {manual_path}. Run `python -m src.ingest {manual_path}` first."
        )
    return VectorStoreIndex.from_vector_store(store)


def _build_llm():
    from llama_index.llms.anthropic import Anthropic

    return Anthropic(model=config.ANTHROPIC_MODEL, api_key=config.ANTHROPIC_API_KEY)


# Returned instead of real token counts when a branch never calls the LLM
# (e.g. no retrieved chunks, missing manual) - keeps the "usage" key uniform
# across every ask_* return value.
NO_USAGE = {"input_tokens": 0, "output_tokens": 0}


def _usage_from_response(response) -> dict:
    """Anthropic's own per-call token counts, straight from the API response
    - not an estimate. `response.raw` is the raw Anthropic message dict for
    both llm.chat() and llm.complete() responses.
    """
    usage = response.raw["usage"]
    return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def _prompt_versions_for_trace(*prompts) -> dict:
    """{"<name>_version": version} for each Langfuse-fetched prompt, recorded on
    the llm_generation span so a trace shows which prompt versions produced it.
    Prompts from the local-file fallback (None) are skipped.
    """
    return {f"{prompt.name}_version": prompt.version for prompt in prompts if prompt is not None}


def _ask_with_context(user_prompt: str, template_prompt=None):
    """Send the system prompt as the system message and user_prompt as the
    user turn. Used by ask_rag and ask_full_doc, not ask_no_context. Returns
    the raw llama_index ChatResponse so callers can read both the answer
    text and token usage.
    """
    from llama_index.core.llms import ChatMessage, MessageRole

    system_prompt, system_langfuse_prompt = load_system_prompt()

    llm = _build_llm()
    with tracing.traced_span(
        "llm_generation", **_prompt_versions_for_trace(system_langfuse_prompt, template_prompt)
    ):
        return llm.chat(
            [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=user_prompt),
            ]
        )


def _load_manual_text(manual_path) -> str:
    """Extract raw text from a single manual PDF, for full-doc mode.

    Deliberately independent of the Chroma index/embedding pipeline - this
    reads the PDF directly with pypdf, no chunking or vector search involved.
    """
    import pypdf

    reader = pypdf.PdfReader(manual_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def ask_rag(question: str, manual_path) -> dict:
    index = load_manuals_index(manual_path)
    nodes = index.as_retriever(similarity_top_k=SIMILARITY_TOP_K).retrieve(question)

    if not nodes:
        return {"answer": NO_CONTEXT_MESSAGE, "sources": [], "contexts": [], "usage": NO_USAGE}

    # Chunks are joined in retrieval-rank order, not document order - an
    # answer split across non-adjacent chunks may read as disjoint fragments.
    contexts = [node.get_content() for node in nodes]
    context = "\n\n".join(contexts)
    user_prompt, template_prompt = build_context_prompt(question, context)

    response = _ask_with_context(user_prompt, template_prompt)

    sources = sorted({node.metadata.get("file_name", "unknown") for node in nodes})
    return {
        "answer": response.message.content,
        "sources": sources,
        "contexts": contexts,
        "usage": _usage_from_response(response),
    }


def ask_full_doc(question: str, manual_path) -> dict:
    from pathlib import Path

    manual_path = Path(manual_path)
    if not manual_path.exists():
        return {"answer": NO_CONTEXT_MESSAGE, "sources": [], "contexts": [], "usage": NO_USAGE}

    with tracing.traced_span("extract_manual_text", manual_path=str(manual_path)) as span:
        context = _load_manual_text(manual_path)
        if span is not None:
            # Full text is already in Anthropic.chat's prompt input; preview is enough here.
            span.update(output={"char_count": len(context), "preview": context[:200]})
    user_prompt, template_prompt = build_context_prompt(question, context)

    response = _ask_with_context(user_prompt, template_prompt)

    return {
        "answer": response.message.content,
        "sources": [manual_path.name],
        "contexts": [context],
        "usage": _usage_from_response(response),
    }


def ask_no_context(question: str) -> dict:
    llm = _build_llm()
    response = llm.complete(question)
    return {"answer": str(response), "sources": [], "usage": _usage_from_response(response)}
