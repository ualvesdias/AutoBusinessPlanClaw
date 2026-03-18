<h2 align="center"><b>Chat an Idea. Get a Business Plan. Multi-Agent, Runnable, Exportable.</b></h2>

<p align="center">
  <b><i><font size="5">Just chat with <a href="#openclaw-integration">OpenClaw</a>: "Create a business plan for X" → done.</font></i></b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="#testing"><img src="https://img.shields.io/badge/Tests-19%20passed-brightgreen?logo=pytest&logoColor=white" alt="19 Tests Passed"></a>
  <a href="https://github.com/ualvesdias/AutoBusinessPlanClaw"><img src="https://img.shields.io/badge/GitHub-AutoBusinessPlanClaw-181717?logo=github" alt="GitHub"></a>
  <a href="#openclaw-integration"><img src="https://img.shields.io/badge/OpenClaw-Compatible-ff4444" alt="OpenClaw Compatible"></a>
</p>

<p align="center">
  <a href="docs/ARCHITECTURE.md">🏗️ Architecture</a> · <a href="docs/OPENCLAW_RUNBOOK.md">🦞 OpenClaw Runbook</a>
</p>

---

## ⚡ One Command. One Plan.

```bash
pip install -e . && businessclaw run --config config.businessclaw.yaml --answers questionnaire.json
```

---

## 🤔 What Is This?

**You describe the business. AutoBusinessPlanClaw builds the plan.**

Drop a startup idea plus a short founder questionnaire — get back a complete business-plan package with market research, competitor mapping, multi-agent critique, 10th-man risk analysis, financial exports, GTM experiments, HTML output, and an Obsidian vault.

<table>
<tr><td>📄</td><td><code>business_plan.md</code></td><td>Full business plan draft with positioning, risks, GTM, and operating model</td></tr>
<tr><td>🔎</td><td><code>research_queries.json</code></td><td>Structured market and competition search queries</td></tr>
<tr><td>🌐</td><td><code>research_results.json</code></td><td>Raw research batches from web-backed discovery</td></tr>
<tr><td>🏁</td><td><code>competitor_matrix.json</code></td><td>Structured competitor inventory for the idea</td></tr>
<tr><td>🧭</td><td><code>competitor_reference_table.json</code></td><td>Cross-reference table comparing your idea vs. competitors</td></tr>
<tr><td>🧠</td><td><code>persona_critiques.json</code></td><td>Investor / client / sales / expert critiques</td></tr>
<tr><td>⚔️</td><td><code>tenth_man_report.json</code></td><td>9-pro / 1-dissent debate and master critique</td></tr>
<tr><td>💸</td><td><code>exports/financial_model.csv</code></td><td>Financial model for spreadsheet use</td></tr>
<tr><td>📈</td><td><code>exports/financial_analysis.md</code></td><td>Financial intelligence paragraph and recommendations</td></tr>
<tr><td>📣</td><td><code>exports/gtm_experiments.md</code></td><td>GTM test plan and experiment ideas</td></tr>
<tr><td>🖥️</td><td><code>exports/report.html</code></td><td>Structured HTML report with collapsible sections</td></tr>
<tr><td>🪨</td><td><code>exports/obsidian-vault/</code></td><td>Obsidian-ready export with notes, MOC and canvas</td></tr>
</table>

The pipeline is designed to be **inspectable, resumable, and OpenClaw-friendly**. Each stage writes artifacts. Each run can be resumed. Each export can be reviewed without digging into prompts. The competition stage now includes a dedicated per-competitor analyst pass plus a quality gate, so weak evidence is surfaced as incomplete instead of being disguised as confident analysis.

---

## 🚀 Quick Start

```bash
# 1. Clone & install
git clone https://github.com/ualvesdias/AutoBusinessPlanClaw.git
cd AutoBusinessPlanClaw
python3 -m pip install virtualenv
python3 -m virtualenv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure
cp config.businessclaw.example.yaml config.businessclaw.yaml
cp examples/questionnaire.example.json questionnaire.json
# Edit config.businessclaw.yaml and questionnaire.json

# 3. Run
export OPENAI_API_KEY="sk-..."
export OPENCLAW_GATEWAY_TOKEN="..."  # preferred when running through OpenClaw gateway
export XAI_API_KEY="xai-..."  # optional, tertiary web-search fallback
businessclaw run --config config.businessclaw.yaml --answers questionnaire.json
```

Output → `runs/abc-YYYYMMDD-HHMMSS/` — plan, research, critiques, financials, HTML, and optional Obsidian vault.

<details>
<summary>📝 Minimum required config</summary>

```yaml
project:
  name: "my-business-plan"

business:
  idea: "AI scheduling assistant for solo professionals"
  region: "Brasil"
  currency: "BRL"

llm:
  provider: "auto"
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  model: "gpt-4o-mini"

runtime:
  allow_web_research: true
  critique_rounds: 1

output:
  root: "runs"
```

</details>

---

## 🧠 What Makes It Different

| Capability | How It Works |
|-----------|-------------|
| **🧩 Staged Pipeline** | 12 explicit stages, each with artifacts, checkpoints, resumability, and stage-level quality metadata |
| **🤖 Multi-Agent Critique** | Investor, potential client, salesman, and expert personas challenge the plan from different angles |
| **⚔️ 10th-Man Protocol** | 9 pro agents argue the case for success, 1 dissenting agent argues the strongest credible failure case |
| **🌐 Web-Aware Research** | OpenClaw/xAI/OpenAI-compatible research path with deterministic fallback when web is unavailable |
| **🪨 Obsidian Export** | Full vault export with MOC, markdown notes, and canvas for further iteration |
| **🖥️ Reviewable HTML** | Human-readable report for quick inspection and sharing |

