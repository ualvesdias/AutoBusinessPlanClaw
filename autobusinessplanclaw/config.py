from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import ABCConfig, ProjectConfig, BusinessConfig, RuntimeConfig, LLMConfig, OutputConfig
from .questionnaire import required_question_map


class ConfigError(ValueError):
    pass


def load_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError("Config root must be a mapping")
    return data


def load_config(path: str | Path) -> ABCConfig:
    data = load_yaml(path)
    project = data.get("project") or {}
    business = data.get("business") or {}
    runtime = data.get("runtime") or {}
    llm = data.get("llm") or {}
    output = data.get("output") or {}

    if not project.get("name"):
        raise ConfigError("Missing required field: project.name")
    if not business.get("idea"):
        raise ConfigError("Missing required field: business.idea")

    return ABCConfig(
        project=ProjectConfig(name=str(project["name"]), mode=str(project.get("mode", "full-auto"))),
        business=BusinessConfig(
            idea=str(business["idea"]),
            region=str(business.get("region", "global")),
            currency=str(business.get("currency", "USD")),
            business_model_hint=str(business.get("business_model_hint", "")),
        ),
        runtime=RuntimeConfig(
            timezone=str(runtime.get("timezone", "America/Sao_Paulo")),
            max_web_results=int(runtime.get("max_web_results", 8)),
            allow_web_research=bool(runtime.get("allow_web_research", True)),
            critique_rounds=int(runtime.get("critique_rounds", 2)),
            pro_agent_count=int(runtime.get("pro_agent_count", 9)),
            parallel_workers=int(runtime.get("parallel_workers", 4)),
            prompt_evidence_limit=int(runtime.get("prompt_evidence_limit", 60)),
            persist_full_prompts=bool(runtime.get("persist_full_prompts", True)),
            exhaustive_mode=bool(runtime.get("exhaustive_mode", True)),
        ),
        llm=LLMConfig(
            provider=str(llm.get("provider", "auto")),
            base_url=str(llm.get("base_url", "https://api.openai.com/v1")),
            api_key_env=str(llm.get("api_key_env", "OPENAI_API_KEY")),
            model=str(llm.get("model", "gpt-4o-mini")),
            temperature=float(llm.get("temperature", 0.2)),
            timeout_seconds=int(llm.get("timeout_seconds", 45)),
            max_completion_tokens=int(llm.get("max_completion_tokens", 16000)),
            openclaw_base_url=str(llm.get("openclaw_base_url", "http://127.0.0.1:18789/v1")),
            openclaw_api_key_env=str(llm.get("openclaw_api_key_env", "OPENCLAW_GATEWAY_TOKEN")),
            openclaw_model=str(llm.get("openclaw_model", "openclaw:main")),
        ),
        output=OutputConfig(root=str(output.get("root", "artifacts"))),
    )


def load_questionnaire(path: str | Path) -> dict[str, str]:
    data = load_yaml(path)
    answers = data.get("answers", data)
    if not isinstance(answers, dict):
        raise ConfigError("Questionnaire must be a mapping or contain an 'answers' mapping")
    cleaned = {str(k): str(v).strip() for k, v in answers.items()}
    missing = [key for key in required_question_map() if not cleaned.get(key)]
    if missing:
        raise ConfigError("Missing questionnaire answers: " + ", ".join(missing))
    return cleaned
