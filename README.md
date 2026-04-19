# Meeting Intelligence & Project Automation Agent

An AI-powered web application that converts client meeting transcripts into structured project execution — with a human approval gate at every stage. Upload a transcript and the system walks you through requirement extraction, clarification Q&A, Scope of Work drafting, sprint planning, and Jira sync.

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
  → Human adjusts plan (drag/drop or manual move), then approves
      │
      ▼
Stage 5 — Jira Sync
  Preview shown before any write. Sync runs in confirmed batches:
  Epics → Issues → Sprints.
  → Human confirms each batch, progress is preserved, summary with links on completion
```

Each stage is a distinct node in a LangGraph state machine. Nothing advances without an explicit human approval.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI (Python 3.11+) |
| Frontend | React 18 + TypeScript + Tailwind CSS + Vite |
| Orchestration | LangGraph (StateGraph with human-in-the-loop interrupts) |
| LLM (local) | Ollama — `llama3.2:3b` recommended on M4 Mac |
| LLM (cloud) | OpenAI / Anthropic / Gemini via LiteLLM (configurable) |
| Structured output | `langchain-ollama` with `with_structured_output()` |
| Jira integration | Atlassian REST API v3 + Agile API via `httpx` |
| State persistence | Configurable: in-memory (default) or MongoDB |
| Runtime checkpoints | LangGraph checkpointer (`memory` or Mongo-backed) |
| Streaming | SSE project state + runtime progress events |
| State management (frontend) | Zustand |

---

## Project Structure

```
meeting-intelligence/
├── src/
│   ├── agent/                 # LangGraph pipeline
│   │   ├── config.py          # Settings loaded from .env
│   │   ├── llm.py             # LLM client (Ollama / OpenAI / Anthropic / Gemini)
│   │   ├── jira.py            # Jira REST API client
│   │   ├── state.py           # Pipeline state + Pydantic models
│   │   ├── graph.py           # LangGraph StateGraph (all 5 stages)
│   │   ├── nodes/             # Stage nodes
│   │   │   ├── parse.py       # Stage 1: transcript parsing + corrections
│   │   │   ├── clarify.py     # Stage 2: question generation + answers
│   │   │   ├── sow.py         # Stage 3: SoW drafting + revision
│   │   │   ├── sprint.py      # Stage 4: task breakdown + sprint planning
│   │   │   └── jira_sync.py   # Stage 5: Jira Epic/Issue/Sprint creation
│   │   └── prompts/           # LLM prompts for each stage
│   └── api/                   # FastAPI backend
│       └── main.py            # REST API endpoints
├── frontend/                  # React frontend
│   ├── src/
│   │   ├── components/        # React components
│   │   │   ├── ui/            # Shared UI components
│   │   │   ├── stages/        # Per-stage components
│   │   │   ├── ProjectSwitcher.tsx
│   │   │   └── StageProgress.tsx
│   │   ├── lib/               # Utilities
│   │   │   ├── api.ts         # API client functions
│   │   │   └── utils.ts       # Helper functions
│   │   ├── store/             # State management
│   │   │   └── projectStore.ts # Zustand store
│   │   ├── types/             # TypeScript types
│   │   │   └── index.ts
│   │   ├── App.tsx            # Main app component
│   │   └── main.tsx           # Entry point
│   ├── package.json
│   └── vite.config.ts
├── langgraph.json             # LangGraph CLI config
├── pyproject.toml             # Python dependencies
├── .env                       # Your local config (gitignored)
├── .env.example               # Template — copy to .env
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Ollama](https://ollama.com) — `brew install ollama`
- Node.js 18+ — `brew install node`

### 1. Clone and install

```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 2. Pull a local model

The pipeline uses Ollama for local inference. For best results on an M4 Mac:

```bash
# Recommended — fast and good at structured extraction
ollama pull llama3.2:3b

# Alternative — higher quality, slower
ollama pull llama3.1:8b
```

> **Note:** Base `mistral` works but is weaker at structured JSON tasks. Use `llama3.2:3b` for reliable Stage 1 output.

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
PROJECT_STORAGE_BACKEND=memory
```

To persist project state across backend restarts, switch to MongoDB:

```env
PROJECT_STORAGE_BACKEND=mongo
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=meeting_intelligence
MONGODB_COLLECTION=projects
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

### 5. Start the backend

```bash
# From the project root
uv run uvicorn src.api.main:app --reload --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}"
```

The API will be available at `http://${API_HOST:-127.0.0.1}:${API_PORT:-8000}`.

### 6. Start the frontend

In a new terminal:

```bash
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:${VITE_PORT:-5173}`.

---

## Using the Application

### Runtime Behavior

