## Why

The app is currently text-only end to end: PDF extraction and chunking treat manuals as plain text with no diagram/image understanding, and the only interface is the CLI — there's no web app to render anything visual into. Raised in conversation while proposing `manual-crawler`: once a web app UI exists, answers should be able to show the actual diagram/illustration from the manual page an answer is grounded in, not just cite the manual by name. This is a stub to track the idea, not a committed design.

## What Changes

(Not designed yet.) Rough shape: extract images from PDF pages during ingestion, associate each extracted image with the page/chunk(s) near it, and — once a web app UI exists to render into — surface the relevant image(s) alongside a RAG-mode answer when its grounding chunk has one nearby. Depends entirely on a web app UI existing first; there is none today (CLI only).

## Capabilities

### New Capabilities
(none yet — stub only, no spec-level commitment until this is picked up)

### Modified Capabilities
(none — likely touches `manual-ingestion` for image extraction and would need a new web-app-facing capability once that UI exists)

## Impact

Not assessed yet. Open questions: whether to extract images at ingest time or on demand, how to associate an image with the specific chunk(s) it's relevant to (page-proximity vs. something smarter), and what the web app's own capability/tech stack looks like — none of that exists yet.
