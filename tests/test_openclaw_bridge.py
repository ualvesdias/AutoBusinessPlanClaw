from autobusinessplanclaw.openclaw_bridge import web_search_via_gateway


def test_web_search_via_gateway_parses_gateway_payload(monkeypatch):
    payload = {
        "ok": True,
        "result": {
            "details": {
                "content": "<<<EXTERNAL_UNTRUSTED_CONTENT id=\"x\">>>\nResult summary with citations [[1]](https://example.com/a)\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id=\"x\">>>",
                "citations": ["https://example.com/a", "https://example.com/b"],
            }
        },
    }

    monkeypatch.setattr(
        "autobusinessplanclaw.openclaw_bridge.call_gateway_tool",
        lambda tool, args, base_url, token: payload,
    )

    results = web_search_via_gateway("demo query", count=2, base_url="http://127.0.0.1:18789", token="t")
    assert results[0]["url"] == "openclaw://web_search/summary"
    assert "Result summary with citations" in results[0]["snippet"]
    assert results[1]["url"] == "https://example.com/a"
