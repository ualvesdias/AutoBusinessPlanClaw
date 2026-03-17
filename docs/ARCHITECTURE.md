# AutoBusinessPlanClaw Architecture

## Design goal
Mirror the strengths of AutoResearchClaw that actually matter here:
- staged pipeline
- inspectable artifacts
- deterministic local execution path
- agent-friendly CLI
- room for future multi-agent expansion
- resumable runs

## Current architecture

### Inputs
- `config.businessclaw.yaml`
- founder questionnaire file

### Runtime stages
- Intake
- Market research
- Competition mapping
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
- checkpoint metadata
- financial CSV/TSV
- competitor matrix CSV/Markdown/JSON
- GTM experiment memo
- critique history
- persona critique layer
- 10th-man debate layer

## Checkpoint/resume model
Each stage writes artifacts and then updates `checkpoint.json`.
A resumed run can reuse:
- market research artifacts
- competitor matrix
- synthesis
- persona critiques
- 10th-man debate
- draft and revisions

This keeps the pipeline inspectable and resumable instead of forcing a full rerun every time.

## Multi-agent critique design

### Layer 1: Persona critique agents
Four named agents evaluate the idea from different viewpoints:
1. Investor
2. Potential client
3. Salesman
4. Expert in the business niche (inferred from the idea and questionnaire)

### Layer 2: 10th-man protocol
After the persona critics:
- 9 pro agents construct the strongest credible case for success
- the 10th man must disagree with the emergent pro verdict and build the strongest credible case for failure

### Layer 3: Master critique synthesis
A final synthesis memo combines:
- the four persona critiques
- the nine pro-agent memos
- the dissenting 10th-man memo

That synthesis becomes core material for the business plan's risk section.

## Competition stage
The competition stage maps direct, indirect, and status-quo competition and exports a matrix.
This improves:
- competitive analysis
- differentiation reasoning
- GTM realism
- risk modeling

## Next architectural upgrades
- stage-level selective reruns
- specialist expert personas by sub-vertical
- competitor evidence normalization
- pricing recommendation engine
- interview-insight ingestion
