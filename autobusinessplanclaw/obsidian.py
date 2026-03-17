from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "note"


def safe_note_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', '-', value).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned or 'Note'


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def export_run_to_obsidian(run_dir: str | Path, vault_dir: str | Path) -> Path:
    run_path = Path(run_dir)
    vault_path = Path(vault_dir)
    vault_path.mkdir(parents=True, exist_ok=True)

    folders = {
        "home": vault_path,
        "overview": vault_path / "00 Overview",
        "inputs": vault_path / "01 Inputs",
        "research": vault_path / "02 Research",
        "competition": vault_path / "03 Competition",
        "debate": vault_path / "04 Debate",
        "plan": vault_path / "05 Plan",
        "finance": vault_path / "06 Finance",
        "gtm": vault_path / "07 GTM",
        "ops": vault_path / "08 Ops",
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)

    answers = read_json(run_path / "answers.json", {})
    summary = read_json(run_path / "run_summary.json", {})
    synthesis = read_json(run_path / "synthesis.json", {})
    persona = read_json(run_path / "persona_critiques.json", {})
    tenth = read_json(run_path / "tenth_man_report.json", {})
    competition = read_json(run_path / "competitor_matrix.json", {})
    critiques = read_json(run_path / "critiques.json", [])
    queries = read_json(run_path / "research_queries.json", [])
    checkpoint = read_json(run_path / "checkpoint.json", {})

    plan_md = (run_path / "business_plan.md").read_text(encoding="utf-8") if (run_path / "business_plan.md").exists() else ""
    gtm_md = (run_path / "exports" / "gtm_experiments.md").read_text(encoding="utf-8") if (run_path / "exports" / "gtm_experiments.md").exists() else ""
    competitor_md = (run_path / "exports" / "competitor_matrix.md").read_text(encoding="utf-8") if (run_path / "exports" / "competitor_matrix.md").exists() else ""
    finance_csv = (run_path / "exports" / "financial_model.csv").read_text(encoding="utf-8") if (run_path / "exports" / "financial_model.csv").exists() else ""

    idea = str(summary.get("idea") or run_path.name)
    idea_slug = slugify(idea)

    index = f"""# {idea}

## Navegação
- [[Project Summary]]
- [[Founder Answers]]
- [[Research Overview]]
- [[Competition Matrix]]
- [[Debate Overview]]
- [[Business Plan]]
- [[Financial Model]]
- [[GTM Experiments]]
- [[Run Metadata]]

## Estrutura
- Inputs: `01 Inputs/`
- Pesquisa: `02 Research/`
- Concorrência: `03 Competition/`
- Debate: `04 Debate/`
- Plano: `05 Plan/`
- Financeiro: `06 Finance/`
- GTM: `07 GTM/`
"""

    (folders["home"] / "Home.md").write_text(index, encoding="utf-8")

    (folders["overview"] / "Project Summary.md").write_text(
        f"# Project Summary\n\n- Ideia: {idea}\n- Run dir: `{run_path}`\n- Vault: `{vault_path}`\n- Evidence count: {summary.get('evidence_count', 0)}\n- Critique rounds: {summary.get('critique_rounds', 0)}\n- Persona agents: {summary.get('persona_count', 0)}\n- Pro agents: {summary.get('pro_agent_count', 0)}\n\n## Links\n- [[Founder Answers]]\n- [[Research Overview]]\n- [[Competition Matrix]]\n- [[Debate Overview]]\n- [[Business Plan]]\n- [[Financial Model]]\n- [[GTM Experiments]]\n- [[Run Metadata]]\n",
        encoding="utf-8",
    )

    answers_lines = ["# Founder Answers", "", "## Respostas"]
    for key, value in answers.items():
        answers_lines.append(f"- **{key}**: {value}")
    answers_lines += ["", "## Links", "- [[Project Summary]]", "- [[Business Plan]]", "- [[Run Metadata]]"]
    (folders["inputs"] / "Founder Answers.md").write_text("\n".join(answers_lines), encoding="utf-8")

    research_lines = ["# Research Overview", "", "## Queries"]
    for query in queries:
        research_lines.append(f"- {query}")
    research_lines += ["", "## Synthesis", "```json", json.dumps(synthesis, indent=2, ensure_ascii=False), "```", "", "## Links", "- [[Competition Matrix]]", "- [[Debate Overview]]", "- [[Business Plan]]"]
    (folders["research"] / "Research Overview.md").write_text("\n".join(research_lines), encoding="utf-8")

    (folders["competition"] / "Competition Matrix.md").write_text(
        f"# Competition Matrix\n\n## Overview\n- [[Research Overview]]\n- [[Business Plan]]\n\n{competitor_md if competitor_md else 'Nenhuma matriz de concorrência encontrada.'}\n",
        encoding="utf-8",
    )

    competitors = competition.get("competitors", []) if isinstance(competition, dict) else []
    for competitor in competitors:
        name = str(competitor.get("name") or "Competitor")
        note_name = f"Competitor - {safe_note_name(name)}.md"
        content = f"# {name}\n\n- Tipo: {competitor.get('type', '')}\n- Posicionamento: {competitor.get('positioning', '')}\n- Forças: {competitor.get('strengths', '')}\n- Fraquezas: {competitor.get('weaknesses', '')}\n- Pricing: {competitor.get('pricing', '')}\n- Evidência: {competitor.get('evidence', '')}\n\n## Links\n- [[Competition Matrix]]\n- [[Business Plan]]\n"
        (folders["competition"] / note_name).write_text(content, encoding="utf-8")

    debate_lines = ["# Debate Overview", "", "## Persona critiques"]
    for name, payload in persona.items():
        note = f"Persona - {name.title()}"
        debate_lines.append(f"- [[{note}]]")
        (folders["debate"] / f"{note}.md").write_text(f"# {note}\n\n{payload.get('memo', '')}\n\n## Links\n- [[Debate Overview]]\n- [[Business Plan]]\n", encoding="utf-8")

    debate_lines += ["", "## Pro agents"]
    for item in tenth.get("pro_agents", []):
        agent = item.get("agent", "pro")
        note = f"Debate - {agent}"
        debate_lines.append(f"- [[{note}]]")
        (folders["debate"] / f"{note}.md").write_text(f"# {note}\n\n{item.get('memo', '')}\n\n## Links\n- [[Debate Overview]]\n- [[Tenth Man]]\n", encoding="utf-8")

    tenth_note = folders["debate"] / "Tenth Man.md"
    tenth_note.write_text(f"# Tenth Man\n\n{tenth.get('tenth_man', {}).get('memo', '')}\n\n## Links\n- [[Debate Overview]]\n- [[Master Critique]]\n- [[Business Plan]]\n", encoding="utf-8")
    master_note = folders["debate"] / "Master Critique.md"
    master_note.write_text(f"# Master Critique\n\n{tenth.get('master_critique', '')}\n\n## Links\n- [[Debate Overview]]\n- [[Tenth Man]]\n- [[Business Plan]]\n", encoding="utf-8")
    debate_lines += ["- [[Tenth Man]]", "- [[Master Critique]]"]
    if critiques:
        critique_summary = "\n\n".join(critiques)
        (folders["debate"] / "Revision Critiques.md").write_text(f"# Revision Critiques\n\n{critique_summary}\n", encoding="utf-8")
        debate_lines.append("- [[Revision Critiques]]")
    (folders["debate"] / "Debate Overview.md").write_text("\n".join(debate_lines), encoding="utf-8")

    (folders["plan"] / "Business Plan.md").write_text(f"# Business Plan\n\n{plan_md}\n", encoding="utf-8")
    (folders["finance"] / "Financial Model.md").write_text(f"# Financial Model\n\n```csv\n{finance_csv}\n```\n\n## Links\n- [[Business Plan]]\n- [[Run Metadata]]\n", encoding="utf-8")
    (folders["gtm"] / "GTM Experiments.md").write_text(f"# GTM Experiments\n\n{gtm_md}\n", encoding="utf-8")
    (folders["ops"] / "Run Metadata.md").write_text(
        "# Run Metadata\n\n## Run summary\n```json\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n```\n\n## Checkpoint\n```json\n"
        + json.dumps(checkpoint, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )

    manifest = {
        "idea": idea,
        "idea_slug": idea_slug,
        "run_dir": str(run_path),
        "vault_dir": str(vault_path),
        "notes_created": sum(1 for _ in vault_path.rglob('*.md')),
    }
    (vault_path / ".obsidian-export.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return vault_path
