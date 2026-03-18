from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from .models import EvidenceItem

GENERIC_POSITIONING_FALLBACK = "Solução de software com aderência parcial ao problema central descrito pelo founder."
GENERIC_STRENGTHS_FALLBACK = "Presença web encontrada em pesquisa externa; análise ainda superficial."
GENERIC_WEAKNESSES_FALLBACK = "Evidência insuficiente para afirmar pricing, profundidade funcional e diferencial competitivo com alta confiança."


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
        "pitchbook.com", "owler.com", "macrotrends.net", "clodura.ai", "leadiq.com", "plusvibe.ai",
    }
    blocked_domain_fragments = (
        "capterra", "g2.com", "g2crowd", "distrito.me", "serasaexperian.com.br", "fastcompanybrasil",
        "jpefconsultoria", "ensun.io", "randoncorp.com", "atlasgov.com", "grcsolutions.com.br", "anbima.com.br",
        "metrobh.com.br", "mercadopago.com.br", "gov.br", "blog.",
    )
    blocked_path_tokens = ("/blog/", "/artigos/", "/article/", "/articles/", "/reel/", "/comments/", ".pdf")
    if domain in blocked_domains:
        return False
    if any(fragment in domain for fragment in blocked_domain_fragments):
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


def _infer_competitor_search_terms(idea: str, answers: dict[str, str]) -> list[str]:
    text = f"{idea} {answers['problem']} {answers['current_solution']} {answers['mvp']} {answers['icp']}".lower()
    if any(tok in text for tok in ["fornecedor", "fornecedores", "supplier", "third party", "tp rm", "tprm", "due diligence", "grc"]):
        return [
            "third party risk management software",
            "vendor risk management platform",
            "supplier onboarding software",
            "supplier due diligence platform",
            "third party due diligence software",
            "vendor compliance platform",
        ]
    if any(tok in text for tok in ["whatsapp", "agendamento", "agenda", "appointment", "scheduling"]):
        return [
            "whatsapp scheduling software",
            "appointment scheduling software",
            "agenda online para profissionais",
            "automação de atendimento whatsapp",
            "booking software",
            "secretária virtual",
        ]
    return [
        _compact_phrase(idea, 80),
        _compact_phrase(answers["current_solution"], 80),
        _compact_phrase(answers["mvp"], 80),
        "competitors",
        "alternatives",
        "software",
    ]


def build_competitor_queries(idea: str, answers: dict[str, str], region: str | None = None) -> list[str]:
    problem = _compact_phrase(answers["problem"], 90)
    icp = _compact_phrase(answers["icp"], 90)
    current = _compact_phrase(answers["current_solution"], 90)
    idea_short = _compact_phrase(idea, 90)
    region_hint = _region_hint(region)
    suffix = f" {region_hint}" if region_hint else ""
    terms = _infer_competitor_search_terms(idea, answers)
    queries = [
        f'{idea_short} competitors{suffix}',
        f'{problem} alternatives {suffix}'.strip(),
        f'{current} software alternatives{suffix}',
        f'{icp} vendor risk tools{suffix}',
    ]
    queries.extend(f'{term}{suffix}' for term in terms[:4])
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


def _is_product_competitor(item: EvidenceItem) -> bool:
    domain = _extract_domain(item.url)
    lowered = f"{domain} {item.snippet}".lower()
    reject_tokens = [
        "deloitte", "econodata", "consultoria", "market size", "directory", "research report",
        "ranking", "largest companies", "seguradoras", "employees", "consulting-risk", "slashdot", "sourceforge",
    ]
    if any(tok in lowered for tok in reject_tokens):
        return False
    positive_tokens = [
        "supplier", "fornecedor", "third party", "due diligence", "homolog", "onboarding",
        "tp rm", "tprm", "vendor risk", "gestão de terceiros", "gestão de fornecedores", "compliance",
    ]
    return any(tok in lowered for tok in positive_tokens)


def _strip_markdown_noise(text: str) -> str:
    cleaned = re.sub(r"[*_#`\[\]]", " ", text or "")
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    return _clean_text(cleaned)


def _split_sentences(text: str) -> list[str]:
    cleaned = _strip_markdown_noise(text)
    return [part.strip(" -") for part in re.split(r"(?<=[\.!?])\s+", cleaned) if part.strip(" -")]


