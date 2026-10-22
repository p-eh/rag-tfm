## Purpose

Sources the app's prompts from Langfuse's prompt management (versioned, editable without a code deploy) instead of local files, while still working offline, so prompt iteration doesn't require touching the codebase.

## Requirements

### Requirement: Prompts are fetched from Langfuse
When Langfuse is configured and reachable, the system SHALL fetch the system prompt and the context-answer template from Langfuse using the `production` label, rather than reading them from local files.

#### Scenario: RAG or full-doc query fetches prompts from Langfuse
- **WHEN** the ask command answers a question in RAG or full-doc mode and Langfuse is configured and reachable
- **THEN** the system prompt and context-answer template used for the LLM call are the `production`-labeled versions fetched from Langfuse

### Requirement: Prompt fetch failure does not block answering
If Langfuse is unreachable, not configured, or the named prompts don't exist there, the system SHALL fall back to the local prompt files and still return an answer, rather than failing the query.

#### Scenario: Langfuse unreachable during prompt fetch
- **WHEN** the ask command answers a question and Langfuse cannot be reached while fetching a prompt
- **THEN** the system falls back to the local `SYSTEM_PROMPT.md` / `PROMPT_TEMPLATE.md` content, prints a warning naming the prompt that couldn't be fetched (once per prompt per run), and still returns an answer

#### Scenario: Langfuse not configured
- **WHEN** no Langfuse credentials are configured
- **THEN** the system uses the local prompt files directly, without attempting a Langfuse fetch

### Requirement: Traces record which prompt version produced a generation
When a query is traced and its prompt was fetched from Langfuse, the trace SHALL record the prompt name and version that produced the LLM call, visible alongside that call in the Langfuse UI.

#### Scenario: Traced generation shows its source prompt
- **WHEN** a RAG or full-doc query is answered using a Langfuse-fetched prompt, and tracing is enabled
- **THEN** the trace containing that LLM call also shows the prompt name and version used to produce it
