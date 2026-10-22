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

**One `chat`-type prompt, `rag-tfm-chat`, fetched via `get_client().get_prompt(name, type="chat", label="production")`.** It holds a system message (from `SYSTEM_PROMPT.md`) and a user message (from `PROMPT_TEMPLATE.md`). Langfuse links a generation to exactly one prompt, so a single chat prompt means one link covers everything sent to the LLM, and any change to either message shows up as a new version of that one prompt. The two local files stay separate, one per message, as the offline fallback.

**`{{context}}` / `{{question}}` stay double-brace.** `PROMPT_TEMPLATE.md` already uses them, which matches Langfuse's variable syntax. `build_chat_messages()` fills them via the fetched prompt's `.compile(context=..., question=...)`, or via `.replace()` on the local file in the fallback path.

**Fallback lives inside `src/prompts.py`.** `build_chat_messages()` tries a Langfuse fetch first when `tracing.is_configured()` is true, catches any exception, and falls back to the local files — mirroring `tracing.flush_tracing()`'s try/except-and-warn shape. A failed fetch prints a warning once per process, so a misconfigured Langfuse doesn't silently serve the local copies, and a multi-question eval run doesn't repeat the warning per question. The not-configured path stays silent, matching tracing's no-op when unconfigured.

**One-time migration script creates the chat prompt, not app code.** `scripts/migrate_prompts_to_langfuse.py` (run manually once per Langfuse project) reads the two `.md` files and calls `create_prompt(type="chat", ..., labels=["production"])`. It is not invoked by the app. An opt-in live test (`tests/test_prompts_live.py`, `RUN_LIVE_LANGFUSE_TESTS=1`) flags drift between the local files and the `production` messages; the fix is a manual copy.

**Prompt linking via a span processor.** Langfuse links an observation to a prompt through the OTel attributes `langfuse.observation.prompt.name` / `.version`. `LlamaIndexInstrumentor` creates the generation span inside `llm.chat()`, so there's no span to update from `_ask_with_context` beforehand (`update_current_generation(prompt=...)` was a no-op on a real trace). Instead, `tracing.linked_prompt(prompt)` sets a context variable around `llm.chat()`, and a span processor registered on Langfuse's tracer provider copies the prompt name and version onto every span started while it's set — in practice only the `Anthropic.chat` generation. Verified via the Langfuse API: the `Anthropic.chat` generation carries `promptName: rag-tfm-chat`, `promptVersion: 1`, and no other observation in the trace is tagged.

**No new dependency.** `langfuse` (already in `requirements.txt` for tracing) includes prompt management in the same client.

## Risks / Trade-offs

- **[Risk]** `update_current_generation(prompt=...)` may not land on the right span given LlamaIndexInstrumentor's auto-instrumentation (see Decisions above) → **Mitigation**: verify against a real Langfuse trace during implementation; fall back to recording prompt name/version as plain span input if generation-level linking doesn't attach.
- **[Risk]** Langfuse cloud outage during prompt fetch → **Mitigation**: same as `query-tracing`'s existing tracing-failure requirement — fall back to local files, still answer.
- **[Trade-off]** Local `.md` files become a fallback copy that can drift from what's live in Langfuse (whoever edits the prod prompt in the Langfuse UI won't also update the `.md` file) — accepted for a demo project; not resolved by auto-syncing Langfuse back to the repo, which would add real complexity for a project scoped to be finished, not perfectly synced.
