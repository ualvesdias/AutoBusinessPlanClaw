import json
from pathlib import Path

from autobusinessplanclaw.config import load_config, load_questionnaire
from autobusinessplanclaw.pipeline import Pipeline


def test_pipeline_generates_outputs(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  allow_web_research: false
  critique_rounds: 1
  pro_agent_count: 9
llm:
  provider: none
output:
  root: artifacts
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: a painful issue
  icp: b2b security teams
  current_solution: spreadsheets
  why_now: current tools are noisy
  advantage: founder expertise
  mvp: prioritization dashboard
  payment_reason: saves time and reduces risk
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    run_dir = Pipeline(cfg).run(answers, web_search_fn=None, output_dir=tmp_path / "run")
    assert (run_dir / "business_plan.md").exists()
    assert (run_dir / "exports" / "financial_model.csv").exists()
    assert (run_dir / "exports" / "competitor_matrix.csv").exists()
    assert (run_dir / "stages" / "competition.json").exists()
    assert (run_dir / "stages" / "persona_critique.json").exists()
    assert (run_dir / "stages" / "tenth_man.json").exists()
    assert (run_dir / "persona_critiques.json").exists()
    assert (run_dir / "tenth_man_report.json").exists()
    assert (run_dir / "checkpoint.json").exists()
    assert (run_dir / "prompts" / "plan_draft.prompt.json").exists()
    assert (run_dir / "prompts" / "plan_draft.response.json").exists()


def test_pipeline_resume_uses_existing_run(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: none
output:
  root: artifacts
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: a painful issue
  icp: b2b security teams
  current_solution: spreadsheets
  why_now: current tools are noisy
  advantage: founder expertise
  mvp: prioritization dashboard
  payment_reason: saves time and reduces risk
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    run_dir = tmp_path / "run"
    pipeline = Pipeline(cfg)
    pipeline.run(answers, web_search_fn=None, output_dir=run_dir)
    resumed = pipeline.run(answers, web_search_fn=None, output_dir=run_dir, resume=True)
    assert resumed == run_dir
    assert (run_dir / "checkpoint.json").exists()


def test_pipeline_fresh_run_cleans_stale_outputs_and_rebuilds_reference_table(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: none
output:
  root: artifacts
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: a painful issue
  icp: b2b security teams
  current_solution: spreadsheets
  why_now: current tools are noisy
  advantage: founder expertise
  mvp: prioritization dashboard
  payment_reason: saves time and reduces risk
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "competitor_reference_table.json").write_text('[{"name":"STALE"}]', encoding="utf-8")
    (run_dir / "research_results.json").write_text('[{"query":"stale","results":[{"title":"old"}]}]', encoding="utf-8")
    exports_dir = run_dir / "exports"
    exports_dir.mkdir()
    (exports_dir / "competitor_reference_table.md").write_text("STALE EXPORT", encoding="utf-8")

    Pipeline(cfg).run(answers, web_search_fn=None, output_dir=run_dir, resume=False)

    reference_rows = json.loads((run_dir / "competitor_reference_table.json").read_text(encoding="utf-8"))
    assert reference_rows[0]["name"] == "Demo idea"
    assert all(row["name"] != "STALE" for row in reference_rows)
    assert "STALE EXPORT" not in (run_dir / "exports" / "competitor_reference_table.md").read_text(encoding="utf-8")
    assert "stale" not in (run_dir / "research_results.json").read_text(encoding="utf-8").lower()


def test_competitor_agent_analysis_marks_incomplete_when_quality_gate_fails(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: none
output:
  root: artifacts
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: a painful issue
  icp: b2b security teams
  current_solution: spreadsheets
  why_now: current tools are noisy
  advantage: founder expertise
  mvp: prioritization dashboard
  payment_reason: saves time and reduces risk
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    run_dir = Pipeline(cfg).run(answers, web_search_fn=None, output_dir=tmp_path / "run")
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    competition = json.loads((run_dir / "competitor_matrix.json").read_text(encoding="utf-8"))
    assert summary["run_status"] == "incomplete"
    assert competition["analysis_quality"]["quality_gate_passed"] is False
    assert all(row["analysis_status"] == "fallback" for row in competition["competitors"])


def test_build_competitor_matrix_uses_analyst_agent_output(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  allow_web_research: true
  critique_rounds: 1
llm:
  provider: none
output:
  root: artifacts
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: due diligence de terceiros é lenta
  icp: times de grc
  current_solution: planilhas
  why_now: volume cresceu
  advantage: founder expertise
  mvp: triagem de fornecedores
  payment_reason: saves time
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    pipeline = Pipeline(cfg)

    pipeline.client.is_configured = lambda: True
    pipeline.client.complete = lambda system, user: json.dumps({
        "positioning": "Plataforma especializada em onboarding e due diligence de fornecedores.",
        "strengths": "Clareza de foco em cadastro e due diligence.",
        "weaknesses": "Pricing e profundidade técnica ainda pouco claros.",
        "analysis_status": "analyzed",
        "confidence": "medium"
    })

    def fake_web_search(query: str, count: int):
        return [{
            "title": "Linkana",
            "url": "https://www.linkana.com/",
            "snippet": "supplier onboarding and due diligence platform for fornecedores with compliance workflows"
        }]

    competition = pipeline._build_competitor_matrix(answers, web_search_fn=fake_web_search)
    assert competition["competitors"]
    first = competition["competitors"][0]
    assert first["analysis_source"] == "competitor_analyst_agent"
    assert first["analysis_status"] == "analyzed"
    assert "due diligence" in first["positioning"].lower()


def test_query_specialist_agent_overrides_heuristics(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Sacolé gourmet em Brasília
  business_model_hint: food brand
runtime:
  allow_web_research: true
  critique_rounds: 1
llm:
  provider: auto
output:
  root: artifacts
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: sobremesa gelada artesanal difícil de encontrar
  icp: consumidores em brasília
  current_solution: picolé industrial
  why_now: calor e delivery
  advantage: marca local
  mvp: 6 sabores de sacolé gourmet
  payment_reason: sabor e conveniência
  first_10_customers: instagram e eventos
  early_success: 100 vendas
  killer_risks: logística fria
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    pipeline = Pipeline(cfg)
    pipeline.client.is_configured = lambda: True

    def fake_complete(system, user):
        if 'market-research query specialist' in system.lower():
            return json.dumps({"queries": ["sacolé gourmet brasília concorrentes", "geladinho gourmet brasília", "picolé artesanal brasília", "sobremesa gelada artesanal brasília"]})
        return json.dumps({
            "positioning": "Marca local de sobremesa gelada artesanal.",
            "strengths": "Posicionamento regional claro.",
            "weaknesses": "Preço e escala ainda incertos.",
            "analysis_status": "analyzed",
            "confidence": "medium"
        })

    pipeline.client.complete = fake_complete
    market_queries = pipeline._build_market_queries(answers)
    assert market_queries[0] == "sacolé gourmet brasília concorrentes"
    assert all("vendor risk" not in q.lower() for q in market_queries)


def test_financial_model_fallback_matches_food_beverage_shape(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Sacolé gourmet Brasília
  business_model_hint: food brand
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: none
output:
  root: artifacts
""", encoding="utf-8")
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: sobremesa gelada artesanal difícil de encontrar
  icp: consumidores em brasília
  current_solution: picolé industrial
  why_now: calor e delivery
  advantage: marca local
  mvp: 6 sabores de sacolé gourmet
  payment_reason: sabor e conveniência
  first_10_customers: instagram e eventos
  early_success: 100 vendas
  killer_risks: logística fria
""", encoding="utf-8")
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    pipeline = Pipeline(cfg)
    model = pipeline._build_financial_model(answers, {}, {"competitors": []}, {}, {})
    assert model["business_archetype"] == "food_beverage"
    assert len(model["rows"]) == 12
    assert model["rows"][0]["customers_or_orders"] > 50
    assert model["rows"][0]["avg_ticket_or_arpa"] < 20
    assert "logística fria" in " ".join(model["assumptions"]["main_cost_drivers"])


def test_financial_model_agent_output_is_normalized(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo SaaS
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: auto
output:
  root: artifacts
""", encoding="utf-8")
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: vuln prioritization
  icp: b2b security teams
  current_solution: spreadsheets
  why_now: current tools are noisy
  advantage: founder expertise
  mvp: prioritization dashboard
  payment_reason: saves time and reduces risk
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""", encoding="utf-8")
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    pipeline = Pipeline(cfg)
    pipeline.client.is_configured = lambda: True
    rows = []
    for m in range(1,13):
        rows.append({"month":m,"customers_or_orders":m,"avg_ticket_or_arpa":1000,"revenue":m*1000,"cogs":100,"gross_profit":m*1000-100,"opex":5000,"cash_flow":m*1000-5100,"notes":"saas model"})
    pipeline.client.complete = lambda system, user: json.dumps({
        "business_archetype": "saas",
        "assumptions": {
            "revenue_model": "clientes x arpa",
            "pricing_logic": "assinatura",
            "unit_economics_logic": "alto gross margin",
            "main_cost_drivers": ["people", "cloud"]
        },
        "rows": rows
    })
    model = pipeline._build_financial_model(answers, {}, {"competitors": []}, {}, {})
    assert model["business_archetype"] == "saas"
    assert len(model["rows"]) == 12
    assert model["rows"][11]["revenue"] == 12000


def test_pipeline_relative_output_is_saved_under_runs(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: none
""",
        encoding="utf-8",
    )
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: a painful issue
  icp: b2b security teams
  current_solution: spreadsheets
  why_now: current tools are noisy
  advantage: founder expertise
  mvp: prioritization dashboard
  payment_reason: saves time and reduces risk
  first_10_customers: founder outbound
  early_success: 2 paying pilots
  killer_risks: no budget
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        run_dir = Pipeline(cfg).run(answers, web_search_fn=None, output_dir="custom-run")
    finally:
        os.chdir(cwd)
    assert run_dir == Path("runs") / "custom-run"
    assert (tmp_path / "runs" / "custom-run" / "business_plan.md").exists()


def test_financial_intelligence_fallback_is_generated(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  name: demo
business:
  idea: Sacolé gourmet Brasília
  business_model_hint: food brand
runtime:
  allow_web_research: false
  critique_rounds: 1
llm:
  provider: none
""", encoding="utf-8")
    answers_path = tmp_path / "answers.yaml"
    answers_path.write_text(
        """
answers:
  problem: sobremesa gelada artesanal difícil de encontrar
  icp: consumidores em brasília
  current_solution: picolé industrial
  why_now: calor e delivery
  advantage: marca local
  mvp: 6 sabores de sacolé gourmet
  payment_reason: sabor e conveniência
  first_10_customers: instagram e eventos
  early_success: 100 vendas
  killer_risks: logística fria
""", encoding="utf-8")
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    run_dir = Pipeline(cfg).run(answers, web_search_fn=None, output_dir=tmp_path / "run")
    financials = json.loads((run_dir / "stages" / "financials.json").read_text(encoding="utf-8"))
    assert financials["analysis"]["intelligence_paragraph"]
    assert len(financials["analysis"]["recommendations"]) >= 1
    assert (run_dir / "exports" / "financial_analysis.md").exists()
