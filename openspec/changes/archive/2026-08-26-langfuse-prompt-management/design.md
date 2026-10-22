## Context

`src/prompts.py` currently reads `SYSTEM_PROMPT.md` and `PROMPT_TEMPLATE.md` from disk on every call (`load_system_prompt`, `build_context_prompt`). `src/tracing.py` already initializes a Langfuse client (`init_tracing`) and instruments LlamaIndex calls process-wide via `openinference.instrumentation.llama_index.LlamaIndexInstrumentor`; the LLM calls in `src/query.py` (`_ask_with_context`, `ask_no_context`) are auto-traced generations, not manual spans — only full-doc mode's pypdf extraction uses a manual `traced_span`. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Fetch both prompts from Langfuse (label `production`) when configured and reachable.
- Fall back to the existing local files when Langfuse isn't configured, is unreachable, or the prompts don't exist there yet — same graceful-degradation shape as tracing.
- Link the fetched prompt to the generation it produced, when tracing is active.

**Non-Goals:**
- No prompt Playground / A/B experiment workflow — out of scope, just fetch-and-use.
- No new prompt content or wording changes — this migrates the existing prompt text verbatim.
- No removal of the local `.md` files — they remain the fallback and the initial migration source.

## Decisions

**Fetch via `langfuse.get_client().get_prompt(name, label="production")`, one `text`-type prompt per file.** Both `SYSTEM_PROMPT.md` and `PROMPT_TEMPLATE.md` are plain strings (not message arrays), so `type="text"` per the Langfuse skill's chat-vs-text guidance. Names: `rag-tfm-system-prompt`, `rag-tfm-context-template`.

**`{{context}}` / `{{question}}` stay double-brace.** `PROMPT_TEMPLATE.md` already uses `{{context}}`/`{{question}}` (see `build_context_prompt`'s `.replace()` calls) — this already matches Langfuse's variable syntax, so no conversion needed; `build_context_prompt` swaps its own `.replace()` calls for the fetched prompt's `.compile(context=..., question=...)`.

**Fallback lives inside `src/prompts.py`, one level below `tracing._configured()`.** `load_system_prompt()` and `build_context_prompt()` try a Langfuse fetch first when `tracing._configured()` is true, catch any exception from the fetch, and fall back to the current file-read path on failure — mirroring `tracing.flush_tracing()`'s try/except-and-warn shape: a failed fetch prints a warning once per prompt name per process, so a misconfigured Langfuse doesn't silently serve the local copies, and a multi-question eval run doesn't repeat the warning per question. The not-configured path stays silent, matching tracing's no-op when unconfigured. Keeping the local files as the always-present fallback (not deleting them) means the two functions' return type and call sites in `src/query.py` don't change at all.

**One-time migration script creates the two prompts, not app code.** A short one-off script (`scripts/migrate_prompts_to_langfuse.py`, run manually once) reads the current `.md` files and calls `create_prompt(..., labels=["production"])` via the Langfuse skill's migration mechanics. It is not invoked by the app and is not part of the normal request path.

**Prompt linking: fallback path used — prompt name/version recorded as input on a manual `llm_generation` span wrapping the LLM call, via the existing `traced_span` helper.** `update_current_generation(prompt=prompt)` was tried first, called immediately before the instrumented `llm.chat()` call, but confirmed **not** to attach against a real trace: `LlamaIndexInstrumentor` only creates its generation span for the duration of the `llm.chat()` call itself, so at the point `_ask_with_context` calls `update_current_generation()` there is no active generation span yet to update — the call is a no-op. Verified via the Langfuse API on a real `ask_full_doc` trace: the auto-instrumented `Anthropic.chat` generation showed `prompt_name: None`. Switched to `tracing.traced_span("llm_generation", **prompt_refs)`, which wraps the `llm.chat()` call and records `{prompt.name}_version` for each Langfuse-sourced prompt as span input — visible in the same trace as the `Anthropic.chat` generation, not linked to it via Langfuse's native prompt-linking field, but still gives the trace viewer the prompt name and version that produced that generation.

**No new dependency.** `langfuse` (already in `requirements.txt` for tracing) includes prompt management in the same client.

## Risks / Trade-offs

- **[Risk]** `update_current_generation(prompt=...)` may not land on the right span given LlamaIndexInstrumentor's auto-instrumentation (see Decisions above) → **Mitigation**: verify against a real Langfuse trace during implementation; fall back to recording prompt name/version as plain span input if generation-level linking doesn't attach.
- **[Risk]** Langfuse cloud outage during prompt fetch → **Mitigation**: same as `query-tracing`'s existing tracing-failure requirement — fall back to local files, still answer.
- **[Trade-off]** Local `.md` files become a fallback copy that can drift from what's live in Langfuse (whoever edits the prod prompt in the Langfuse UI won't also update the `.md` file) — accepted for a demo project; not resolved by auto-syncing Langfuse back to the repo, which would add real complexity for a project scoped to be finished, not perfectly synced.
