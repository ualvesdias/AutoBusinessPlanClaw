from autobusinessplanclaw.research import build_market_queries, build_competitor_queries, dedupe_queries, dedupe_evidence
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
    assert len(competition) == 6
    assert all("Brazil" not in query for query in market)
    assert all(query.count("Brasil") <= 1 for query in market)
    assert dedupe_queries(["A", "a ", "B"]) == ["A", "B"]


def test_dedupe_evidence():
    items = [
        EvidenceItem(title="X", url="https://a.com", snippet="1"),
        EvidenceItem(title="X", url="https://a.com", snippet="2"),
        EvidenceItem(title="Y", url="https://b.com", snippet="3"),
    ]
    deduped = dedupe_evidence(items)
    assert len(deduped) == 2