def _collect_candidate_evidence(items: list[EvidenceItem]) -> dict[str, dict[str, object]]:
    candidates: dict[str, dict[str, object]] = {}
    for item in items:
        if item.url.startswith("xai://") or item.url.startswith("founder://"):
            continue
        if not _looks_like_product_url(item.url):
            continue
        if not _is_product_competitor(item):
            continue
        domain = _extract_domain(item.url)
        if not domain:
            continue
        brand = _domain_to_brand(domain)
        lowered_brand = brand.lower()
        if lowered_brand in {"web source 1", "web source 2", "web source 3", "web source 4", "web source 5", "search trace 1", "search trace 2", "search trace 3", "br"}:
            continue
        if len(brand) <= 2:
            continue
        bucket = candidates.setdefault(lowered_brand, {
            "name": brand,
            "domain": domain,
            "type": _infer_competitor_type(item.snippet, domain),
            "pricing": "Desconhecido",
            "evidence": item.url,
            "evidence_items": [],
        })
        bucket["evidence_items"].append(item)
        pricing = ", ".join(_extract_prices(item.snippet)) or "Desconhecido"
        if bucket["pricing"] == "Desconhecido" and pricing != "Desconhecido":
            bucket["pricing"] = pricing
        if bucket["type"] != "direct" and _infer_competitor_type(item.snippet, domain) == "direct":
            bucket["type"] = "direct"
    return candidates


def prepare_competitor_candidates(items: list[EvidenceItem]) -> list[dict[str, object]]:
    candidates = _collect_candidate_evidence(items)
    prepared: list[dict[str, object]] = []
    for bucket in candidates.values():
        evidence_items = list(bucket.get("evidence_items", []))
        prepared.append({
            "name": str(bucket.get("name", "Unknown")),
            "domain": str(bucket.get("domain", "")),
            "type": str(bucket.get("type", "indirect")),
            "pricing": str(bucket.get("pricing", "Desconhecido")),
            "evidence": str(bucket.get("evidence", "")),
            "evidence_count": len(evidence_items),
            "evidence_excerpt": _compact_phrase(" ".join(item.snippet for item in evidence_items if item.snippet), limit=180) if evidence_items else "",
            "evidence_snippets": [item.snippet for item in evidence_items if item.snippet][:8],
            "evidence_urls": [item.url for item in evidence_items if item.url][:8],
        })
    prepared.sort(key=lambda c: (c.get("type") != "direct", c.get("name", "")))
    return prepared[:10]


def build_competitor_quality(competitors: list[dict[str, object]], raw_candidate_count: int | None = None) -> dict[str, object]:
    quality = {
        "raw_candidate_count": raw_candidate_count if raw_candidate_count is not None else len(competitors),
        "competitor_count": len(competitors),
        "fallback_count": sum(1 for c in competitors if c.get("analysis_status") == "fallback"),
        "analyzed_count": sum(1 for c in competitors if c.get("analysis_status") == "analyzed"),
        "agent_count": sum(1 for c in competitors if c.get("analysis_source") == "competitor_analyst_agent"),
    }
    quality["fallback_ratio"] = round((quality["fallback_count"] / quality["competitor_count"]), 3) if quality["competitor_count"] else 1.0
    quality["quality_gate_passed"] = quality["competitor_count"] > 0 and quality["fallback_ratio"] <= 0.5
    return quality


def _derive_positioning(name: str, snippets: list[str], domain: str) -> str:
    keyword_map = [
        (("supplier", "fornecedor", "fornecedores"), "Plataforma focada em gestão e relacionamento de fornecedores"),
        (("third party", "terceiros", "third-party"), "Solução voltada à gestão e avaliação de terceiros"),
        (("due diligence",), "Plataforma de due diligence e validação de risco"),
        (("onboarding", "homolog"), "Ferramenta de onboarding, homologação e coleta documental"),
        (("compliance",), "Solução com foco em compliance operacional e controles"),
        (("background check",), "Serviço de background check e validação cadastral"),
        (("procurement", "srm"), "Plataforma de procurement/SRM com processos de cadastro e governança"),
    ]
    joined = " ".join(snippets).lower()
    for sentence in _split_sentences(" ".join(snippets)):
        lowered = sentence.lower()
        if name.lower() in lowered and any(tok in lowered for tokens, _ in keyword_map for tok in tokens):
            return sentence[:220]
    for tokens, description in keyword_map:
        if any(tok in joined for tok in tokens):
            return description + "."
    if any(k in domain for k in ["sap", "ariba", "coupa", "softexpert"]):
        return "Suite enterprise com supplier management, compliance e workflows de procurement."
    return GENERIC_POSITIONING_FALLBACK


