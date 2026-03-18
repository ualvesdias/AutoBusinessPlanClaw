from autobusinessplanclaw.research import build_market_queries, build_competitor_queries, dedupe_queries, dedupe_evidence, fallback_competitors
from autobusinessplanclaw.models import EvidenceItem


def test_query_builders_expand_and_dedupe():
    answers = {
        "problem": "manual scheduling overhead",
        "icp": "solo health professionals",
        "current_solution": "manual whatsapp scheduling",
        "why_now": "existing tools are expensive",
        "advantage": "domain insight",
        "mvp": "whatsapp scheduling assistant",
        "payment_reason": "saves time",
        "first_10_customers": "founder referrals",
        "early_success": "5 paying clients",
        "killer_risks": "poor onboarding",
    }
    market = build_market_queries("scheduling assistant", answers, region="Brazil")
    competition = build_competitor_queries("scheduling assistant", answers, region="Brasil")
    assert len(market) == 8
    assert len(competition) >= 6
    assert all("Brazil" not in query for query in market)
    assert all(query.count("Brasil") <= 1 for query in market)
    assert any("whatsapp" in query.lower() or "booking" in query.lower() for query in competition)
    assert dedupe_queries(["A", "a ", "B"]) == ["A", "B"]


def test_food_fallback_competitors_do_not_leak_founder_text_as_evidence():
    answers = {
        "problem": "consumidores querem sobremesas geladas premium",
        "icp": "famílias e jovens adultos",
        "current_solution": "picolés industriais e delivery de sobremesa",
        "why_now": "mercado local aberto para marca premium",
        "advantage": "branding e execução local",
        "mvp": "linha enxuta de sacolé gourmet",
        "payment_reason": "produto melhor e acessível",
        "first_10_customers": "instagram e condomínios",
        "early_success": "vendas recorrentes",
        "killer_risks": "baixa diferenciação percebida",
    }
    competitors = fallback_competitors(answers, "marca de sacolé gourmet")
    assert any(c["name"] == "Sorveterias artesanais locais" for c in competitors)
    assert all(c["evidence"].startswith("heuristic://") for c in competitors)


def test_dedupe_evidence():
    items = [
        EvidenceItem(title="X", url="https://a.com", snippet="1"),
        EvidenceItem(title="X", url="https://a.com", snippet="2"),
        EvidenceItem(title="Y", url="https://b.com", snippet="3"),
    ]
    deduped = dedupe_evidence(items)
    assert len(deduped) == 2
