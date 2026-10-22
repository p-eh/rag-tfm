## Purpose

Sources the app's prompts from Langfuse's prompt management (versioned, editable without a code deploy) instead of local files, while still working offline, so prompt iteration doesn't require touching the codebase.

## ADDED Requirements

### Requirement: Prompts are fetched from Langfuse
When Langfuse is configured and reachable, the system SHALL fetch one chat prompt from Langfuse using the `production` label, holding the system message and the context-answer message, rather than reading them from local files.

#### Scenario: RAG or full-doc query fetches prompts from Langfuse
- **WHEN** the ask command answers a question in RAG or full-doc mode and Langfuse is configured and reachable
- **THEN** the system and context-answer messages used for the LLM call come from the `production`-labeled version of the chat prompt fetched from Langfuse

### Requirement: Prompt fetch failure does not block answering
If Langfuse is unreachable, not configured, or the chat prompt doesn't exist there, the system SHALL fall back to the local prompt files and still return an answer, rather than failing the query.

#### Scenario: Langfuse unreachable during prompt fetch
- **WHEN** the ask command answers a question and Langfuse cannot be reached while fetching a prompt
- **THEN** the system falls back to the local `SYSTEM_PROMPT.md` / `PROMPT_TEMPLATE.md` content, prints a warning naming the prompt that couldn't be fetched (once per run), and still returns an answer

#### Scenario: Langfuse not configured
- **WHEN** no Langfuse credentials are configured
- **THEN** the system uses the local prompt files directly, without attempting a Langfuse fetch

### Requirement: Traces record which prompt version produced a generation
When a query is traced and its prompt was fetched from Langfuse, the LLM generation SHALL be linked to the prompt name and version that produced it, so the generation is listed under that prompt version in Langfuse's prompt management UI.

#### Scenario: Traced generation shows its source prompt
- **WHEN** a RAG or full-doc query is answered using a Langfuse-fetched prompt, and tracing is enabled
- **THEN** the LLM generation in the trace carries the prompt name and version used to produce it, and appears under that prompt version in Langfuse's prompt UI
