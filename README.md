```
██████╗       ████████╗ ███████╗ ███╗   ███╗
██╔══██╗      ╚══██╔══╝ ██╔════╝ ████╗ ████║
██████╔╝         ██║    █████╗   ██╔████╔██║
██╔══██╗ _. _    ██║    ██╔══╝   ██║╚██╔╝██║
██║  ██║(_|(_|   ██║    ██║      ██║ ╚═╝ ██║
╚═╝  ╚═╝    _|   ╚═╝    ╚═╝      ╚═╝     ╚═╝
```

# rag-tfm

A small RAG (Retrieval-Augmented Generation) demo: ask questions about a
technical manual and get grounded, cited answers, with end-to-end LLMOps
tracing and a comparative evaluation against a no-RAG baseline. Built to
demonstrate RAG development, tracing, and evaluation practice end to end.

## Architecture

Two phases against one manual at a time, named explicitly on the CLI:

1. **Ingest** (`python -m src.ingest <manual.pdf>`, run once per manual):
   chunk the PDF, embed each chunk locally (`BAAI/bge-small-en-v1.5`), and
   persist the vectors to a Chroma collection keyed by a hash of the
   manual's content. Re-ingesting an unchanged file is a no-op.
2. **Ask** (`python -m src.ask`, every invocation): answer a question in
   one of three modes — **RAG** (retrieve top-k chunks, answer from those),
   **`--full-doc`** (skip retrieval, send the whole manual as context), or
   **`--no-context`** (bare question, no manual content at all — the
   baseline). Every mode calls Claude (Anthropic) for answer generation.

Full component-level diagrams and a walkthrough of what runs locally vs.
over the network: [`docs/architecture.md`](docs/architecture.md).

## Setup

