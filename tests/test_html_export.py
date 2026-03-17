from autobusinessplanclaw.config import load_config, load_questionnaire
from autobusinessplanclaw.pipeline import Pipeline
from autobusinessplanclaw.html_export import export_run_to_html


def test_html_export(tmp_path):
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '''
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
''',
        encoding='utf-8'
    )
    answers_path = tmp_path / 'answers.yaml'
    answers_path.write_text(
        '''
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
''',
        encoding='utf-8'
    )
    cfg = load_config(config_path)
    answers = load_questionnaire(answers_path)
    run_dir = Pipeline(cfg).run(answers, web_search_fn=None, output_dir=tmp_path / 'run')
    html_path = export_run_to_html(run_dir, tmp_path / 'report.html')
    assert html_path.exists()
    text = html_path.read_text(encoding='utf-8')
    assert 'Business Plan' in text
    assert 'Competition Matrix' in text
