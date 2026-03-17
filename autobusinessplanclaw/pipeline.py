from __future__ import annotations

import csv
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from .llm import LLMError, OpenAICompatibleClient
from .models import ABCConfig, EvidenceItem, Stage
from .prompts import (
    SYSTEM_PROMPT,
    CRITIC_PROMPT,
    REVISION_PROMPT,
    TENTH_MAN_PROMPT,
    master_critique_prompt,
    persona_prompt,
    planning_prompt,
    pro_agent_prompt,
)
from .research import build_market_queries, fallback_evidence


class Pipeline:
    PERSONAS = ("investor", "potential client", "salesman", "expert")

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

        persona_critiques = self._run_persona_critiques(answers, evidence, synthesis)
        (run_dir / "persona_critiques.json").write_text(json.dumps(persona_critiques, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_stage(stages_dir, Stage.PERSONA_CRITIQUE, persona_critiques)

        tenth_man_report = self._run_tenth_man(answers, evidence, synthesis, persona_critiques)
        (run_dir / "tenth_man_report.json").write_text(json.dumps(tenth_man_report, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_stage(stages_dir, Stage.TENTH_MAN, tenth_man_report)

        draft = self._generate_plan(answers, evidence, synthesis, persona_critiques, tenth_man_report)
        self._write_markdown_stage(stages_dir, Stage.PLAN_DRAFT, draft)

        current_plan = draft
        critiques: list[str] = []
        for round_idx in range(1, self.config.runtime.critique_rounds + 1):
            critique = self._critique_plan(current_plan, synthesis, persona_critiques, tenth_man_report, round_idx)
            critiques.append(critique)
            self._write_markdown_stage(stages_dir, Stage.CRITIQUE, critique, suffix=f"-{round_idx}")
            current_plan = self._revise_plan(current_plan, critique, synthesis, persona_critiques, tenth_man_report, round_idx)
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
            "persona_count": len(self.PERSONAS),
            "pro_agent_count": self.config.runtime.pro_agent_count,
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_stage(stages_dir, Stage.EXPORT, summary)
        return run_dir

    def _generate_plan(
        self,
        answers: dict[str, str],
        evidence: list[EvidenceItem],
        synthesis: dict[str, Any],
        persona_critiques: dict[str, Any],
        tenth_man_report: dict[str, Any],
    ) -> str:
        evidence_lines = [f"{item.title} — {item.url} — {item.snippet}" for item in evidence[:20]]
        prompt = planning_prompt(
            self.config.business.idea,
            answers,
            evidence_lines,
            self.config.business.currency,
            self.config.business.region,
        )
        prompt += "\n\nStructured synthesis:\n" + json.dumps(synthesis, indent=2, ensure_ascii=False)
        prompt += "\n\nPersona critiques:\n" + json.dumps(persona_critiques, indent=2, ensure_ascii=False)
        prompt += "\n\n10th-man debate:\n" + json.dumps(tenth_man_report, indent=2, ensure_ascii=False)
        prompt += "\n\nUse the 10th-man material as core input for the risk section."
        try:
            if self.client.is_configured():
                return self.client.complete(SYSTEM_PROMPT, prompt)
        except LLMError:
            pass
        return self._fallback_plan(answers, evidence, synthesis, persona_critiques, tenth_man_report)

    def _critique_plan(
        self,
        plan: str,
        synthesis: dict[str, Any],
        persona_critiques: dict[str, Any],
        tenth_man_report: dict[str, Any],
        round_idx: int,
    ) -> str:
        critique_input = (
            f"Round {round_idx}\n\nPlan:\n{plan}\n\nSynthesis:\n{json.dumps(synthesis, indent=2, ensure_ascii=False)}"
            f"\n\nPersona critiques:\n{json.dumps(persona_critiques, indent=2, ensure_ascii=False)}"
            f"\n\n10th-man debate:\n{json.dumps(tenth_man_report, indent=2, ensure_ascii=False)}"
        )
        try:
            if self.client.is_configured():
                return self.client.complete(CRITIC_PROMPT, critique_input)
        except LLMError:
            pass
        return self._fallback_critique(plan, synthesis, persona_critiques, tenth_man_report, round_idx)

    def _revise_plan(
        self,
        plan: str,
        critique: str,
        synthesis: dict[str, Any],
        persona_critiques: dict[str, Any],
        tenth_man_report: dict[str, Any],
        round_idx: int,
    ) -> str:
        revision_input = (
            f"Round {round_idx}\n\nOriginal plan:\n{plan}\n\nCritique:\n{critique}"
            f"\n\nSynthesis:\n{json.dumps(synthesis, indent=2, ensure_ascii=False)}"
            f"\n\nPersona critiques:\n{json.dumps(persona_critiques, indent=2, ensure_ascii=False)}"
            f"\n\n10th-man debate:\n{json.dumps(tenth_man_report, indent=2, ensure_ascii=False)}"
        )
        try:
            if self.client.is_configured():
                return self.client.complete(REVISION_PROMPT, revision_input)
        except LLMError:
            pass
        return plan + "\n\n---\n\n## Internal critique adjustments\n\n" + critique

    def _run_persona_critiques(
        self,
        answers: dict[str, str],
        evidence: list[EvidenceItem],
        synthesis: dict[str, Any],
    ) -> dict[str, Any]:
        niche = self._infer_niche(answers)
        results: dict[str, Any] = {}
        for persona in self.PERSONAS:
            memo = self._run_persona_agent(persona, niche, answers, evidence, synthesis)
            results[persona] = {"persona": persona, "memo": memo}
        return results

    def _run_tenth_man(
        self,
        answers: dict[str, str],
        evidence: list[EvidenceItem],
        synthesis: dict[str, Any],
        persona_critiques: dict[str, Any],
    ) -> dict[str, Any]:
        pro_agents: list[dict[str, Any]] = []
        for idx in range(1, self.config.runtime.pro_agent_count + 1):
            memo = self._run_pro_agent(idx, answers, evidence, synthesis, persona_critiques)
            pro_agents.append({"agent": f"pro_{idx}", "memo": memo})
        tenth_memo = self._run_tenth_man_agent(answers, evidence, synthesis, persona_critiques, pro_agents)
        master = self._run_master_critique(persona_critiques, pro_agents, tenth_memo, synthesis)
        return {
            "pro_agents": pro_agents,
            "tenth_man": {"agent": "tenth_man", "memo": tenth_memo},
            "master_critique": master,
        }

    def _run_persona_agent(self, persona: str, niche: str, answers: dict[str, str], evidence: list[EvidenceItem], synthesis: dict[str, Any]) -> str:
        prompt = self._agent_context(answers, evidence, synthesis) + f"\n\nPersona: {persona}\nNiche: {niche}"
        try:
            if self.client.is_configured():
                return self.client.complete(persona_prompt(persona, niche), prompt)
        except LLMError:
            pass
        return self._fallback_persona_memo(persona, niche, answers)

    def _run_pro_agent(self, idx: int, answers: dict[str, str], evidence: list[EvidenceItem], synthesis: dict[str, Any], persona_critiques: dict[str, Any]) -> str:
        prompt = self._agent_context(answers, evidence, synthesis)
        prompt += "\n\nPersona critique summary:\n" + json.dumps(persona_critiques, indent=2, ensure_ascii=False)
        try:
            if self.client.is_configured():
                return self.client.complete(pro_agent_prompt(idx), prompt)
        except LLMError:
            pass
        return self._fallback_pro_memo(idx, answers)

    def _run_tenth_man_agent(self, answers: dict[str, str], evidence: list[EvidenceItem], synthesis: dict[str, Any], persona_critiques: dict[str, Any], pro_agents: list[dict[str, Any]]) -> str:
        prompt = self._agent_context(answers, evidence, synthesis)
        prompt += "\n\nPersona critique summary:\n" + json.dumps(persona_critiques, indent=2, ensure_ascii=False)
        prompt += "\n\nNine pro agents:\n" + json.dumps(pro_agents, indent=2, ensure_ascii=False)
        try:
            if self.client.is_configured():
                return self.client.complete(TENTH_MAN_PROMPT, prompt)
        except LLMError:
            pass
        return self._fallback_tenth_man_memo(answers)

    def _run_master_critique(self, persona_critiques: dict[str, Any], pro_agents: list[dict[str, Any]], tenth_memo: str, synthesis: dict[str, Any]) -> str:
        prompt = (
            "Persona critiques:\n" + json.dumps(persona_critiques, indent=2, ensure_ascii=False)
            + "\n\nPro agents:\n" + json.dumps(pro_agents, indent=2, ensure_ascii=False)
            + "\n\n10th man:\n" + tenth_memo
            + "\n\nSynthesis:\n" + json.dumps(synthesis, indent=2, ensure_ascii=False)
        )
        try:
            if self.client.is_configured():
                return self.client.complete(master_critique_prompt(), prompt)
        except LLMError:
            pass
        return self._fallback_master_critique(persona_critiques, tenth_memo)

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

    def _fallback_plan(
        self,
        answers: dict[str, str],
        evidence: list[EvidenceItem],
        synthesis: dict[str, Any],
        persona_critiques: dict[str, Any],
        tenth_man_report: dict[str, Any],
    ) -> str:
        evidence_md = "\n".join(f"- {e.title}: {e.snippet}" for e in evidence[:8])
        persona_names = ", ".join(persona_critiques.keys())
        tam = self._estimate_market_sizes(answers)["tam"]
        sam = self._estimate_market_sizes(answers)["sam"]
        som = self._estimate_market_sizes(answers)["som"]
        risk_base = tenth_man_report["master_critique"]
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
- Note: these are directional planning estimates using heuristic logic rather than audited market data.

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
- This section is grounded in the 10th-man workflow, not just generic startup anxiety.
- Biggest risks: {answers['killer_risks']}
- Multi-agent critique personas used: {persona_names}
- Mitigation 1: run discovery calls and pre-sell pilots.
- Mitigation 2: prove ROI on a narrow use case.
- Mitigation 3: shorten time-to-value with a brutally simple onboarding flow.
- 10th-man base work summary:
{risk_base}

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

    def _fallback_critique(
        self,
        plan: str,
        synthesis: dict[str, Any],
        persona_critiques: dict[str, Any],
        tenth_man_report: dict[str, Any],
        round_idx: int,
    ) -> str:
        return f"""# Critique Round {round_idx}

1. Top 5 issues
- Market sizing is directional and not backed by strong external data.
- Pricing logic needs validation through live conversations.
- Buyer persona is implied more than proven.
- Operational delivery assumptions are still founder-heavy.
- The 10th-man analysis raises credible failure modes that should shape execution.

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

    def _fallback_persona_memo(self, persona: str, niche: str, answers: dict[str, str]) -> str:
        if persona == "investor":
            return f"""# Investor memo
- Strongest concerns: defensibility, sales efficiency, and whether the wedge can grow into a large-enough market.
- Strongest positives: founder-domain fit and a painful problem with recurring value.
- Missing evidence: market size proof, sales cycle data, and retention signals.
- Verdict: CONDITIONAL GO.
- Next experiments: validate ACV, pilot conversion, and upsell path.
"""
        if persona == "potential client":
            return f"""# Potential client memo
- Strongest concerns: switching cost, trust, integration friction, and whether this is must-have or just nice-to-have.
- Strongest positives: clear pain around {answers['problem']}.
- Missing evidence: budget owner, onboarding burden, and measurable ROI.
- Verdict: interested but skeptical.
- Next experiments: customer interviews, pilot design, and ROI promise testing.
"""
        if persona == "salesman":
            return f"""# Sales memo
- Strongest concerns: the message may still be too broad and the buyer may not feel urgency fast enough.
- Strongest positives: founder-led outbound is plausible for early traction.
- Missing evidence: response rates, objection patterns, and a crisp wedge.
- Verdict: sellable if narrowed.
- Next experiments: outbound script testing and objection logging.
"""
        return f"""# Expert memo ({niche})
- Strongest concerns: technical differentiation may be thinner than it looks and operational trust matters.
- Strongest positives: the problem is real within the niche and current tooling often overproduces noise.
- Missing evidence: workflow fit and measurable superiority over current alternatives.
- Verdict: technically plausible, commercially unproven.
- Next experiments: benchmark the MVP against status quo workflows.
"""

    def _fallback_pro_memo(self, idx: int, answers: dict[str, str]) -> str:
        return f"""# Pro agent {idx}
1. Strongest success arguments
- The problem is painful and frequent.
- The founder has a believable advantage: {answers['advantage']}.
- A narrow MVP exists: {answers['mvp']}.

2. Key enabling assumptions
- The ICP will pay if ROI is visible.
- Sales can start with founder-led outbound.

3. How to increase odds of success
- Narrow the wedge and prove value quickly.

4. Confidence level
Moderate

5. Provisional verdict
CONDITIONAL GO
"""

    def _fallback_tenth_man_memo(self, answers: dict[str, str]) -> str:
        return f"""# 10th Man Dissent Memo

1. Strongest failure case
- The problem is real but not budget-priority enough to support a repeatable business.

2. Where the 9 pro agents may be fooling themselves
- They may be confusing founder expertise with market demand.
- They may be overestimating urgency and underestimating sales friction.

3. Failure modes
- Market: ICP does not allocate budget.
- Product: MVP is too shallow to displace current workflows.
- GTM: founder outbound generates interest but not paid conversion.
- Financial: CAC rises before retention is proven.
- Execution: long feedback loops slow iteration.

4. Early warning indicators
- Low response rates
- Positive interviews but no pilot commitment
- Pilots that do not convert
- Weak ROI evidence

5. What evidence would prove this wrong
- Fast pilot conversion, repeated usage, and a clear budget owner.

6. Final dissent verdict
NO-GO until real buying behavior is observed.
"""

    def _fallback_master_critique(self, persona_critiques: dict[str, Any], tenth_memo: str) -> str:
        return f"""# Master Critique

## strongest reasons to believe
- Multiple personas see a real underlying pain.
- The founder appears to have domain credibility.

## strongest reasons to doubt
- Budget ownership and conversion remain unproven.
- The dissent case warns that urgency may be overstated.

## conflict map
- Positive side: pain exists and MVP is plausible.
- Negative side: willingness-to-pay and repeatable GTM are still hypothetical.

## what must be validated before green-lighting
- 10-15 interviews
- 2-3 pilots
- at least one paid conversion path

## final committee verdict
CONDITIONAL GO

## dissent memo anchor
{tenth_memo}
"""

    def _estimate_market_sizes(self, answers: dict[str, str]) -> dict[str, str]:
        icp_lower = answers["icp"].lower()
        if "smb" in icp_lower or "20 to 200" in icp_lower:
            acv = 12000
            tam_accounts = 50000
            sam_accounts = 5000
            som_accounts = 50
        elif "enterprise" in icp_lower:
            acv = 48000
            tam_accounts = 10000
            sam_accounts = 1000
            som_accounts = 20
        else:
            acv = 18000
            tam_accounts = 20000
            sam_accounts = 2000
            som_accounts = 30
        return {
            "tam": f"{tam_accounts:,} target accounts × {acv:,} annual contract value = {tam_accounts * acv:,}".replace(",", ","),
            "sam": f"{sam_accounts:,} reachable accounts × {acv:,} ACV = {sam_accounts * acv:,}".replace(",", ","),
            "som": f"{som_accounts:,} first-wave accounts × {acv:,} ACV = {som_accounts * acv:,}".replace(",", ","),
        }

    def _infer_niche(self, answers: dict[str, str]) -> str:
        text = " ".join([answers["problem"], answers["icp"], answers["mvp"], self.config.business.idea])
        lowered = text.lower()
        if any(token in lowered for token in ("cyber", "security", "vulnerability", "ciso", "appsec")):
            return "cybersecurity"
        if any(token in lowered for token in ("health", "clinic", "medical", "patient")):
            return "healthcare"
        if any(token in lowered for token in ("fintech", "bank", "payment", "fraud")):
            return "fintech"
        return "the target business niche"

    def _agent_context(self, answers: dict[str, str], evidence: list[EvidenceItem], synthesis: dict[str, Any]) -> str:
        evidence_lines = [f"{e.title} — {e.url} — {e.snippet}" for e in evidence[:12]]
        return (
            f"Idea: {self.config.business.idea}\n"
            f"Region: {self.config.business.region}\n"
            f"Currency: {self.config.business.currency}\n\n"
            f"Founder answers:\n{json.dumps(answers, indent=2, ensure_ascii=False)}\n\n"
            f"Evidence:\n{json.dumps(evidence_lines, indent=2, ensure_ascii=False)}\n\n"
            f"Synthesis:\n{json.dumps(synthesis, indent=2, ensure_ascii=False)}"
        )

    def _write_stage(self, stages_dir: Path, stage: Stage, payload: dict[str, Any]) -> None:
        (stages_dir / f"{stage.value}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_markdown_stage(self, stages_dir: Path, stage: Stage, content: str, suffix: str = "") -> None:
        (stages_dir / f"{stage.value}{suffix}.md").write_text(content, encoding="utf-8")
