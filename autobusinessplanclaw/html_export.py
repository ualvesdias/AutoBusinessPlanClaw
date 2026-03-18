from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _strip_internal_appendices(md: str) -> str:
    markers = ["\n---\n\n## Internal critique adjustments", "\n## Internal critique adjustments"]
    for marker in markers:
        if marker in md:
            return md.split(marker, 1)[0].rstrip()
    return md


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"


def _format_label(value: str) -> str:
    mapping = {
        "arpa": "ARPA",
        "cogs": "COGS",
        "opex": "Opex",
        "net_burn": "Net burn",
        "cash_flow": "Cash flow",
        "icp_fit": "ICP fit",
        "comparison_to_idea": "Comparison to idea",
    }
    return mapping.get(value, value.replace("_", " ").title())


def _linkify(text: str) -> str:
    escaped = _esc(text)
    return re.sub(r"(https?://[^\s<]+)", lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noreferrer">{m.group(1)}</a>', escaped)


def _render_markdown(md: str) -> str:
    if not md.strip():
        return '<p class="muted">No content.</p>'

    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    in_ul = False
    in_ol = False
    in_code = False
    code_lines: list[str] = []
    table_rows: list[list[str]] | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{_linkify(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        header = table_rows[0]
        body = table_rows[1:]
        out.append('<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{_esc(c)}</th>' for c in header) + '</tr></thead><tbody>')
        for row in body:
            out.append('<tr>' + ''.join(f'<td>{_linkify(c)}</td>' for c in row) + '</tr>')
        out.append('</tbody></table></div>')
        table_rows = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_lists()
            flush_table()
            if in_code:
                out.append(f'<pre>{_esc(chr(10).join(code_lines))}</pre>')
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            flush_lists()
            row = [cell.strip() for cell in stripped.strip("|").split("|")]
            if set("".join(row).replace("-", "").replace(":", "").strip()) == set():
                continue
            if table_rows is None:
                table_rows = []
            table_rows.append(row)
            continue
        else:
            flush_table()

        if not stripped:
            flush_paragraph()
            flush_lists()
            continue

        if stripped.startswith("### "):
            flush_paragraph(); flush_lists(); out.append(f'<h4>{_linkify(stripped[4:])}</h4>'); continue
        if stripped.startswith("## "):
            flush_paragraph(); flush_lists(); out.append(f'<h3>{_linkify(stripped[3:])}</h3>'); continue
        if stripped.startswith("# "):
            flush_paragraph(); flush_lists(); out.append(f'<h2>{_linkify(stripped[2:])}</h2>'); continue

        ol_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ol_match:
            flush_paragraph()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f'<li>{_linkify(ol_match.group(2))}</li>')
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f'<li>{_linkify(stripped[2:])}</li>')
            continue

        paragraph.append(stripped)

    flush_paragraph()
    flush_lists()
    flush_table()
    if in_code:
        out.append(f'<pre>{_esc(chr(10).join(code_lines))}</pre>')
    return ''.join(out)


def _render_dict_list(items: dict[str, Any]) -> str:
    rows = ''.join(f'<tr><th>{_esc(str(k))}</th><td>{_linkify(str(v))}</td></tr>' for k, v in items.items())
    return f'<div class="table-wrap"><table><tbody>{rows}</tbody></table></div>'


def _render_table_from_rows(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return '<p class="muted">No rows.</p>'
    cols = columns or list(rows[0].keys())
    head = ''.join(f'<th>{_esc(_format_label(col))}</th>' for col in cols)
    body_parts = []
    for row in rows:
        body_parts.append('<tr>' + ''.join(f'<td>{_linkify(str(row.get(col, "")))}</td>' for col in cols) + '</tr>')
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body_parts)}</tbody></table></div>'


def _render_csv_table(text: str) -> str:
    if not text.strip():
        return '<p class="muted">No financial model exported.</p>'
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return _render_table_from_rows(rows, list(reader.fieldnames or []))


