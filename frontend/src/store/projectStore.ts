import { create } from 'zustand'
import { ProjectListItem, ProjectState, StreamEventPayload } from '@/types'

interface ProjectStore {
  // Current project
  currentProject: ProjectState | null
  setCurrentProject: (project: ProjectState | null) => void
  syncCurrentProject: (project: ProjectState) => void

  // Runtime stream state
  latestStreamEvent: StreamEventPayload | null
  streamEvents: StreamEventPayload[]
  setLatestStreamEvent: (event: StreamEventPayload | null) => void
  pushStreamEvent: (event: StreamEventPayload) => void

  // All projects list
  projects: ProjectListItem[]
  setProjects: (projects: ProjectListItem[]) => void
  addProject: (project: ProjectListItem) => void
  removeProject: (projectId: string) => void

  // UI state
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  error: string | null
  setError: (error: string | null) => void
}

export const useProjectStore = create<ProjectStore>((set) => ({
  // Current project
  currentProject: null,
  setCurrentProject: (project) => set({ currentProject: project, error: null }),
  syncCurrentProject: (project) => set({ currentProject: project }),
  latestStreamEvent: null,
  streamEvents: [],
  setLatestStreamEvent: (event) => set({ latestStreamEvent: event }),
  pushStreamEvent: (event) =>
    set((state) => ({
      latestStreamEvent: event,
      streamEvents: [...state.streamEvents.slice(-24), event],
    })),

  // All projects list
  projects: [],
  setProjects: (projects) => set({ projects }),
  addProject: (project) => set((state) => ({ projects: [...state.projects, project] })),
  removeProject: (projectId) =>
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== projectId),
      currentProject: state.currentProject?.id === projectId ? null : state.currentProject,
    })),

  // UI state
  isLoading: false,
  setIsLoading: (isLoading) => set({ isLoading }),
  error: null,
  setError: (error) => set({ error }),
}))