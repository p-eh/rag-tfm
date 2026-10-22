## Why

Prompts (`SYSTEM_PROMPT.md`, `PROMPT_TEMPLATE.md`) currently live as local files, edited by hand and shipped with the code. Langfuse — already wired in for tracing (`query-tracing` capability) — also offers prompt management: versioned prompts editable in its UI, fetched at runtime, with generations linked back to the exact prompt version that produced them. Moving prompts there demonstrates that LLMOps practice end to end (not just tracing) and removes the need for a code deploy to iterate on prompt wording.

## What Changes

- `src/prompts.py` fetches the system prompt and context-answer template from Langfuse (label `production`) instead of reading `SYSTEM_PROMPT.md` / `PROMPT_TEMPLATE.md` from disk.
- A one-time migration step creates one chat prompt in Langfuse (system message + context-answer message) from the current file contents, labeled `production`.
- Prompt variables use Langfuse's `{{var}}` syntax (already the case: `{{context}}`, `{{question}}`).
- Each trace records the Langfuse prompt name/version that produced its generation, via the existing tracing instrumentation (`src/tracing.py`).
- **BREAKING**: `SYSTEM_PROMPT.md` and `PROMPT_TEMPLATE.md` stop being read at runtime once migrated (kept in the repo only as the historical/fallback source, per graceful-degradation below — not as the live source of truth).
- Graceful degradation: if Langfuse is unreachable or prompts can't be fetched, fall back to the local files rather than failing the query — mirrors the existing tracing failure behavior (`query-tracing` capability's "Langfuse unreachable" scenario).

## Capabilities

### New Capabilities
- `prompt-management`: prompts are sourced from Langfuse at runtime (labeled `production`), with local files as an offline fallback, and generations link to the prompt version used.

### Modified Capabilities
(none — `query-tracing` behavior is unchanged; prompt linking is additive to the existing trace/generation calls, not a change to what tracing already requires)

## Impact

- `src/prompts.py`: rewritten to call the Langfuse Python SDK's `get_prompt()` / `.compile()`, with a local-file fallback path.
- `src/query.py`, `src/ask.py`: pass the fetched Langfuse prompt object through to the instrumented LLM call so it can be linked to the generation (per `references/instrumentation.md` / `link-to-traces` in the installed Langfuse skill).
- `requirements.txt`: no new dependency — `langfuse` is already installed for tracing and includes prompt management.
- One-time data migration into the user's Langfuse project (via the Langfuse skill's CLI), not a schema/code migration.
- `SYSTEM_PROMPT.md`, `PROMPT_TEMPLATE.md` remain in the repo as the fallback/reference copy.