- **Stages 1-4** now execute through the LangGraph runtime, not just direct API-node calls
- Human review steps are backed by **LangGraph interrupts** and resumed by the API with user input
- Each project thread tracks checkpoint metadata such as:
  - `graph_checkpoint_id`
  - `graph_next_nodes`
  - `pending_interrupts`
  - `last_checkpoint_at`
- SSE now streams both the latest `project_state` and runtime events like progress, completed nodes, checkpoint saves, interrupts, and LLM lifecycle events
- **Stage 5** Jira creation now runs through graph-backed `preview_jira_*` → `review_jira_*` → `create_jira_*` batch nodes, with interrupt checkpoints and ordering guardrails between epics, issues, and sprints

### 1. Create a Project

1. Open `http://localhost:5173` in your browser
2. Click the project switcher dropdown
3. Click "New Project"
4. Enter a project name
5. Paste your meeting transcript
6. Click "Create"

### 2. Stage 1: Parse & Extract

- Review the extracted modules, requirements, integrations, constraints, and unknowns
- Each field shows a confidence indicator (high/medium/low)
- Type corrections in plain language (e.g., "Add a module for User Authentication")
- Click "Approve & Continue" when satisfied

### 3. Stage 2: Clarification Loop

- AI generates targeted questions based on gaps in the transcript
- Answer questions in plain text, or skip with a reason
- Click "Done & Continue to SoW" when satisfied

### 4. Stage 3: Scope of Work

- Review the AI-drafted SoW
- Provide feedback in plain text (at least one round required)
- AI will revise and show a changelog
- Click "Approve & Continue" when satisfied
- You can download the SoW as a Markdown file

### 5. Stage 4: Sprint Planning

- Review the generated tasks and sprints
- Each task has story points, dependencies, and acceptance criteria
- Warnings are shown if sprints exceed 40 points
- Move tasks between sprints with drag-and-drop
- You can still use the "Move" dropdown/button as a fallback
- Request adjustments in plain text if needed
- Click "Approve & Continue to Jira" when satisfied

### 6. Stage 5: Jira Integration

- Enter your Jira credentials (domain, email, API token, project key)
- Click "Test Connection" to verify
- Preview what will be created (epics, issues, sprints)
- Confirm and run **Create Epics**
- Confirm and run **Create Issues**
- Confirm and run **Create Sprints**
- View results with direct links to each created issue

---

## Jira Configuration

📖 **For detailed step-by-step instructions, see [JIRA_SETUP.md](docs/JIRA_SETUP.md)**

### Quick Setup

