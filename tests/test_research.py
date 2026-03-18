from autobusinessplanclaw.research import build_market_queries, build_competitor_queries, dedupe_queries, dedupe_evidence, normalize_evidence, extract_competitors_from_evidence, analyze_competitors_from_evidence
from autobusinessplanclaw.models import EvidenceItem


def test_query_builders_expand_and_dedupe():
    answers = {
        "problem": "manual scheduling overhead",
        "icp": "solo health professionals",
        "current_solution": "manual whatsapp scheduling",
        "why_now": "existing tools are expensive",
        "advantage": "domain insight",
        "mvp": "workflow automation software",
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


def test_dedupe_evidence():
    items = [
        EvidenceItem(title="X", url="https://a.com", snippet="1"),
        EvidenceItem(title="X", url="https://a.com", snippet="2"),
        EvidenceItem(title="Y", url="https://b.com", snippet="3"),
    ]
    deduped = dedupe_evidence(items)
    assert len(deduped) == 2


def test_extract_competitors_filters_consulting_and_directory_noise():
    items = normalize_evidence([
        {"title": "Deloitte", "url": "https://www.deloitte.com/br/pt/services/consulting-risk/services/governanca-terceiros-gestao-riscos.html", "snippet": "consulting risk for third party governance"},
        {"title": "Econodata", "url": "https://www.econodata.com.br/empresas/todo-brasil/busca-seguradora/ate-500-funcionarios", "snippet": "directory of insurers and employees"},
        {"title": "Linkana", "url": "https://www.linkana.com/", "snippet": "supplier onboarding and homologação platform for fornecedores"},
        {"title": "Kronoos", "url": "https://www.kronoos.com/", "snippet": "due diligence e compliance de terceiros"},
    ])
    competitors = extract_competitors_from_evidence(items)
    names = [c["name"] for c in competitors]
    assert "Linkana" in names
    assert "Kronoos" in names
    assert "Deloitte" not in names
    assert "Econodata" not in names


def test_competitor_analysis_generates_non_generic_fields_and_quality_metrics():
    items = normalize_evidence([
        {"title": "Linkana", "url": "https://www.linkana.com/", "snippet": "Linkana is a supplier onboarding and homologação platform for fornecedores with compliance workflows and portal features."},
        {"title": "Linkana pricing", "url": "https://www.linkana.com/platform", "snippet": "Supplier onboarding, documentação e compliance automation for procurement teams."},
        {"title": "Kronoos", "url": "https://www.kronoos.com/", "snippet": "Kronoos offers due diligence e compliance de terceiros for vendor risk and onboarding workflows."},
    ])
    competitors, quality = analyze_competitors_from_evidence(items)
    by_name = {c["name"]: c for c in competitors}
    assert quality["competitor_count"] >= 2
    assert quality["analyzed_count"] >= 2
    assert quality["quality_gate_passed"] is True
    assert by_name["Linkana"]["analysis_status"] == "analyzed"
    assert "onboarding" in by_name["Linkana"]["positioning"].lower() or "forneced" in by_name["Linkana"]["positioning"].lower()
    assert by_name["Linkana"]["strengths"] != "Presença web encontrada em pesquisa externa; análise ainda superficial."
    assert by_name["Linkana"]["weaknesses"] != "Evidência insuficiente para afirmar pricing, profundidade funcional e diferencial competitivo com alta confiança."
