from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib import request, error


class OpenClawBridgeError(RuntimeError):
    pass


def load_gateway_token(token_env: str = "OPENCLAW_GATEWAY_TOKEN") -> str:
    token = os.getenv(token_env, "").strip()
    if token:
        return token
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return str(((data.get("gateway") or {}).get("auth") or {}).get("token") or "").strip()
        except Exception:
            return ""
    return ""


def call_gateway_tool(tool: str, args: dict[str, Any], base_url: str = "http://127.0.0.1:18789", token: str = "") -> dict[str, Any]:
    if not token:
        raise OpenClawBridgeError("Missing gateway token for OpenClaw bridge")
    url = base_url.rstrip("/") + "/tools/invoke"
    payload = json.dumps({"tool": tool, "args": args}).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenClawBridgeError(f"Gateway tool call failed: HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise OpenClawBridgeError(f"Gateway tool call failed: {exc}") from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise OpenClawBridgeError(f"Gateway returned non-JSON response: {data[:500]}") from exc


_CITATION_RE = re.compile(r"\[\[(\d+)\]\]\((https?://[^)]+)\)")


def web_search_via_gateway(query: str, count: int = 5, base_url: str = "http://127.0.0.1:18789", token: str = "") -> list[dict[str, Any]]:
    response = call_gateway_tool("web_search", {"query": query, "count": count}, base_url=base_url, token=token)
    if not response.get("ok"):
        return []
    result = response.get("result") or {}
    details = result.get("details") or {}
    content = str(details.get("content") or result.get("content") or "").strip()
    citations = details.get("citations") or []
    items: list[dict[str, Any]] = []

    cleaned_content = re.sub(r"<<<EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>|<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>", "", content).strip()
    cleaned_content = _CITATION_RE.sub("", cleaned_content).strip()
    if cleaned_content:
        items.append({
            "title": f"OpenClaw web synthesis: {query[:120]}",
            "url": "openclaw://web_search/summary",
            "snippet": cleaned_content[:4000],
        })

    seen: set[str] = set()
    for idx, url in enumerate(citations[: max(3, min(count, 8))], start=1):
        url = str(url).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        items.append({
            "title": f"OpenClaw web source {idx}: {query[:80]}",
            "url": url,
            "snippet": cleaned_content[:600] if cleaned_content else query,
        })
    return items
