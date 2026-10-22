"""Drift check between the local prompt files and Langfuse - opt-in only,
skipped by default because it calls the real Langfuse API. To run it:

    RUN_LIVE_LANGFUSE_TESTS=1 pytest tests/test_prompts_live.py

Requires the Langfuse keys set (via .env or the environment). A failure means
someone changed a "production" prompt in Langfuse; copy its text into the
matching local file by hand.
"""

import os

import pytest

from src import config, prompts

RUN_LIVE = os.getenv("RUN_LIVE_LANGFUSE_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live Langfuse API call - set RUN_LIVE_LANGFUSE_TESTS=1 to run",
)


@pytest.mark.parametrize(
    ("name", "local_path"),
    [
        (prompts.SYSTEM_PROMPT_NAME, prompts._SYSTEM_PROMPT_PATH),
        (prompts.TEMPLATE_PROMPT_NAME, prompts._PROMPT_TEMPLATE_PATH),
    ],
)
def test_local_prompt_file_matches_langfuse_production(name, local_path):
    from langfuse import Langfuse

    if not (config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY):
        pytest.skip("Langfuse keys are not set")

    client = Langfuse(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST,
    )
    remote = client.get_prompt(name, label="production", cache_ttl_seconds=0)
    local = local_path.read_text(encoding="utf-8")

    assert remote.prompt.strip() == local.strip(), (
        f"{local_path.name} differs from Langfuse prompt '{name}' (production, v{remote.version})"
    )
