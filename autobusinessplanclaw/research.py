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


def build_competitor_queries(idea: str, answers: dict[str, str]) -> list[str]:
    return [
        f'{answers["problem"]} software competitors',
        f'{answers["icp"]} alternatives to {idea}',
        f'{answers["current_solution"]} vendor comparison',
    ]


def normalize_evidence(raw_items: list[dict]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for item in raw_items:
        title = str(item.get("title") or item.get("name") or "Untitled source")
        url = str(item.get("url") or item.get("link") or "")
        snippet = str(item.get("snippet") or item.get("description") or item.get("text") or "")
        items.append(EvidenceItem(title=title, url=url, snippet=snippet))
    return items


def fallback_evidence(idea: str, answers: dict[str, str]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            title="Founder problem statement",
            url="founder://problem",
            snippet=answers["problem"],
        ),
        EvidenceItem(
            title="Founder ICP hypothesis",
            url="founder://icp",
            snippet=answers["icp"],
        ),
        EvidenceItem(
            title="Current workaround analysis",
            url="founder://status-quo",
            snippet=answers["current_solution"],
        ),
        EvidenceItem(
            title="Monetization hypothesis",
            url="founder://monetization",
            snippet=answers["payment_reason"],
        ),
        EvidenceItem(
            title="Initial distribution hypothesis",
            url="founder://gtm",
            snippet=answers["first_10_customers"],
        ),
        EvidenceItem(
            title="Core startup idea",
            url="founder://idea",
            snippet=idea,
        ),
    ]


def fallback_competitors(answers: dict[str, str]) -> list[dict[str, str]]:
    niche = answers["icp"]
    return [
        {
            "name": "Status quo / planilhas",
            "type": "status_quo",
            "positioning": f"Equipes de {niche} usando processos manuais",
            "strengths": "Baixo custo inicial, nenhuma adoção nova necessária",
            "weaknesses": "Baixa escala, priorização fraca, pouca automação",
            "pricing": "Baixo ou implícito",
            "evidence": answers["current_solution"],
        },
        {
            "name": "Consultoria especializada",
            "type": "indirect",
            "positioning": "Serviço humano para resolver ou priorizar o problema",
            "strengths": "Profundidade técnica, credibilidade",
            "weaknesses": "Escala ruim, custo alto, dependência de horas humanas",
            "pricing": "Projeto / retainer",
            "evidence": answers["problem"],
        },
        {
            "name": "Ferramenta horizontal existente",
            "type": "direct",
            "positioning": "Ferramenta genérica que resolve parte da dor",
            "strengths": "Já conhecida pelo mercado, onboarding mais fácil",
            "weaknesses": "Pode gerar ruído ou não atacar o fluxo exato do ICP",
            "pricing": "SaaS",
            "evidence": answers["why_now"],
        },
    ]
