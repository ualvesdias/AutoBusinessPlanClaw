from __future__ import annotations

from dataclasses import dataclass, field, asdict
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


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


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


@dataclass(frozen=True)
class StageOutput:
    name: str
    content: str
    data: dict[str, Any] = field(default_factory=dict)
