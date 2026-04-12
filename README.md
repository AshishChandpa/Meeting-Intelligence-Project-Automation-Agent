# Meeting Intelligence & Project Automation Agent

An AI-powered pipeline that converts client meeting transcripts into structured project execution — with a human approval gate at every stage. Upload a transcript and the system walks you through requirement extraction, clarification Q&A, Scope of Work drafting, sprint planning, and Jira sync.

---

## Pipeline Overview

```
Upload Transcript
      │
      ▼
Stage 1 — Parse & Extract
  AI extracts modules, requirements, integrations, constraints,
  assumptions, and unknowns with confidence scores.
  → Human reviews, corrects, then approves
      │
      ▼
Stage 2 — Clarification Loop
  AI generates targeted questions from gaps in the transcript.
  Human answers, skips, or asks their own questions.
  → Human marks done when satisfied
      │
      ▼
Stage 3 — Scope of Work
  AI drafts a full SoW using extraction + clarification answers.
  Human gives feedback, AI revises and shows a changelog.
  → Human approves final version (at least one feedback round required)
      │
      ▼
Stage 4 — Sprint Planning
  AI breaks SoW into tasks with story points, dependencies, and
  acceptance criteria. Organises into 2-week sprints (max 40pts).
  → Human adjusts plan, then approves
      │
      ▼
Stage 5 — Jira Sync
  Preview shown before any write. Creates Epics → Issues → Sprints.
  → Human confirms, live progress shown, summary with links on completion
```

Each stage is a distinct node in a LangGraph state machine. Nothing advances without an explicit human approval.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Orchestration | LangGraph (StateGraph with human-in-the-loop interrupts) |
| LLM (local) | Ollama — `llama3.2:3b` recommended on M4 Mac |
| LLM (cloud) | OpenAI / Anthropic / Gemini via LiteLLM (configurable) |
| Structured output | `langchain-ollama` with `with_structured_output()` |
| Jira integration | Atlassian REST API v3 + Agile API via `httpx` |
| State persistence | LangGraph built-in checkpointing (`.langgraph_api/`) |
| Dev UI | LangGraph Studio (`uv run langgraph dev`) |

---

## Project Structure

```
meeting-intelligence/
├── src/agent/
│   ├── config.py              # Settings loaded from .env
│   ├── llm.py                 # Ollama client with structured output
│   ├── jira.py                # Jira REST API client
│   ├── state.py               # Full pipeline state + Pydantic models
│   ├── graph.py               # LangGraph StateGraph (all 5 stages)
│   ├── nodes/
│   │   ├── parse.py           # Stage 1: transcript parsing + corrections
│   │   ├── clarify.py         # Stage 2: question generation + answers
│   │   ├── sow.py             # Stage 3: SoW drafting + revision
│   │   ├── sprint.py          # Stage 4: task breakdown + sprint planning
│   │   └── jira_sync.py       # Stage 5: Jira Epic/Issue/Sprint creation
│   └── prompts/
│       ├── extraction.py      # Stage 1 prompts
│       ├── clarification.py   # Stage 2 prompts
│       ├── sow.py             # Stage 3 prompts
│       └── sprint.py          # Stage 4 prompts
├── langgraph.json             # LangGraph CLI config
├── pyproject.toml             # Dependencies (managed with uv)
├── .env                       # Your local config (gitignored)
├── .env.example               # Template — copy to .env
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `brew install uv`
- [Ollama](https://ollama.com) — `brew install ollama`

### 1. Clone and install

```bash
git clone <repo-url>
cd meeting-intelligence
uv sync
```

### 2. Pull a local model

The pipeline uses Ollama for local inference. For best results on an M4 Mac:

```bash
# Recommended — fast and good at structured extraction
ollama pull llama3.2:3b

# Alternative — higher quality, slower
ollama pull llama3.1:8b
```

> **Note:** Base `mistral` works but is weaker at structured JSON tasks. Use `llama3.2:3b` for reliable extractions.

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

To use a cloud LLM instead:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### 4. Start Ollama

```bash
ollama serve
```

### 5. Run the dev server

```bash
uv run langgraph dev
```

This starts the LangGraph API server at `http://127.0.0.1:2024` and opens LangGraph Studio at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`.

---

## Using the Pipeline

### In LangGraph Studio

1. Open the Studio URL printed in your terminal
2. Click **"Server connection settings"** and confirm the URL is `http://127.0.0.1:2024`
3. Select the `meeting_pipeline` graph
4. Create a new run with this input:

```json
{
  "raw_transcript": "paste your meeting transcript here..."
}
```

5. The pipeline pauses at each stage for your review — respond to the interrupt prompts to advance

### Human gate interactions