Requires Python 3.11+ and an [Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/p-eh/rag-tfm.git
cd rag-tfm
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY; Langfuse keys are optional (see Tracing below)
pre-commit install     # optional, only needed if you plan to commit changes
```

A synthetic sample manual is committed at
`data/manuals/aquaflow-200-manual.pdf`, so the app runs out of the box
without sourcing your own PDF (see [Corpus](#corpus) below):

```bash
python -m src.ingest data/manuals/aquaflow-200-manual.pdf

python -m src.ask "How long should I soak a new filter cartridge before using it?" data/manuals/aquaflow-200-manual.pdf
# -> "...soak a new filter cartridge in cold water for 15 minutes before first use."
#    Sources: aquaflow-200-manual.pdf

python -m src.ask "How long should I soak a new filter cartridge before using it?" data/manuals/aquaflow-200-manual.pdf --full-doc
# -> same grounded answer, built from the whole document instead of retrieved chunks

python -m src.ask "How long should I soak a new filter cartridge before using it?" --no-context
# -> generic, product-agnostic, uncited guidance that doesn't match this manual - the baseline
```

More example questions: [`data/sample-questions.md`](data/sample-questions.md).

## Manual discovery

If you don't already have a manual PDF, `find_manual` can locate one by
product name: it searches the web with Claude's web search tool, shows you
the candidate manual's URL for confirmation (or a numbered list when
multiple are plausible), downloads the one you pick, and ingests it —
equivalent to running `ingest` yourself, just without needing the PDF path
up front.

```bash
python -m src.find_manual "Aquaflow 200 water filter"
```

This is a convenience layered on top of `ingest`, not a replacement for it —
if you already have the manual's path, `python -m src.ingest <manual.pdf>`
is still the direct route.

## Tracing

Every `ask` invocation, in every mode, is traced end-to-end in
[Langfuse](https://langfuse.com/) — retrieved chunks (RAG), the prompt
sent, per-step latency, and token usage — via OpenTelemetry instrumentation
(`openinference-instrumentation-llama-index`). Tracing degrades gracefully:
with no Langfuse credentials configured, tracing is silently skipped; with
credentials configured but Langfuse unreachable, the CLI still prints the
answer and adds a warning about the failed trace flush — either way, the
query itself never fails because of a tracing problem.

A full walkthrough of one question traced in all three modes — trace IDs,
per-step latency breakdown, and the token counts that later feed the eval's
cost numbers — is in
[`results/sample_trace.md`](results/sample_trace.md). Note: loading local
embeddings gives RAG a disadvantage in single-shot CLI invocations — see
the trade-offs section below.

## Evaluation

The empirical case for RAG: 18 hand-written questions against the ingested
manual, each answered under all three modes and scored with
[Ragas](https://github.com/explodinggradients/ragas) (faithfulness and
answer relevancy for all three conditions; context precision/recall for
RAG only, since only RAG has a retrieval step to score). No-context is
judged against RAG's retrieved chunks, not against nothing — its score
shows how much it invents versus what the manual actually documents.

| Metric | No-context baseline | Full-doc | RAG |
|---|---|---|---|
| Faithfulness | 0.10 | 0.98 | 0.96 |
| Answer relevancy | 0.11 | 0.82 | 0.74 |
| Context precision | n/a | n/a | 0.62 |
| Context recall | n/a | n/a | 0.89 |

RAG scores 0.96 on faithfulness against the manual's actual content, versus
0.10 for the no-context baseline judged against that same content — on
manual-specific questions (exact soak times, model numbers, safety limits),
no-context either hedges or invents a plausible-sounding but ungrounded
answer, while RAG's answer traces back to retrieved chunks that can be
checked. Full-doc scores 0.98 on faithfulness, close to RAG's 0.96 — sending
the whole manual isn't meaningfully more accurate here, it's just more
expensive (see below). Full numbers, per-question breakdown, and the
complete interpretation: [`results/eval_results.md`](results/eval_results.md)
(raw scores: [`results/eval_results.json`](results/eval_results.json)).

## Cost, latency, and scalability trade-offs

- **Chunking is a tuned guess, not a solved problem.** `SentenceSplitter`
  at 512 tokens / 64 overlap (configurable via `CHUNK_SIZE`/`CHUNK_OVERLAP`)
  balances multi-step procedure recall against retrieval precision and
  per-query cost — bigger chunks recall more of a procedure at the cost of
  precision and tokens; smaller chunks do the opposite and risk splitting
  a procedure mid-step. Not tuned per-manual; a real deployment with
  diverse manual formats would need this to adapt to document size (see
  the `dynamic-chunking-by-doc-size` stub).
- **Per-query cost is real money, and RAG is the cheap option, not the
  free one.** At Claude Haiku 4.5's published rates, this eval's 18
  questions averaged **$0.0021/query for RAG** vs. **$0.0032/query for
  full-doc** (~1.5x) vs. **$0.0008/query for the unhelpful no-context
  baseline** — full-doc's extra cost is almost entirely input tokens (the
  whole manual resent every query, 2,891 tokens average vs. RAG's 1,786).
  That gap scales linearly with manual size for full-doc and stays roughly
  flat for RAG; at higher query volume or larger manuals, the gap only
  widens in RAG's favor.
- **Local Chroma doesn't scale past one demo.** A file-based, single-process
  vector store with no concurrent-write handling, no replication, and no
  API surface. Fine for one manual at a time on one machine; a real
  deployment needs a hosted/managed vector store, not `storage/` on disk.
- **The embedding model reloads on every CLI invocation** (~7s, the single
  largest cost in a RAG trace — see [Tracing](#tracing) above), because
  this is a single-shot process, not a long-running service. A warm
  process would pay that cost once, not per query (see the
  `interactive-cli` stub).
- **What production would need instead:** a hosted vector store; a
  persistent process or service instead of a single-shot CLI; a
  configurable/pluggable LLM backend instead of Anthropic-only (see
  `pluggable-llm-backend`); an optional hosted embedding API for better
  retrieval quality than the local model (see `openai-embeddings-option`);
  and retrieval beyond plain top-k similarity - reranking, hybrid search,
  etc. (see `retrieval-technique-selector`).

## Corpus

The app indexes and answers questions about **one manual at a time**,
always named explicitly on the command line
(`python -m src.ingest <manual.pdf>`). A
synthetic sample manual (`data/manuals/aquaflow-200-manual.pdf`, generated
for this repo, not a real product) is committed so the app works out of the
box; point `src.ingest`/`src.ask` at your own PDF instead if you want to.
Your own manuals belong in the gitignored `data/manuals/` and are never
committed - only the sample manual and a `.gitkeep` are tracked. A curated,
openly-licensed multi-manual sample corpus is deferred (see the
`sample-corpus-sourcing` stub).

## Status

**Demo project, not production-ready.** Built to show RAG development,
tracing, and evaluation practice, not to run at scale or serve real users.
Deliberately deferred/out-of-scope work is tracked as separate OpenSpec
stub changes under [`openspec/changes/`](openspec/changes/), not silently
dropped:

- [`interactive-cli`](openspec/changes/interactive-cli/) — a session/REPL
  CLI (ask multiple questions per process, switch modes without
  re-invoking) instead of today's single-shot `ask`
- [`pluggable-llm-backend`](openspec/changes/pluggable-llm-backend/) —
  swap the LLM backend via config, including a fully local option
- [`openai-embeddings-option`](openspec/changes/openai-embeddings-option/) —
  a configurable hosted embedding API alongside the local model
- [`retrieval-technique-selector`](openspec/changes/retrieval-technique-selector/) —
  reranking, hybrid search, and other retrieval techniques beyond plain
  top-k similarity
- [`dynamic-chunking-by-doc-size`](openspec/changes/dynamic-chunking-by-doc-size/) —
  chunking/retrieval parameters that adapt to document size
- [`rag-context-continuity`](openspec/changes/rag-context-continuity/) —
  mitigating retrieved chunks that read as disjoint fragments
- [`sample-corpus-sourcing`](openspec/changes/sample-corpus-sourcing/) —
  a curated, openly-licensed multi-manual sample corpus
- [`rag-context-window-growth`](openspec/changes/rag-context-window-growth/) —
  whether RAG's accumulated context (and answer quality) degrades over a
  longer multi-turn session, once `interactive-cli` exists

## License

[MIT](LICENSE)
