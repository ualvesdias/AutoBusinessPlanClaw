import json
from pathlib import Path

from autobusinessplanclaw.cli import _load_injected_web_search_payload, _make_injected_web_search_fn


def test_load_injected_web_search_payload_and_wrapper(tmp_path):
    payload_path = tmp_path / "web.json"
    payload_path.write_text(
        json.dumps(
            {
                "batches": {
                    "query one": [
                        {"title": "Result A", "url": "https://example.com/a", "snippet": "alpha"},
                        {"title": "Result B", "url": "https://example.com/b", "snippet": "beta"},
                    ],
                    "query two": [
                        {"title": "Result C", "url": "https://example.com/c", "snippet": "gamma"}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    payload = _load_injected_web_search_payload(payload_path)
    search_fn = _make_injected_web_search_fn(payload)

    assert list(payload.keys()) == ["query one", "query two"]
    assert len(search_fn("query one", 1)) == 1
    assert search_fn("query two", 5)[0]["title"] == "Result C"
    assert search_fn("missing", 5) == []
