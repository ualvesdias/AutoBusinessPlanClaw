from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .models import ABCConfig
from .llm import OpenAICompatibleClient


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class DoctorReport:
    checks: list[CheckResult]
    overall: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "detail": c.detail,
                    "fix": c.fix,
                }
                for c in self.checks
            ],
        }


def _check_openclaw_http(config: ABCConfig) -> CheckResult:
    client = OpenAICompatibleClient(config.llm)
    token = client._openclaw_token()
    if not token:
        return CheckResult(
            name="openclaw_http",
            status="fail",
            detail="Nenhum token do OpenClaw encontrado.",
            fix="Defina OPENCLAW_GATEWAY_TOKEN ou configure ~/.openclaw/openclaw.json",
        )
    try:
        resp = requests.get(
            f"{config.llm.openclaw_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {token}"},
            timeout=(5, 10),
        )
    except requests.RequestException as exc:
        return CheckResult(
            name="openclaw_http",
            status="fail",
            detail=f"Falha de transporte ao acessar OpenClaw HTTP: {exc}",
            fix="Verifique se o gateway está ativo e se o endpoint chatCompletions/models está habilitado",
        )
    if resp.status_code >= 400:
        return CheckResult(
            name="openclaw_http",
            status="fail",
            detail=f"OpenClaw HTTP respondeu {resp.status_code}: {resp.text[:200]}",
            fix="Habilite gateway.http.endpoints.chatCompletions.enabled e valide o token",
        )
    return CheckResult(name="openclaw_http", status="pass", detail="OpenClaw HTTP acessível")


def _check_openai_compatible(config: ABCConfig) -> CheckResult:
    key = os.getenv(config.llm.api_key_env, "")
    if not key:
        return CheckResult(
            name="openai_compatible",
            status="warn",
            detail=f"{config.llm.api_key_env} não está definido.",
            fix="Defina a variável de ambiente se quiser fallback por API direta",
        )
    try:
        resp = requests.get(
            f"{config.llm.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=(5, 10),
        )
    except requests.RequestException as exc:
        return CheckResult(
            name="openai_compatible",
            status="fail",
            detail=f"Falha de transporte ao acessar API direta: {exc}",
            fix="Verifique rede, endpoint e chave",
        )
    if resp.status_code >= 400:
        return CheckResult(
            name="openai_compatible",
            status="fail",
            detail=f"API direta respondeu {resp.status_code}: {resp.text[:200]}",
            fix="Verifique endpoint, modelo e chave",
        )
    return CheckResult(name="openai_compatible", status="pass", detail="API direta acessível")


def _check_web_search() -> CheckResult:
    if not os.getenv("XAI_API_KEY", ""):
        return CheckResult(
            name="web_search",
            status="warn",
            detail="XAI_API_KEY não definido; pesquisa web ficará limitada/desativada.",
            fix="Defina XAI_API_KEY para habilitar enriquecimento web",
        )
    return CheckResult(name="web_search", status="pass", detail="XAI_API_KEY presente")


def run_doctor(config: ABCConfig) -> DoctorReport:
    checks: list[CheckResult] = []
    provider = config.llm.provider.lower()
    if provider in {"openclaw-http", "auto"}:
        checks.append(_check_openclaw_http(config))
    if provider in {"openai-compatible", "auto"}:
        checks.append(_check_openai_compatible(config))
    if provider == "none":
        checks.append(CheckResult(name="llm_provider", status="pass", detail="provider=none (modo controlado/local)"))
    checks.append(_check_web_search())
    statuses = {c.status for c in checks}
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    return DoctorReport(checks=checks, overall=overall)


def write_doctor_report(report: DoctorReport, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
