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