| Stage | To approve | To correct / adjust |
|-------|-----------|-------------------|
| Stage 1 (Extraction) | Type `approve` | Type a plain-language correction |
| Stage 2 (Clarify) | Type `done` | Type `q1: your answer` or `q1: skip reason` |
| Stage 3 (SoW) | Type `approve` (after ≥1 feedback round) | Type feedback in plain text |
| Stage 4 (Sprint Plan) | Type `approve` | Describe the adjustment in plain text |
| Stage 5 (Jira) | Type `confirm` | Set Jira config in `.env` first |

---

## Jira Configuration

### 1. Create a free Jira account

Sign up at [atlassian.com](https://www.atlassian.com) — no credit card required.

### 2. Create a Jira project

- Type: **Scrum** (required for sprint creation via the Agile API)
- Note your **project key** (e.g. `MIP`)

### 3. Generate an API token

Go to [id.atlassian.com/manage-api-tokens](https://id.atlassian.com/manage-api-tokens) → **Create API token**

### 4. Add to `.env`

```env
JIRA_DOMAIN=yourcompany.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-token-here
JIRA_PROJECT_KEY=MIP
```

### What gets created in Jira

- **Epics** — one per module (e.g. Returns Management, User Authentication)
- **Stories / Tasks** — one per task, linked to their parent Epic
- **Sprints** — named with a goal (e.g. "Sprint 1 — Returns Core"), populated with issues

### Error handling

- Failed API calls show the error clearly with context
- Rate limiting handled with exponential backoff
- Partial failures are reported per item — succeeded items are not re-created

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | Yes | `ollama` / `openai` / `anthropic` / `gemini` |
| `OLLAMA_BASE_URL` | If Ollama | Default: `http://localhost:11434` |
| `OLLAMA_MODEL` | If Ollama | Default: `llama3.2:3b` |
| `OPENAI_API_KEY` | If OpenAI | Your OpenAI API key |
| `ANTHROPIC_API_KEY` | If Anthropic | Your Anthropic API key |
| `GEMINI_API_KEY` | If Gemini | Your Google AI API key |
| `JIRA_DOMAIN` | For Stage 5 | e.g. `mycompany.atlassian.net` |
| `JIRA_EMAIL` | For Stage 5 | Your Atlassian account email |
| `JIRA_API_TOKEN` | For Stage 5 | From id.atlassian.com/manage-api-tokens |
| `JIRA_PROJECT_KEY` | For Stage 5 | e.g. `MIP` |
| `LANGCHAIN_TRACING_V2` | No | Set `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | If tracing | Your LangSmith API key |

---

## Design Decisions

**LangGraph over a custom state machine** — The 5-stage pipeline with approval gates maps naturally to LangGraph's `StateGraph`. `interrupt()` handles human pauses natively, and the built-in checkpointer gives us session persistence (page refresh = no lost progress) without any extra infrastructure.

**`langchain-ollama` with `with_structured_output()`** — Rather than prompting the model to return JSON and hoping it complies, `with_structured_output()` uses Ollama's native schema-constrained decoding. This makes structured extraction reliable even on smaller models.

**LiteLLM as a cloud fallback** — For cloud providers (OpenAI, Anthropic, Gemini), we route through LiteLLM so switching providers is a single env var change with no code changes.

**Plain `httpx` for Jira** — The Jira Python SDK adds significant overhead and version fragility. The REST API is simple enough to call directly with `httpx`, and it gives us full control over retry and error handling.

**Single `PipelineState` TypedDict** — All stage data lives in one state object that flows through the entire graph. Each stage reads what it needs and writes its output. This makes the data flow explicit and easy to inspect in LangGraph Studio.

---

## Known Limitations

- **Local model quality** — Base `mistral` produces weak structured extractions. Use `llama3.2:3b` or higher for reliable Stage 1 output.
- **Frontend not yet built** — Currently testable via LangGraph Studio only. A React + FastAPI frontend is planned.
- **Jira Scrum board required** — Sprint creation via the Agile API requires a Scrum-type board. Kanban-only projects won't support Stage 5 sprints.
- **Long transcripts** — Very long transcripts (>8k tokens) may hit context limits on smaller local models. Chunking support is planned.
- **No multi-project support in Studio** — LangGraph Studio runs one thread at a time. Multi-project switching will be part of the frontend.

---

## What's Remaining

- [ ] Fix extraction for local models — pull `llama3.2:3b` and test
- [ ] React frontend (project switcher, per-stage UI, approval buttons)
- [ ] FastAPI wrapper exposing the graph as REST + SSE endpoints
- [ ] End-to-end test with the provided client transcripts
- [ ] Screen recording (2-3 min): full pipeline with approval gates + Jira sync