1. **Create a free Jira account** at [atlassian.com](https://www.atlassian.com) — no credit card required

2. **Create a Jira project**
   - Type: **Scrum** (required for sprint creation via the Agile API)
   - Note your **project key** (e.g. `MIP`, `DEMO`, `TEST`)

3. **Get your domain**
   - Check your browser URL when logged into Jira
   - Format: `yourcompany.atlassian.net` (no `https://`)

4. **Generate an API token**
   - Go to [id.atlassian.com/manage-api-tokens](https://id.atlassian.com/manage-api-tokens)
   - Click **"Create API token"**
   - Copy the token immediately (you won't see it again!)

5. **Configure** — either in the web UI (Stage 5) or via `.env`:
   ```env
   API_HOST=127.0.0.1
   API_PORT=8000
   VITE_PORT=5173
   VITE_API_URL=http://127.0.0.1:8000
   JIRA_DOMAIN=yourcompany.atlassian.net
   JIRA_EMAIL=you@example.com
   JIRA_API_TOKEN=ATATT3yFfxf0Jm...
   JIRA_PROJECT_KEY=MIP
   ```

### What gets created in Jira

- **Epics** — one per module (e.g. Returns Management, User Authentication)
- **Stories / Tasks** — one per task, linked to their parent Epic
- **Sprints** — named with a goal (e.g. "Sprint 1 — Returns Core"), populated with issues

Creation is intentionally gated by batch in the UI: Epics must complete before Issues, and Issues must complete before Sprints.

### Configuration Fields

| Field | Description | Example |
|-------|-------------|---------|
| **Domain** | Your Atlassian domain (without `https://`) | `mycompany.atlassian.net` |
| **Email** | Your Atlassian account email | `you@example.com` |
| **API Token** | Token from id.atlassian.com/manage-api-tokens | `ATATT3yFfxf0Jm...` |
| **Project Key** | Uppercase project identifier | `MIP`, `DEMO`, `TEST` |

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
| `API_HOST` | No | Backend bind host, default `127.0.0.1` |
| `API_PORT` | No | Backend port, default `8000` |
| `VITE_PORT` | No | Frontend dev server port, default `5173` |
| `VITE_API_URL` | No | Frontend API base URL / Vite proxy target |
| `CORS_ALLOWED_ORIGINS` | No | Optional comma-separated backend CORS override |
| `PROJECT_STORAGE_BACKEND` | No | `memory` (default) or `mongo` |
| `MONGODB_URI` | If Mongo | MongoDB connection string |
| `MONGODB_DATABASE` | If Mongo | Database name (default `meeting_intelligence`) |
| `MONGODB_COLLECTION` | If Mongo | Collection name (default `projects`) |
| `LANGCHAIN_TRACING_V2` | No | Set `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | If tracing | Your LangSmith API key |

---

## Design Decisions

**LangGraph over a custom state machine** — The 5-stage pipeline with approval gates maps naturally to LangGraph's `StateGraph`. `interrupt()` semantics map cleanly to approval checkpoints, while the API layer handles stage transitions explicitly.

**Configurable persistence backend** — Project state storage is backend-driven via `PROJECT_STORAGE_BACKEND` (`memory` or `mongo`). `memory` keeps local setup simple; `mongo` adds restart-safe persistence without changing API contracts.

**Checkpoint-aware runtime** — Stages 1-4 and the Stage 5 Jira write path run through a compiled LangGraph runtime with checkpoint persistence, so review steps can resume from saved interrupt state instead of replaying the whole pipeline.

**SSE for state + progress** — The frontend receives both project snapshots and runtime events over SSE, which makes long-running LLM calls and graph node transitions visible while keeping the integration simpler than WebSockets.

**`langchain-ollama` with `with_structured_output()`** — Rather than prompting the model to return JSON and hoping it complies, `with_structured_output()` uses Ollama's native schema-constrained decoding. This makes structured extraction reliable even on smaller models.

**FastAPI + React** — FastAPI provides async support and automatic OpenAPI docs. React with TypeScript gives us type safety and a great developer experience. Zustand for state management keeps things simple without Redux overhead.

**Single `PipelineState` TypedDict** — All stage data lives in one state object that flows through the entire graph. Each stage reads what it needs and writes its output. This makes the data flow explicit and easy to debug.

---

## Known Limitations

- **Local model quality** — Base `mistral` produces weak structured extractions. Use `llama3.2:3b` or higher for reliable Stage 1 output.
- **State persistence** — `memory` is still the default backend. Use `mongo` backend in `.env` for restart-safe persistence.
- **Stage 5 setup UX** — Jira config save, connection test, and preview retrieval remain API-facing helpers, but the actual Jira batch execution path now runs through graph interrupts, checkpoints, and enforced batch ordering.
- **Jira Scrum board required** — Sprint creation via the Agile API requires a Scrum-type board. Kanban-only projects won't support Stage 5 sprints.
- **Long transcripts** — transcript extraction now uses three strategies: `full` (short), `topic` (medium), `chunked` (long). Long transcripts are split into overlapping chunks, each extracted independently, then merged, de-duplicated, and validated. If the merged result is sparse, the pipeline falls back to a focused single-pass or full-transcript retry. All thresholds are configurable via env vars.
- **Streaming granularity** — SSE now emits runtime progress events, but provider-level token streaming is not implemented yet.

---

## Development

### Running validation and smoke tests

```bash
# Syntax-check the main backend/runtime files
python3 -m py_compile src/api/main.py src/agent/runtime.py src/agent/graph.py src/agent/nodes/jira_sync.py src/agent/nodes/parse.py src/agent/transcript_preprocessor.py

# Graph-backed API smoke test (mocked runtime / no real LLM required)
PYTHONPATH=src python3 scripts/api_graph_runtime_smoke.py

# Long-transcript chunk/merge smoke test (mocked LLM)
PYTHONPATH=src python3 scripts/long_transcript_chunking_smoke.py

# Additional API / pipeline smoke helpers
PYTHONPATH=src python3 scripts/api_smoke.py
PYTHONPATH=src python3 scripts/api_stage_checks.py

# Frontend production build validation
cd frontend
npm run build
```

### Building for production

```bash
# Build frontend
cd frontend
npm run build

# The build output will be in frontend/dist/
# Serve this with your FastAPI backend or a CDN
```

---

## What's Remaining

- [ ] Add MongoDB indexes/backups + operational docs for production-grade persistence
- [ ] Add finer-grained token streaming where provider support allows it
- [ ] Add transcript chunking for long inputs
- [ ] Add end-to-end tests
- [ ] Record the screen demo using `docs/SCREEN_RECORDING_DEMO_PACKAGING.md`
- [ ] Add more comprehensive error handling
- [ ] Add user authentication
- [ ] Add more export formats (PDF, DOCX)