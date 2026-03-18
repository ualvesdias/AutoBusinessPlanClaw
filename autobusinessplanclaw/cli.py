from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from .config import ConfigError, load_config, load_questionnaire
from .health import run_doctor, write_doctor_report
from .html_export import export_run_to_html
from .llm import OpenAICompatibleClient
from .obsidian import export_run_to_obsidian
from .pipeline import Pipeline
from .questionnaire import REQUIRED_QUESTIONS
from .research import normalize_evidence

console = Console()


def _parse_responses_payload(payload: dict[str, Any], provider_label: str, query: str, count: int) -> list[dict[str, Any]]:
    text_chunks: list[str] = []
    page_urls: list[str] = []
    search_queries: list[str] = []

    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        text_chunks.append(output_text.strip())

    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        action = item.get("action") or {}
        if action.get("type") == "open_page" and action.get("url"):
            page_urls.append(str(action.get("url")))
        if action.get("type") == "search" and action.get("query"):
            search_queries.append(str(action.get("query")))
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and content.get("text"):
                text_chunks.append(str(content.get("text")))
            for annotation in content.get("annotations") or []:
                if isinstance(annotation, dict) and annotation.get("url"):
                    page_urls.append(str(annotation.get("url")))

    summary = "\n\n".join(chunk for chunk in text_chunks if chunk).strip()
    page_urls = list(dict.fromkeys(url for url in page_urls if url))
    search_queries = list(dict.fromkeys(q for q in search_queries if q))

    evidence: list[dict[str, Any]] = []
    if summary:
        evidence.append({
            "title": f"{provider_label} web synthesis: {query[:120]}",
            "url": f"{provider_label.lower()}://responses/web_search",
            "snippet": summary[:4000],
        })
    for idx, url in enumerate(page_urls[: max(3, min(count, 8))], start=1):
        evidence.append({
            "title": f"Web source {idx} for: {query[:80]}",
            "url": url,
            "snippet": summary[:600] if summary else f"Derived from {provider_label} web search for query: {query}",
        })
    for idx, sq in enumerate(search_queries[:3], start=1):
        evidence.append({
            "title": f"Search trace {idx}",
            "url": f"{provider_label.lower()}://search/{idx}",
            "snippet": sq,
        })
    return evidence


def _call_responses_web_search(base_url: str, bearer: str, model: str, tool_type: str, provider_label: str, query: str, count: int) -> list[dict[str, Any]]:
    try:
        import requests
    except ImportError:
        return []
    response = requests.post(
        f"{base_url.rstrip('/')}/responses",
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        json={
            "model": model,
            "input": [{"role": "user", "content": f"Search the web and return concrete findings for: {query}"}],
            "tools": [{"type": tool_type}],
            "temperature": 0.1,
        },
        timeout=(10, 90),
    )
    if response.status_code >= 400:
        return []
    return _parse_responses_payload(response.json(), provider_label, query, count)


def _call_openclaw_web_search(config, query: str, count: int) -> list[dict[str, Any]]:
    try:
        client = OpenAICompatibleClient(config.llm)
        token = client._openclaw_token()
    except Exception:
        return []
    if not token:
        return []
    try:
        return _call_responses_web_search(
            base_url=config.llm.openclaw_base_url,
            bearer=token,
            model=config.llm.openclaw_model,
            tool_type="web_search",
            provider_label="openclaw",
            query=query,
            count=count,
        )
    except Exception:
        return []


def _call_openai_web_search(config, query: str, count: int) -> list[dict[str, Any]]:
    try:
        import os
    except ImportError:
        return []
    api_key = os.getenv(config.llm.api_key_env, "")
    if not api_key:
        return []
    try:
        return _call_responses_web_search(
            base_url=config.llm.base_url,
            bearer=api_key,
            model=config.llm.model,
            tool_type="web_search_preview",
            provider_label="openai",
            query=query,
            count=count,
        )
    except Exception:
        return []


def _call_xai_web_search(query: str, count: int) -> list[dict[str, Any]]:
    try:
        import os
    except ImportError:
        return []
    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key:
        return []
    try:
        return _call_responses_web_search(
            base_url="https://api.x.ai/v1",
            bearer=api_key,
            model="grok-4.20-beta-latest-non-reasoning",
            tool_type="web_search",
            provider_label="xai",
            query=query,
            count=count,
        )
    except Exception:
        return []


def _web_search_cascade(config, query: str, count: int) -> list[dict[str, Any]]:
    for provider in (
        lambda: _call_openclaw_web_search(config, query, count),
        lambda: _call_openai_web_search(config, query, count),
        lambda: _call_xai_web_search(query, count),
    ):
        results = provider()
        if results:
            return results
    return []


