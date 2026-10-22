"""Discover a product's manual on the web via Claude's web search tool,
confirm it with the user, download it, then hand it to `src.ingest`.

Heavy/network-touching calls are kept inside the functions that need them,
not at module level, so this module stays importable without a live
Anthropic connection.
"""

import argparse
import json
import sys
from pathlib import Path

from src import config

SEARCH_SYSTEM_PROMPT = (
    "You find official technical manuals for products on the web. Given a "
    "product name, use web search to locate its official PDF manual or "
    "documentation. Respond with ONLY a JSON array (no prose, no markdown "
    "fences) of candidate objects, most likely correct first: "
    '[{"url": "...", "title": "...", "confidence": "high|medium|low", '
    '"note": "..."}]. Only include candidates whose url links directly to a '
    'PDF document. "confidence": "high" means you are confident this is the '
    "correct, official manual for the named product, not a different "
    "product, a retailer listing, a forum post, or a review. If nothing "
    "plausible is found, respond with an empty JSON array []."
)


def _build_client():
    import anthropic

    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


SEARCH_MAX_TOKENS = 8192
MAX_SEARCH_CONTINUATIONS = 5


class SearchIncompleteError(Exception):
    """Raised when the search turn stops before producing a final answer."""


def search_candidates(product_name: str) -> list[dict]:
    """Ask the model to search the web and rank candidate manual PDFs for
    `product_name`. Returns a list of {url, title, confidence, note} dicts,
    most likely correct first; empty if nothing plausible was found.

    Raises SearchIncompleteError if the turn is cut off before finishing.
    """
    client = _build_client()
    user_message = {"role": "user", "content": f"Find the official manual for: {product_name}"}
    content = []
    for _ in range(MAX_SEARCH_CONTINUATIONS):
        # On pause_turn the server-side search loop resumes from the
        # assistant content sent back so far.
        messages = [user_message] + ([{"role": "assistant", "content": content}] if content else [])
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=SEARCH_MAX_TOKENS,
            system=SEARCH_SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )
        content = content + list(response.content)
        if response.stop_reason != "pause_turn":
            break

    if response.stop_reason != "end_turn":
        raise SearchIncompleteError(f"web search stopped early ({response.stop_reason})")

    text = "\n".join(block.text for block in content if block.type == "text")
    return parse_candidates(text)


def parse_candidates(text: str) -> list[dict]:
    """Extract the JSON candidate array from the model's reply text.

    Prose between searches can contain stray brackets, so every `[` is tried
    as the start of a JSON array and the last one that parses wins. Returns
    [] if no valid JSON array is present.
    """
    decoder = json.JSONDecoder()
    found = None
    pos = text.find("[")
    while pos != -1:
        try:
            value, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.find("[", pos + 1)
            continue
        if isinstance(value, list):
            found = value
        pos = text.find("[", end)

    if found is None:
        return []
    return [c for c in found if isinstance(c, dict) and c.get("url")]


def needs_selection(candidates: list[dict]) -> bool:
    """A single high-confidence candidate gets a yes/no confirmation;
    anything else (multiple candidates, or one at less than high
    confidence) gets a numbered pick-list instead.
    """
    if len(candidates) != 1:
        return True
    return str(candidates[0].get("confidence", "")).strip().lower() != "high"


def confirm_single(candidate: dict, input_func=input) -> dict | None:
    print(f"Found: {candidate.get('title', candidate['url'])}")
    print(f"  {candidate['url']}")
    if candidate.get("note"):
        print(f"  {candidate['note']}")
    answer = input_func("Use this manual? [y/N] ").strip().lower()
    return candidate if answer == "y" else None


def select_from_list(candidates: list[dict], input_func=input) -> dict | None:
    print("Multiple possible manuals found:")
    for i, candidate in enumerate(candidates, start=1):
        print(f"  {i}. {candidate.get('title', candidate['url'])}")
        print(f"     {candidate['url']}")
        if candidate.get("note"):
            print(f"     {candidate['note']}")
    answer = input_func("Pick a number, or press Enter to skip: ").strip()
    if not answer.isdigit():
        return None
    index = int(answer)
    if not (1 <= index <= len(candidates)):
        return None
    return candidates[index - 1]


