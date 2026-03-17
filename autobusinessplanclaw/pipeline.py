from __future__ import annotations

import csv
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from .llm import LLMError, OpenAICompatibleClient
from .models import ABCConfig, EvidenceItem, Stage
from .prompts import SYSTEM_PROMPT, CRITIC_PROMPT, REVISION_PROMPT, planning_prompt
from .research import build_market_queries, fallback_evidence


class Pipeline:
    def __init__(self, config: ABCConfig):
        self.config = config
        self.client = OpenAICompatibleClient(config.llm)

    def run(self, answers: dict[str, str], web_search_fn=None, output_dir: str | None = None) -> Path:
        run_id = datetime.now(UTC).strftime("abc-%Y%m%d-%H%M%S")
        run_dir = Path(output_dir or Path(self.config.output.root) / run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        stages_dir = run_dir / "stages"
        exports_dir = run_dir / "exports"
        stages_dir.mkdir(exist_ok=True)
        exports_dir.mkdir(exist_ok=True)

        queries = build_market_queries(self.config.business.idea, answers)
        raw_research: list[dict[str, Any]] = []
        evidence: list[EvidenceItem] = []

        self._write_stage(stages_dir, Stage.INTAKE, {
            "idea": self.config.business.idea,
            "answers": answers,
        })

        if self.config.runtime.allow_web_research and web_search_fn is not None:
            for query in queries:
                results = web_search_fn(query=query, count=self.config.runtime.max_web_results)
                raw_research.append({"query": query, "results": results})
                for item in results:
                    evidence.append(EvidenceItem(**item))

        if not evidence:
            evidence = fallback_evidence(self.config.business.idea, answers)

        self._write_stage(stages_dir, Stage.MARKET_RESEARCH, {
            "queries": queries,
            "raw_research": raw_research,
            "evidence": [e.__dict__ for e in evidence],
        })

        synthesis = self._build_synthesis(answers, evidence)
        self._write_stage(stages_dir, Stage.SYNTHESIS, synthesis)

        draft = self._generate_plan(answers, evidence, synthesis)
        self._write_markdown_stage(stages_dir, Stage.PLAN_DRAFT, draft)

        current_plan = draft
        critiques: list[str] = []
        for round_idx in range(1, self.config.runtime.critique_rounds + 1):
            critique = self._critique_plan(current_plan, synthesis, round_idx)
            critiques.append(critique)
            self._write_markdown_stage(stages_dir, Stage.CRITIQUE, critique, suffix=f"-{round_idx}")
            current_plan = self._revise_plan(current_plan, critique, synthesis, round_idx)
            self._write_markdown_stage(stages_dir, Stage.REVISION, current_plan, suffix=f"-{round_idx}")

        finance_rows = self._build_financial_rows(answers)
        self._write_financial_exports(exports_dir, finance_rows)
        self._write_stage(stages_dir, Stage.FINANCIALS, {"rows": finance_rows})

        gtm_pack = self._build_gtm_pack(answers)
        (exports_dir / "gtm_experiments.md").write_text(gtm_pack, encoding="utf-8")
        self._write_markdown_stage(stages_dir, Stage.GTM_PACK, gtm_pack)

        (run_dir / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "research_queries.json").write_text(json.dumps(queries, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "research_results.json").write_text(json.dumps(raw_research, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "synthesis.json").write_text(json.dumps(synthesis, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "critiques.json").write_text(json.dumps(critiques, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "business_plan.md").write_text(current_plan, encoding="utf-8")

        summary = {
            "idea": self.config.business.idea,
            "run_dir": str(run_dir),
            "queries": queries,
            "evidence_count": len(evidence),
            "generated_at": datetime.now(UTC).isoformat(),
            "llm_configured": self.client.is_configured(),
            "critique_rounds": self.config.runtime.critique_rounds,
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_stage(stages_dir, Stage.EXPORT, summary)
        return run_dir

    def _generate_plan(self, answers: dict[str, str], evidence: list[EvidenceItem], synthesis: dict[str, Any]) -> str:
        evidence_lines = [f"{item.title} — {item.url} — {item.snippet}" for item in evidence[:20]]
        prompt = planning_prompt(
            self.config.business.idea,
            answers,
            evidence_lines,
            self.config.business.currency,
            self.config.business.region,
        ) + "\n\nStructured synthesis:\n" + json.dumps(synthesis, indent=2, ensure_ascii=False)
        try:
            if self.client.is_configured():
                return self.client.complete(SYSTEM_PROMPT, prompt)
        except LLMError:
            pass
        return self._fallback_plan(answers, evidence, synthesis)

    def _critique_plan(self, plan: str, synthesis: dict[str, Any], round_idx: int) -> str:
        critique_input = f"Round {round_idx}\n\nPlan:\n{plan}\n\nSynthesis:\n{json.dumps(synthesis, indent=2, ensure_ascii=False)}"
        try:
            if self.client.is_configured():
                return self.client.complete(CRITIC_PROMPT, critique_input)
        except LLMError:
            pass
        return self._fallback_critique(plan, synthesis, round_idx)

    def _revise_plan(self, plan: str, critique: str, synthesis: dict[str, Any], round_idx: int) -> str:
        revision_input = f"Round {round_idx}\n\nOriginal plan:\n{plan}\n\nCritique:\n{critique}\n\nSynthesis:\n{json.dumps(synthesis, indent=2, ensure_ascii=False)}"
        try:
            if self.client.is_configured():
                return self.client.complete(REVISION_PROMPT, revision_input)
        except LLMError:
            pass
        return plan + "\n\n---\n\n## Internal critique adjustments\n\n" + critique

    def _build_synthesis(self, answers: dict[str, str], evidence: list[EvidenceItem]) -> dict[str, Any]:
        return {
            "problem": answers["problem"],
            "icp": answers["icp"],
            "existing_alternatives": answers["current_solution"],
            "differentiation": answers["advantage"],
            "mvp": answers["mvp"],
            "willingness_to_pay": answers["payment_reason"],
            "acquisition": answers["first_10_customers"],
            "success_window": answers["early_success"],
            "killer_risks": answers["killer_risks"],
            "evidence_summary": [e.title for e in evidence[:10]],
        }

    def _build_financial_rows(self, answers: dict[str, str]) -> list[dict[str, Any]]:
        price = 3000 if "enterprise" in answers["icp"].lower() or "ciso" in answers["icp"].lower() else 1200
        customers = [1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18]
        rows: list[dict[str, Any]] = []
        base_opex = 35000
        for month, customer_count in enumerate(customers, start=1):
            revenue = customer_count * price
            cogs = max(500, int(revenue * 0.12))
            opex = base_opex + (2000 if month > 6 else 0)
            net = revenue - cogs - opex
            rows.append({
                "month": month,
                "customers": customer_count,
                "arpa": price,
                "revenue": revenue,
                "cogs": cogs,
                "opex": opex,
                "net_burn": -net,
                "cash_flow": net,
            })
        return rows

    def _write_financial_exports(self, exports_dir: Path, rows: list[dict[str, Any]]) -> None:
        csv_path = exports_dir / "financial_model.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        tsv_path = exports_dir / "financial_model.xlsx-ready.tsv"
        with tsv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    def _build_gtm_pack(self, answers: dict[str, str]) -> str:
        return f"""# GTM Experiment Pack

## ICP
{answers['icp']}

## Main acquisition hypothesis
{answers['first_10_customers']}

## 3 fast experiments
1. Founder-led outbound: contact 30 ICP accounts with a pain-first message tied to `{answers['problem']}`.
2. Discovery sprint: run 10 interviews focused on `{answers['current_solution']}` and willingness to pay.
3. Pilot conversion: offer 2-3 structured pilots around the MVP: `{answers['mvp']}`.

## Messaging angles
- Pain: {answers['problem']}
- Why current options fail: {answers['why_now']}
- Why this founder may win: {answers['advantage']}

## Success metric in 30-60 days
{answers['early_success']}
"""

    def _fallback_plan(self, answers: dict[str, str], evidence: list[EvidenceItem], synthesis: dict[str, Any]) -> str:
        evidence_md = "\n".join(f"- {e.title}: {e.snippet}" for e in evidence[:8])
        tam = "50,000 target accounts × 12,000 annual contract value = 600M"
        sam = "5,000 reachable early-stage accounts × 12,000 ACV = 60M"
        som = "50 first-wave accounts × 12,000 ACV = 600k"
        return f"""# Business Plan — {self.config.business.idea}

## 1. Executive summary
- Idea: {self.config.business.idea}
- Region: {self.config.business.region}
- Verdict: CONDITIONAL GO
- Reason: the problem appears credible and monetizable, but willingness-to-pay and repeatable acquisition still need live validation.

## 2. Problem definition and urgency
- Problem: {answers['problem']}
- Why now: {answers['why_now']}
- Current workaround: {answers['current_solution']}

## 3. Ideal customer profile (ICP)
- ICP: {answers['icp']}
- Likely buyer: inferred from founder input and problem ownership.

## 4. Market analysis
- TAM estimate: {tam}
- SAM estimate: {sam}
- SOM estimate: {som}
- Note: these are directional planning estimates, not audited market data.

## 5. Competitive landscape
- Direct competitors: tools that already address slices of this problem.
- Indirect competitors: services, spreadsheets, internal workflows, consultants.
- Status quo: do nothing and absorb inefficiency/risk.
- Differentiation thesis: {answers['advantage']}

## 6. Value proposition and positioning
- We help {answers['icp']} solve `{answers['problem']}` through `{answers['mvp']}`.
- Why better: {answers['advantage']}
- Positioning: practical, ROI-driven, focused on a painful workflow rather than generic platform sprawl.

## 7. Product strategy
- MVP: {answers['mvp']}
- Phase 2: workflow integrations, reporting, analytics, collaboration.
- Phase 3: automation, recommendations, expansion modules.

## 8. Business model and pricing
- Payment rationale: {answers['payment_reason']}
- Recommended model: recurring B2B subscription with pilot-to-subscription conversion.
- Suggested entry pricing: land with a pilot, then move to recurring pricing once value is demonstrated.

## 9. Go-to-market plan
- First 10 customers: {answers['first_10_customers']}
- First 100 customers: systematize outbound, referrals, founder content, and case-study-led sales.
- Main channel: founder-led outbound + authority content.
- Sales motion: high-touch early sales, then productized onboarding.

## 10. Operating model
- Early team: founder-led sales, product, and domain expertise; add engineering and customer success selectively.
- Delivery: tightly scoped pilots with explicit success metrics.
- Support: founder-led initially; document patterns fast.

## 11. Financial model
- Revenue driver: paying ICP accounts.
- Cost drivers: engineering time, cloud costs, sales effort, onboarding/support.
- Burn assumption: stay lean until repeatable conversion exists.

## 12. Risk register with mitigation experiments
- Biggest risks: {answers['killer_risks']}
- Mitigation 1: run discovery calls and pre-sell pilots.
- Mitigation 2: prove ROI on a narrow use case.
- Mitigation 3: shorten time-to-value with a brutally simple onboarding flow.

## 13. 30/60 day action plan
- Days 1-15: interview prospects, refine ICP language, test pain severity.
- Days 16-30: build MVP slice, pitch pilots, collect objections.
- Days 31-60: run pilots, measure ROI, convert early users into references.

## 14. Assumptions vs Evidence
### Evidence
{evidence_md}

### Assumptions
- TAM/SAM/SOM numbers are directional.
- Pricing and conversion depend on demonstrated ROI.
- Retention depends on ongoing pain frequency and workflow fit.

## 15. Final verdict
**CONDITIONAL GO** — promising if the founder can quickly validate urgent pain, short time-to-value, and credible willingness-to-pay.
"""

    def _fallback_critique(self, plan: str, synthesis: dict[str, Any], round_idx: int) -> str:
        return f"""# Critique Round {round_idx}

1. Top 5 issues
- Market sizing is directional and not backed by strong external data.
- Pricing logic needs validation through live conversations.
- Buyer persona is implied more than proven.
- Operational delivery assumptions are still founder-heavy.
- Risk mitigation is sensible but needs explicit experiments and thresholds.

2. Missing evidence
- Proof of budget ownership
- Competitive win/loss detail
- Pilot-to-paid conversion benchmark
- Sales cycle estimate
- Retention indicators

3. Must change before approval
- Validate 10-15 ICP calls.
- Narrow the first wedge further.
- Define one measurable ROI promise.
- Build a cleaner pilot-to-annual pricing path.

4. Current verdict
CONDITIONAL GO
"""

    def _write_stage(self, stages_dir: Path, stage: Stage, payload: dict[str, Any]) -> None:
        (stages_dir / f"{stage.value}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_markdown_stage(self, stages_dir: Path, stage: Stage, content: str, suffix: str = "") -> None:
        (stages_dir / f"{stage.value}{suffix}.md").write_text(content, encoding="utf-8")