def cmd_init_questionnaire(args: argparse.Namespace) -> int:
    path = Path(args.output)
    template = {"answers": {key: "" for key, _ in REQUIRED_QUESTIONS}}
    path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    console.print(f"Questionnaire template written to {path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        answers = load_questionnaire(args.answers)
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        return 1

    if not args.skip_preflight:
        report = run_doctor(config)
        for check in report.checks:
            color = {"pass": "green", "warn": "yellow", "fail": "red"}.get(check.status, "white")
            console.print(f"[{color}]{check.status.upper()}[/{color}] {check.name}: {check.detail}")
        if args.doctor_output:
            write_doctor_report(report, args.doctor_output)
        if report.overall == "fail":
            console.print("[red]Preflight failed. Use --skip-preflight only if you know exactly what you're doing.[/red]")
            return 1

    pipeline = Pipeline(config)

    def web_search_wrapper(query: str, count: int):
        raw = _web_search_cascade(config, query, count)
        return [vars(item) for item in normalize_evidence(raw)]

    run_dir = pipeline.run(
        answers=answers,
        web_search_fn=web_search_wrapper,
        output_dir=args.output,
        resume=args.resume,
    )
    console.print(f"Business plan generated in [bold]{run_dir}[/bold]")
    console.print(f"- {run_dir / 'business_plan.md'}")
    console.print(f"- {run_dir / 'persona_critiques.json'}")
    console.print(f"- {run_dir / 'tenth_man_report.json'}")
    console.print(f"- {run_dir / 'competitor_matrix.json'}")
    console.print(f"- {run_dir / 'exports' / 'competitor_matrix.csv'}")
    console.print(f"- {run_dir / 'exports' / 'financial_model.csv'}")
    console.print(f"- {run_dir / 'exports' / 'gtm_experiments.md'}")

    html_path = Path(args.html_output) if args.html_output else Path(run_dir) / 'exports' / 'report.html'
    html_path = export_run_to_html(run_dir, html_path)
    console.print(f"- HTML report: {html_path}")

    if args.export_obsidian:
        vault_dir = Path(args.obsidian_vault_dir) if args.obsidian_vault_dir else Path(run_dir) / 'exports' / 'obsidian-vault'
        vault_dir = export_run_to_obsidian(run_dir, vault_dir)
        console.print(f"- Vault Obsidian: {vault_dir}")
        console.print(f"- {vault_dir / 'Home.md'}")
        console.print(f"- {vault_dir / '00 Overview' / 'MOC.md'}")
    return 0


def cmd_export_obsidian(args: argparse.Namespace) -> int:
    vault_dir = export_run_to_obsidian(args.run_dir, args.vault_dir)
    console.print(f"Vault Obsidian exportado para [bold]{vault_dir}[/bold]")
    console.print(f"- {vault_dir / 'Home.md'}")
    console.print(f"- {vault_dir / '00 Overview' / 'Project Summary.md'}")
    console.print(f"- {vault_dir / '00 Overview' / 'MOC.md'}")
    console.print(f"- {vault_dir / '04 Debate' / 'Tenth Man.md'}")
    return 0


def cmd_export_html(args: argparse.Namespace) -> int:
    html_path = export_run_to_html(args.run_dir, args.html_path)
    console.print(f"HTML exportado para [bold]{html_path}[/bold]")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        return 1
    report = run_doctor(config)
    for check in report.checks:
        color = {"pass": "green", "warn": "yellow", "fail": "red"}.get(check.status, "white")
        console.print(f"[{color}]{check.status.upper()}[/{color}] {check.name}: {check.detail}")
    if args.output:
        write_doctor_report(report, args.output)
    return 0 if report.overall != "fail" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="businessclaw", description="AutoBusinessPlanClaw CLI")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init-questionnaire", help="Write a questionnaire template")
    init_p.add_argument("--output", "-o", default="questionnaire.json")

    run_p = sub.add_parser("run", help="Generate a business plan")
    run_p.add_argument("--config", "-c", default="config.businessclaw.yaml")
    run_p.add_argument("--answers", "-a", default="questionnaire.json")
    run_p.add_argument("--output", "-o")
    run_p.add_argument("--resume", action="store_true", help="Retomar um run existente usando checkpoint.json")
    run_p.add_argument("--skip-preflight", action="store_true", help="Pular preflight de backend/rede/web")
    run_p.add_argument("--doctor-output", help="Salvar relatório JSON do preflight")
    run_p.add_argument("--html-output", help="Caminho do HTML self-contained (padrão: exports/report.html dentro do run)")
    run_p.add_argument("--export-obsidian", action="store_true", help="Exportar automaticamente para um vault do Obsidian ao final do run")
    run_p.add_argument("--obsidian-vault-dir", help="Diretório do vault do Obsidian para export automático")

    obs_p = sub.add_parser("export-obsidian", help="Exportar um run para um novo vault do Obsidian")
    obs_p.add_argument("--run-dir", required=True)
    obs_p.add_argument("--vault-dir", required=True)

    html_p = sub.add_parser("export-html", help="Exportar um run para HTML self-contained")
    html_p.add_argument("--run-dir", required=True)
    html_p.add_argument("--html-path", required=True)

    doctor_p = sub.add_parser("doctor", help="Verificar backend LLM/rede/web antes do run")
    doctor_p.add_argument("--config", "-c", default="config.businessclaw.yaml")
    doctor_p.add_argument("--output", "-o")

    args = parser.parse_args(argv)
    if args.command == "init-questionnaire":
        return cmd_init_questionnaire(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "export-obsidian":
        return cmd_export_obsidian(args)
    if args.command == "export-html":
        return cmd_export_html(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
