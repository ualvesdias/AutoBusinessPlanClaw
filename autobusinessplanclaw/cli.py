from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from .config import ConfigError, load_config, load_questionnaire
from .pipeline import Pipeline
from .questionnaire import REQUIRED_QUESTIONS
from .research import normalize_evidence

console = Console()


def _call_xai_web_search(query: str, count: int) -> list[dict[str, Any]]:
    try:
        import os
        import requests
    except ImportError:
        return []

    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key:
        return []
    response = requests.post(
        "https://api.x.ai/v1/search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "count": count, "country": "ALL", "language": "en"},
        timeout=60,
    )
    if response.status_code >= 400:
        return []
    payload = response.json()
    items = payload.get("results") or payload.get("data") or []
    return [item for item in items if isinstance(item, dict)]


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

    pipeline = Pipeline(config)

    def web_search_wrapper(query: str, count: int):
        raw = _call_xai_web_search(query, count)
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
    return 0


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

    args = parser.parse_args(argv)
    if args.command == "init-questionnaire":
        return cmd_init_questionnaire(args)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
