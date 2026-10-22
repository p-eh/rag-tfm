## Context

See `proposal.md` - Why/What Changes for motivation and scope. Relevant existing state:

- `src/config.py` already configures an Anthropic client (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) — no other LLM/search provider or API key is wired in today.
- `src/ingest.py` takes one explicit PDF path (`manual-ingestion` spec) and reads from/writes to the gitignored `data/manuals/` directory (`MANUALS_DIR` in config).
- The project's interface is CLI-only; there is no web app layer to plug a UI into today.

## Goals / Non-Goals

**Goals:**
- Turn a product name into a locally ingested manual with one command and one user confirmation step.
- Reuse the existing Anthropic client/config rather than adding a second LLM/search provider.
- Keep the discovery step decoupled from ingestion: it only needs to produce a valid local PDF path and call the existing ingestion entry point.

**Non-Goals:**
- No web app / GUI (CLI only, per proposal).
- No support for non-PDF manual formats (HTML manuals, video, etc.) — same text-only PDF scope as `manual-ingestion`.
- No attempt to crawl beyond a single search-and-fetch pass (no following links across multiple pages, no site-specific scrapers).
- No persistence of rejected candidates or search history.

## Decisions

### Search + ranking via Anthropic's server-side web search tool, not a separate search API
Use the Anthropic Messages API's built-in web search tool in a single tool-enabled call: give Claude the product name, let it search and reason over results, and have it return a ranked list of candidate manual URLs with a short justification per candidate. This reuses the Anthropic client/key already configured in `src/config.py`.

Alternative considered: a dedicated search API (Tavily, SerpAPI, Bing) called directly, with a second LLM call to rank plain-text results. Rejected for now — it adds a second provider/API key for a demo-scoped project, and the built-in web search tool already gives the model direct access to page content for judging "is this the official manual" rather than just a search snippet.

### Ranking and candidate selection happen in one LLM turn
The LLM performs search, evaluates candidates against "is this the correct product's official manual" and "is it a PDF," and returns a structured list of `{url, title, confidence, note}`. The CLI applies a simple rule on that structured output: one candidate returned with high confidence → confirm that one; multiple candidates or ambiguous confidence → show the list.

Alternative considered: a separate ranking pass after search (search call, then a second classification call per candidate). Rejected as unnecessary complexity for the number of candidates involved (a handful of web results) — one turn with the web search tool is sufficient for this scope.

### Download validated by content-type before handing off to ingestion
After user confirmation, fetch the URL and check that the response both starts with the PDF magic bytes and declares a PDF (or generic `application/octet-stream`) content-type before writing it to `data/manuals/` and invoking ingestion. This satisfies the `manual-discovery` spec's "confirmed candidate is not a downloadable PDF" scenario without relying on the LLM's judgment alone (a page can look right but not actually serve a PDF).

### CLI shape mirrors existing commands
New entry point `python -m src.find_manual "<product name>"`, following the same `python -m src.<verb>` convention as `src.ingest` and `src.ask`. On confirmation it downloads to `data/manuals/` and then calls `src.ingest`'s existing ingestion function directly (in-process), rather than shelling out, printing the same "ready to query" confirmation ingestion already prints.

## Risks / Trade-offs

- [Model picks a wrong-but-plausible manual (right brand, wrong model number)] → Mitigation: the confirmation step always shows the URL (and title) before download; the user is the final check, not the LLM.
- [Web search tool returns a page that isn't actually a PDF despite looking official] → Mitigation: content-type/magic-byte validation before ingestion, per the spec's error scenario.
- [Manufacturer sites block automated fetches (403, bot detection)] → Mitigation: surface the fetch failure as a clear CLI error; no retry/evasion logic is in scope (would risk crossing into scraping-around-blocks territory, which this project doesn't need to solve for a demo).
- [Copyright: downloading and locally ingesting a manufacturer's manual at runtime] → Mitigation: same posture as the rest of the project — downloaded manuals land in the already-gitignored `data/manuals/`, never committed; this is a personal/local runtime convenience, not redistribution.

## Open Questions

- Exact structured-output schema for the ranked candidate list (tool-use JSON shape) — an implementation detail to settle in `tasks.md`/code, doesn't change the spec or approach.