def _derive_strengths(snippets: list[str], domain: str) -> tuple[str, str]:
    joined = " ".join(snippets).lower()
    reasons = []
    if any(tok in joined for tok in ["compliance", "due diligence", "background check", "monitoramento"]):
        reasons.append("cobre componentes claros de risco/compliance")
    if any(tok in joined for tok in ["onboarding", "homolog", "document", "cadastro"]):
        reasons.append("endereça onboarding documental e fluxo operacional")
    if any(tok in joined for tok in ["portal", "platform", "plataforma", "software", "saas"]):
        reasons.append("tem proposta de produto B2B relativamente clara")
    if any(k in domain for k in ["sap", "ariba", "coupa", "softexpert"]):
        reasons.append("marca e cobertura enterprise")
    if reasons:
        text = "Pelos sinais públicos coletados, parece forte porque " + "; ".join(reasons[:3]) + "."
        status = "analyzed"
    else:
        text = GENERIC_STRENGTHS_FALLBACK
        status = "fallback"
    return text, status


def _derive_weaknesses(snippets: list[str], domain: str, type_: str) -> tuple[str, str]:
    joined = " ".join(snippets).lower()
    concerns = []
    if any(k in domain for k in ["sap", "ariba", "coupa", "softexpert"]):
        concerns.append("pode ser excessivamente enterprise para times mid-market enxutos")
    if not any(tok in joined for tok in ["pricing", "preço", "r$", "usd", "/mês", "per month"]):
        concerns.append("pricing não ficou claro nas evidências públicas coletadas")
    if not any(tok in joined for tok in ["security", "segurança", "risk", "risco", "tprm", "due diligence"]):
        concerns.append("profundidade específica de risco/segurança ainda não ficou comprovada")
    if type_ != "direct":
        concerns.append("a aderência ao caso principal parece parcial, não total")
    if concerns:
        text = "Possíveis fragilidades: " + "; ".join(concerns[:3]) + "."
        status = "analyzed"
    else:
        text = GENERIC_WEAKNESSES_FALLBACK
        status = "fallback"
    return text, status


def analyze_competitors_from_evidence(items: list[EvidenceItem]) -> tuple[list[dict[str, str]], dict[str, object]]:
    candidates = _collect_candidate_evidence(items)
    competitors: list[dict[str, str]] = []
    fallback_count = 0
    for lowered_brand, bucket in candidates.items():
        evidence_items = bucket.get("evidence_items", [])
        snippets = [item.snippet for item in evidence_items if item.snippet]
        domain = str(bucket.get("domain", ""))
        positioning = _derive_positioning(str(bucket.get("name", "")), snippets, domain)
        strengths, strengths_status = _derive_strengths(snippets, domain)
        weaknesses, weaknesses_status = _derive_weaknesses(snippets, domain, str(bucket.get("type", "indirect")))
        used_fallback = positioning == GENERIC_POSITIONING_FALLBACK or strengths_status == "fallback" or weaknesses_status == "fallback"
        if used_fallback:
            fallback_count += 1
        competitors.append({
            "name": str(bucket.get("name", "Unknown")),
            "type": str(bucket.get("type", "indirect")),
            "positioning": positioning,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "pricing": str(bucket.get("pricing", "Desconhecido")),
            "evidence": str(bucket.get("evidence", "")),
            "analysis_status": "fallback" if used_fallback else "analyzed",
            "analysis_source": "evidence_synthesis",
            "evidence_count": str(len(evidence_items)),
            "evidence_excerpt": _compact_phrase(" ".join(snippets), limit=180) if snippets else "",
        })
    competitors.sort(key=lambda c: (c.get("type") != "direct", c.get("analysis_status") == "fallback", c.get("name", "")))
    competitors = competitors[:10]
    quality = build_competitor_quality(competitors, raw_candidate_count=len(candidates))
    return competitors, quality


def extract_competitors_from_evidence(items: list[EvidenceItem]) -> list[dict[str, str]]:
    competitors, _quality = analyze_competitors_from_evidence(items)
    return competitors


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
    if any(tok in lowered for tok in ["thirdsafe", "linkana", "vaas", "fornecedor", "supplier", "third party", "vendor"]):
        return "Alta aderência a times de GRC/compliance/segurança com processo de terceiros."[:120]
    if any(tok in lowered for tok in ["sap", "ariba", "coupa", "softexpert"]):
        return "Aderência funcional relevante, mas mais típica de operação enterprise."[:120]
    return f"Parcialmente alinhado ao ICP-alvo: {default_icp[:70]}"[:120]