def confirm_candidate(candidates: list[dict], input_func=input) -> dict | None:
    """Run the full confirmation flow and return the user-picked candidate,
    or None if the user declined or there was nothing to pick from.
    """
    if not candidates:
        return None
    if needs_selection(candidates):
        return select_from_list(candidates, input_func=input_func)
    return confirm_single(candidates[0], input_func=input_func)


PDF_MAGIC = b"%PDF-"
PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}


class ManualDownloadError(Exception):
    """Raised when a confirmed candidate can't be fetched as a real PDF."""


def is_pdf_response(content: bytes, content_type: str) -> bool:
    """Both must hold: the body starts with the PDF magic bytes, and the
    declared media type is PDF or generic binary (some hosts serve PDFs as
    `application/octet-stream`).
    """
    media_type = content_type.split(";")[0].strip().lower()
    return media_type in PDF_CONTENT_TYPES and content.startswith(PDF_MAGIC)


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in text).strip("-.")


def filename_for(candidate: dict, url: str) -> str:
    from urllib.parse import unquote, urlparse

    name = Path(unquote(urlparse(url).path)).name
    if name.lower().endswith(".pdf"):
        stem = _slugify(name[: -len(".pdf")])
        if stem:
            return f"{stem}.pdf"
    slug = _slugify(candidate.get("title") or "")
    return f"{slug or 'manual'}.pdf"


def unique_path(dest_dir: Path, filename: str, content: bytes) -> tuple[Path, bool]:
    """Pick where to store `content` under `dest_dir` without clobbering a
    different manual: reuse an existing file with identical bytes, otherwise
    append -2, -3, ... to the stem. Returns (path, already_existed).
    """
    candidate = dest_dir / filename
    stem, suffix = candidate.stem, candidate.suffix
    counter = 2
    while candidate.exists():
        if candidate.read_bytes() == content:
            return candidate, True
        candidate = dest_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate, False


def download_manual(candidate: dict, dest_dir: Path | None = None) -> tuple[Path, bool]:
    """Fetch the confirmed candidate's URL and, once confirmed to actually
    be a PDF, store it under `dest_dir` (default: config.MANUALS_DIR) via
    unique_path. Returns (path, already_existed).

    Raises ManualDownloadError on any network failure or non-PDF response;
    nothing is written to disk unless the response passes validation.
    """
    import httpx

    dest_dir = Path(dest_dir) if dest_dir is not None else config.MANUALS_DIR
    url = candidate["url"]

    try:
        response = httpx.get(url, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ManualDownloadError(f"Failed to download {url}: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if not is_pdf_response(response.content, content_type):
        raise ManualDownloadError(
            f"{url} did not return a PDF (content-type: {content_type or 'unknown'})"
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path, already_existed = unique_path(
        dest_dir, filename_for(candidate, url), response.content
    )
    if not already_existed:
        dest_path.write_bytes(response.content)
    return dest_path, already_existed


def find_and_ingest(product_name: str, input_func=input) -> Path | None:
    """Search, confirm, download, and ingest a manual for `product_name`.

    Returns the ingested manual's local path, or None if the search was
    incomplete, nothing was found, the user declined, or download/ingestion
    failed.
    """
    from src.ingest import ingest_and_report

    try:
        candidates = search_candidates(product_name)
    except SearchIncompleteError as exc:
        print(f"Search incomplete: {exc}")
        return None
    if not candidates:
        print(f"No manual found for {product_name!r}.")
        return None

    candidate = confirm_candidate(candidates, input_func=input_func)
    if candidate is None:
        print("No manual selected.")
        return None

    try:
        manual_path, already_existed = download_manual(candidate)
    except ManualDownloadError as exc:
        print(f"Download failed: {exc}")
        return None

    try:
        ingest_and_report(manual_path)
    except Exception as exc:
        if not already_existed:
            manual_path.unlink(missing_ok=True)
        print(f"Ingestion failed for {manual_path.name}: {exc}")
        return None
    return manual_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find a product's manual on the web and ingest it."
    )
    parser.add_argument("product_name", help="Product name to search a manual for")
    args = parser.parse_args()

    if find_and_ingest(args.product_name) is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
