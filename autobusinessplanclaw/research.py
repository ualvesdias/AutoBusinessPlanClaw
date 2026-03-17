from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from .models import EvidenceItem


PRICE_PATTERNS = [
    r"R\$\s?\d+[\.,]?\d*",
    r"US\$\s?\d+[\.,]?\d*",
    r"\d+[\.,]?\d*\s?/mês",
    r"\d+[\.,]?\d*\s?per month",
]

STOP_URL_PREFIXES = (
    "xai://responses/web_search",
    "xai://search/",
    "founder://",
)

COMPETITOR_NAME_PATTERNS = [
    r"\*\*(.+?)\*\*",
    r"-\s*\*\*(.+?)\*\*",
]

IGNORED_ENTITY_PATTERNS = (
    "aqui estão",
    "principais achados",
    "achados concretos",
    "concrete findings",
    "key problems",
    "key findings",
    "soluções concretas",
    "principais plataformas",
    "outras opções",
    "necessidades comuns",
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _extract_domain(url: str) -> str:
    if not url.startswith("http"):
        return ""
    try:
        return url.split("/")[2].lower()
    except Exception:
        return ""


def _looks_like_product_url(url: str) -> bool:
    domain = _extract_domain(url)
    lowered = url.lower()
    blocked_domains = {
        "reddit.com", "www.reddit.com", "instagram.com", "www.instagram.com", "researchgate.net", "www.researchgate.net",
        "youtube.com", "www.youtube.com", "youtu.be", "facebook.com", "www.facebook.com", "linkedin.com", "www.linkedin.com",
    }
    blocked_path_tokens = ("/blog/", "/artigos/", "/article/", "/articles/", "/reel/", "/comments/")
    if domain in blocked_domains:
        return False
    if any(token in lowered for token in blocked_path_tokens):
        return False
    return True


def _extract_prices(text: str) -> list[str]:
    prices: list[str] = []
    for pattern in PRICE_PATTERNS:
        prices.extend(re.findall(pattern, text, flags=re.I))
    deduped: list[str] = []
    seen: set[str] = set()
    for price in prices:
        key = price.lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(price.strip())
    return deduped[:5]


def _infer_competitor_type(text: str, domain: str) -> str:
    lowered = f"{text} {domain}".lower()
    if any(tok in lowered for tok in ["whatsapp", "agendamento", "scheduling", "agenda", "appointment"]):
        return "direct"
    if any(tok in lowered for tok in ["crm", "pipeline", "marketing", "omnichannel"]):
        return "indirect"
    return "indirect"


BRAND_OVERRIDES = {
    "agendaai.com.br": "AgendaAí",
    "gendo.com.br": "Gendo",
    "plenne.com.br": "Plenne",
    "tuaagenda.com": "Tua Agenda",
    "minhaagendavirtual.com.br": "Minha Agenda Virtual",
    "horariointeligente.com.br": "Horário Inteligente",
    "secretariahumanizada.com": "Secretaria Humanizada",
    "secretariahumanizada.com.br": "Secretaria Humanizada",
    "psicomanager.com.br": "PsicoManager",
    "doctoralia.com.br": "Doctoralia",
    "iclinic.com.br": "iClinic",
    "simplybook.me": "SimplyBook.me",
    "reservio.com": "Reservio",
    "agendago.com.br": "Agenda GO",
    "spagenda.com": "SP Agenda",
    "fitcloud.com.br": "FitCloud",
}


def _domain_to_brand(domain: str) -> str:
    host = domain.replace("www.", "")
    if host in BRAND_OVERRIDES:
        return BRAND_OVERRIDES[host]
    brand = host.split(".")[0]
    brand = brand.replace("-", " ").replace("_", " ").strip()
    return brand.title() if brand else domain


def _extract_named_entities_from_text(text: str) -> list[str]:
    names: list[str] = []
    for pattern in COMPETITOR_NAME_PATTERNS:
        names.extend(re.findall(pattern, text))
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in names:
        candidate = _clean_text(re.sub(r"\s*\(.+?\)$", "", name))
        lowered = candidate.lower()
        if len(candidate) < 3:
            continue
        if any(token in lowered for token in IGNORED_ENTITY_PATTERNS):
            continue
        if lowered in {"vantagens", "desvantagens", "principais players", "outras opções", "brasil"}:
            continue
        if candidate.startswith("[[") or candidate.startswith("http"):
            continue
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(candidate)
    return cleaned


def _compact_phrase(value: str, limit: int = 120) -> str:
    cleaned = _clean_text(value)
    cleaned = re.sub(r"[\(\)\[\]{}]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[:limit]
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    return shortened.strip(" .,-")


REGION_ALIASES = {
    "brasil": "Brasil",
    "brazil": "Brasil",
    "pt-br": "Brasil",
    "latam": "LATAM",
}


def _region_hint(region: str | None) -> str:
    if not region:
        return ""
    lowered = _clean_text(region).lower()
    for key, value in REGION_ALIASES.items():
        if key in lowered:
            return value
    return _compact_phrase(region, limit=30)


def build_market_queries(idea: str, answers: dict[str, str], region: str | None = None) -> list[str]:
    problem = _compact_phrase(answers["problem"])
    icp = _compact_phrase(answers["icp"])
    mvp = _compact_phrase(answers["mvp"])
    payment = _compact_phrase(answers["payment_reason"])
    current = _compact_phrase(answers["current_solution"])
    risks = _compact_phrase(answers["killer_risks"])
    idea_short = _compact_phrase(idea)
    region_hint = _region_hint(region)
    suffix = f" {region_hint}" if region_hint else ""
    queries = [
        f'{idea_short} market size {icp}{suffix}',
        f'{problem} competitors {icp}{suffix}',
        f'{current} pricing alternatives {suffix}'.strip(),
        f'{payment} willingness to pay {icp}{suffix}',
        f'{risks} startup risk industry analysis {suffix}'.strip(),
        f'{mvp} software buyer objections {icp}{suffix}',
        f'{problem} workflow inefficiency {icp}{suffix}',
        f'{idea_short} go to market strategy {icp}{suffix}',
    ]
    return dedupe_queries(queries)


def build_competitor_queries(idea: str, answers: dict[str, str], region: str | None = None) -> list[str]:
    problem = _compact_phrase(answers["problem"])
    icp = _compact_phrase(answers["icp"])
    current = _compact_phrase(answers["current_solution"])
    mvp = _compact_phrase(answers["mvp"])
    idea_short = _compact_phrase(idea)
    region_hint = _region_hint(region)
    suffix = f" {region_hint}" if region_hint else ""
    queries = [
        f'{problem} software competitors{suffix}',
        f'{icp} alternatives to {idea_short}{suffix}',
        f'{current} vendor comparison{suffix}',
        f'{mvp} competitors pricing{suffix}',
        f'{icp} scheduling automation tools{suffix}',
        f'{icp} whatsapp automation tools{suffix}',
    ]
    return dedupe_queries(queries)


def dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for query in queries:
        key = _clean_text(query).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(_clean_text(query))
    return result


def normalize_evidence(raw_items: list[dict]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for item in raw_items:
        title = str(item.get("title") or item.get("name") or "Untitled source")
        url = str(item.get("url") or item.get("link") or "")
        snippet = str(item.get("snippet") or item.get("description") or item.get("text") or "")
        items.append(EvidenceItem(title=_clean_text(title), url=_clean_text(url), snippet=_clean_text(snippet)))
    return items


def dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[tuple[str, str]] = set()
    deduped: list[EvidenceItem] = []
    for item in items:
        key = (item.url.strip().lower(), item.title.strip().lower())
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def build_evidence_summary(items: list[EvidenceItem], limit: int = 20) -> dict[str, object]:
    domains = []
    for item in items:
        domain = _extract_domain(item.url)
        if domain:
            domains.append(domain)
    top_domains = Counter(domains).most_common(10)
    return {
        "count": len(items),
        "top_domains": top_domains,
        "sample_titles": [item.title for item in items[:limit]],
    }


def extract_competitors_from_evidence(items: list[EvidenceItem]) -> list[dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    for item in items:
        if item.url.startswith("xai://"):
            continue
        if item.url.startswith("founder://"):
            continue
        if not _looks_like_product_url(item.url):
            continue

        domain = _extract_domain(item.url)
        if not domain:
            continue
        brand = _domain_to_brand(domain)
        lowered_brand = brand.lower()
        if lowered_brand in {"web source 1", "web source 2", "web source 3", "web source 4", "web source 5", "search trace 1", "search trace 2", "search trace 3"}:
            continue
        prices = _extract_prices(item.snippet)
        candidate = {
            "name": brand,
            "type": _infer_competitor_type(item.snippet, domain),
            "positioning": item.snippet[:300],
            "strengths": "Presença web encontrada em pesquisa externa; solução ativa no mercado.",
            "weaknesses": "Necessita validação manual mais precisa de aderência ao ICP e pricing final.",
            "pricing": ", ".join(prices) if prices else "Desconhecido",
            "evidence": item.url,
        }
        existing = candidates.get(lowered_brand)
        if existing is None:
            candidates[lowered_brand] = candidate
        else:
            if existing.get("pricing") == "Desconhecido" and candidate["pricing"] != "Desconhecido":
                existing["pricing"] = candidate["pricing"]
            if len(candidate["positioning"]) > len(existing.get("positioning", "")):
                existing["positioning"] = candidate["positioning"]
            if existing.get("evidence", "").startswith("xai://") and item.url.startswith("http"):
                existing["evidence"] = item.url

    competitors = list(candidates.values())
    competitors.sort(key=lambda c: (c.get("type") != "direct", c.get("name", "")))
    return competitors[:12]


def _summarize_positioning(text: str) -> str:
    cleaned = _clean_text(re.sub(r"[*_#`\[\]]", "", text))
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    generic_prefixes = (
        "sim, ", "aqui estão", "existem ", "essa solução", "esta solução", "a frase ",
        "profissionais liberais como", "profissionais liberais autônomos",
    )
    sentences = re.split(r"(?<=[\.!?])\s+", cleaned)
    for sentence in sentences:
        candidate = sentence.strip(" -")
        if len(candidate) < 30:
            continue
        lowered = candidate.lower()
        if any(lowered.startswith(prefix) for prefix in generic_prefixes):
            continue
        return candidate[:180]
    return cleaned[:180]



def _infer_icp_fit(name: str, evidence: str, default_icp: str) -> str:
    lowered = f"{name} {evidence}".lower()
    matches = []
    if any(tok in lowered for tok in ["psic", "mental"]):
        matches.append("psicólogos")
    if any(tok in lowered for tok in ["nutri", "diet"]):
        matches.append("nutricionistas")
    if any(tok in lowered for tok in ["personal", "fitness", "gym", "treino"]):
        matches.append("personal trainers")
    if any(tok in lowered for tok in ["clinic", "consult", "health", "saude"]):
        matches.append("clínicas/saúde")
    if any(tok in lowered for tok in ["sal", "spa", "beauty", "barbear"]):
        matches.append("beleza/bem-estar")
    if matches:
        uniq = []
        for item in matches:
            if item not in uniq:
                uniq.append(item)
        return f"Mais forte em {', '.join(uniq[:3])}."[:120]
    return f"Parcialmente alinhado ao ICP-alvo: {default_icp[:70]}"[:120]



def build_comparison_rows(competitors: list[dict[str, str]], idea_name: str, answers: dict[str, str]) -> list[dict[str, str]]:
    rows = [
        {
            "name": idea_name,
            "type": "our_idea",
            "icp_fit": _clean_text(answers["icp"])[:120],
            "channel": "WhatsApp-first + dashboard web",
            "pricing": "TBD / validation stage",
            "positioning": _clean_text(answers["problem"])[:180],
            "strengths": _clean_text(answers["advantage"])[:180],
            "weaknesses": _clean_text(answers["killer_risks"])[:180],
            "comparison_to_idea": "Reference product",
            "evidence": "founder://idea",
        }
    ]
    default_icp = _clean_text(answers["icp"])
    for competitor in competitors:
        evidence = competitor.get("evidence", "")
        rows.append({
            "name": competitor.get("name", "Unknown"),
            "type": competitor.get("type", "unknown"),
            "icp_fit": _infer_icp_fit(competitor.get("name", ""), evidence, default_icp),
            "channel": "Web / scheduling / WhatsApp / inferred",
            "pricing": competitor.get("pricing", "Desconhecido"),
            "positioning": _summarize_positioning(competitor.get("positioning", "")),
            "strengths": competitor.get("strengths", "")[:180],
            "weaknesses": competitor.get("weaknesses", "")[:180],
            "comparison_to_idea": "Competes with or overlaps the idea on scheduling automation / workflow outsourcing.",
            "evidence": evidence,
        })
    return rows


def write_comparison_exports(rows: list[dict[str, str]], export_dir: str | Path) -> None:
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)
    csv_path = export_path / "competitor_reference_table.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    md_lines = ["# Tabela de referência cruzada", ""]
    header = ["name", "type", "icp_fit", "channel", "pricing", "positioning", "strengths", "weaknesses", "comparison_to_idea"]
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        md_lines.append("| " + " | ".join((row.get(col, "") or "").replace("|", "/")[:120] for col in header) + " |")
    (export_path / "competitor_reference_table.md").write_text("\n".join(md_lines), encoding="utf-8")


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