def _metric_card(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{_esc(label)}</span><strong>{_esc(str(value))}</strong></div>'


def _details(title: str, body: str, open_by_default: bool = False) -> str:
    open_attr = ' open' if open_by_default else ''
    return f'<details class="detail"{open_attr}><summary>{_esc(title)}</summary><div class="detail-body">{body}</div></details>'


def export_run_to_html(run_dir: str | Path, html_path: str | Path) -> Path:
    run_path = Path(run_dir)
    out_path = Path(html_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = _read_json(run_path / 'run_summary.json', {})
    answers = _read_json(run_path / 'answers.json', {})
    synthesis = _read_json(run_path / 'synthesis.json', {})
    kb_readme = _read_text(run_path / 'knowledge_base' / 'README.md')
    lessons_md = _read_text(run_path / 'evolution' / 'README.md')
    competition = _read_json(run_path / 'competitor_matrix.json', {})
    competitor_reference = _read_json(run_path / 'competitor_reference_table.json', [])
    persona = _read_json(run_path / 'persona_critiques.json', {})
    tenth = _read_json(run_path / 'tenth_man_report.json', {})
    doctor = _read_json(run_path / 'doctor.json', {})
    checkpoint = _read_json(run_path / 'checkpoint.json', {})

    plan_md = _strip_internal_appendices(_read_text(run_path / 'business_plan.md'))
    gtm_md = _read_text(run_path / 'exports' / 'gtm_experiments.md')
    finance_csv = _read_text(run_path / 'exports' / 'financial_model.csv')
    queries = _read_json(run_path / 'research_queries.json', [])
    research_results = _read_json(run_path / 'research_results.json', [])

    idea = str(summary.get('idea') or run_path.name)
    competitors = competition.get('competitors', []) if isinstance(competition, dict) else []

    nav_items = [
        ('overview', 'Overview'), ('answers', 'Founder answers'), ('research', 'Research'),
        ('competition', 'Competition'), ('debate', 'Debate'), ('plan', 'Business plan'),
        ('finance', 'Financial model'), ('gtm', 'GTM'), ('kb', 'Knowledge base'), ('learning', 'Self-learning'), ('meta', 'Metadata')
    ]
    nav = '<nav class="sidebar"><div class="brand">AutoBusinessPlanClaw</div>' + ''.join(
        f'<a href="#{slug}">{label}</a>' for slug, label in nav_items
    ) + '</nav>'

    overview = (
        '<div class="hero">'
        f'<h1>{_esc(idea)}</h1>'
        '<p>Run exportado em HTML com dados estruturados, seções colapsáveis e renderização de markdown.</p>'
        '<div class="metrics">'
        + _metric_card('Evidence', summary.get('evidence_count', 0))
        + _metric_card('Competitors', len(competitors))
        + _metric_card('Personas', summary.get('persona_count', 0))
        + _metric_card('Pro agents', summary.get('pro_agent_count', 0))
        + '</div></div>'
    )

    answers_body = _render_dict_list(answers)

    query_list = '<ul>' + ''.join(f'<li>{_esc(str(q))}</li>' for q in queries) + '</ul>' if queries else '<p class="muted">No queries.</p>'
    research_batches = []
    for batch in research_results:
        q = str(batch.get('query', 'Query'))
        results = batch.get('results', [])
        rows = []
        for item in results:
            rows.append({
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'snippet': item.get('snippet', ''),
            })
        research_batches.append(_details(q, _render_table_from_rows(rows, ['title', 'url', 'snippet'])))
    research_body = (
        _details('Research queries', query_list, True)
        + _details('Structured synthesis', _render_dict_list(synthesis))
        + _details('Raw research batches', ''.join(research_batches) or '<p class="muted">No research batches.</p>')
    )

    competitor_rows = []
    for competitor in competitors:
        competitor_rows.append({
            'name': competitor.get('name', ''),
            'type': competitor.get('type', ''),
            'pricing': competitor.get('pricing', ''),
            'positioning': competitor.get('positioning', ''),
            'strengths': competitor.get('strengths', ''),
            'weaknesses': competitor.get('weaknesses', ''),
            'evidence': competitor.get('evidence', ''),
        })
    competition_body = (
        _details('Competition matrix', _render_table_from_rows(competitor_rows, ['name', 'type', 'pricing', 'positioning', 'strengths', 'weaknesses', 'evidence']), True)
        + '<p class="muted">If evidence uses <code>heuristic://</code>, the row is an archetype inferred from founder input, not a validated live-market competitor.</p>'
        + _details('Reference table', _render_table_from_rows(competitor_reference, ['name', 'type', 'icp_fit', 'channel', 'pricing', 'positioning', 'strengths', 'weaknesses', 'comparison_to_idea', 'evidence']), True)
        + _details('Competitor dossiers', ''.join(
            _details(
                str(c.get('name', 'Competitor')),
                _render_dict_list({
                    'Type': c.get('type', ''),
                    'Pricing': c.get('pricing', ''),
                    'Positioning': c.get('positioning', ''),
                    'Strengths': c.get('strengths', ''),
                    'Weaknesses': c.get('weaknesses', ''),
                    'Evidence': c.get('evidence', ''),
                })
            ) for c in competitors
        ) or '<p class="muted">No dossiers.</p>', True)
    )

    persona_blocks = ''.join(_details(name.title(), _render_markdown(str(payload.get('memo', '')))) for name, payload in persona.items())
    debate_body = (
        _details('Persona critiques', persona_blocks or '<p class="muted">No persona critiques.</p>', True)
        + _details('Tenth man', _render_markdown(str((tenth.get('tenth_man') or {}).get('memo', ''))), True)
        + _details('Master critique', _render_markdown(str(tenth.get('master_critique', ''))), True)
    )

    plan_body = _details('Rendered business plan', _render_markdown(plan_md), True)
    finance_body = _details('Financial model table', _render_csv_table(finance_csv), True)
    gtm_body = _details('Rendered GTM pack', _render_markdown(gtm_md), True)
    kb_body = _details('Knowledge base overview', _render_markdown(kb_readme), True)
    learning_body = _details('Self-learning lessons', _render_markdown(lessons_md), True)
    meta_body = _details('Run metadata', _render_dict_list({
        'run_dir': summary.get('run_dir', run_path),
        'generated_at': summary.get('generated_at', ''),
        'completed_stages': ', '.join(summary.get('completed_stages', [])),
        'doctor_checks': json.dumps(doctor, ensure_ascii=False),
        'checkpoint': json.dumps(checkpoint, ensure_ascii=False),
    }), True)

    sections = [
        ('overview', 'Overview', overview),
        ('answers', 'Founder answers', answers_body),
        ('research', 'Research', research_body),
        ('competition', 'Competition Matrix', competition_body),
        ('debate', 'Debate', debate_body),
        ('plan', 'Business Plan', plan_body),
        ('finance', 'Financial Model', finance_body),
        ('gtm', 'GTM', gtm_body),
        ('kb', 'Knowledge Base', kb_body),
        ('learning', 'Self-Learning', learning_body),
        ('meta', 'Metadata', meta_body),
    ]

    main = ''.join(f'<section id="{_slug(sid)}" class="panel"><h2>{_esc(title)}</h2>{body}</section>' for sid, title, body in sections)

    html_doc = f'''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(idea)} — AutoBusinessPlanClaw</title>
  <style>
    :root {{ --bg:#0b1020; --panel:#121933; --soft:#192341; --soft2:#0f1730; --text:#e8eefc; --muted:#9ba8ca; --accent:#67e8f9; --border:#28355f; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,system-ui,Arial,sans-serif; background:linear-gradient(180deg,#0a1020,#10192d); color:var(--text); display:grid; grid-template-columns:260px 1fr; min-height:100vh; }}
    .sidebar {{ position:sticky; top:0; height:100vh; overflow:auto; padding:22px 16px; border-right:1px solid var(--border); background:rgba(8,12,24,.86); }}
    .brand {{ font-size:18px; font-weight:700; color:var(--accent); margin-bottom:16px; }}
    .sidebar a {{ display:block; color:var(--muted); text-decoration:none; padding:9px 10px; border-radius:10px; margin:4px 0; }}
    .sidebar a:hover {{ background:var(--soft); color:var(--text); }}
    main {{ padding:24px; max-width:1400px; width:100%; }}
    .panel {{ background:rgba(18,25,51,.9); border:1px solid var(--border); border-radius:18px; padding:20px; margin-bottom:18px; box-shadow:0 14px 34px rgba(0,0,0,.24); }}
    .hero {{ display:flex; flex-direction:column; gap:16px; }}
    .hero h1 {{ margin:0; font-size:30px; line-height:1.15; }}
    .hero p, .muted {{ color:var(--muted); }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }}
    .metric {{ background:var(--soft); border:1px solid var(--border); border-radius:14px; padding:14px; }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .metric strong {{ display:block; margin-top:6px; color:var(--accent); font-size:24px; }}
    details.detail {{ background:var(--soft2); border:1px solid var(--border); border-radius:14px; margin:12px 0; overflow:hidden; }}
    details.detail > summary {{ cursor:pointer; list-style:none; padding:14px 16px; font-weight:600; }}
    details.detail > summary::-webkit-details-marker {{ display:none; }}
    .detail-body {{ padding:0 16px 16px 16px; }}
    table {{ width:100%; border-collapse:collapse; min-width:780px; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--border); border-radius:12px; background:#0c1328; }}
    th, td {{ border-bottom:1px solid var(--border); padding:10px 12px; text-align:left; vertical-align:top; }}
    th {{ background:#111a36; position:sticky; top:0; }}
    pre {{ white-space:pre-wrap; word-break:break-word; background:#0c1328; border:1px solid var(--border); border-radius:12px; padding:14px; overflow:auto; }}
    p, li {{ line-height:1.55; }}
    ul, ol {{ padding-left:22px; }}
    a {{ color:var(--accent); }}
    h2, h3, h4 {{ margin-top:0; }}
    @media (max-width: 980px) {{ body {{ grid-template-columns:1fr; }} .sidebar {{ position:relative; height:auto; border-right:none; border-bottom:1px solid var(--border); }} main {{ padding:16px; }} table {{ min-width:640px; }} }}
  </style>
</head>
<body>
{nav}
<main>{main}</main>
</body>
</html>'''

    out_path.write_text(html_doc, encoding='utf-8')
    return out_path
