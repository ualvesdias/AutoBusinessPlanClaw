from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    mode: str = "full-auto"


@dataclass(frozen=True)
class BusinessConfig:
    idea: str
    region: str = "global"
    currency: str = "USD"
    business_model_hint: str = ""


@dataclass(frozen=True)
class RuntimeConfig:
    timezone: str = "America/Sao_Paulo"
    max_web_results: int = 8
    allow_web_research: bool = True
    critique_rounds: int = 2
    pro_agent_count: int = 9


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "auto"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    timeout_seconds: int = 45
    openclaw_base_url: str = "http://127.0.0.1:18789/v1"
    openclaw_api_key_env: str = "OPENCLAW_GATEWAY_TOKEN"
    openclaw_model: str = "openclaw:main"


@dataclass(frozen=True)
class OutputConfig:
    root: str = "artifacts"


@dataclass(frozen=True)
class ABCConfig:
    project: ProjectConfig
    business: BusinessConfig
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Questionnaire:
    answers: dict[str, str]


@dataclass(frozen=True)
class EvidenceItem:
    title: str
    url: str
    snippet: str


class Stage(str, Enum):
    INTAKE = "intake"
    MARKET_RESEARCH = "market_research"
    COMPETITION = "competition"
    SYNTHESIS = "synthesis"
    PERSONA_CRITIQUE = "persona_critique"
    TENTH_MAN = "tenth_man"
    PLAN_DRAFT = "plan_draft"
    CRITIQUE = "critique"
    REVISION = "revision"
    FINANCIALS = "financials"
    GTM_PACK = "gtm_pack"
    EXPORT = "export"


@dataclass(frozen=True)
class StageOutput:
    name: str
    content: str
    data: dict[str, Any] = field(default_factory=dict)
