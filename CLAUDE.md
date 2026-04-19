# Meeting Intelligence & Project Automation Agent

> **AI Engineer Technical Assessment Project**
>
> A web application that transforms client meeting transcripts into structured project scopes, sprint plans, and Jira tasks with human review at every stage.

---

## 🎯 Project Overview

This is a **5-stage pipeline application** that uses AI to extract project requirements from meeting transcripts, creates a Scope of Work (SoW), builds sprint plans, and syncs everything to Jira. Each stage requires explicit human approval before proceeding.

### Core Philosophy
- **Human-in-the-loop**: Nothing moves forward without user approval
- **Transparency**: Confidence levels, assumptions, and unknowns are always visible
- **Multi-project support**: Each project maintains independent state
- **No data leakage**: Projects don't share context

---

## 🏗️ Architecture

### Technology Stack

**Backend:**
- **Python 3.13** with FastAPI
- **LangGraph** for orchestration (state machine with interrupts)
- **LangGraph Checkpointer** for resumable runtime state (`memory` or Mongo-backed)
- **LangChain** for LLM abstraction (supports Ollama, OpenAI, Anthropic, Gemini)
- **Pydantic** for structured output validation
- **Uvicorn** ASGI server

**Frontend:**
- **React 18** with TypeScript
- **Vite** for fast development
- **TailwindCSS** for styling (via shadcn/ui components)
- **Axios** for API calls
- **Server-Sent Events (SSE)** for project-state and runtime progress streaming

**LLM Support:**
- Local: Ollama (llama3.2:3b recommended)
- Cloud: OpenAI (GPT-4o), Anthropic (Claude Sonnet 4), Gemini 2.0 Flash

---

## 📊 Pipeline Stages

### Stage 1: Transcript Parsing & Requirement Extraction
**Location:** `src/agent/nodes/parse.py`

**Extracts:**
- `project_name`, `client_name`, `vendor_name`
- `modules[]` - name, description, priority, deadline
- `requirements[]` - description, module, type (Functional/Non-Functional/Integration)
- `integrations[]` - third-party systems (QuickBooks, Okta, etc.)
- `constraints[]` - timelines, budget, compliance
- `assumptions[]` - inferred information (low confidence)
- `unknowns[]` - unresolved items

**Key Features:**
- **Validation step** with low temperature (0.1) to catch extraction errors
- **Auto-correction** button to fix common issues (e.g., "Client" → actual name)
- **Deduplication** removes duplicate requirements based on 80% similarity
- **Confidence levels** (high/medium/low) on every field

**Prompt:** `src/agent/prompts/extraction_enhanced.py`

---

### Stage 2: Clarification Loop
**Location:** `src/agent/nodes/clarify.py`

**Features:**
- AI generates targeted questions from gaps in Stage 1
- Minimum 5 questions specific to the transcript
- Each question cites transcript context
- User can answer, skip with reason, or ask their own questions
- AI follows up if answers create new questions

**UI Features:**
- Question list with status (open/answered/skipped)
- "Ask a question" feature for user queries
- "Done" button when user is satisfied

**Prompt:** `src/agent/prompts/clarification.py`

---

### Stage 3: Scope of Work (SoW)
**Location:** `src/agent/nodes/sow.py`

**SoW Sections:**
- Executive Summary
- In-scope items (by module)
- Out-of-scope items (explicitly called out)
- Modules & Deliverables (features + acceptance criteria)
- Integrations (purpose, type, data flow)
- Constraints & Assumptions
- Open Items
- Timeline Overview

**Feedback Loop:**
- User provides free-text feedback
- AI incorporates all points and shows changelog
- Must complete at least one feedback round before approval
- Final SoW downloadable as .md

**Prompt:** `src/agent/prompts/sow.py`

---

### Stage 4: Task Breakdown & Sprint Planning
**Location:** `src/agent/nodes/sprint.py`

**Task Schema:**
- `title` - action-oriented (e.g., "Build returns submission form")
- `description` - 2-3 sentences
- `module`, `type` (Story/Task/Epic), `priority`
- `story_points` - Fibonacci: 1, 2, 3, 5, 8, 13
- `dependencies` - task IDs that must complete first
- `acceptance_criteria` - at least 2 per task

