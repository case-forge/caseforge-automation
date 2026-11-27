from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vergil_chat.vergil_chat_status import extract_status_query, looks_like_status_prompt


def test_status_prompt_detection_and_query():
    prompt = "What's happening with John Calicotest?"

    assert looks_like_status_prompt(prompt)
    assert extract_status_query(prompt) == "John Calicotest"


def test_tell_me_about_routes_to_status_query():
    prompt = "tell me about shnnon briartest"

    assert looks_like_status_prompt(prompt)
    assert extract_status_query(prompt) == "shnnon briartest"










