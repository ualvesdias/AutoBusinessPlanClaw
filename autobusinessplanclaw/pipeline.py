from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .llm import OpenAICompatibleClient
from .models import ABCConfig, EvidenceItem
from .prompts import SYSTEM_PROMPT, planning_prompt
from .research import build_market_queries


class Pipeline:
    def __init__(self, config: ABCConfig):
        self.config = config
        self.client = OpenAICompatibleClient(config.llm)

    def run(self, answers: dict[str, str], web_search_fn=None, output_dir: str | None = None) -> Path:
        run_id = datetime.now().strftime("abc-%Y%m%d-%H%M%S")
        run_dir = Path(output_dir or Path(self.config.output.root) / run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        queries = build_market_queries(self.config.business.idea, answers)
        evidence: list[EvidenceItem] = []
        raw_research: list[dict] = []
        if self.config.runtime.allow_web_research and web_search_fn is not None:
            for query in queries:
                results = web_search_fn(query=query, count=self.config.runtime.max_web_results)
                raw_research.append({"query": query, "results": results})
                for item in results:
                    evidence.append(EvidenceItem(**asdict(item) if hasattr(item, "__dataclass_fields__") else item))

        evidence_lines = [f"{item.title} — {item.url} — {item.snippet}" for item in evidence[:20]]
        plan_markdown = self.client.complete(
            SYSTEM_PROMPT,
            planning_prompt(
                self.config.business.idea,
                answers,
                evidence_lines,
                self.config.business.currency,
                self.config.business.region,
            ),
        )

        (run_dir / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "research_queries.json").write_text(json.dumps(queries, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "research_results.json").write_text(json.dumps(raw_research, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "business_plan.md").write_text(plan_markdown, encoding="utf-8")

        summary = {
            "idea": self.config.business.idea,
            "run_dir": str(run_dir),
            "queries": queries,
            "evidence_count": len(evidence_lines),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return run_dir