**Sprint Rules:**
- 2-week sprints, max 40 story points (warns if exceeded)
- Sprint names reflect goal (e.g., "Sprint 1 — Returns Core")
- Dependencies respected
- Tasks movable between sprints

**UI Notes:**
- Tasks can be moved between sprint cards via drag-and-drop
- Manual move (dropdown + button) remains available as a fallback

**Prompt:** `src/agent/prompts/sprint.py`

---

### Stage 5: Jira Integration
**Location:** `src/agent/nodes/jira_sync.py`

**Setup:**
- User enters Jira domain, email, API token, project key
- Connection test before any writes
- Works with free Atlassian accounts

**Creation Flow:**
1. **Preview** Epics → User confirms
2. **Create** Epics (one per module)
3. **Preview** Issues → User confirms
4. **Create** Issues (linked to parent Epic)
5. **Preview** Sprints → User confirms
6. **Create** Sprints via Agile API, add issues

**Error Handling:**
- Clear error messages with retry
- Rate limiting with backoff
- Partial failures shown explicitly
- Summary table with issue keys and direct links

---

## 📁 Project Structure

```
meeting-intelligence-project-automation-agent/
├── src/
│   ├── agent/
│   │   ├── nodes/           # Stage implementation functions
│   │   │   ├── parse.py     # Stage 1: Extraction
│   │   │   ├── clarify.py   # Stage 2: Questions
│   │   │   ├── sow.py       # Stage 3: Scope of Work
│   │   │   ├── sprint.py    # Stage 4: Sprint Planning
│   │   │   └── jira_sync.py # Stage 5: Jira Integration
│   │   ├── prompts/         # LLM prompts for each stage
│   │   │   ├── extraction_enhanced.py
│   │   │   ├── clarification.py
│   │   │   ├── sow.py
│   │   │   ├── sprint.py
│   │   │   └── validation.py
│   │   ├── graph.py         # LangGraph state machine
│   │   ├── state.py         # Pydantic state schemas
│   │   ├── llm.py           # LLM abstraction layer
│   │   └── transcript_preprocessor.py
│   └── api/
│       └── main.py          # FastAPI REST API
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── stages/      # Stage-specific UI components
│   │   │   │   ├── ParseStage.tsx
│   │   │   │   ├── ClarifyStage.tsx
│   │   │   │   ├── SowStage.tsx
│   │   │   │   ├── SprintStage.tsx
│   │   │   │   └── JiraStage.tsx
│   │   │   └── ui/          # Reusable components (Button, Card, etc.)
│   │   ├── lib/
│   │   │   └── api.ts       # API client functions
│   │   ├── store/
│   │   │   └── projectStore.ts # Zustand state management
│   │   └── types/
│   │       └── index.ts     # TypeScript type definitions
│   └── package.json
├── .env.example             # Environment variables template
├── pyproject.toml           # Python dependencies
├── README.md                # User-facing documentation
├── CLAUDE.md                # This file - developer documentation
└── VALIDATION_FEATURE_SUMMARY.md  # Feature documentation
```

---

## 🔧 Key Implementation Details

### LangGraph State Machine

**Graph Definition:** `src/agent/graph.py`

```python
# Stage flow with human interrupts
parse_transcript → review_extraction
    ↓
generate_questions → review_clarification
    ↓
draft_sow → review_sow → revise_sow → review_sow
    ↓
generate_sprint_plan → review_sprint → adjust_sprint_plan → review_sprint
    ↓
preview_jira_epics → review_jira_epics → create_jira_epics
    ↓
preview_jira_issues → review_jira_issues → create_jira_issues
    ↓
preview_jira_sprints → review_jira_sprints → create_jira_sprints → stage5_done
```

**Key Function:**
- `interrupt()` - Pauses execution for human review
- `Command[Literal["next_node"]]` - Routes to next node based on user input

