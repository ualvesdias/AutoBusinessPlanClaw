# AutoBusinessPlanClaw

Turn a raw startup idea plus a short founder questionnaire into a **complete, actionable business plan**.

Inspired by AutoResearchClaw, but aimed at founders and operators instead of academic publishing. The repo now behaves like a staged pipeline, not just a single prompt wrapper pretending to be infrastructure.

## What it does

AutoBusinessPlanClaw takes:
- an initial business idea
- a required 10-question founder questionnaire
- optional live market signals from web search
- optional LLM generation and critique rounds

And generates:
- `business_plan.md` — final plan after critique/revision rounds
- `answers.json` — normalized founder inputs
- `research_queries.json` — market research search strategy
- `research_results.json` — collected web evidence
- `synthesis.json` — structured business synthesis
- `critiques.json` — critique history
- `exports/financial_model.csv` — spreadsheet-friendly financial model
- `exports/financial_model.xlsx-ready.tsv` — Excel-friendly tab-separated export
- `exports/gtm_experiments.md` — first GTM experiment pack
- `stages/` — per-stage artifacts for pipeline introspection
- `run_summary.json` — run metadata

## Pipeline stages

1. `intake` — normalize founder idea + questionnaire
2. `market_research` — build search queries and gather evidence
3. `synthesis` — compress inputs into strategic assumptions
4. `plan_draft` — create the first full business plan
5. `critique` — challenge weak assumptions and holes
6. `revision` — tighten the plan
7. `financials` — export a 12-month starter financial model
8. `gtm_pack` — generate first GTM experiments
9. `export` — write final run summary

This makes it much closer in spirit to AutoResearchClaw: staged, inspectable, artifact-driven, and designed for autonomous agent execution.

## Required founder questions

- What specific problem am I solving?
- Who exactly is my target customer (ICP)?
- How are they solving this problem today?
- Why are current solutions not good enough?
- What is my unique advantage or insight?
- What is the simplest version of my solution (MVP)?
- Why would someone pay for this?
- How will I get my first 10 customers?
- What does success look like in the first 30–60 days?
- What are the biggest risks that could kill this idea?

## Generated plan structure

The plan targets these sections:
1. Executive summary
2. Problem definition and urgency
3. ICP
4. Market analysis (TAM / SAM / SOM)
5. Competitive landscape
6. Value proposition and positioning
7. Product strategy (MVP → roadmap)
8. Business model and pricing
9. Go-to-market plan
10. Operating model
11. Financial model
12. Risk register with mitigation experiments
13. 30/60 day action plan
14. Assumptions vs evidence
15. Final verdict: GO / CONDITIONAL GO / NO-GO

## Installation

### Preferred
```bash
git clone <your-fork-or-local-path> AutoBusinessPlanClaw
cd AutoBusinessPlanClaw
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### If Ubuntu is missing `venv` / `pip`
Install system packages first:
```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
```

Then create the local `.venv` inside the project folder.

## Configuration

```bash
cp config.businessclaw.example.yaml config.businessclaw.yaml
cp examples/questionnaire.example.json questionnaire.json
export OPENAI_API_KEY="sk-..."
# optional for live search enrichment
export XAI_API_KEY="xai-..."
```

## Usage

```bash
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json
```

Or create a blank questionnaire first:

```bash
businessclaw init-questionnaire --output questionnaire.json
```

## Offline fallback mode

If no `OPENAI_API_KEY` is configured, the pipeline still runs in a deterministic fallback mode:
- it uses founder inputs + fallback evidence
- it produces a full first-pass business plan
- it still emits stage artifacts, critiques, GTM pack, and financial exports

That means the repo remains usable for development, testing, and OpenClaw orchestration even without live model access.

## OpenClaw-native workflow

This repo is designed so an OpenClaw agent can:
1. ask the founder the required questions
2. write the answers file
3. run the generator locally
4. return the resulting `business_plan.md`
5. schedule follow-up validation tasks or reminders

See:
- `AUTOBUSINESSPLANCLAW_AGENTS.md`
- `docs/OPENCLAW_RUNBOOK.md`

## Suggested next upgrades

- stronger evidence extraction and citations
- reusable ICP scoring
- benchmark pricing library
- scenario-based financial sensitivity analysis
- customer interview script generator
- OpenClaw adapters for memory, cron, sessions, and messaging

## License

MIT