def _infer_solution_frame(idea_name: str, answers: dict[str, str]) -> tuple[str, str, str]:
    text = f"{idea_name} {answers['problem']} {answers['mvp']} {answers['current_solution']}".lower()
    if any(tok in text for tok in ["fornecedor", "fornecedores", "supplier", "third party", "tprm", "grc", "due diligence"]):
        return (
            "Portal SaaS de intake, due diligence e priorização de risco",
            "Software / workflow / compliance platform inferred",
            "Compete na gestão de terceiros, homologação, due diligence ou priorização de risco de fornecedores.",
        )
    if any(tok in text for tok in ["whatsapp", "agendamento", "agenda", "appointment", "scheduling"]):
        return (
            "WhatsApp-first + dashboard web",
            "Web / scheduling / WhatsApp / inferred",
            "Competes with or overlaps the idea on scheduling automation / workflow outsourcing.",
        )
    return (
        "Digital product / workflow software",
        "Software / service inferred",
        "Competes with or overlaps the core workflow targeted by the idea.",
    )


def build_comparison_rows(competitors: list[dict[str, str]], idea_name: str, answers: dict[str, str]) -> list[dict[str, str]]:
    our_channel, competitor_channel, comparison_frame = _infer_solution_frame(idea_name, answers)
    rows = [
        {
            "name": idea_name,
            "type": "our_idea",
            "icp_fit": _clean_text(answers["icp"])[:120],
            "channel": our_channel,
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
            "channel": competitor_channel,
            "pricing": competitor.get("pricing", "Desconhecido"),
            "positioning": _summarize_positioning(competitor.get("positioning", "")),
            "strengths": competitor.get("strengths", "")[:180],
            "weaknesses": competitor.get("weaknesses", "")[:180],
            "comparison_to_idea": comparison_frame,
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


def fallback_competitors(answers: dict[str, str], idea: str = "") -> list[dict[str, str]]:
    text = f"{idea} {answers['problem']} {answers['current_solution']} {answers['mvp']} {answers['icp']}".lower()
    if any(tok in text for tok in ["fornecedor", "fornecedores", "supplier", "third party", "tprm", "grc", "due diligence"]):
        return [
            {
                "name": "TPRM suite enterprise",
                "type": "direct",
                "positioning": "Plataforma mais robusta de third-party risk para empresas com programa maduro de compliance e procurement.",
                "strengths": "Cobertura funcional ampla e marca enterprise reconhecida.",
                "weaknesses": "Pode ser pesada, cara e lenta para mid-market com time pequeno.",
                "pricing": "Enterprise",
                "evidence": "heuristic://enterprise-tprm-suite",
            },
            {
                "name": "Portal de homologação de fornecedores",
                "type": "direct",
                "positioning": "Solução focada em cadastro, documentos, homologação e workflow de fornecedores.",
                "strengths": "Resolve onboarding e organização operacional com clareza.",
                "weaknesses": "Nem sempre prioriza risco de forma contextual para segurança/GRC.",
                "pricing": "SaaS B2B",
                "evidence": "heuristic://supplier-onboarding-platform",
            },
            {
                "name": "Consultoria e due diligence manual",
                "type": "status_quo",
                "positioning": "Processo humano com planilhas, formulários e análise artesanal de terceiros.",
                "strengths": "Flexível e possível de começar sem software novo.",
                "weaknesses": "Baixa escala, pouca rastreabilidade e priorização inconsistente.",
                "pricing": "Projeto / horas",
                "evidence": "heuristic://manual-third-party-risk-process",
            },
        ]
    niche = answers["icp"]
    return [
        {
            "name": "Status quo / planilhas",
            "type": "status_quo",
            "positioning": f"Equipes de {niche} usando processos manuais",
            "strengths": "Baixo custo inicial, nenhuma adoção nova necessária",
            "weaknesses": "Baixa escala, priorização fraca, pouca automação",
            "pricing": "Baixo ou implícito",
            "evidence": "heuristic://status-quo",
        },
        {
            "name": "Consultoria especializada",
            "type": "indirect",
            "positioning": "Serviço humano para resolver ou priorizar o problema",
            "strengths": "Profundidade técnica, credibilidade",
            "weaknesses": "Escala ruim, custo alto, dependência de horas humanas",
            "pricing": "Projeto / retainer",
            "evidence": "heuristic://specialized-service",
        },
        {
            "name": "Ferramenta horizontal existente",
            "type": "direct",
            "positioning": "Ferramenta genérica que resolve parte da dor",
            "strengths": "Já conhecida pelo mercado, onboarding mais fácil",
            "weaknesses": "Pode gerar ruído ou não atacar o fluxo exato do ICP",
            "pricing": "SaaS",
            "evidence": "heuristic://horizontal-tool",
        },
    ]