**Runtime Notes:**
- Stages 1-4 plus the Stage 5 Jira batch write path are executed through the compiled LangGraph runtime and resumed via `Command(resume=...)`
- Checkpoint metadata is surfaced back to the API as `graph_checkpoint_id`, `graph_next_nodes`, `pending_interrupts`, and `last_checkpoint_at`
- Jira config save, connection testing, and preview retrieval remain API-facing helpers, while Jira writes execute through graph-backed preview/review/create nodes

---

### Validation System

**Location:** `src/agent/nodes/parse.py`

**Two-Step Validation:**
1. **validate_extraction()** - Low temp (0.1) compares extraction to transcript
2. **auto_correct_extraction()** - Applies fixes automatically

**Error Categories:**
- Wrong names (e.g., "Client" instead of "AI Money")
- Wrong values (null when transcript has data)
- Generic placeholders (e.g., "API integration" instead of "Domain API")
- Missing details (competitors, integrations)

---

### Deduplication System

**Location:** `src/agent/nodes/parse.py:26-92`

**Algorithm:**
1. Exact match (normalized lowercase)
2. Similarity check (Jaccard word overlap, 80% threshold)
3. Same module grouping

**Result:**
```
Removed 15 duplicate requirements. Original: 45, Unique: 30
```

---

### LLM Abstraction Layer

**Location:** `src/agent/llm.py`

**Supports:**
- `complete_structured(messages, schema)` - Returns Pydantic model
- `complete_text(messages, temperature=None)` - Returns plain text

**Temperature Control:**
- Default: 0.2 (balanced)
- Validation: 0.1 (strict, deterministic)
- Creative tasks: 0.7 (varied)

---

### Frontend State Management

**Store:** `frontend/src/store/projectStore.ts` (Zustand)

**State:**
```typescript
{
  projects: ProjectListItem[]
  currentProject: ProjectState | null
  isLoading: boolean
  error: string | null
}
```

**API Layer:** `frontend/src/lib/api.ts`
- All functions return typed responses
- Error handling with try/catch
- Automatic project refresh after mutations

**Streaming Layer:** `frontend/src/hooks/useProjectStream.ts`
- Subscribes to `project_state` plus runtime events such as `stage_progress`, `graph_node_finished`, `llm_start`, `llm_complete`, `checkpoint_saved`, `interrupt`, and `graph_error`
- Updates Zustand with latest runtime progress and pending human-review status

### Checkpoint & Resume Semantics

**Runtime Helpers:** `src/agent/runtime.py`, `src/agent/checkpoints.py`

**Behavior:**
- Each project uses the project id as the LangGraph `thread_id`
- `memory` backend uses LangGraph `InMemorySaver`
- `mongo` backend persists checkpoints in a separate collection named `{MONGODB_COLLECTION}_checkpoints`
- API endpoints resume graph execution with the user's approval/feedback payload instead of replaying the whole workflow

**Useful State Fields:**
- `graph_checkpoint_id`
- `graph_next_nodes[]`
- `pending_interrupts[]`
- `last_checkpoint_at`

### SSE Runtime Progress

**Backend Emitters:** `src/api/main.py`, `src/agent/streaming.py`, `src/agent/llm.py`

**Current Events:**
- `project_state`
- `stage_progress`
- `graph_node_finished`
- `llm_start`
- `llm_complete`
- `checkpoint_saved`
- `interrupt`
- `graph_error`

---

## 🚀 Setup & Running

### Backend

```bash
# Install dependencies
uv pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run backend
PYTHONPATH=/path/to/project/src uv run uvicorn src.api.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}" --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

### Environment Variables

```bash
# LLM Provider (ollama | openai | anthropic | gemini)
LLM_PROVIDER=ollama

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# OpenAI (optional)
OPENAI_API_KEY=sk-...

# Anthropic (optional)
ANTHROPIC_API_KEY=sk-ant-...

# Gemini (optional)
GEMINI_API_KEY=...

# Project storage backend (memory | mongo)
PROJECT_STORAGE_BACKEND=memory

