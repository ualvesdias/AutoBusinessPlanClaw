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
- path to `exports/financial_analysis.md`
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
2. `competitor_matrix.json` (check `analysis_status` and `analysis_quality`)
3. `competitor_reference_table.json`
4. `synthesis.json`
5. `persona_critiques.json`
6. `tenth_man_report.json`
7. `critiques.json`
8. `business_plan.md`
9. `stages/financials.json`
10. `exports/financial_model.csv`
11. `exports/financial_analysis.md`
12. `exports/gtm_experiments.md`

## Competition-stage review rule
Do not trust the competition output blindly. Inspect:
- whether rows are marked `analyzed` vs `fallback`
- whether `analysis_quality.quality_gate_passed` is true
- whether evidence excerpts actually support the positioning / strengths / weaknesses claims

If many rows are still `fallback`, treat the run as incomplete competitive intelligence rather than final analysis.

## Notes
- Preferred web-search path: OpenClaw gateway token.
- Fallback web-search path: `OPENAI_API_KEY`.
- `XAI_API_KEY` is optional tertiary fallback only.
- This makes the repo useful both for deterministic local runs and richer research-backed runs.


## Stability expectation
When the competition stage cannot gather enough trustworthy evidence, the run should still finish, but it must be labeled `run_status: incomplete`. OpenClaw operators should report that status clearly instead of presenting the competitor section as fully validated.


## Financial-stage review rule
Check whether the exported model matches the business archetype. For food/beverage, expect order volume, ticket, COGS and local operational costs. For SaaS, expect ARPA/subscription logic. If the shape does not match the business, treat the financial output as suspect and inspect `stages/financials.json`.


When reviewing finance output, also read `exports/financial_analysis.md` for the model interpretation and recommendations.
