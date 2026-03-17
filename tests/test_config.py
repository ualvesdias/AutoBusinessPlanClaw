from autobusinessplanclaw.config import load_config, load_questionnaire


def test_load_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
project:
  name: demo
business:
  idea: Demo idea
runtime:
  critique_rounds: 3
  pro_agent_count: 9
llm:
  provider: openclaw-http
  timeout_seconds: 20
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.project.name == "demo"
    assert cfg.business.idea == "Demo idea"
    assert cfg.runtime.critique_rounds == 3
    assert cfg.runtime.pro_agent_count == 9
    assert cfg.llm.provider == "openclaw-http"
    assert cfg.llm.timeout_seconds == 20


def test_load_questionnaire(tmp_path):
    path = tmp_path / "answers.yaml"
    path.write_text(
        """
answers:
  problem: a
  icp: b
  current_solution: c
  why_now: d
  advantage: e
  mvp: f
  payment_reason: g
  first_10_customers: h
  early_success: i
  killer_risks: j
""",
        encoding="utf-8",
    )
    answers = load_questionnaire(path)
    assert answers["problem"] == "a"
