# AutoBusinessPlanClaw Agent Guide

If you are an OpenClaw-compatible agent helping a founder:

## Mission
Turn a founder idea into a rigorous business plan, not fluffy startup fanfiction.

## Required workflow
1. Ask for or collect the 10 required founder answers.
2. Write them into a questionnaire file.
3. Confirm config has the target idea, region, and currency.
4. Run `businessclaw run --config ... --answers ...`.
5. Return the generated artifact path and summarize the business verdict.

## Preferred OpenClaw flow
- Use the main session for discovery questions.
- Use an ACP/session run if you want isolated long-running generation.
- Use web research when available; otherwise mark claims as assumptions.
- Save important founder preferences and business context in workspace memory.
- If asked for reminders or follow-ups, create cron reminders with explicit business context.

## Quality bar
- Be skeptical.
- Surface assumptions explicitly.
- Prefer evidence over optimism.
- Distinguish founder claims from market evidence.
- End with a clear go / no-go style recommendation.

## When evidence is weak
Do not fake certainty. Recommend the next validation experiments instead.
