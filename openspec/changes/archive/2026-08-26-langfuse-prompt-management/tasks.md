## 1. Migration script

- [x] 1.1 Write `scripts/migrate_prompts_to_langfuse.py`: reads `SYSTEM_PROMPT.md` and `PROMPT_TEMPLATE.md`, creates `rag-tfm-system-prompt` and `rag-tfm-context-template` in Langfuse as `type="text"`, labeled `production`, using the installed Langfuse skill's migration mechanics (fetch current SDK docs, don't implement from memory)
- [x] 1.2 Run the script once against the project's Langfuse account (credentials already in `.env`) — verify: both prompts appear in the Langfuse UI under Prompts, labeled `production`, with content matching the local `.md` files

## 2. Fetch-with-fallback in `src/prompts.py`

- [x] 2.1 Add a Langfuse fetch path to `load_system_prompt()`: when `tracing._configured()` is true, try `langfuse.get_client().get_prompt("rag-tfm-system-prompt", label="production")`; on any exception, fall back to reading `SYSTEM_PROMPT.md` as today
- [x] 2.2 Add the same fetch-with-fallback to `build_context_prompt()` for `rag-tfm-context-template`, using `.compile(context=context, question=question)` on success instead of the current `.replace()` calls
- [x] 2.3 Verify: with valid Langfuse credentials in `.env`, run a query and confirm (via a temporary print or debugger) the prompt text came from Langfuse, not the local file — confirmed 2026-08-26, both `load_system_prompt()` and `build_context_prompt()` returned Langfuse-sourced text (version 2)
- [x] 2.4 Verify: temporarily point `LANGFUSE_BASE_URL` at an unreachable host, run a query, confirm it still answers using the local `.md` file content and prints no unhandled exception — confirmed 2026-08-26, fetch raised internally (SDK logged it), code fell back to local file text

## 3. Link prompts to generations

- [x] 3.1 In `src/query.py`'s `_ask_with_context`, wrap the instrumented `llm.chat()` call in `tracing.traced_span("llm_generation", **prompt_refs)` — tried `update_current_generation(prompt=prompt)` first, confirmed it doesn't attach (see below), switched to the span-based fallback
- [x] 3.2 Verified against a real trace via the Langfuse API on an `ask_full_doc` run: `update_current_generation` left `prompt_name`/`prompt_version` empty on the auto-instrumented `Anthropic.chat` generation (that span doesn't exist yet when `_ask_with_context` calls it, before `llm.chat()` runs); switched to the `traced_span`-wrapped fallback, confirmed the `llm_generation` span shows `{'rag-tfm-system-prompt_version': 2, 'rag-tfm-context-template_version': 2}` in the same trace. design.md's Decisions section updated to match
- [x] 3.3 Confirmed RAG and full-doc modes produce correct answers with prompt-version spans (full-doc verified end-to-end above; RAG covered by the mocked test suite, live-verifiable via `RUN_LIVE_LLM_TESTS=1`). `ask_no_context` uses no system/template prompt at all (bare `llm.complete(question)`, per `src/query.py`), so it has no Langfuse prompt to fetch or link — unaffected by this change, matching the `query-tracing` spec's existing no-context scenario

## 4. Cleanup and docs

- [x] 4.1 Add a short note stating the local files are now the offline fallback, not the live source of truth — placed in `src/prompts.py` next to the path constants rather than inside the `.md` files themselves, since their full content is read verbatim as fallback prompt text and a comment there would leak into what's sent to the LLM
- [x] 4.2 Update `requirements.txt` only if the migration script needs anything beyond the already-installed `langfuse` package — confirmed no change needed, `langfuse` v4.14.4 already installed includes prompt management in the same client
- [x] 4.3 Run existing `tests/` suite, confirm nothing broke — 26 passed, 3 skipped (opt-in live tests). Added an explicit `monkeypatch.setattr(tracing, "is_configured", lambda: False)` in every mocked test that now calls prompt-loading, since real Langfuse credentials in this dev `.env` would otherwise make the mocked suite silently hit the real Langfuse API

## 5. Review follow-ups (PR #12)

- [x] 5.1 Print a warning, once per process, when the Langfuse fetch fails and the local files are used; stay silent when Langfuse isn't configured — covered by `tests/test_prompts.py`
- [x] 5.2 Add `tests/test_prompts_live.py`, an opt-in (`RUN_LIVE_LANGFUSE_TESTS=1`) drift check between the local files and the `production` prompt — passed against the project's Langfuse account
- [x] 5.3 Replace the two text prompts with one chat prompt, `rag-tfm-chat`; migration script updated and run, prompt created in Langfuse as v1 (`production`)
- [x] 5.4 Link the generation natively via `tracing.linked_prompt()` and a span processor; remove the `llm_generation` span — verified on a real `ask_full_doc` trace that `Anthropic.chat` carries `promptName: rag-tfm-chat`, `promptVersion: 1`
