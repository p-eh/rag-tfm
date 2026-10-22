"""Real web-search + download + ingest smoke test - opt-in only, skipped by
default. Makes actual billed Anthropic API calls (including the web search
tool) and a real HTTP download, so it does not run as part of the normal
`pytest` suite.

    RUN_LIVE_LLM_TESTS=1 pytest tests/test_find_manual_live.py

Requires ANTHROPIC_API_KEY set and the full requirements.txt stack
installed. Ingests into a temp storage dir and temp manuals dir - never the
repo's own storage/ or data/manuals/.
"""

import os

import pytest

from src import config

RUN_LIVE = os.getenv("RUN_LIVE_LLM_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live web search + Anthropic API call - set RUN_LIVE_LLM_TESTS=1 to run "
    "(costs real API usage)",
)


def test_find_and_ingest_real_product(tmp_path, monkeypatch):
    from src.find_manual import find_and_ingest

    if not config.ANTHROPIC_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(config, "STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr(config, "MANUALS_DIR", tmp_path / "manuals")

    def auto_confirm(prompt: str) -> str:
        # Search results/confidence aren't deterministic - answer whichever
        # prompt shape comes back (single yes/no vs. numbered pick-list).
        return "1" if "Pick a number" in prompt else "y"

    manual_path = find_and_ingest("Aquaflow 200 water filter", input_func=auto_confirm)

    assert manual_path is not None
    assert manual_path.exists()
    assert manual_path.suffix == ".pdf"
