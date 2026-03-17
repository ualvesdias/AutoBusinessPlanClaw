# AutoBusinessPlanClaw

Turn a raw startup idea plus a short founder questionnaire into a **complete, actionable business plan**.

Inspired by AutoResearchClaw, but aimed at founders and operators instead of academic publishing. The repo now behaves like a staged pipeline with a multi-agent critique system, checkpoint/resume support, structured competitor mapping, and Obsidian export with MOC + canvas.

## What it does

AutoBusinessPlanClaw takes:
- an initial business idea
- a required 10-question founder questionnaire
- optional live market signals from web search
- optional LLM generation and critique rounds

And generates:
- `business_plan.md`
- `answers.json`
- `research_queries.json`
- `research_results.json`
- `synthesis.json`
- `persona_critiques.json`
- `tenth_man_report.json`
- `competitor_matrix.json`
- `critiques.json`
- `checkpoint.json`
- `exports/financial_model.csv`
- `exports/financial_model.xlsx-ready.tsv`
- `exports/competitor_matrix.csv`
- `exports/competitor_matrix.md`
- `exports/gtm_experiments.md`
- novo vault Obsidian com notas `.md` linkadas, `MOC.md` e `.canvas`
- `stages/`
- `run_summary.json`

## Pipeline stages

1. `intake`
2. `market_research`
3. `competition`
4. `synthesis`
5. `persona_critique`
6. `tenth_man`
7. `plan_draft`
8. `critique`
9. `revision`
10. `financials`
11. `gtm_pack`
12. `export`

## Multi-agent 10th-man system

### Persona critics
The first critique layer uses 4 agents:
- `investor`
- `potential client`
- `salesman`
- `expert` (expert on the idea's niche, inferred from the idea + questionnaire)

### 10th-man protocol
After the persona critics:
- 9 pro agents construct the strongest credible case for success
- the 10th man must disagree with the pro consensus and construct the strongest credible case for failure

The output of this debate becomes the base material for the **risk section** of the business plan.

## Checkpoint and resume
Each run now writes `checkpoint.json` with the completed stages.
You can resume an existing run directory with:

```bash
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json --output artifacts/my-run --resume
```

## Competitor matrix
The pipeline now creates a structured competitor mapping stage and exports:
- `competitor_matrix.json`
- `exports/competitor_matrix.csv`
- `exports/competitor_matrix.md`

## Obsidian export
The project now supports:
- export manual de um run para um novo vault
- export automático ao final do `run`
- `MOC.md` com trilhas de navegação
- `.canvas` para visualização gráfica
- links cruzados mais ricos entre plano, debate, concorrência, pesquisa e financeiro

### Export manual
```bash
businessclaw export-obsidian --run-dir artifacts/my-run --vault-dir exports/obsidian/my-run-vault
```

### Export automático ao final do run
```bash
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json --export-obsidian --obsidian-vault-dir exports/obsidian/my-run-vault
```

## Installation
```bash
git clone <your-fork-or-local-path> AutoBusinessPlanClaw
cd AutoBusinessPlanClaw
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration
```bash
cp config.businessclaw.example.yaml config.businessclaw.yaml
cp examples/questionnaire.example.json questionnaire.json
export OPENAI_API_KEY="sk-..."
export XAI_API_KEY="xai-..."  # optional
```

### LLM providers
The project now supports two LLM paths:
- `openai-compatible` → direct API via `OPENAI_API_KEY`
- `openclaw-http` → OpenClaw Gateway OpenAI-compatible endpoint
- `auto` → tries direct API first, then OpenClaw HTTP if configured

Example:
```yaml
llm:
  provider: auto
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  model: "gpt-4o-mini"
  timeout_seconds: 45
  openclaw_base_url: "http://127.0.0.1:18789/v1"
  openclaw_api_key_env: "OPENCLAW_GATEWAY_TOKEN"
  openclaw_model: "openclaw:main"
```

Note: OpenClaw HTTP support requires the Gateway chat-completions endpoint to be enabled and a valid gateway token.

## Usage
```bash
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json
```

With resume:
```bash
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json --output artifacts/my-run --resume
```

## Offline fallback mode
If no `OPENAI_API_KEY` is configured, the pipeline still runs in deterministic fallback mode and still emits:
- persona critiques
- 10th-man outputs
- competitor matrix
- GTM pack
- financial exports
- checkpoint metadata
- Obsidian-ready artifacts

## OpenClaw-native workflow
See:
- `AUTOBUSINESSPLANCLAW_AGENTS.md`
- `docs/OPENCLAW_RUNBOOK.md`
- `docs/ARCHITECTURE.md`

## License
MIT
