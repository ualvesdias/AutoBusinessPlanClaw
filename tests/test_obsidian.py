from autobusinessplanclaw.config import load_config, load_questionnaire
from autobusinessplanclaw.pipeline import Pipeline
from autobusinessplanclaw.obsidian import export_run_to_obsidian


def test_obsidian_export(tmp_path):
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
    vault_dir = export_run_to_obsidian(run_dir, tmp_path / "vault")
    assert (vault_dir / "Home.md").exists()
    assert (vault_dir / "00 Overview" / "MOC.md").exists()
    assert (vault_dir / "00 Overview" / "demo-idea.canvas").exists()
    assert (vault_dir / "05 Plan" / "Business Plan Hub.md").exists()
    assert (vault_dir / "04 Debate" / "Tenth Man.md").exists()
    assert (vault_dir / ".obsidian-export.json").exists()
