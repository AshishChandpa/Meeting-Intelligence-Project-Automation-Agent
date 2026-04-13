// ── Core types matching the backend state schema ───────────────────────────────

export type Stage = "parse" | "clarify" | "sow" | "sprint" | "jira" | "done"

export type Confidence = "high" | "medium" | "low"
export type Priority = "High" | "Medium" | "Low"
export type RequirementType = "Functional" | "Non-Functional" | "Integration"
export type TaskType = "Epic" | "Story" | "Task"
export type QuestionStatus = "open" | "answered" | "skipped"
export type StoryPoints = 1 | 2 | 3 | 5 | 8 | 13

// ── Stage 1: Extraction types ────────────────────────────────────────────────

export interface Module {
  name: string
  description: string
  priority: Priority
  deadline?: string
  confidence: Confidence
}

export interface Requirement {
  description: string
  module: string
  type: RequirementType
  confidence: Confidence
}

export interface Integration {
  system: string
  purpose: string
  confidence: Confidence
}

export interface Constraint {
  description: string
  confidence: Confidence
}

export interface Assumption {
  description: string
  confidence: Confidence
}

export interface Unknown {
  description: string
  source: string
}

export interface Extraction {
  project_name: string
  client_name: string
  vendor_name: string
  modules: Module[]
  requirements: Requirement[]
  integrations: Integration[]
  constraints: Constraint[]
  assumptions: Assumption[]
  unknowns: Unknown[]
}

// ── Stage 2: Clarification types ────────────────────────────────────────────

export interface Question {
  id: string
  question: string
  context: string
  status: QuestionStatus
  answer: string
  skip_reason: string
}

// ── Stage 3: SoW types ───────────────────────────────────────────────────────

export interface SowRevision {
  version: number
  feedback: string
  changelog: string
}

// ── Stage 4: Sprint types ───────────────────────────────────────────────────

export interface Task {
  id: string
  title: string
  description: string
  module: string
  type: TaskType
  priority: Priority
  story_points: StoryPoints
  dependencies: string[]
  acceptance_criteria: string[]
}

export interface Sprint {
  name: string
  goal: string
  task_ids: string[]
  total_points: number
}

// ── Stage 5: Jira types ─────────────────────────────────────────────────────

export interface JiraConfig {
  domain: string
  email: string
  api_token: string
  project_key: string
}

export interface JiraResult {
  type: string
  key: string
  title: string
  url: string
  status: "created" | "failed"
  error: string
}

// ── Full Project State ──────────────────────────────────────────────────────

export interface ProjectState {
  id: string
  name: string
  current_stage: Stage
  extraction?: Extraction
  questions?: Question[]
  sow?: string
  sow_version?: number
  sow_revisions?: SowRevision[]
  tasks?: Task[]
  sprints?: Sprint[]
  sprint_warnings?: string[]
  jira_results?: JiraResult[]
  validation_result?: string
  validation_passed?: boolean
  correction_applied?: boolean
  stage1_approved?: boolean
  stage2_approved?: boolean
  stage3_approved?: boolean
  stage4_approved?: boolean
  stage5_done?: boolean
  created_at?: number
}

// ── API Request/Response types ───────────────────────────────────────────────

export interface CreateProjectRequest {
  name: string
  transcript: string
}

export interface FeedbackRequest {
  feedback: string
}

export interface AnswerRequest {
  question_id: string
  answer: string
}

export interface SkipRequest {
  question_id: string
  reason: string
}

export interface JiraConfigRequest {
  domain: string
  email: string
  api_token: string
  project_key: string
}

// ── UI State types ─────────────────────────────────────────────────────────

export interface ProjectListItem {
  id: string
  name: string
  current_stage: Stage
  created_at: number | null
}