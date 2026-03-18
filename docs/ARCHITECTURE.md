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
- financial CSV/TSV + financial analysis markdown
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
The competition stage no longer stops at URL extraction. It now has three internal substeps:
1. competitor discovery from research evidence
2. per-competitor evidence synthesis (positioning / strengths / weaknesses / pricing hints)
3. quality gate evaluation (`analysis_quality`) to detect overuse of fallback text

This improves:
- competitive analysis
- differentiation reasoning
- GTM realism
- risk modeling
- artifact trustworthiness

### Competition artifact contract
Each competitor row now carries:
- `analysis_status` (`analyzed` or `fallback`)
- `analysis_source`
- `evidence_count`
- `evidence_excerpt`

The stage output also includes an `analysis_quality` block with analyzed/fallback counts and a `quality_gate_passed` flag.

## Next architectural upgrades
- stage-level selective reruns
- specialist expert personas by sub-vertical
- stronger competitor evidence normalization and optional LLM-based analyst agents per competitor
- pricing recommendation engine
- interview-insight ingestion


## Competitor analyst agent
After discovery, each competitor candidate is passed through a dedicated analyst step. That step receives aggregated snippets/URLs for one competitor and must produce positioning, strengths, weaknesses, analysis status, and confidence.

If the agent cannot support a claim from evidence, the row is explicitly marked as fallback rather than silently inheriting generic text.

## Financial model agent
The financial stage now has a dedicated financial-modeling agent. It receives the idea, founder answers, synthesis, critiques, competition context, and an inferred business archetype (for example: saas, services, marketplace, consumer_brand, food_beverage).

If LLM output is unavailable or invalid, the pipeline falls back to an archetype-specific 12-month model instead of forcing everything into SaaS-style ARPA logic.

## Run completion semantics
A run can now finish with `run_status = complete` or `run_status = incomplete`.
- `complete`: competition quality gate passed
- `incomplete`: competition quality gate failed, meaning the final plan exists but competitive intelligence should not be treated as fully trustworthy


## Financial model stage
The financial stage now includes a dedicated financial-model agent. It receives the idea, founder questionnaire, synthesis, critiques, and inferred business archetype, then returns a structured 12-month model.

### Financial artifact contract
The stage writes:
- `business_archetype`
- `assumptions`
- `rows` (12 months)
- `analysis.intelligence_paragraph`
- `analysis.recommendations`

If the agent output is invalid or unavailable, the pipeline uses an archetype-specific fallback model rather than a one-size-fits-all SaaS template. A second finance-analysis pass then summarizes the model and emits recommendations.
