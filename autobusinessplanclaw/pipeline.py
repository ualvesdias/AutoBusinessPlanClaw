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
from .research import build_competitor_queries, build_market_queries, fallback_competitors, fallback_evidence


class Pipeline:
    PERSONAS = ("investor", "potential client", "salesman", "expert")

    def __init__(self, config: ABCConfig):
        self.config = config
        self.client = OpenAICompatibleClient(config.llm)

    def run(
        self,
        answers: dict[str, str],
        web_search_fn=None,
        output_dir: str | None = None,
        resume: bool = False,
    ) -> Path:
        run_id = datetime.now(UTC).strftime("abc-%Y%m%d-%H%M%S")
        run_dir = Path(output_dir or Path(self.config.output.root) / run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        stages_dir = run_dir / "stages"
        exports_dir = run_dir / "exports"
        stages_dir.mkdir(exist_ok=True)
        exports_dir.mkdir(exist_ok=True)
        checkpoint_path = run_dir / "checkpoint.json"

        state = self._load_checkpoint(checkpoint_path) if resume else {"completed_stages": []}
        completed = set(state.get("completed_stages", []))

        def stage_done(stage: Stage) -> bool:
            return stage.value in completed

        queries = build_market_queries(self.config.business.idea, answers)
        raw_research: list[dict[str, Any]] = self._safe_read_json(run_dir / "research_results.json", []) if resume else []
        evidence_data = self._safe_read_json(stages_dir / f"{Stage.MARKET_RESEARCH.value}.json", {}) if resume else {}
        evidence: list[EvidenceItem] = []
        if evidence_data and isinstance(evidence_data, dict):
            for item in evidence_data.get("evidence", []):
                evidence.append(EvidenceItem(**item))

        if not stage_done(Stage.INTAKE):
            self._write_stage(stages_dir, Stage.INTAKE, {
                "idea": self.config.business.idea,
                "answers": answers,
            })
            self._mark_stage_complete(checkpoint_path, Stage.INTAKE, completed)

        if not stage_done(Stage.MARKET_RESEARCH):
            raw_research = []
            evidence = []
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
            (run_dir / "research_queries.json").write_text(json.dumps(queries, indent=2, ensure_ascii=False), encoding="utf-8")
            (run_dir / "research_results.json").write_text(json.dumps(raw_research, indent=2, ensure_ascii=False), encoding="utf-8")
            self._mark_stage_complete(checkpoint_path, Stage.MARKET_RESEARCH, completed)
        elif not evidence:
            evidence = fallback_evidence(self.config.business.idea, answers)

        competition = self._safe_read_json(run_dir / "competitor_matrix.json", None) if resume else None
        if not stage_done(Stage.COMPETITION):
            competition = self._build_competitor_matrix(answers, web_search_fn)
            self._write_stage(stages_dir, Stage.COMPETITION, competition)
            (run_dir / "competitor_matrix.json").write_text(json.dumps(competition, indent=2, ensure_ascii=False), encoding="utf-8")
            self._write_competitor_exports(exports_dir, competition["competitors"])
            self._mark_stage_complete(checkpoint_path, Stage.COMPETITION, completed)

        synthesis = self._safe_read_json(run_dir / "synthesis.json", None) if resume else None
        if not stage_done(Stage.SYNTHESIS):
            synthesis = self._build_synthesis(answers, evidence, competition)
            self._write_stage(stages_dir, Stage.SYNTHESIS, synthesis)
            (run_dir / "synthesis.json").write_text(json.dumps(synthesis, indent=2, ensure_ascii=False), encoding="utf-8")
            self._mark_stage_complete(checkpoint_path, Stage.SYNTHESIS, completed)

        persona_critiques = self._safe_read_json(run_dir / "persona_critiques.json", None) if resume else None
        if not stage_done(Stage.PERSONA_CRITIQUE):
            persona_critiques = self._run_persona_critiques(answers, evidence, synthesis)
            (run_dir / "persona_critiques.json").write_text(json.dumps(persona_critiques, indent=2, ensure_ascii=False), encoding="utf-8")
            self._write_stage(stages_dir, Stage.PERSONA_CRITIQUE, persona_critiques)
            self._mark_stage_complete(checkpoint_path, Stage.PERSONA_CRITIQUE, completed)

        tenth_man_report = self._safe_read_json(run_dir / "tenth_man_report.json", None) if resume else None
        if not stage_done(Stage.TENTH_MAN):
            tenth_man_report = self._run_tenth_man(answers, evidence, synthesis, persona_critiques)
            (run_dir / "tenth_man_report.json").write_text(json.dumps(tenth_man_report, indent=2, ensure_ascii=False), encoding="utf-8")
            self._write_stage(stages_dir, Stage.TENTH_MAN, tenth_man_report)
            self._mark_stage_complete(checkpoint_path, Stage.TENTH_MAN, completed)

        draft_path = stages_dir / f"{Stage.PLAN_DRAFT.value}.md"
        draft = draft_path.read_text(encoding="utf-8") if resume and draft_path.exists() else None
        if not stage_done(Stage.PLAN_DRAFT):
            draft = self._generate_plan(answers, evidence, synthesis, persona_critiques, tenth_man_report)
            self._write_markdown_stage(stages_dir, Stage.PLAN_DRAFT, draft)
            self._mark_stage_complete(checkpoint_path, Stage.PLAN_DRAFT, completed)

        critiques = self._safe_read_json(run_dir / "critiques.json", []) if resume else []
        current_plan = draft or ""
        revision_completed = stage_done(Stage.REVISION)
        if not revision_completed:
            critiques = []
            for round_idx in range(1, self.config.runtime.critique_rounds + 1):
                critique = self._critique_plan(current_plan, synthesis, persona_critiques, tenth_man_report, round_idx)
                critiques.append(critique)
                self._write_markdown_stage(stages_dir, Stage.CRITIQUE, critique, suffix=f"-{round_idx}")
                current_plan = self._revise_plan(current_plan, critique, synthesis, persona_critiques, tenth_man_report, round_idx)
                self._write_markdown_stage(stages_dir, Stage.REVISION, current_plan, suffix=f"-{round_idx}")
            (run_dir / "critiques.json").write_text(json.dumps(critiques, indent=2, ensure_ascii=False), encoding="utf-8")
            self._mark_stage_complete(checkpoint_path, Stage.CRITIQUE, completed)
            self._mark_stage_complete(checkpoint_path, Stage.REVISION, completed)
        else:
            final_revision = stages_dir / f"{Stage.REVISION.value}-{self.config.runtime.critique_rounds}.md"
            if final_revision.exists():
                current_plan = final_revision.read_text(encoding="utf-8")

        if not stage_done(Stage.FINANCIALS):
            finance_rows = self._build_financial_rows(answers)
            self._write_financial_exports(exports_dir, finance_rows)
            self._write_stage(stages_dir, Stage.FINANCIALS, {"rows": finance_rows})
            self._mark_stage_complete(checkpoint_path, Stage.FINANCIALS, completed)

        if not stage_done(Stage.GTM_PACK):
            gtm_pack = self._build_gtm_pack(answers)
            (exports_dir / "gtm_experiments.md").write_text(gtm_pack, encoding="utf-8")
            self._write_markdown_stage(stages_dir, Stage.GTM_PACK, gtm_pack)
            self._mark_stage_complete(checkpoint_path, Stage.GTM_PACK, completed)

        (run_dir / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
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
            "completed_stages": sorted(completed),
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_stage(stages_dir, Stage.EXPORT, summary)
        self._mark_stage_complete(checkpoint_path, Stage.EXPORT, completed)
        return run_dir

    def _build_competitor_matrix(self, answers: dict[str, str], web_search_fn=None) -> dict[str, Any]:
        queries = build_competitor_queries(self.config.business.idea, answers)
        competitors: list[dict[str, str]] = []
        raw: list[dict[str, Any]] = []
        if self.config.runtime.allow_web_research and web_search_fn is not None:
            for query in queries:
                results = web_search_fn(query=query, count=min(5, self.config.runtime.max_web_results))
                raw.append({"query": query, "results": results})
                for idx, item in enumerate(results[:2], start=1):
                    competitors.append({
                        "name": item.get("title", f"Concorrente {idx}"),
                        "type": "direct" if idx == 1 else "indirect",
                        "positioning": item.get("snippet", "Posicionamento não extraído")[:180],
                        "strengths": "Marca / presença de mercado",
                        "weaknesses": "Necessita validação específica para o ICP",
                        "pricing": "Desconhecido",
                        "evidence": item.get("url", ""),
                    })
        if not competitors:
            competitors = fallback_competitors(answers)
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for competitor in competitors:
            key = competitor["name"].strip().lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(competitor)
        return {
            "queries": queries,
            "raw_results": raw,
            "competitors": deduped,
        }

    def _generate_plan(self, answers, evidence, synthesis, persona_critiques, tenth_man_report) -> str:
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

    def _critique_plan(self, plan, synthesis, persona_critiques, tenth_man_report, round_idx: int) -> str:
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

    def _revise_plan(self, plan, critique, synthesis, persona_critiques, tenth_man_report, round_idx: int) -> str:
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

    def _run_persona_critiques(self, answers, evidence, synthesis) -> dict[str, Any]:
        niche = self._infer_niche(answers)
        results = {}
        for persona in self.PERSONAS:
            memo = self._run_persona_agent(persona, niche, answers, evidence, synthesis)
            results[persona] = {"persona": persona, "memo": memo}
        return results

    def _run_tenth_man(self, answers, evidence, synthesis, persona_critiques) -> dict[str, Any]:
        pro_agents = []
        for idx in range(1, self.config.runtime.pro_agent_count + 1):
            memo = self._run_pro_agent(idx, answers, evidence, synthesis, persona_critiques)
            pro_agents.append({"agent": f"pro_{idx}", "memo": memo})
        tenth_memo = self._run_tenth_man_agent(answers, evidence, synthesis, persona_critiques, pro_agents)
        master = self._run_master_critique(persona_critiques, pro_agents, tenth_memo, synthesis)
        return {"pro_agents": pro_agents, "tenth_man": {"agent": "tenth_man", "memo": tenth_memo}, "master_critique": master}

    def _run_persona_agent(self, persona, niche, answers, evidence, synthesis) -> str:
        prompt = self._agent_context(answers, evidence, synthesis) + f"\n\nPersona: {persona}\nNiche: {niche}"
        try:
            if self.client.is_configured():
                return self.client.complete(persona_prompt(persona, niche), prompt)
        except LLMError:
            pass
        return self._fallback_persona_memo(persona, niche, answers)

    def _run_pro_agent(self, idx, answers, evidence, synthesis, persona_critiques) -> str:
        prompt = self._agent_context(answers, evidence, synthesis)
        prompt += "\n\nPersona critique summary:\n" + json.dumps(persona_critiques, indent=2, ensure_ascii=False)
        try:
            if self.client.is_configured():
                return self.client.complete(pro_agent_prompt(idx), prompt)
        except LLMError:
            pass
        return self._fallback_pro_memo(idx, answers)

    def _run_tenth_man_agent(self, answers, evidence, synthesis, persona_critiques, pro_agents) -> str:
        prompt = self._agent_context(answers, evidence, synthesis)
        prompt += "\n\nPersona critique summary:\n" + json.dumps(persona_critiques, indent=2, ensure_ascii=False)
        prompt += "\n\nNine pro agents:\n" + json.dumps(pro_agents, indent=2, ensure_ascii=False)
        try:
            if self.client.is_configured():
                return self.client.complete(TENTH_MAN_PROMPT, prompt)
        except LLMError:
            pass
        return self._fallback_tenth_man_memo(answers)

    def _run_master_critique(self, persona_critiques, pro_agents, tenth_memo, synthesis) -> str:
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

    def _build_synthesis(self, answers, evidence, competition) -> dict[str, Any]:
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
            "competitor_names": [c["name"] for c in (competition or {}).get("competitors", [])],
        }

    def _build_financial_rows(self, answers) -> list[dict[str, Any]]:
        price = 3000 if "enterprise" in answers["icp"].lower() or "ciso" in answers["icp"].lower() else 1200
        customers = [1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18]
        rows = []
        base_opex = 35000
        for month, customer_count in enumerate(customers, start=1):
            revenue = customer_count * price
            cogs = max(500, int(revenue * 0.12))
            opex = base_opex + (2000 if month > 6 else 0)
            net = revenue - cogs - opex
            rows.append({"month": month, "customers": customer_count, "arpa": price, "revenue": revenue, "cogs": cogs, "opex": opex, "net_burn": -net, "cash_flow": net})
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

    def _write_competitor_exports(self, exports_dir: Path, competitors: list[dict[str, str]]) -> None:
        csv_path = exports_dir / "competitor_matrix.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["name", "type", "positioning", "strengths", "weaknesses", "pricing", "evidence"])
            writer.writeheader()
            writer.writerows(competitors)
        md_path = exports_dir / "competitor_matrix.md"
        lines = ["# Matriz de concorrência", ""]
        for competitor in competitors:
            lines.extend([
                f"## {competitor['name']}",
                f"- Tipo: {competitor['type']}",
                f"- Posicionamento: {competitor['positioning']}",
                f"- Forças: {competitor['strengths']}",
                f"- Fraquezas: {competitor['weaknesses']}",
                f"- Pricing: {competitor['pricing']}",
                f"- Evidência: {competitor['evidence']}",
                "",
            ])
        md_path.write_text("\n".join(lines), encoding="utf-8")

    def _build_gtm_pack(self, answers) -> str:
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

    def _fallback_plan(self, answers, evidence, synthesis, persona_critiques, tenth_man_report) -> str:
        evidence_md = "\n".join(f"- {e.title}: {e.snippet}" for e in evidence[:8])
        persona_names = ", ".join(persona_critiques.keys())
        market_sizes = self._estimate_market_sizes(answers)
        tam, sam, som = market_sizes["tam"], market_sizes["sam"], market_sizes["som"]
        risk_base = tenth_man_report["master_critique"]
        competitors = synthesis.get("competitor_names", [])
        competition_line = ", ".join(competitors) if competitors else "status quo, consultoria especializada e ferramenta horizontal existente"
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
- Competidores principais mapeados: {competition_line}
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

    def _fallback_critique(self, plan, synthesis, persona_critiques, tenth_man_report, round_idx):
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

    def _fallback_persona_memo(self, persona, niche, answers):
        if persona == "investor":
            return "# Investor memo\n- Strongest concerns: defensibility, sales efficiency, and whether the wedge can grow into a large-enough market.\n- Strongest positives: founder-domain fit and a painful problem with recurring value.\n- Missing evidence: market size proof, sales cycle data, and retention signals.\n- Verdict: CONDITIONAL GO.\n- Next experiments: validate ACV, pilot conversion, and upsell path.\n"
        if persona == "potential client":
            return f"# Potential client memo\n- Strongest concerns: switching cost, trust, integration friction, and whether this is must-have or just nice-to-have.\n- Strongest positives: clear pain around {answers['problem']}.\n- Missing evidence: budget owner, onboarding burden, and measurable ROI.\n- Verdict: interested but skeptical.\n- Next experiments: customer interviews, pilot design, and ROI promise testing.\n"
        if persona == "salesman":
            return "# Sales memo\n- Strongest concerns: the message may still be too broad and the buyer may not feel urgency fast enough.\n- Strongest positives: founder-led outbound is plausible for early traction.\n- Missing evidence: response rates, objection patterns, and a crisp wedge.\n- Verdict: sellable if narrowed.\n- Next experiments: outbound script testing and objection logging.\n"
        return f"# Expert memo ({niche})\n- Strongest concerns: technical differentiation may be thinner than it looks and operational trust matters.\n- Strongest positives: the problem is real within the niche and current tooling often overproduces noise.\n- Missing evidence: workflow fit and measurable superiority over current alternatives.\n- Verdict: technically plausible, commercially unproven.\n- Next experiments: benchmark the MVP against status quo workflows.\n"

    def _fallback_pro_memo(self, idx, answers):
        return f"# Pro agent {idx}\n1. Strongest success arguments\n- The problem is painful and frequent.\n- The founder has a believable advantage: {answers['advantage']}.\n- A narrow MVP exists: {answers['mvp']}.\n\n2. Key enabling assumptions\n- The ICP will pay if ROI is visible.\n- Sales can start with founder-led outbound.\n\n3. How to increase odds of success\n- Narrow the wedge and prove value quickly.\n\n4. Confidence level\nModerate\n\n5. Provisional verdict\nCONDITIONAL GO\n"

    def _fallback_tenth_man_memo(self, answers):
        return "# 10th Man Dissent Memo\n\n1. Strongest failure case\n- The problem is real but not budget-priority enough to support a repeatable business.\n\n2. Where the 9 pro agents may be fooling themselves\n- They may be confusing founder expertise with market demand.\n- They may be overestimating urgency and underestimating sales friction.\n\n3. Failure modes\n- Market: ICP does not allocate budget.\n- Product: MVP is too shallow to displace current workflows.\n- GTM: founder outbound generates interest but not paid conversion.\n- Financial: CAC rises before retention is proven.\n- Execution: long feedback loops slow iteration.\n\n4. Early warning indicators\n- Low response rates\n- Positive interviews but no pilot commitment\n- Pilots that do not convert\n- Weak ROI evidence\n\n5. What evidence would prove this wrong\n- Fast pilot conversion, repeated usage, and a clear budget owner.\n\n6. Final dissent verdict\nNO-GO until real buying behavior is observed.\n"

    def _fallback_master_critique(self, persona_critiques, tenth_memo):
        return f"# Master Critique\n\n## strongest reasons to believe\n- Multiple personas see a real underlying pain.\n- The founder appears to have domain credibility.\n\n## strongest reasons to doubt\n- Budget ownership and conversion remain unproven.\n- The dissent case warns that urgency may be overstated.\n\n## conflict map\n- Positive side: pain exists and MVP is plausible.\n- Negative side: willingness-to-pay and repeatable GTM are still hypothetical.\n\n## what must be validated before green-lighting\n- 10-15 interviews\n- 2-3 pilots\n- at least one paid conversion path\n\n## final committee verdict\nCONDITIONAL GO\n\n## dissent memo anchor\n{tenth_memo}\n"

    def _estimate_market_sizes(self, answers):
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
            "tam": f"{tam_accounts:,} target accounts × {acv:,} annual contract value = {tam_accounts * acv:,}",
            "sam": f"{sam_accounts:,} reachable accounts × {acv:,} ACV = {sam_accounts * acv:,}",
            "som": f"{som_accounts:,} first-wave accounts × {acv:,} ACV = {som_accounts * acv:,}",
        }

    def _infer_niche(self, answers):
        text = " ".join([answers["problem"], answers["icp"], answers["mvp"], self.config.business.idea])
        lowered = text.lower()
        if any(token in lowered for token in ("cyber", "security", "vulnerability", "ciso", "appsec")):
            return "cybersecurity"
        if any(token in lowered for token in ("health", "clinic", "medical", "patient")):
            return "healthcare"
        if any(token in lowered for token in ("fintech", "bank", "payment", "fraud")):
            return "fintech"
        return "the target business niche"

    def _agent_context(self, answers, evidence, synthesis):
        evidence_lines = [f"{e.title} — {e.url} — {e.snippet}" for e in evidence[:12]]
        return (
            f"Idea: {self.config.business.idea}\n"
            f"Region: {self.config.business.region}\n"
            f"Currency: {self.config.business.currency}\n\n"
            f"Founder answers:\n{json.dumps(answers, indent=2, ensure_ascii=False)}\n\n"
            f"Evidence:\n{json.dumps(evidence_lines, indent=2, ensure_ascii=False)}\n\n"
            f"Synthesis:\n{json.dumps(synthesis, indent=2, ensure_ascii=False)}"
        )

    def _safe_read_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def _load_checkpoint(self, checkpoint_path: Path) -> dict[str, Any]:
        return self._safe_read_json(checkpoint_path, {"completed_stages": []})

    def _mark_stage_complete(self, checkpoint_path: Path, stage: Stage, completed: set[str]) -> None:
        completed.add(stage.value)
        payload = {
            "completed_stages": sorted(completed),
            "updated_at": datetime.now(UTC).isoformat(),
            "last_completed_stage": stage.value,
        }
        checkpoint_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_stage(self, stages_dir: Path, stage: Stage, payload: dict[str, Any]) -> None:
        (stages_dir / f"{stage.value}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_markdown_stage(self, stages_dir: Path, stage: Stage, content: str, suffix: str = "") -> None:
        (stages_dir / f"{stage.value}{suffix}.md").write_text(content, encoding="utf-8")
