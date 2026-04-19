import axios from 'axios'
import type {
  CreateProjectRequest,
  FeedbackRequest,
  AnswerRequest,
  SkipRequest,
  JiraConfigRequest,
  JiraPreview,
  JiraBatchSyncResponse,
  JiraBatch,
  ProjectState,
  ProjectListItem,
} from '@/types'

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── Health check ─────────────────────────────────────────────────────────────

export async function healthCheck() {
  const response = await api.get('/health')
  return response.data
}

// ── Projects ────────────────────────────────────────────────────────────────

export async function listProjects(): Promise<ProjectListItem[]> {
  const response = await api.get('/api/projects')
  return response.data
}

export async function createProject(request: CreateProjectRequest): Promise<ProjectListItem> {
  const response = await api.post('/api/projects', request)
  return response.data
}

export async function getProject(projectId: string): Promise<ProjectState> {
  const response = await api.get(`/api/projects/${projectId}`)
  return response.data
}

export async function deleteProject(projectId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}`)
}

// ── Stage 1: Parse & Extract ────────────────────────────────────────────────

export async function approveStage1(projectId: string): Promise<{ message: string; next_stage: string }> {
  const response = await api.post(`/api/projects/${projectId}/stage/parse/approve`)
  return response.data
}

export async function submitStage1Feedback(
  projectId: string,
  request: FeedbackRequest,
): Promise<{ message: string; extraction: any }> {
  const response = await api.post(`/api/projects/${projectId}/stage/parse/feedback`, request)
  return response.data
}

// ── Stage 2: Clarification ──────────────────────────────────────────────────

export async function answerQuestion(
  projectId: string,
  request: AnswerRequest,
): Promise<{ message: string; questions: any[] }> {
  const response = await api.post(`/api/projects/${projectId}/stage/clarify/answer`, request)
  return response.data
}

export async function skipQuestion(
  projectId: string,
  request: SkipRequest,
): Promise<{ message: string; questions: any[] }> {
  const response = await api.post(`/api/projects/${projectId}/stage/clarify/skip`, request)
  return response.data
}

export async function doneClarification(projectId: string): Promise<{ message: string; next_stage: string }> {
  const response = await api.post(`/api/projects/${projectId}/stage/clarify/done`)
  return response.data
}

export async function askClarificationQuestion(
  projectId: string,
  request: { question: string },
): Promise<{ message: string; answer: string; questions: any[] }> {
  const response = await api.post(`/api/projects/${projectId}/stage/clarify/ask`, request)
  return response.data
}

// ── Stage 3: Scope of Work ──────────────────────────────────────────────────

export async function submitSowFeedback(
  projectId: string,
  request: FeedbackRequest,
): Promise<{ message: string; sow: string; version: number }> {
  const response = await api.post(`/api/projects/${projectId}/stage/sow/feedback`, request)
  return response.data
}

export async function approveSow(projectId: string): Promise<{ message: string; next_stage: string }> {
  const response = await api.post(`/api/projects/${projectId}/stage/sow/approve`)
  return response.data
}

// ── Stage 4: Sprint Planning ────────────────────────────────────────────────

export async function submitSprintFeedback(
  projectId: string,
  request: FeedbackRequest,
): Promise<{ message: string; sprints: any[] }> {
  const response = await api.post(`/api/projects/${projectId}/stage/sprint/feedback`, request)
  return response.data
}

export async function approveSprintPlan(projectId: string): Promise<{ message: string; next_stage: string }> {
  const response = await api.post(`/api/projects/${projectId}/stage/sprint/approve`)
  return response.data
}

export async function moveSprintTask(
  projectId: string,
  request: { task_id: string; sprint_name: string },
): Promise<{ message: string; sprints: any[]; warnings: string[] }> {
  const response = await api.post(`/api/projects/${projectId}/stage/sprint/move-task`, request)
  return response.data
}

// ── Stage 5: Jira ───────────────────────────────────────────────────────────

export async function setJiraConfig(projectId: string, request: JiraConfigRequest): Promise<{ message: string }> {
  const response = await api.post(`/api/projects/${projectId}/jira/config`, request)
  return response.data
}

export async function testJiraConnection(projectId: string): Promise<{ message: string }> {
  const response = await api.post(`/api/projects/${projectId}/jira/test`)
  return response.data
}

export async function getJiraPreview(projectId: string): Promise<JiraPreview> {
  const response = await api.get(`/api/projects/${projectId}/jira/preview`)
  return response.data
}

export async function syncToJiraBatch(
  projectId: string,
  batch: JiraBatch,
): Promise<JiraBatchSyncResponse> {
  const response = await api.post(`/api/projects/${projectId}/jira/sync/${batch}`)
  return response.data
}

export async function syncToJira(projectId: string): Promise<{ message: string; results: any[] }> {
  const response = await api.post(`/api/projects/${projectId}/jira/sync`)
  return response.data
}