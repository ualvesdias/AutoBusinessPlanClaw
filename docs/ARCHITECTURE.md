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
- Persona critique
- 10th-man debate
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
- persona critique layer
- 10th-man debate layer

## Multi-agent critique design

### Layer 1: Persona critique agents
Four named agents evaluate the idea from different viewpoints:
1. Investor
2. Potential client
3. Salesman
4. Expert in the business niche

These agents identify different classes of weakness:
- investor → market size, defensibility, return profile
- potential client → urgency, trust, switching cost, budget ownership
- salesman → wedge, objections, conversion friction, message-market fit
- expert → technical realism, domain workflow fit, superiority over status quo

### Layer 2: 10th-man protocol
After the persona critics:
- 9 pro agents construct the strongest credible case for success
- the 10th man must disagree with the emergent pro verdict and build the strongest credible case for failure

This avoids a common failure mode in agent systems: consensus collapse into polished optimism.

### Layer 3: Master critique synthesis
A final synthesis memo combines:
- the four persona critiques
- the nine pro-agent memos
- the dissenting 10th-man memo

That synthesis becomes core material for the business plan's risk section.

## Why this shape works
A business plan generator should not be a single call that emits polished nonsense. The pipeline forces structure:
- founder hypotheses are explicit
- research queries are inspectable
- synthesis is separated from writing
- critique and revision are first-class stages
- spreadsheet exports support actual operator work
- the dissent mechanism prevents shallow consensus

## Next architectural upgrades
- multiple specialist expert agents by vertical
- competitor-evidence normalization
- pricing recommendation engine
- interview-insight ingestion
- validation backlog prioritization
- checkpoint/resume per stage
