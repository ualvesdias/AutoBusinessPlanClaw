from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SECTION_NOTE_MAP = {
    "Executive summary": "Project Summary",
    "Problem definition and urgency": "Founder Answers",
    "Ideal customer profile (ICP)": "Founder Answers",
    "Market analysis": "Research Overview",
    "Competitive landscape": "Competition Matrix",
    "Value proposition and positioning": "Project Summary",
    "Product strategy": "Project Summary",
    "Business model and pricing": "Financial Model",
    "Go-to-market plan": "GTM Experiments",
    "Operating model": "Run Metadata",
    "Financial model": "Financial Model",
    "Risk register with mitigation experiments": "Master Critique",
    "30/60 day action plan": "GTM Experiments",
    "Assumptions vs Evidence": "Research Overview",
    "Final verdict": "Master Critique",
}


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


def _link(note: str) -> str:
    return f"[[{note}]]"


def _build_plan_hub(plan_md: str) -> str:
    lines = ["# Business Plan Hub", "", "## Seções do plano"]
    for heading, note in SECTION_NOTE_MAP.items():
        lines.append(f"- **{heading}** → {_link(note)}")
    lines += ["", "## Plano completo", "", plan_md or "Plano não encontrado."]
    return "\n".join(lines)


def _build_moc(idea: str) -> str:
    return f"""# MOC - {idea}

## Navegação principal
- {_link('Home')}
- {_link('Project Summary')}
- {_link('Founder Answers')}
- {_link('Research Overview')}
- {_link('Competition Matrix')}
- {_link('Debate Overview')}
- {_link('Business Plan Hub')}
- {_link('Financial Model')}
- {_link('GTM Experiments')}
- {_link('Run Metadata')}

## Trilhas de leitura
### Estratégia
- {_link('Project Summary')} → {_link('Research Overview')} → {_link('Business Plan Hub')}

### Risco
- {_link('Debate Overview')} → {_link('Tenth Man')} → {_link('Master Critique')}

### Mercado
- {_link('Research Overview')} → {_link('Competition Matrix')} → {_link('Business Plan Hub')}
"""