---

## 🦞 OpenClaw Integration

**AutoBusinessPlanClaw is an OpenClaw-compatible project.** You can use it standalone as a CLI tool, or hand the repo to OpenClaw and let it orchestrate the entire business-plan run conversationally.

### 🚀 Use with OpenClaw (Recommended)

If you already use OpenClaw as your assistant:

```text
1️⃣ Share the repo URL with OpenClaw
2️⃣ OpenClaw reads AUTOBUSINESSPLANCLAW_AGENTS.md
3️⃣ You describe the business idea
4️⃣ OpenClaw fills the questionnaire, runs the pipeline, and returns outputs
```

**That’s it.** OpenClaw can guide config, collect founder input, execute the run, and return the HTML/vault/financial outputs.

<details>
<summary>💡 What happens under the hood</summary>

1. OpenClaw reads `AUTOBUSINESSPLANCLAW_AGENTS.md`
2. It loads the project structure and runbook
3. It prepares config and questionnaire files
4. It validates runtime with `businessclaw doctor`
5. It runs the pipeline and returns artifacts

</details>

### 🔌 OpenClaw Workflow Files

See:
- `AUTOBUSINESSPLANCLAW_AGENTS.md`
- `docs/OPENCLAW_RUNBOOK.md`
- `docs/ARCHITECTURE.md`

---

## 🔬 Pipeline: 12 Stages

```text
1. intake
2. market_research
3. competition
4. synthesis
5. persona_critique
6. tenth_man
7. plan_draft
8. critique
9. revision
10. financials
11. gtm_pack
12. export
```

<details>
<summary>📋 What Each Stage Does</summary>

| Stage | What Happens |
|-------|-------------|
| **intake** | Loads the founder idea and validated questionnaire |
| **market_research** | Builds queries, runs web-backed discovery when available, stores raw evidence |
| **competition** | Extracts competitors, runs evidence-backed analysis per competitor, applies a quality gate, and generates comparison exports |
| **synthesis** | Summarizes findings into market, pain, GTM, pricing, and competition insights |
| **persona_critique** | Runs 4 critique personas against the current opportunity |
| **tenth_man** | Generates 9 pro-success memos, 1 dissent memo, and a master critique |
| **plan_draft** | Produces the first full plan draft |
| **critique** | Audits the current plan for weak logic and missing evidence |
| **revision** | Revises the plan based on critique rounds |
| **financials** | Runs a dedicated financial-modeling agent, normalizes a 12-month model, and falls back by business archetype when needed |
| **gtm_pack** | Builds GTM experiment suggestions and next actions |
| **export** | Writes summary metadata and final output package |

</details>

---

## ✨ Key Features

| Feature | Description |
|---------|------------|
| **🧾 Required Founder Questionnaire** | Uses 10 mandatory inputs so the plan is grounded in explicit founder assumptions |
| **📊 Competition Mapping** | Produces a competitor matrix, competitor reference table, per-competitor analyst output, and a quality gate that flags incomplete competitive intelligence |
| **🧠 Debate-Driven Risk Analysis** | The risk section is informed by personas + 10th-man dissent, not generic startup filler |
| **♻️ Resume Support** | Re-run safely with checkpoints and fresh-run directory cleanup |
| **🖥️ HTML + Markdown + CSV Exports** | Outputs are easy to inspect, share, and import into other tools |
| **🪨 Obsidian Export** | Generates a vault for long-form exploration and iteration |

---

## ⚙️ Configuration Reference

<details>
<summary>Click to expand configuration reference</summary>

```yaml
project:
  name: "my-business-plan"

business:
  idea: "..."
  region: "Brasil"
  currency: "BRL"

runtime:
  timezone: "America/Sao_Paulo"
  allow_web_research: true
  max_web_results: 5
  parallel_workers: 4
  critique_rounds: 1
  pro_agent_count: 9
  prompt_evidence_limit: 8

llm:
  provider: "auto"                # auto | openclaw-http | openai-compatible | none
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  model: "gpt-4o-mini"
  timeout_seconds: 45
  openclaw_base_url: "http://127.0.0.1:18789/v1"
  openclaw_api_key_env: "OPENCLAW_GATEWAY_TOKEN"
  openclaw_model: "openclaw:main"

output:
  root: "runs"
```

</details>

---

## 🧪 Testing

```bash
source .venv/bin/activate
python -m pytest -q
```

If you do not have `virtualenv` installed yet:

```bash
python3 -m pip install virtualenv
```

---

## 🙏 Acknowledgments

Inspired by:

- 🦞 [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) — pipeline structure and OpenClaw-first repo UX
- 🧠 Multi-agent critique / 10th-man decision frameworks for adversarial plan review
- 🪨 Obsidian-style knowledge packaging for inspectable outputs

---

## 📄 License

MIT — see `LICENSE` for details.

<p align="center">
  <sub>Built for founder workflows with 🦞</sub>
</p>


## Financial model agent
The financial stage now uses a dedicated financial-model agent. It first infers the business archetype (`saas`, `services`, `marketplace`, `consumer_brand`, `food_beverage`, or `other`), then asks the agent for a structured 12-month model. If the agent is unavailable or returns invalid JSON, the pipeline falls back to an archetype-specific model instead of a generic SaaS-shaped spreadsheet.
