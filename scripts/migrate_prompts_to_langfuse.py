"""One-off script: creates the app's chat prompt in Langfuse from the local
SYSTEM_PROMPT.md (system message) and PROMPT_TEMPLATE.md (user message)
files, labeled "production". Not part of the app's request path - run
manually once per Langfuse project:

    python scripts/migrate_prompts_to_langfuse.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.prompts import CHAT_PROMPT_NAME  # noqa: E402


def main() -> None:
    from langfuse import get_client

    system_prompt = (_ROOT / "SYSTEM_PROMPT.md").read_text(encoding="utf-8").strip()
    template = (_ROOT / "PROMPT_TEMPLATE.md").read_text(encoding="utf-8")
    get_client().create_prompt(
        name=CHAT_PROMPT_NAME,
        type="chat",
        prompt=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": template},
        ],
        labels=["production"],
    )
    print(f"Created prompt '{CHAT_PROMPT_NAME}' (production)")


if __name__ == "__main__":
    main()