# Local app networking
API_HOST=127.0.0.1
API_PORT=8000
VITE_PORT=5173
VITE_API_URL=http://127.0.0.1:8000
# Optional comma-separated override
# CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Mongo (required only for PROJECT_STORAGE_BACKEND=mongo)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=meeting_intelligence
MONGODB_COLLECTION=projects
```

---

## 🧪 Testing

### Test Transcripts

Two transcripts are provided:
1. `Eco_Chase_Discovery_Transcript_Anonymised.txt` - Eco Chase project
2. `Software Co _ Smart Money Discovery Transcript.txt` - Smart Money Mate project

### Test Flow

1. **Create project** with transcript
2. **Stage 1**: Review extraction, click "Auto-Correct" if validation fails, approve
3. **Stage 2**: Answer questions or skip, click "Done"
4. **Stage 3**: Review SoW, provide feedback, approve after revision
5. **Stage 4**: Review sprint plan, move tasks if needed, approve
6. **Stage 5**: Configure Jira, confirm each batch (Epics → Issues → Sprints)

---

## 📝 Design Decisions

### Why LangGraph over simple chaining?

**Decision:** Use LangGraph with interrupts

**Rationale:**
- Human-in-the-loop requires pausing execution
- State machine makes approval gates explicit
- Natural representation of pipeline stages
- Built-in state persistence

### Why separate validation step?

**Decision:** Add low-temperature validation after extraction

**Rationale:**
- Catches extraction errors before human review
- Temperature 0.1 is strict vs. 0.2 for extraction
- Reduces human correction rounds
- Prevents "Client" placeholder issue

### Why deduplication in code vs. prompt?

**Decision:** Both - anti-duplication rules + post-processing

**Rationale:**
- Prompts can reduce but not eliminate duplicates
- Post-processing guarantees uniqueness
- Similarity threshold catches near-duplicates
- Logging provides transparency

### Why Pydantic for structured output?

**Decision:** Use `with_structured_output()` from LangChain

**Rationale:**
- Schema validation at LLM boundary
- Type safety throughout pipeline
- Clear data models for frontend
- Easy serialization for API

---

## 🐛 Known Limitations

1. **LLM Dependency**: Quality depends on model capability (llama3.2:3b recommended for Ollama)
2. **Long Transcripts**: >25 min may need topic-based preprocessing (implemented but not battle-tested)
3. **Jira Rate Limits**: Free accounts have strict limits, backoff implemented but may be slow
4. **Persistence Backend Default**: Default `memory` backend loses state on backend restart; use `mongo` backend for durable storage
5. **Stage 5 Setup Split**: Jira config, connection testing, and preview retrieval are still API-facing helpers, but batch creation now runs through interrupt-driven graph nodes with checkpoints between epics, issues, and sprints
6. **Concurrent Projects**: No locking, possible race conditions if multiple users edit same project

---

## 🔮 Future Enhancements

### Phase 2 (Post-Assessment)
- Persistence hardening (indexes, retention, backup/restore docs)
- Token-level provider streaming where supported
- User authentication
- Project history/audit trail
- Export to PDF (SoW)
- Import from existing Jira projects

### Phase 3 (Advanced Features)
- Multi-language transcripts
- Sentiment analysis
- Automated risk scoring
- Sprint velocity tracking
- Burndown charts

---

## 📚 Key Files to Understand

**For Pipeline Logic:**
- `src/agent/graph.py` - State machine definition
- `src/agent/state.py` - State schemas

**For Each Stage:**
- `src/agent/nodes/[stage].py` - Implementation
- `src/agent/prompts/[stage].py` - LLM prompts
- `frontend/src/components/stages/[Stage]Stage.tsx` - UI

**For Integration:**
- `src/api/main.py` - FastAPI endpoints
- `frontend/src/lib/api.ts` - API client

**For Core Utilities:**
- `src/agent/llm.py` - LLM abstraction
- `src/agent/transcript_preprocessor.py` - Preprocessing

---

## 🤝 Contributing

This is an assessment project, but if extending:

1. **Add stages**: Update `graph.py`, create node in `nodes/`, prompt in `prompts/`
2. **Modify extraction**: Update `state.py` schemas, regenerate types
3. **UI changes**: Component-based, add to `stages/`, update types

---

## 📄 License

Proprietary - Assessment Submission

---

**Built for:** AI Engineer Technical Assessment
**Date:** April 2025
**Candidate:** [Your Name]
