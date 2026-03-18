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
  parallel_workers: 6
  prompt_evidence_limit: 80
llm:
  provider: openclaw-http
  timeout_seconds: 20
  max_completion_tokens: 12000
knowledge_base:
  enabled: true
  root_name: kb
self_learning:
  enabled: true
  root_name: evolution
  decay_days: 21
openclaw_bridge:
  enabled: true
  gateway_url: http://127.0.0.1:18789
  gateway_token_env: OPENCLAW_GATEWAY_TOKEN
  use_gateway_web_search: true
  use_web_search_injection: true
  web_search_results_path: injected-web.json
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.project.name == "demo"
    assert cfg.business.idea == "Demo idea"
    assert cfg.runtime.critique_rounds == 3
    assert cfg.runtime.pro_agent_count == 9
    assert cfg.runtime.parallel_workers == 6
    assert cfg.runtime.prompt_evidence_limit == 80
    assert cfg.llm.provider == "openclaw-http"
    assert cfg.llm.timeout_seconds == 20
    assert cfg.llm.max_completion_tokens == 12000
    assert cfg.knowledge_base.root_name == "kb"
    assert cfg.self_learning.decay_days == 21
    assert cfg.openclaw_bridge.enabled is True
    assert cfg.openclaw_bridge.gateway_url == "http://127.0.0.1:18789"
    assert cfg.openclaw_bridge.use_gateway_web_search is True
    assert cfg.openclaw_bridge.use_web_search_injection is True
    assert cfg.openclaw_bridge.web_search_results_path == "injected-web.json"


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
