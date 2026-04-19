import { useEffect } from 'react'
import { API_BASE_URL } from '@/lib/api'
import { useProjectStore } from '@/store/projectStore'
import type { ProjectState, StreamEventPayload } from '@/types'

export function useProjectStream(projectId: string | null) {
  const { syncCurrentProject, pushStreamEvent, setError } = useProjectStore()

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

    const handleRuntimeEvent = (eventName: StreamEventPayload['event']) => (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as Omit<StreamEventPayload, 'event'>
        pushStreamEvent({ event: eventName, ...data })
      } catch {
        // Ignore malformed payloads for non-critical stream events.
      }
    }

    const runtimeEvents: StreamEventPayload['event'][] = [
      'stage_progress',
      'graph_node_finished',
      'llm_start',
      'llm_complete',
      'checkpoint_saved',
      'interrupt',
      'graph_error',
    ]

    const handlers = runtimeEvents.map((eventName) => ({
      eventName,
      handler: handleRuntimeEvent(eventName),
    }))

    const handleError = () => {
      setError('Live stream disconnected. Reconnecting automatically on next update.')
    }

    eventSource.addEventListener('project_state', handleProjectState as EventListener)
    handlers.forEach(({ eventName, handler }) => {
      eventSource.addEventListener(eventName, handler as EventListener)
    })
    eventSource.addEventListener('error', handleError as EventListener)

    return () => {
      eventSource.removeEventListener('project_state', handleProjectState as EventListener)
      handlers.forEach(({ eventName, handler }) => {
        eventSource.removeEventListener(eventName, handler as EventListener)
      })
      eventSource.removeEventListener('error', handleError as EventListener)
      eventSource.close()
    }
  }, [projectId, pushStreamEvent, setError, syncCurrentProject])
}

