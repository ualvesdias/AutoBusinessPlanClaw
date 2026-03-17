from __future__ import annotations

from .models import EvidenceItem


def build_market_queries(idea: str, answers: dict[str, str]) -> list[str]:
    return [
        f'{idea} market size {answers["icp"]}',
        f'{answers["problem"]} competitors {answers["icp"]}',
        f'{answers["current_solution"]} pricing alternatives',
        f'{answers["first_10_customers"]} demand signals case study',
        f'{answers["killer_risks"]} startup risk industry analysis',
    ]


def normalize_evidence(raw_items: list[dict]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for item in raw_items:
        title = str(item.get("title") or item.get("name") or "Untitled source")
        url = str(item.get("url") or item.get("link") or "")
        snippet = str(item.get("snippet") or item.get("description") or item.get("text") or "")
        items.append(EvidenceItem(title=title, url=url, snippet=snippet))
    return items
