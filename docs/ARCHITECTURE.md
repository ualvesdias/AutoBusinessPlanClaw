# AutoBusinessPlanClaw Architecture

## Design goal
Mirror the strengths of AutoResearchClaw that actually matter here:
- staged pipeline
- inspectable artifacts
- deterministic local execution path
- agent-friendly CLI
- room for future multi-agent expansion

## Current architecture

### Inputs
- `config.businessclaw.yaml`
- founder questionnaire file

### Runtime stages
- Intake
- Market research
- Synthesis
- Plan draft
- Critique
- Revision
- Financial export
- GTM experiment export
- Run summary export

### Outputs
- final markdown plan
- JSON stage artifacts
- financial CSV/TSV
- GTM experiment memo
- critique history

## Why this shape works
A business plan generator should not be a single call that emits polished nonsense. The pipeline forces structure:
- founder hypotheses are explicit
- research queries are inspectable
- synthesis is separated from writing
- critique and revision are first-class stages
- spreadsheet exports support actual operator work

## Next architectural upgrades
- multiple critic personas (investor, operator, buyer, red team)
- market-size calculators with reusable heuristics
- interview-insight ingestion
- competitor evidence normalization
- pricing recommendation engine
- validation backlog prioritization