def _build_canvas() -> dict[str, Any]:
    notes = [
        ("Home", 0, 0),
        ("Project Summary", 350, -200),
        ("Founder Answers", 350, 0),
        ("Research Overview", 350, 220),
        ("Competition Matrix", 750, 220),
        ("Debate Overview", 750, 0),
        ("Tenth Man", 1100, -80),
        ("Master Critique", 1100, 80),
        ("Business Plan Hub", 750, -220),
        ("Financial Model", 1100, -260),
        ("GTM Experiments", 1100, 260),
        ("Run Metadata", 350, 420),
    ]
    nodes = []
    edges = []
    for idx, (name, x, y) in enumerate(notes, start=1):
        node_id = f"node-{idx}"
        nodes.append({
            "id": node_id,
            "type": "file",
            "file": f"{name}.md",
            "x": x,
            "y": y,
            "width": 280,
            "height": 80,
        })
    name_to_id = {name: f"node-{idx}" for idx, (name, _, _) in enumerate(notes, start=1)}
    links = [
        ("Home", "Project Summary"),
        ("Home", "Founder Answers"),
        ("Home", "Research Overview"),
        ("Home", "Competition Matrix"),
        ("Home", "Debate Overview"),
        ("Home", "Business Plan Hub"),
        ("Project Summary", "Business Plan Hub"),
        ("Research Overview", "Competition Matrix"),
        ("Debate Overview", "Tenth Man"),
        ("Debate Overview", "Master Critique"),
        ("Master Critique", "Business Plan Hub"),
        ("Business Plan Hub", "Financial Model"),
        ("Business Plan Hub", "GTM Experiments"),
    ]
    for edge_idx, (src, dst) in enumerate(links, start=1):
        edges.append({
            "id": f"edge-{edge_idx}",
            "fromNode": name_to_id[src],
            "toNode": name_to_id[dst],
            "fromSide": "right",
            "toSide": "left",
        })
    return {"nodes": nodes, "edges": edges}


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

    home = f"""# {idea}

## Navegação
- {_link('MOC')}
- {_link('Project Summary')}
- {_link('Founder Answers')}
- {_link('Research Overview')}
- {_link('Competition Matrix')}
- {_link('Debate Overview')}
- {_link('Business Plan Hub')}
- {_link('Financial Model')}
- {_link('GTM Experiments')}
- {_link('Run Metadata')}

## Estrutura
- Inputs: `01 Inputs/`
- Pesquisa: `02 Research/`
- Concorrência: `03 Competition/`
- Debate: `04 Debate/`
- Plano: `05 Plan/`
- Financeiro: `06 Finance/`
- GTM: `07 GTM/`

## Visualização
- Canvas: `00 Overview/{idea_slug}.canvas`
"""
    (folders["home"] / "Home.md").write_text(home, encoding="utf-8")
    (folders["overview"] / "MOC.md").write_text(_build_moc(idea), encoding="utf-8")

    (folders["overview"] / "Project Summary.md").write_text(
        f"# Project Summary\n\n- Ideia: {idea}\n- Run dir: `{run_path}`\n- Vault: `{vault_path}`\n- Evidence count: {summary.get('evidence_count', 0)}\n- Critique rounds: {summary.get('critique_rounds', 0)}\n- Persona agents: {summary.get('persona_count', 0)}\n- Pro agents: {summary.get('pro_agent_count', 0)}\n\n## Links\n- {_link('MOC')}\n- {_link('Founder Answers')}\n- {_link('Research Overview')}\n- {_link('Competition Matrix')}\n- {_link('Debate Overview')}\n- {_link('Business Plan Hub')}\n- {_link('Financial Model')}\n- {_link('GTM Experiments')}\n- {_link('Run Metadata')}\n",
        encoding="utf-8",
    )

    answers_lines = ["# Founder Answers", "", "## Respostas"]
    for key, value in answers.items():
        answers_lines.append(f"- **{key}**: {value}")
    answers_lines += ["", "## Links", f"- {_link('MOC')}", f"- {_link('Project Summary')}", f"- {_link('Business Plan Hub')}", f"- {_link('Run Metadata')}"]
    (folders["inputs"] / "Founder Answers.md").write_text("\n".join(answers_lines), encoding="utf-8")

    research_lines = ["# Research Overview", "", "## Queries"]
    for query in queries:
        research_lines.append(f"- {query}")
    research_lines += ["", "## Synthesis", "```json", json.dumps(synthesis, indent=2, ensure_ascii=False), "```", "", "## Links", f"- {_link('MOC')}", f"- {_link('Competition Matrix')}", f"- {_link('Debate Overview')}", f"- {_link('Business Plan Hub')}"]
    (folders["research"] / "Research Overview.md").write_text("\n".join(research_lines), encoding="utf-8")

    comp_overview_lines = [
        "# Competition Matrix",
        "",
        "## Overview",
        f"- {_link('MOC')}",
        f"- {_link('Research Overview')}",
        f"- {_link('Business Plan Hub')}",
        "",
        competitor_md if competitor_md else 'Nenhuma matriz de concorrência encontrada.',
        "",
        "## Notas individuais",
    ]
    competitors = competition.get("competitors", []) if isinstance(competition, dict) else []
    for competitor in competitors:
        name = str(competitor.get("name") or "Competitor")
        note_title = f"Competitor - {safe_note_name(name)}"
        comp_overview_lines.append(f"- {_link(note_title)}")
        note_name = f"{note_title}.md"
        content = (
            f"# {name}\n\n"
            f"- Tipo: {competitor.get('type', '')}\n"
            f"- Posicionamento: {competitor.get('positioning', '')}\n"
            f"- Forças: {competitor.get('strengths', '')}\n"
            f"- Fraquezas: {competitor.get('weaknesses', '')}\n"
            f"- Pricing: {competitor.get('pricing', '')}\n"
            f"- Evidência: {competitor.get('evidence', '')}\n\n"
            f"## Links\n- {_link('Competition Matrix')}\n- {_link('Business Plan Hub')}\n- {_link('Research Overview')}\n"
        )
        (folders["competition"] / note_name).write_text(content, encoding="utf-8")
    (folders["competition"] / "Competition Matrix.md").write_text("\n".join(comp_overview_lines), encoding="utf-8")

    debate_lines = ["# Debate Overview", "", "## Persona critiques"]
    for name, payload in persona.items():
        note = f"Persona - {name.title()}"
        debate_lines.append(f"- {_link(note)}")
        (folders["debate"] / f"{note}.md").write_text(
            f"# {note}\n\n{payload.get('memo', '')}\n\n## Links\n- {_link('Debate Overview')}\n- {_link('Business Plan Hub')}\n- {_link('Master Critique')}\n",
            encoding="utf-8",
        )

    debate_lines += ["", "## Pro agents"]
    for item in tenth.get("pro_agents", []):
        agent = item.get("agent", "pro")
        note = f"Debate - {agent}"
        debate_lines.append(f"- {_link(note)}")
        (folders["debate"] / f"{note}.md").write_text(
            f"# {note}\n\n{item.get('memo', '')}\n\n## Links\n- {_link('Debate Overview')}\n- {_link('Tenth Man')}\n- {_link('Master Critique')}\n",
            encoding="utf-8",
        )

    (folders["debate"] / "Tenth Man.md").write_text(
        f"# Tenth Man\n\n{tenth.get('tenth_man', {}).get('memo', '')}\n\n## Links\n- {_link('Debate Overview')}\n- {_link('Master Critique')}\n- {_link('Business Plan Hub')}\n",
        encoding="utf-8",
    )
    (folders["debate"] / "Master Critique.md").write_text(
        f"# Master Critique\n\n{tenth.get('master_critique', '')}\n\n## Links\n- {_link('Debate Overview')}\n- {_link('Tenth Man')}\n- {_link('Business Plan Hub')}\n",
        encoding="utf-8",
    )
    debate_lines += [f"- {_link('Tenth Man')}", f"- {_link('Master Critique')}"]
    if critiques:
        critique_summary = "\n\n".join(critiques)
        (folders["debate"] / "Revision Critiques.md").write_text(
            f"# Revision Critiques\n\n{critique_summary}\n\n## Links\n- {_link('Debate Overview')}\n- {_link('Business Plan Hub')}\n",
            encoding="utf-8",
        )
        debate_lines.append(f"- {_link('Revision Critiques')}")
    (folders["debate"] / "Debate Overview.md").write_text("\n".join(debate_lines), encoding="utf-8")

    (folders["plan"] / "Business Plan.md").write_text(f"# Business Plan\n\n{plan_md}\n", encoding="utf-8")
    (folders["plan"] / "Business Plan Hub.md").write_text(_build_plan_hub(plan_md), encoding="utf-8")
    (folders["finance"] / "Financial Model.md").write_text(
        f"# Financial Model\n\n```csv\n{finance_csv}\n```\n\n## Links\n- {_link('Business Plan Hub')}\n- {_link('Run Metadata')}\n- {_link('Project Summary')}\n",
        encoding="utf-8",
    )
    (folders["gtm"] / "GTM Experiments.md").write_text(
        f"# GTM Experiments\n\n{gtm_md}\n\n## Links\n- {_link('Business Plan Hub')}\n- {_link('Founder Answers')}\n- {_link('Project Summary')}\n",
        encoding="utf-8",
    )
    (folders["ops"] / "Run Metadata.md").write_text(
        "# Run Metadata\n\n## Run summary\n```json\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n```\n\n## Checkpoint\n```json\n"
        + json.dumps(checkpoint, indent=2, ensure_ascii=False)
        + "\n```\n\n## Links\n"
        + f"- {_link('MOC')}\n- {_link('Project Summary')}\n- {_link('Business Plan Hub')}\n",
        encoding="utf-8",
    )

    canvas = _build_canvas()
    (folders["overview"] / f"{idea_slug}.canvas").write_text(json.dumps(canvas, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "idea": idea,
        "idea_slug": idea_slug,
        "run_dir": str(run_path),
        "vault_dir": str(vault_path),
        "notes_created": sum(1 for _ in vault_path.rglob('*.md')),
        "canvas_created": f"00 Overview/{idea_slug}.canvas",
        "moc_created": "00 Overview/MOC.md",
    }
    (vault_path / ".obsidian-export.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return vault_path
