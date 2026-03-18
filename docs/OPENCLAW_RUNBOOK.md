# OpenClaw Runbook for AutoBusinessPlanClaw

## Goal
Use OpenClaw to turn a founder idea into a grounded business plan with explicit assumptions, evidence, financial exports, and next-step validation work.

## Recommended operator flow

### 1. Discovery in the main session
Ask for:
- the business idea
- region / market focus
- pricing currency
- the 10 required founder answers

### 2. Write local files
- copy `config.businessclaw.example.yaml` to `config.businessclaw.yaml`
- write questionnaire answers to `questionnaire.json`

### 3. Generate
Run:
```bash
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json
```

### 4. Return artifacts
Minimum response back to the founder:
- path to `business_plan.md`
- path to `exports/financial_model.csv`
- final verdict (GO / CONDITIONAL GO / NO-GO)
- top 3 validation actions

## How OpenClaw should behave
- Be skeptical.
- Do not treat founder confidence as evidence.
- Clearly separate facts, assumptions, and recommendations.
- Prefer narrower ICPs and narrower MVPs in early versions.
- If evidence is weak, recommend interviews and pilots instead of pretending certainty.

## Multi-agent critique expectation
Before treating the plan as strong, review:
1. `persona_critiques.json`
2. `tenth_man_report.json`
3. `critiques.json`
4. `business_plan.md`

The `tenth_man_report.json` file is especially important because it contains:
- 9 pro-agent cases for success
- 1 dissenter case for failure
- a master critique synthesis

## Good follow-up automations
- set a reminder to review the plan after 10 customer interviews
- schedule a weekly GTM review
- generate a customer interview guide from the existing questionnaire
- create an execution checklist for the next 30 days

## Recommended artifact review order
1. `run_summary.json`
2. `synthesis.json`
3. `persona_critiques.json`
4. `tenth_man_report.json`
5. `critiques.json`
6. `business_plan.md`
7. `exports/financial_model.csv`
8. `exports/gtm_experiments.md`

## Notes
- If `OPENAI_API_KEY` is not available, the tool still runs in fallback mode.
- If `XAI_API_KEY` is available, live market search enrichment can be used.
- This makes the repo useful both for deterministic local runs and richer research-backed runs.
