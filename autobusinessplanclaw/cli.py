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
from .obsidian import export_run_to_obsidian
from .openclaw_bridge import OpenClawBridgeError, load_gateway_token, web_search_via_gateway
from .pipeline import Pipeline
from .questionnaire import REQUIRED_QUESTIONS
console = Console()


def _load_injected_web_search_payload(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    payload_path = Path(path).expanduser().resolve()
    data = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("Injected web search payload must be a JSON object")

    batches = data.get("batches", data)
    if not isinstance(batches, dict):
        raise ConfigError("Injected web search payload must contain a 'batches' object or be a query->results mapping")

    normalized: dict[str, list[dict[str, Any]]] = {}
    for query, results in batches.items():
        if not isinstance(results, list):
            continue
        normalized[str(query).strip()] = [item for item in results if isinstance(item, dict)]
    return normalized



def _make_injected_web_search_fn(payload: dict[str, list[dict[str, Any]]]):
    def _search(query: str, count: int):
        results = payload.get(query.strip(), [])
        return results[:count] if count > 0 else results

    return _search



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

    injected_path = args.web_search_results or config.openclaw_bridge.web_search_results_path
    web_search_fn = None
    if config.runtime.allow_web_research and (args.use_gateway_web_search or (config.openclaw_bridge.enabled and config.openclaw_bridge.use_gateway_web_search)):
        try:
            gateway_token = load_gateway_token(config.openclaw_bridge.gateway_token_env)
            if not gateway_token:
                console.print("[yellow]OpenClaw bridge enabled, but no gateway token was found. Falling back.[/yellow]")
            else:
                bridge_url = config.openclaw_bridge.gateway_url
                web_search_fn = lambda query, count: web_search_via_gateway(query=query, count=count, base_url=bridge_url, token=gateway_token)
                console.print(f"[green]Using OpenClaw Gateway web search bridge:[/green] {bridge_url}")
        except OpenClawBridgeError as exc:
            console.print(f"[yellow]OpenClaw bridge unavailable:[/yellow] {exc}")

    if web_search_fn is None and config.runtime.allow_web_research and (args.use_injected_web_search or config.openclaw_bridge.use_web_search_injection):
        if not injected_path:
            console.print("[yellow]Injected web search enabled, but no payload path was provided. Falling back to local evidence only.[/yellow]")
        else:
            payload = _load_injected_web_search_payload(injected_path)
            web_search_fn = _make_injected_web_search_fn(payload)
            console.print(f"[green]Using injected web search payload:[/green] {injected_path}")

    run_dir = pipeline.run(
        answers=answers,
        web_search_fn=web_search_fn,
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
    run_p.add_argument("--use-gateway-web-search", action="store_true", help="Usar o Gateway local do OpenClaw para executar web_search durante o run")
    run_p.add_argument("--use-injected-web-search", action="store_true", help="Consumir resultados de busca web injetados pelo orquestrador/OpenClaw")
    run_p.add_argument("--web-search-results", help="JSON com batches de web search no formato query -> [results]")

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
