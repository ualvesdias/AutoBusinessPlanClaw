from __future__ import annotations

from .questionnaire import REQUIRED_QUESTIONS

SYSTEM_PROMPT = """You are AutoBusinessPlanClaw, an elite startup strategy analyst.
Your job is to transform a founder idea and validated answers into a precise, evidence-aware, actionable business plan.
Rules:
- Be skeptical, specific, and commercially grounded.
- Distinguish facts, assumptions, and recommendations.
- If evidence is thin, say so clearly and propose validation steps.
- Avoid vague consultant filler.
- Produce execution-ready content.
"""

CRITIC_PROMPT = """You are the internal investment committee.
Critique the plan brutally but constructively.
Focus on weak assumptions, missing evidence, GTM gaps, pricing weaknesses, operational blind spots, financial nonsense, and unvalidated risks.
Return a concise markdown memo with:
1. Top 5 issues
2. What evidence is missing
3. What must change before approval
4. Current verdict: GO / CONDITIONAL GO / NO-GO
"""

REVISION_PROMPT = """Revise the business plan using the critique memo.
Keep what is strong, fix what is weak, and explicitly tighten assumptions, GTM, pricing, operations, and risk mitigation.
The result must still be a polished final business plan in markdown.
"""


def questionnaire_block(answers: dict[str, str]) -> str:
    lines = []
    for key, question in REQUIRED_QUESTIONS:
        lines.append(f"- {question}\n  Answer: {answers[key]}")
    return "\n".join(lines)


def evidence_block(evidence_lines: list[str]) -> str:
    if not evidence_lines:
        return "No external evidence was provided. Explicitly label assumptions and recommend validation steps."
    return "\n".join(f"- {line}" for line in evidence_lines)


def planning_prompt(idea: str, answers: dict[str, str], evidence_lines: list[str], currency: str, region: str) -> str:
    return f"""
Idea: {idea}
Region: {region}
Currency: {currency}

Founder questionnaire:
{questionnaire_block(answers)}

External evidence / market signals:
{evidence_block(evidence_lines)}

Generate a complete business plan in Markdown with these sections:
1. Executive summary
2. Problem definition and urgency
3. Ideal customer profile (ICP)
4. Market analysis (TAM / SAM / SOM with explicit estimation logic)
5. Competitive landscape (direct, indirect, status quo)
6. Value proposition and positioning
7. Product strategy (MVP, roadmap, differentiators)
8. Business model and pricing
9. Go-to-market plan (first 10 customers, first 100 customers, main channel, sales motion)
10. Operating model (team, delivery, tooling, support)
11. Financial model (12-month assumptions, revenue drivers, cost drivers, burn/runway commentary)
12. Risk register with mitigation experiments
13. 30/60 day action plan
14. Assumptions vs Evidence
15. Final verdict: GO / CONDITIONAL GO / NO-GO and why

Constraints:
- Use bullet points and short tables only when they improve clarity.
- Whenever you estimate a market number, show the formula or logic.
- Mention when an estimate is based on founder input vs external evidence.
- End with a brutally honest investment-style verdict.
""".strip()
