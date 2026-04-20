import { create } from 'zustand'
import { ProjectListItem, ProjectState, StreamEventPayload } from '@/types'

function syncProjectListItem(projects: ProjectListItem[], project: ProjectState | null): ProjectListItem[] {
  if (!project) return projects

  return projects.map((item) =>
    item.id === project.id
      ? {
          ...item,
          name: project.name,
          current_stage: project.current_stage,
        }
      : item,
  )
}

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
  setCurrentProject: (project) =>
    set((state) => {
      const previousId = state.currentProject?.id ?? null
      const nextId = project?.id ?? null
      const didSwitchProject = previousId !== nextId

      return {
        currentProject: project,
        error: null,
        latestStreamEvent: didSwitchProject ? null : state.latestStreamEvent,
        streamEvents: didSwitchProject ? [] : state.streamEvents,
        projects: syncProjectListItem(state.projects, project),
      }
    }),
  syncCurrentProject: (project) =>
    set((state) => ({
      currentProject: project,
      projects: syncProjectListItem(state.projects, project),
    })),
  latestStreamEvent: null,
  streamEvents: [],
  setLatestStreamEvent: (event) => set({ latestStreamEvent: event }),
  pushStreamEvent: (event) =>
    set((state) => {
      const stampedEvent = event.timestamp ? event : { ...event, timestamp: Date.now() }

      return {
        latestStreamEvent: stampedEvent,
        streamEvents: [...state.streamEvents.slice(-24), stampedEvent],
      }
    }),

  // All projects list
  projects: [],
  setProjects: (projects) => set({ projects }),
  addProject: (project) =>
    set((state) => ({
      projects: state.projects.some((item) => item.id === project.id)
        ? state.projects.map((item) => (item.id === project.id ? project : item))
        : [...state.projects, project],
    })),
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