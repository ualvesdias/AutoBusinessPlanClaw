from __future__ import annotations

import csv
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    COMPETITOR_ANALYST_PROMPT,
    FINANCIAL_MODEL_PROMPT,
    FINANCIAL_INTELLIGENCE_PROMPT,
    QUERY_SPECIALIST_PROMPT,
    FINANCIAL_MODEL_PROMPT,
    FINANCIAL_INTELLIGENCE_PROMPT,
    master_critique_prompt,
    persona_prompt,
    planning_prompt,
    pro_agent_prompt,
)
from .research import (
    GENERIC_POSITIONING_FALLBACK,
    GENERIC_STRENGTHS_FALLBACK,
    GENERIC_WEAKNESSES_FALLBACK,
    build_comparison_rows,
    build_competitor_quality,
    build_competitor_queries,
    build_evidence_summary,
    build_market_queries,
    dedupe_evidence,
    fallback_competitors,
    fallback_evidence,
    normalize_evidence,
    prepare_competitor_candidates,
    write_comparison_exports,
)


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
        root_dir = Path(self.config.output.root)
        if output_dir is None:
            run_dir = root_dir / run_id
        else:
            candidate = Path(output_dir)
            run_dir = candidate if candidate.is_absolute() else (candidate if candidate.parts and candidate.parts[0] == root_dir.name else root_dir / candidate)
        self._prepare_run_dir(run_dir, resume=resume)
        run_dir.mkdir(parents=True, exist_ok=True)
        stages_dir = run_dir / "stages"
        exports_dir = run_dir / "exports"
        prompts_dir = run_dir / "prompts"
        stages_dir.mkdir(exist_ok=True)
        exports_dir.mkdir(exist_ok=True)
        prompts_dir.mkdir(exist_ok=True)
        self.current_run_dir = run_dir
        checkpoint_path = run_dir / "checkpoint.json"

        state = self._load_checkpoint(checkpoint_path) if resume else {"completed_stages": []}
        completed = set(state.get("completed_stages", []))

        def stage_done(stage: Stage) -> bool:
            return stage.value in completed

        queries = self._build_market_queries(answers)
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
                with ThreadPoolExecutor(max_workers=self.config.runtime.parallel_workers) as executor:
                    future_map = {
                        executor.submit(web_search_fn, query=query, count=self.config.runtime.max_web_results): query
                        for query in queries
                    }
                    for future in as_completed(future_map):
                        query = future_map[future]
                        try:
                            results = future.result()
                        except Exception:
                            results = []
                        raw_research.append({"query": query, "results": results})
                        for item in results:
                            evidence.append(EvidenceItem(**item))
            evidence = dedupe_evidence(evidence)
            if not evidence:
                evidence = fallback_evidence(self.config.business.idea, answers)
            self._write_stage(stages_dir, Stage.MARKET_RESEARCH, {
                "queries": queries,
                "raw_research": raw_research,
                "evidence": [e.__dict__ for e in evidence],
                "evidence_summary": build_evidence_summary(evidence),
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
            comparison_rows = build_comparison_rows(competition["competitors"], self.config.business.idea, answers)
            (run_dir / "competitor_reference_table.json").write_text(json.dumps(comparison_rows, indent=2, ensure_ascii=False), encoding="utf-8")
            write_comparison_exports(comparison_rows, exports_dir)
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
            finance_model = self._build_financial_model(answers, synthesis, persona_critiques, tenth_man_report, current_plan)
            finance_analysis = self._build_financial_intelligence(finance_model)
            finance_payload = {**finance_model, "analysis": finance_analysis}
            self._write_financial_exports(exports_dir, finance_model["rows"])
            (exports_dir / "financial_analysis.md").write_text(self._render_financial_analysis_markdown(finance_analysis), encoding="utf-8")
            self._write_stage(stages_dir, Stage.FINANCIALS, finance_payload)
            self._mark_stage_complete(checkpoint_path, Stage.FINANCIALS, completed)

        if not stage_done(Stage.GTM_PACK):
            gtm_pack = self._build_gtm_pack(answers)
            (exports_dir / "gtm_experiments.md").write_text(gtm_pack, encoding="utf-8")
            self._write_markdown_stage(stages_dir, Stage.GTM_PACK, gtm_pack)
            self._mark_stage_complete(checkpoint_path, Stage.GTM_PACK, completed)

        (run_dir / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "business_plan.md").write_text(current_plan, encoding="utf-8")

        competition_quality = (competition or {}).get("analysis_quality", {}) if isinstance(competition, dict) else {}
        run_status = "complete" if competition_quality.get("quality_gate_passed", True) else "incomplete"
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
            "competition_quality": competition_quality,
            "run_status": run_status,
            "warnings": (["Competition stage quality gate failed; treat output as incomplete competitive intelligence."] if run_status == "incomplete" else []),
            "completed_stages": sorted(completed),
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_stage(stages_dir, Stage.EXPORT, summary)
        self._mark_stage_complete(checkpoint_path, Stage.EXPORT, completed)
        return run_dir

    def _prepare_run_dir(self, run_dir: Path, resume: bool) -> None:
        if resume or not run_dir.exists():
            return
        managed_dirs = ["stages", "exports", "prompts"]
        managed_files = [
            "answers.json",
            "business_plan.md",
            "checkpoint.json",
            "competitor_matrix.json",
            "competitor_reference_table.json",
            "critiques.json",
            "persona_critiques.json",
            "research_queries.json",
            "research_results.json",
            "run_summary.json",
            "synthesis.json",
            "tenth_man_report.json",
            "doctor.json",
        ]
        for dirname in managed_dirs:
            path = run_dir / dirname
            if path.exists():
                shutil.rmtree(path)
        for filename in managed_files:
            path = run_dir / filename
            if path.exists():
                path.unlink()

    def _build_competitor_matrix(self, answers: dict[str, str], web_search_fn=None) -> dict[str, Any]:
        queries = self._build_competitor_queries(answers)
        raw: list[dict[str, Any]] = []
        evidence_items: list[EvidenceItem] = []
        if self.config.runtime.allow_web_research and web_search_fn is not None:
            with ThreadPoolExecutor(max_workers=self.config.runtime.parallel_workers) as executor:
                future_map = {
                    executor.submit(web_search_fn, query=query, count=min(5, self.config.runtime.max_web_results)): query
                    for query in queries
                }
                for future in as_completed(future_map):
                    query = future_map[future]
                    try:
                        results = future.result()
                    except Exception:
                        results = []
                    raw.append({"query": query, "results": results})
                    evidence_items.extend(normalize_evidence(results))

        candidates = prepare_competitor_candidates(dedupe_evidence(evidence_items))
        competitors = [self._analyze_competitor_candidate(candidate, answers) for candidate in candidates]
        if len(competitors) < 3:
            fallback = fallback_competitors(answers, self.config.business.idea)
            existing = {c["name"].strip().lower() for c in competitors}
            for competitor in fallback:
                key = competitor["name"].strip().lower()
                if key not in existing:
                    enriched = dict(competitor)
                    enriched.setdefault("analysis_status", "fallback")
                    enriched.setdefault("analysis_source", "heuristic_fallback")
                    enriched.setdefault("evidence_count", "0")
                    enriched.setdefault("evidence_excerpt", "")
                    enriched.setdefault("confidence", "low")
                    competitors.append(enriched)
                    existing.add(key)
        quality = build_competitor_quality(competitors, raw_candidate_count=len(candidates))

        return {
            "queries": queries,
            "raw_results": raw,
            "competitors": competitors,
            "evidence_summary": {
                "raw_result_batches": len(raw),
                "competitor_count": len(competitors),
            },
            "analysis_quality": quality,
        }

    def _build_market_queries(self, answers: dict[str, str]) -> list[str]:
        fallback = build_market_queries(self.config.business.idea, answers, region=self.config.business.region)
        return self._query_specialist_agent("market_research", answers, fallback)

    def _build_competitor_queries(self, answers: dict[str, str]) -> list[str]:
        fallback = build_competitor_queries(self.config.business.idea, answers, region=self.config.business.region)
        return self._query_specialist_agent("competition", answers, fallback)

    def _query_specialist_agent(self, intent: str, answers: dict[str, str], fallback: list[str]) -> list[str]:
        prompt = (
            f"Intent: {intent}\n"
            f"Idea: {self.config.business.idea}\n"
            f"Region: {self.config.business.region}\n"
            f"Business model hint: {self.config.business.business_model_hint}\n"
            f"Founder answers: {json.dumps(answers, ensure_ascii=False)}\n"
            f"Fallback heuristic queries: {json.dumps(fallback, ensure_ascii=False)}\n"
            "Return strict JSON only."
        )
        stage_name = f"query_specialist_{intent}"
        self._record_prompt(stage_name, QUERY_SPECIALIST_PROMPT, prompt)
        try:
            if self.client.is_configured():
                raw = self.client.complete(QUERY_SPECIALIST_PROMPT, prompt)
                self._record_response(stage_name, raw)
                parsed = self._parse_competitor_analysis_json(raw)
                if isinstance(parsed, dict) and isinstance(parsed.get("queries"), list):
                    cleaned = [str(q).strip() for q in parsed["queries"] if str(q).strip()]
                    deduped = []
                    seen = set()
                    for q in cleaned:
                        key = q.lower()
                        if key not in seen:
                            seen.add(key)
                            deduped.append(q)
                    if len(deduped) >= 4:
                        return deduped[:10]
        except LLMError as exc:
            self._record_response(stage_name, f"LLM_ERROR: {exc}")
        return fallback

    def _analyze_competitor_candidate(self, candidate: dict[str, Any], answers: dict[str, str]) -> dict[str, str]:
        fallback = self._fallback_competitor_analysis(candidate)
        prompt = (
            f"Idea: {self.config.business.idea}\n"
            f"ICP: {answers['icp']}\n"
            f"Problem: {answers['problem']}\n"
            f"Competitor name: {candidate.get('name', 'Unknown')}\n"
            f"Competitor type: {candidate.get('type', 'indirect')}\n"
            f"Competitor domain: {candidate.get('domain', '')}\n"
            f"Pricing hint: {candidate.get('pricing', 'Desconhecido')}\n"
            f"Evidence count: {candidate.get('evidence_count', 0)}\n"
            f"Evidence URLs: {json.dumps(candidate.get('evidence_urls', []), ensure_ascii=False)}\n"
            f"Evidence snippets: {json.dumps(candidate.get('evidence_snippets', []), ensure_ascii=False)}\n"
            "Return strict JSON only."
        )
        stage_name = f"competitor_analyst_{str(candidate.get('name', 'unknown')).lower().replace(' ', '_')}"
        self._record_prompt(stage_name, COMPETITOR_ANALYST_PROMPT, prompt)
        try:
            if self.client.is_configured():
                raw = self.client.complete(COMPETITOR_ANALYST_PROMPT, prompt)
                self._record_response(stage_name, raw)
                parsed = self._parse_competitor_analysis_json(raw)
                if parsed:
                    result = {
                        "name": str(candidate.get("name", "Unknown")),
                        "type": str(candidate.get("type", "indirect")),
                        "positioning": str(parsed.get("positioning") or fallback["positioning"]),
                        "strengths": str(parsed.get("strengths") or fallback["strengths"]),
                        "weaknesses": str(parsed.get("weaknesses") or fallback["weaknesses"]),
                        "pricing": str(candidate.get("pricing", "Desconhecido")),
                        "evidence": str(candidate.get("evidence", "")),
                        "analysis_status": str(parsed.get("analysis_status") or "analyzed"),
                        "analysis_source": "competitor_analyst_agent",
                        "evidence_count": str(candidate.get("evidence_count", 0)),
                        "evidence_excerpt": str(candidate.get("evidence_excerpt", "")),
                        "confidence": str(parsed.get("confidence") or "medium"),
                    }
                    if result["analysis_status"] not in {"analyzed", "fallback"}:
                        result["analysis_status"] = "analyzed"
                    return result
        except LLMError as exc:
            self._record_response(stage_name, f"LLM_ERROR: {exc}")
        return fallback

    def _parse_competitor_analysis_json(self, raw: str) -> dict[str, Any] | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        candidates = [raw]
        if "```json" in raw:
            candidates.append(raw.split("```json", 1)[1].split("```", 1)[0].strip())
        elif "```" in raw:
            candidates.append(raw.split("```", 1)[1].split("```", 1)[0].strip())
        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                start = candidate.find("{")
                end = candidate.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        data = json.loads(candidate[start:end + 1])
                    except json.JSONDecodeError:
                        continue
                else:
                    continue
            if isinstance(data, dict):
                return data
        return None

    def _fallback_competitor_analysis(self, candidate: dict[str, Any]) -> dict[str, str]:
        snippets = list(candidate.get("evidence_snippets", []))
        domain = str(candidate.get("domain", ""))
        joined = " ".join(snippets).lower()
        positioning = GENERIC_POSITIONING_FALLBACK
        if any(tok in joined for tok in ["supplier", "fornecedor", "fornecedores"]):
            positioning = "Plataforma focada em fornecedores, cadastro e relacionamento operacional."
        elif any(tok in joined for tok in ["third party", "terceiros", "vendor risk"]):
            positioning = "Solução voltada à gestão e avaliação de risco de terceiros."
        elif any(tok in joined for tok in ["due diligence", "background check"]):
            positioning = "Ferramenta de due diligence e verificação de terceiros."
        elif any(tok in joined for tok in ["onboarding", "homolog"]):
            positioning = "Ferramenta de onboarding, homologação e coleta documental de fornecedores."
        strengths = GENERIC_STRENGTHS_FALLBACK
        if snippets:
            signals = []
            if any(tok in joined for tok in ["compliance", "risk", "risco", "due diligence"]):
                signals.append("há sinais de foco em risco/compliance")
            if any(tok in joined for tok in ["onboarding", "homolog", "document", "cadastro"]):
                signals.append("endereça onboarding documental")
            if any(tok in joined for tok in ["platform", "plataforma", "portal", "software", "saas"]):
                signals.append("parece ter proposta clara de software B2B")
            if signals:
                strengths = "Pelas evidências agregadas, parece forte porque " + "; ".join(signals[:3]) + "."
        weaknesses = GENERIC_WEAKNESSES_FALLBACK
        concerns = []
        if not any(tok in joined for tok in ["pricing", "preço", "r$", "usd", "/mês", "per month"]):
            concerns.append("pricing não apareceu de forma clara")
        if not any(tok in joined for tok in ["security", "segurança", "risk", "risco", "tprm", "due diligence"]):
            concerns.append("a profundidade específica do motor de risco não ficou comprovada")
        if str(candidate.get("type", "indirect")) != "direct":
            concerns.append("a aderência ao caso central parece parcial")
        if any(k in domain for k in ["sap", "ariba", "coupa", "softexpert"]):
            concerns.append("pode ser enterprise demais para operações mais enxutas")
        if concerns:
            weaknesses = "Possíveis fragilidades: " + "; ".join(concerns[:3]) + "."
        status = "analyzed" if snippets else "fallback"
        return {
            "name": str(candidate.get("name", "Unknown")),
            "type": str(candidate.get("type", "indirect")),
            "positioning": positioning,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "pricing": str(candidate.get("pricing", "Desconhecido")),
            "evidence": str(candidate.get("evidence", "")),
            "analysis_status": status,
            "analysis_source": "competitor_analyst_fallback",
            "evidence_count": str(candidate.get("evidence_count", 0)),
            "evidence_excerpt": str(candidate.get("evidence_excerpt", "")),
            "confidence": "medium" if snippets else "low",
        }

    def _generate_plan(self, answers, evidence, synthesis, persona_critiques, tenth_man_report) -> str:
        evidence_lines = [f"{item.title} — {item.url} — {item.snippet}" for item in evidence[: self.config.runtime.prompt_evidence_limit]]
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
        self._record_prompt("plan_draft", SYSTEM_PROMPT, prompt)
        try:
            if self.client.is_configured():
                result = self.client.complete(SYSTEM_PROMPT, prompt)
                self._record_response("plan_draft", result)
                return result
        except LLMError as exc:
            self._record_response("plan_draft", f"LLM_ERROR: {exc}")
        result = self._fallback_plan(answers, evidence, synthesis, persona_critiques, tenth_man_report)
        self._record_response("plan_draft", result)
        return result

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
        stage_name = f"revision_round_{round_idx}"
        self._record_prompt(stage_name, REVISION_PROMPT, revision_input)
        try:
            if self.client.is_configured():
                result = self.client.complete(REVISION_PROMPT, revision_input)
                self._record_response(stage_name, result)
                return result
        except LLMError as exc:
            self._record_response(stage_name, f"LLM_ERROR: {exc}")
        result = plan + "\n\n---\n\n## Internal critique adjustments\n\n" + critique
        self._record_response(stage_name, result)
        return result

    def _run_persona_critiques(self, answers, evidence, synthesis) -> dict[str, Any]:
        niche = self._infer_niche(answers)
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(self.PERSONAS), self.config.runtime.parallel_workers)) as executor:
            future_map = {
                executor.submit(self._run_persona_agent, persona, niche, answers, evidence, synthesis): persona
                for persona in self.PERSONAS
            }
            for future in as_completed(future_map):
                persona = future_map[future]
                memo = future.result()
                results[persona] = {"persona": persona, "memo": memo}
        return results

    def _run_tenth_man(self, answers, evidence, synthesis, persona_critiques) -> dict[str, Any]:
        pro_agents = []
        with ThreadPoolExecutor(max_workers=min(self.config.runtime.pro_agent_count, self.config.runtime.parallel_workers)) as executor:
            future_map = {
                executor.submit(self._run_pro_agent, idx, answers, evidence, synthesis, persona_critiques): idx
                for idx in range(1, self.config.runtime.pro_agent_count + 1)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                memo = future.result()
                pro_agents.append({"agent": f"pro_{idx}", "memo": memo})
        pro_agents.sort(key=lambda x: x["agent"])
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
        stage_name = "master_critique"
        system = master_critique_prompt()
        self._record_prompt(stage_name, system, prompt)
        try:
            if self.client.is_configured():
                result = self.client.complete(system, prompt)
                self._record_response(stage_name, result)
                return result
        except LLMError as exc:
            self._record_response(stage_name, f"LLM_ERROR: {exc}")
        result = self._fallback_master_critique(persona_critiques, tenth_memo)
        self._record_response(stage_name, result)
        return result

    def _infer_business_archetype(self, answers: dict[str, str]) -> str:
        text = " ".join([self.config.business.idea, self.config.business.business_model_hint, *answers.values()]).lower()
        if any(tok in text for tok in ["saas", "software", "dashboard", "platform", "plataforma", "api", "workflow"]):
            return "saas"
        if any(tok in text for tok in ["consultoria", "agency", "service", "serviço", "fração", "outsourcing"]):
            return "services"
        if any(tok in text for tok in ["marketplace", "take rate", "seller", "buyer", "comissão"]):
            return "marketplace"
        if any(tok in text for tok in ["sacolé", "geladinho", "picolé", "food", "beverage", "cafeteria", "sorvete", "sobremesa", "restaurant"]):
            return "food_beverage"
        if any(tok in text for tok in ["marca", "ecommerce", "d2c", "retail", "consumer", "produto físico"]):
            return "consumer_brand"
        return "other"

    def _build_financial_model(self, answers, synthesis, competition, persona_critiques, tenth_man_report) -> dict[str, Any]:
        archetype = self._infer_business_archetype(answers)
        fallback = self._fallback_financial_model(answers, archetype)
        prompt = (
            f"Idea: {self.config.business.idea}\n"
            f"Region: {self.config.business.region}\n"
            f"Currency: {self.config.business.currency}\n"
            f"Business archetype: {archetype}\n"
            f"Founder answers: {json.dumps(answers, ensure_ascii=False)}\n"
            f"Synthesis: {json.dumps(synthesis, ensure_ascii=False)}\n"
            f"Competition: {json.dumps((competition or {}).get('competitors', []), ensure_ascii=False)}\n"
            f"Persona critiques: {json.dumps(persona_critiques, ensure_ascii=False)}\n"
            f"10th man: {json.dumps(tenth_man_report, ensure_ascii=False)}\n"
            f"Fallback model: {json.dumps(fallback, ensure_ascii=False)}\n"
            "Return strict JSON only."
        )
        stage_name = "financial_model_agent"
        self._record_prompt(stage_name, FINANCIAL_MODEL_PROMPT, prompt)
        try:
            if self.client.is_configured():
                raw = self.client.complete(FINANCIAL_MODEL_PROMPT, prompt)
                self._record_response(stage_name, raw)
                parsed = self._parse_competitor_analysis_json(raw)
                normalized = self._normalize_financial_model(parsed, fallback)
                if normalized:
                    return normalized
        except LLMError as exc:
            self._record_response(stage_name, f"LLM_ERROR: {exc}")
        self._record_response(stage_name, json.dumps(fallback, ensure_ascii=False))
        return fallback

    def _normalize_financial_model(self, parsed: dict[str, Any] | None, fallback: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(parsed, dict):
            return None
        rows = parsed.get("rows")
        if not isinstance(rows, list) or len(rows) != 12:
            return None
        normalized_rows = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                return None
            try:
                customers_or_orders = int(float(row.get("customers_or_orders", 0)))
                avg_ticket_or_arpa = round(float(row.get("avg_ticket_or_arpa", 0)), 2)
                revenue = round(float(row.get("revenue", 0)), 2)
                cogs = round(float(row.get("cogs", 0)), 2)
                gross_profit = round(float(row.get("gross_profit", revenue - cogs)), 2)
                opex = round(float(row.get("opex", 0)), 2)
                cash_flow = round(float(row.get("cash_flow", gross_profit - opex)), 2)
            except Exception:
                return None
            normalized_rows.append({
                "month": idx,
                "customers_or_orders": customers_or_orders,
                "avg_ticket_or_arpa": avg_ticket_or_arpa,
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": gross_profit,
                "opex": opex,
                "cash_flow": cash_flow,
                "notes": str(row.get("notes", "")).strip(),
            })
        return {
            "business_archetype": str(parsed.get("business_archetype") or fallback["business_archetype"]),
            "assumptions": parsed.get("assumptions") or fallback["assumptions"],
            "rows": normalized_rows,
        }

    def _build_financial_intelligence(self, finance_model: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback_financial_intelligence(finance_model)
        prompt = (
            f"Business archetype: {finance_model.get('business_archetype', 'other')}\n"
            f"Assumptions: {json.dumps(finance_model.get('assumptions', {}), ensure_ascii=False)}\n"
            f"Rows: {json.dumps(finance_model.get('rows', []), ensure_ascii=False)}\n"
            "Return strict JSON only."
        )
        stage_name = "financial_intelligence_agent"
        self._record_prompt(stage_name, FINANCIAL_INTELLIGENCE_PROMPT, prompt)
        try:
            if self.client.is_configured():
                raw = self.client.complete(FINANCIAL_INTELLIGENCE_PROMPT, prompt)
                self._record_response(stage_name, raw)
                parsed = self._parse_competitor_analysis_json(raw)
                if isinstance(parsed, dict) and parsed.get("intelligence_paragraph") and isinstance(parsed.get("recommendations"), list):
                    return {
                        "intelligence_paragraph": str(parsed.get("intelligence_paragraph")).strip(),
                        "recommendations": [str(x).strip() for x in parsed.get("recommendations", []) if str(x).strip()][:5],
                        "analysis_source": "financial_intelligence_agent",
                    }
        except LLMError as exc:
            self._record_response(stage_name, f"LLM_ERROR: {exc}")
        self._record_response(stage_name, json.dumps(fallback, ensure_ascii=False))
        return fallback

    def _fallback_financial_intelligence(self, finance_model: dict[str, Any]) -> dict[str, Any]:
        rows = finance_model.get("rows", [])
        if not rows:
            return {
                "intelligence_paragraph": "O modelo financeiro ainda não possui dados suficientes para análise.",
                "recommendations": ["Revisar premissas básicas do modelo financeiro."],
                "analysis_source": "financial_intelligence_fallback",
            }
        first = rows[0]
        last = rows[-1]
        avg_margin = 0
        if rows:
            margins = []
            for row in rows:
                revenue = float(row.get("revenue", 0) or 0)
                gross = float(row.get("gross_profit", 0) or 0)
                margins.append((gross / revenue) if revenue > 0 else 0)
            avg_margin = sum(margins) / len(margins)
        paragraph = (
            f"O modelo sugere um negócio do tipo {finance_model.get('business_archetype', 'other')} com crescimento de volume de "
            f"{first.get('customers_or_orders', 0)} para {last.get('customers_or_orders', 0)} no horizonte de 12 meses. "
            f"A margem bruta média implícita fica em torno de {round(avg_margin * 100, 1)}%, enquanto o fluxo de caixa mensal sai de "
            f"{first.get('cash_flow', 0)} para {last.get('cash_flow', 0)}. Isso indica que a principal restrição financeira está em "
            f"equilibrar crescimento comercial com disciplina de custos antes do break-even."
        )
        recs = [
            "Reduzir ou segurar opex fixo até validar demanda recorrente com margem bruta saudável.",
            "Testar aumento de ticket médio e mix de produtos/planos antes de acelerar aquisição paga.",
            "Acompanhar margem bruta e payback mensalmente para decidir o momento de expandir operação.",
        ]
        return {
            "intelligence_paragraph": paragraph,
            "recommendations": recs,
            "analysis_source": "financial_intelligence_fallback",
        }

    def _render_financial_analysis_markdown(self, analysis: dict[str, Any]) -> str:
        lines = ["# Financial Intelligence", "", analysis.get("intelligence_paragraph", ""), "", "## Recommendations"]
        for item in analysis.get("recommendations", []):
            lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    def _fallback_financial_model(self, answers: dict[str, str], archetype: str) -> dict[str, Any]:
        if archetype == "food_beverage":
            tickets = [7, 7.2, 7.2, 7.5, 7.5, 7.8, 7.8, 8, 8, 8.2, 8.2, 8.5]
            orders = [180, 260, 340, 420, 520, 620, 720, 820, 920, 1020, 1120, 1250]
            cogs_ratio = 0.38
            opex_base = 6500
            notes = "food_beverage model based on order volume, average ticket, production/logistics COGS, and lean local operations"
            revenue_model = "pedido × ticket médio"
            pricing_logic = "ticket médio por unidade/combos e pequenos canais de revenda"
            unit_logic = "margem bruta depende de insumos, embalagem, perdas e entrega"
            cost_drivers = ["ingredientes", "embalagem", "logística fria", "mão de obra operacional", "eventos/revenda"]
        elif archetype == "consumer_brand":
            tickets = [90, 92, 94, 96, 98, 100, 102, 104, 106, 108, 110, 112]
            orders = [25, 35, 45, 60, 75, 90, 105, 120, 140, 160, 180, 210]
            cogs_ratio = 0.42
            opex_base = 12000
            notes = "consumer_brand model based on orders, average order value, inventory COGS, and marketing-heavy opex"
            revenue_model = "pedidos × ticket médio"
            pricing_logic = "ticket por pedido com mix entre produto principal e upsell"
            unit_logic = "margem bruta depende de produto, frete subsidiado e devoluções"
            cost_drivers = ["CMV", "frete", "performance marketing", "embalagem", "estoque"]
        elif archetype == "services":
            tickets = [3500, 3500, 4000, 4000, 4500, 4500, 5000, 5000, 5500, 5500, 6000, 6000]
            orders = [1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7]
            cogs_ratio = 0.1
            opex_base = 18000
            notes = "services model based on active clients and average monthly contract value"
            revenue_model = "clientes ativos × ticket mensal"
            pricing_logic = "retainer/projeto com expansão gradual de ticket"
            unit_logic = "COGS baixo; margem depende mais de horas da equipe"
            cost_drivers = ["mão de obra", "vendas", "ferramentas", "viagens/projetos"]
        else:
            tickets = [1200, 1200, 1200, 1500, 1500, 1800, 1800, 2000, 2200, 2400, 2600, 2800]
            orders = [1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18]
            cogs_ratio = 0.12 if archetype == "saas" else 0.2
            opex_base = 35000 if archetype == "saas" else 20000
            notes = f"{archetype} fallback model"
            revenue_model = "clientes × ticket"
            pricing_logic = "ARPA/ticket crescente com prova de valor"
            unit_logic = "margem depende do modelo operacional e aquisição"
            cost_drivers = ["pessoas", "aquisição", "ferramentas", "operação"]
        rows=[]
        for month, volume in enumerate(orders, start=1):
            avg_ticket=tickets[month-1]
            revenue=round(volume*avg_ticket,2)
            cogs=round(revenue*cogs_ratio,2)
            gross_profit=round(revenue-cogs,2)
            opex=round(opex_base + (month-1)* (250 if archetype in {"food_beverage","consumer_brand"} else 500),2)
            cash_flow=round(gross_profit-opex,2)
            rows.append({
                "month": month,
                "customers_or_orders": volume,
                "avg_ticket_or_arpa": avg_ticket,
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": gross_profit,
                "opex": opex,
                "cash_flow": cash_flow,
                "notes": notes,
            })
        return {
            "business_archetype": archetype,
            "assumptions": {
                "revenue_model": revenue_model,
                "pricing_logic": pricing_logic,
                "unit_economics_logic": unit_logic,
                "main_cost_drivers": cost_drivers,
            },
            "rows": rows,
        }

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

    def _write_financial_exports(self, exports_dir: Path, rows: list[dict[str, Any]]) -> None:
        fieldnames = ["month", "customers_or_orders", "avg_ticket_or_arpa", "revenue", "cogs", "gross_profit", "opex", "cash_flow", "notes"]
        csv_path = exports_dir / "financial_model.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        tsv_path = exports_dir / "financial_model.xlsx-ready.tsv"
        with tsv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    def _write_competitor_exports(self, exports_dir: Path, competitors: list[dict[str, str]]) -> None:
        csv_path = exports_dir / "competitor_matrix.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["name", "type", "positioning", "strengths", "weaknesses", "pricing", "evidence", "analysis_status", "analysis_source", "evidence_count", "evidence_excerpt", "confidence"])
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
                f"- Status da análise: {competitor.get('analysis_status', 'unknown')}",
                f"- Fonte da análise: {competitor.get('analysis_source', 'unknown')}",
                f"- Evidências agregadas: {competitor.get('evidence_count', '0')}",
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
        evidence_md = "\n".join(f"- {e.title}: {e.url}" for e in evidence[:5])
        persona_names = ", ".join(persona_critiques.keys())
        market_sizes = self._estimate_market_sizes(answers)
        tam, sam, som = market_sizes["tam"], market_sizes["sam"], market_sizes["som"]
        risk_summary = [
            "- Budget ownership and conversion remain unproven.",
            "- O risco principal é o ICP sentir a dor, mas não pagar recorrência.",
            "- O MVP precisa provar time-to-value e confiabilidade rapidamente.",
        ]
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
- 10th-man summary:
{chr(10).join(risk_summary)}

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
        problem = answers['problem']
        icp = answers['icp']
        current = answers['current_solution']
        why_now = answers['why_now']
        advantage = answers['advantage']
        mvp = answers['mvp']
        first_10 = answers['first_10_customers']
        if persona == "investor":
            return (
                f"# Investor memo\n"
                f"- Strongest concerns: o mercado pode até sentir a dor `{problem}`, mas ainda faltar evidência de ticket, retenção e eficiência comercial no ICP `{icp}`.\n"
                f"- Strongest positives: o founder tem uma tese de vantagem defensável (`{advantage}`) e existe uma alternativa ruim/status quo (`{current}`).\n"
                f"- Missing evidence: payback do canal inicial, taxa de conversão para pago e potencial de expansão além do MVP `{mvp}`.\n"
                f"- Verdict: CONDITIONAL GO.\n"
                f"- Next experiments: validar willingness-to-pay, churn inicial e economics dos primeiros 10 clientes via `{first_10}`.\n"
            )
        if persona == "potential client":
            return (
                f"# Potential client memo\n"
                f"- Strongest concerns: quero saber se `{mvp}` realmente resolve meu fluxo sem me gerar retrabalho, especialmente porque hoje eu já faço `{current}`.\n"
                f"- Strongest positives: a proposta ataca uma dor operacional concreta: `{problem}`.\n"
                f"- Missing evidence: tempo economizado por semana, confiabilidade da automação e clareza de suporte/onboarding.\n"
                f"- Verdict: interessado, mas só pago se o ganho de tempo for óbvio.\n"
                f"- Next experiments: pilotos curtos com métrica de tempo poupado e redução de fricção operacional.\n"
            )
        if persona == "salesman":
            return (
                f"# Sales memo\n"
                f"- Strongest concerns: a mensagem ainda pode soar ampla demais para `{icp}` e a urgência precisa estar ancorada em `{why_now}`.\n"
                f"- Strongest positives: existe um wedge comercial claro se o pitch ficar centrado em economia de tempo e eliminação de trabalho manual.\n"
                f"- Missing evidence: objeções dominantes, copy que converte e taxa real de indicação a partir de `{first_10}`.\n"
                f"- Verdict: vendável se a promessa comercial for extremamente específica.\n"
                f"- Next experiments: testar 3 versões de pitch, registrar objeções e comparar conversão por sub-ICP.\n"
            )
        return (
            f"# Expert memo ({niche})\n"
            f"- Strongest concerns: no nicho {niche}, a solução precisa se encaixar no fluxo real do usuário e não apenas parecer elegante no papel.\n"
            f"- Strongest positives: a tese de produto parece pragmaticamente conectada ao problema `{problem}`.\n"
            f"- Missing evidence: benchmark contra status quo (`{current}`), cobertura de edge cases e estabilidade operacional do MVP `{mvp}`.\n"
            f"- Verdict: tecnicamente plausível, mas ainda precisa provar aderência de fluxo.\n"
            f"- Next experiments: validar os 5 cenários operacionais mais críticos do nicho e comparar erro humano vs automação.\n"
        )

    def _fallback_pro_memo(self, idx, answers):
        themes = [
            "frequência da dor",
            "economia de tempo",
            "vantagem do founder",
            "clareza do MVP",
            "canal inicial de aquisição",
            "potencial de indicação",
            "adequação de preço",
            "simplicidade operacional",
            "aprendizado rápido com pilotos",
        ]
        theme = themes[(idx - 1) % len(themes)]
        lines = {
            "frequência da dor": f"- O problema `{answers['problem']}` é recorrente e tende a gerar fricção semanal no ICP.",
            "economia de tempo": f"- O ganho econômico é legível porque `{answers['payment_reason']}`.",
            "vantagem do founder": f"- O founder traz uma vantagem concreta: `{answers['advantage']}`.",
            "clareza do MVP": f"- Há um wedge inicial claro: `{answers['mvp']}`.",
            "canal inicial de aquisição": f"- Existe um caminho plausível para os primeiros clientes: `{answers['first_10_customers']}`.",
            "potencial de indicação": f"- Se o MVP funcionar, o canal de boca a boca pode acelerar adoção no ICP `{answers['icp']}`.",
            "adequação de preço": f"- A tese de preço ganha força porque `{answers['why_now']}` aponta espaço para uma opção mais acessível.",
            "simplicidade operacional": f"- A solução pode vencer por simplicidade porque hoje o status quo é `{answers['current_solution']}`.",
            "aprendizado rápido com pilotos": f"- O critério de sucesso inicial (`{answers['early_success']}`) permite aprender rápido e iterar cedo.",
        }
        return (
            f"# Pro agent {idx}\n"
            f"1. Strongest success arguments\n"
            f"{lines[theme]}\n"
            f"- Se a tese principal se sustentar, o produto melhora um fluxo operacional que já existe.\n"
            f"\n2. Key enabling assumptions\n"
            f"- O ICP percebe valor antes de exigir feature sprawl.\n"
            f"- O onboarding para o MVP `{answers['mvp']}` é simples o suficiente para não matar adoção.\n"
            f"\n3. How to increase odds of success\n"
            f"- Explorar explicitamente a frente de `{theme}` como argumento comercial e métrica de produto.\n"
            f"\n4. Confidence level\nModerate\n\n5. Provisional verdict\nCONDITIONAL GO\n"
        )

    def _fallback_tenth_man_memo(self, answers):
        return (
            f"# 10th Man Dissent Memo\n\n"
            f"1. Strongest failure case\n"
            f"- A dor existe, mas pode não ser forte o suficiente para deslocar o comportamento atual (`{answers['current_solution']}`) nem justificar pagamento recorrente.\n\n"
            f"2. Where the 9 pro agents may be fooling themselves\n"
            f"- Eles podem estar assumindo que entender a dor (`{answers['advantage']}`) equivale a ter product-market fit.\n"
            f"- Eles podem estar superestimando a qualidade do canal inicial descrito em `{answers['first_10_customers']}`.\n\n"
            f"3. Failure modes\n"
            f"- Market: o ICP `{answers['icp']}` sente a dor, mas não prioriza orçamento.\n"
            f"- Product: o MVP `{answers['mvp']}` não cobre exceções básicas e quebra confiança.\n"
            f"- GTM: há interesse, mas pouco compromisso pago ou baixa indicação.\n"
            f"- Financial: o ticket real fica abaixo do necessário para sustentar suporte e evolução.\n"
            f"- Execution: falta velocidade para iterar em cima dos riscos declarados (`{answers['killer_risks']}`).\n\n"
            f"4. Early warning indicators\n"
            f"- Usuários gostam da ideia, mas continuam no processo manual.\n"
            f"- O founder precisa operar manualmente demais para entregar valor.\n"
            f"- Os primeiros usuários não indicam novos clientes.\n"
            f"- O feedback positivo não vira renovação ou expansão.\n\n"
            f"5. What evidence would prove this wrong\n"
            f"- Pagamento recorrente real, uso consistente e prova de economia de tempo ou redução de fricção.\n\n"
            f"6. Final dissent verdict\n"
            f"NO-GO until real buying behavior is observed.\n"
        )

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

    def _record_prompt(self, stage_name: str, system: str, user: str) -> None:
        if not getattr(self.config.runtime, "persist_full_prompts", True):
            return
        run_dir = getattr(self, "current_run_dir", None)
        if not run_dir:
            return
        prompt_dir = Path(run_dir) / "prompts"
        prompt_dir.mkdir(exist_ok=True)
        payload = {
            "stage": stage_name,
            "system": system,
            "user": user,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        (prompt_dir / f"{stage_name}.prompt.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _record_response(self, stage_name: str, response_text: str) -> None:
        if not getattr(self.config.runtime, "persist_full_prompts", True):
            return
        run_dir = getattr(self, "current_run_dir", None)
        if not run_dir:
            return
        prompt_dir = Path(run_dir) / "prompts"
        prompt_dir.mkdir(exist_ok=True)
        payload = {
            "stage": stage_name,
            "response": response_text,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        (prompt_dir / f"{stage_name}.response.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

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
