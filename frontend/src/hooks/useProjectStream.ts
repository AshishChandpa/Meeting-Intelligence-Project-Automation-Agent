import { useEffect } from 'react'
import { API_BASE_URL } from '@/lib/api'
import { useProjectStore } from '@/store/projectStore'
import type { ProjectState } from '@/types'

export function useProjectStream(projectId: string | null) {
  const { syncCurrentProject } = useProjectStore()

  useEffect(() => {
    if (!projectId) return

    const streamUrl = `${API_BASE_URL}/api/projects/${projectId}/stream`
    const eventSource = new EventSource(streamUrl)

    const handleProjectState = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as ProjectState
        if (data?.id === projectId) {
          syncCurrentProject(data)
        }
      } catch {
        // Ignore malformed stream payloads to keep UI subscription resilient.
      }
    }

    eventSource.addEventListener('project_state', handleProjectState as EventListener)

    return () => {
      eventSource.removeEventListener('project_state', handleProjectState as EventListener)
      eventSource.close()
    }
  }, [projectId, syncCurrentProject])
}

