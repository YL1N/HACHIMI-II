from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.root_cause_workflow import _build_llm_client  # noqa: E402


def main() -> None:
    config_path = Path(__file__).resolve().parent / "configs" / "run_local.json"
    if not os.environ.get("XES_LLM_API_KEY", "").strip():
        raise RuntimeError("missing environment variable: XES_LLM_API_KEY")

    client = _build_llm_client(config_path)
    result = client.chat_json(
        system_prompt=(
            'Return exactly one JSON object with keys "status" and "provider". '
            'Example: {"status":"ok","provider":"provider_name"}'
        ),
        user_prompt='请只返回一个JSON对象，status填ok，provider填你所属模型提供方。',
        partial_string_keys=["status", "provider"],
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
