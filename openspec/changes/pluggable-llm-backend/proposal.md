## Why

`rag-tfm-mvp` hardcodes Anthropic Claude for generation. Review feedback on the MVP (PR #1) asked for the backend to be swappable via config instead of code changes, including a fully local, CUDA-accelerated option. This is a stub to track the idea, not a committed design.

## What Changes

- (Not designed yet.) Rough shape: an env-var-selected backend (e.g. `LLM_PROVIDER=anthropic|openai|ollama`), at least one fully local CUDA-accelerated option (e.g. Ollama), MVP default behavior unchanged when no override is set.

- Also covers `src/find_manual.py` (manual discovery): it depends on Anthropic's server-side web search tool (`web_search_20250305`) and Anthropic-specific stop reasons (`pause_turn`), and its docstrings refer to "Claude" directly. A non-Anthropic backend needs its own web search source (provider-native search, or a separate search API feeding the same ranking prompt), and those references need making provider-neutral. Raised in PR #14 review.

## Capabilities

### New Capabilities
(none yet — stub only, no spec-level commitment until this is picked up)

### Modified Capabilities
(none)

## Impact

Not assessed yet. Open questions: whether the MVP's default backend itself should change (raised but unresolved on PR #1); implementation approach — native llama-index provider classes per backend vs. a proxy layer (e.g. LiteLLM) vs. a small custom factory (options discussed on PR #1: Ollama for local CUDA inference, LiteLLM as a multi-provider adapter, or an env-var-keyed factory — leaning toward Ollama or the factory for this project's scope); whether the Ragas judge model in the eval harness follows the same selected backend or stays fixed.
