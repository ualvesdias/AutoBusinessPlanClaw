# AutoBusinessPlanClaw

Turn a raw startup idea plus a short founder questionnaire into a **complete, actionable business plan**.

Inspired by AutoResearchClaw, but pointed at something more commercially useful for founders: market validation, positioning, monetization, GTM, operations, financial assumptions, and risk mitigation.

## What it does

AutoBusinessPlanClaw takes:
- an initial business idea
- a required 10-question founder questionnaire
- optional live market signals from web search

And generates:
- `business_plan.md` — full actionable business plan
- `answers.json` — normalized founder inputs
- `research_queries.json` — market research search strategy
- `research_results.json` — collected web evidence
- `run_summary.json` — run metadata

## Core workflow

1. Founder defines the idea in config
2. Founder answers the required questions
3. Pipeline builds market-research queries
4. Pipeline gathers external market signals
5. LLM drafts a structured business plan grounded in founder inputs + evidence
6. Artifacts are written to a local run directory

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

## Recommended business-plan structure

The generated plan targets these sections:
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
# optional if you want live search enrichment
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

## OpenClaw usage pattern

This repo is designed so an OpenClaw agent can:
1. ask the founder the required questions
2. write the answers file
3. run the generator locally
4. return the resulting `business_plan.md`

## What should improve next

This first version is intentionally practical, not bloated. The obvious next upgrades are:
- multi-stage critique/revision loops
- stronger source extraction and citation formatting
- financial spreadsheet export
- customer interview script generation
- GTM experiment pack generation
- scorecards for market attractiveness and founder advantage
- OpenClaw bridge adapters for memory, messaging, cron, and parallel sessions

## License

MIT
