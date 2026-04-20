import { Activity, AlertTriangle, Bot, CheckCircle2, CircleDashed, Clock3, Siren, Sparkles } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/Card'
import { Badge } from './ui/Badge'
import { cn } from '@/lib/utils'
import type { ProjectState, StreamEventPayload } from '@/types'

interface RuntimeActivityPanelProps {
  project: ProjectState
  latestEvent: StreamEventPayload | null
  events: StreamEventPayload[]
}

type EventTone = 'info' | 'success' | 'warning' | 'destructive' | 'secondary'

const EVENT_LABELS: Record<StreamEventPayload['event'], string> = {
  stage_progress: 'Stage progress',
  graph_node_finished: 'Graph node complete',
  llm_start: 'LLM started',
  llm_complete: 'LLM complete',
  checkpoint_saved: 'Checkpoint saved',
  interrupt: 'Awaiting review',
  graph_error: 'Runtime error',
}

function getEventTone(event: StreamEventPayload | null, project: ProjectState): EventTone {
  if (event?.event === 'graph_error') return 'destructive'
  if (project.pending_interrupts?.length) return 'warning'
  if (project.stage5_done || project.current_stage === 'done') return 'success'
  if (event?.event === 'checkpoint_saved' || event?.event === 'llm_complete') return 'success'
  if (event?.event === 'interrupt') return 'warning'
  if (!event) return 'secondary'
  return 'info'
}

function getEventIcon(event: StreamEventPayload['event']) {
  switch (event) {
    case 'graph_error':
      return Siren
    case 'interrupt':
      return AlertTriangle
    case 'checkpoint_saved':
      return CheckCircle2
    case 'llm_start':
      return Bot
    case 'llm_complete':
      return Sparkles
    case 'graph_node_finished':
      return Activity
    case 'stage_progress':
    default:
      return CircleDashed
  }
}

function formatRelativeTime(timestamp?: number) {
  if (!timestamp) return 'just now'

  const deltaMs = Date.now() - timestamp
  const seconds = Math.max(0, Math.round(deltaMs / 1000))

  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.round(minutes / 60)
  return `${hours}h ago`
}

function toneClasses(tone: EventTone) {
  return {
    info: 'surface-info',
    success: 'surface-success',
    warning: 'surface-warning',
    destructive: 'surface-destructive',
    secondary: 'surface-muted',
  }[tone]
}

export function RuntimeActivityPanel({ project, latestEvent, events }: RuntimeActivityPanelProps) {
  const latestProjectEvent = latestEvent?.project_id === project.id ? latestEvent : null
  const recentEvents = events
    .filter((event) => !event.project_id || event.project_id === project.id)
    .slice(-6)
    .reverse()

  const progress = typeof latestProjectEvent?.progress === 'number' ? latestProjectEvent.progress : undefined
  const tone = getEventTone(latestProjectEvent, project)
  const interruptMessage = project.pending_interrupts?.[0]?.message
  const nextNode = project.graph_next_nodes?.[0]

  return (
    <Card className="border-primary/10 shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-lg">Live activity</CardTitle>
              <Badge variant={tone}>{project.current_stage}</Badge>
              {progress !== undefined && <Badge variant="outline">{progress}%</Badge>}
              {project.graph_checkpoint_id && (
                <Badge variant="secondary" className="font-mono">
                  ckpt {project.graph_checkpoint_id.slice(0, 8)}
                </Badge>
              )}
            </div>
            <CardDescription>
              Runtime events stream here while the graph processes the transcript, pauses for review, and advances to the next stage.
            </CardDescription>
          </div>
          <div className={cn('rounded-lg border px-3 py-2 text-sm', toneClasses(tone))}>
            <div className="flex items-center gap-2 font-medium">
              <Clock3 className="h-4 w-4" />
              {project.pending_interrupts?.length ? 'Human review needed' : EVENT_LABELS[latestProjectEvent?.event ?? 'stage_progress']}
            </div>
            <div className="mt-1 text-sm opacity-90">
              {interruptMessage || latestProjectEvent?.message || 'Waiting for the next runtime update...'}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="surface-muted rounded-lg border p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Current stage</div>
            <div className="mt-2 text-sm font-medium capitalize">{project.current_stage}</div>
            <div className="mt-1 text-xs text-muted-foreground">Project-scoped execution with resumable state.</div>
          </div>
          <div className="surface-muted rounded-lg border p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Next graph node</div>
            <div className="mt-2 text-sm font-medium">{nextNode || 'Awaiting runtime update'}</div>
            <div className="mt-1 text-xs text-muted-foreground">Resumes from the saved checkpoint instead of replaying prior stages.</div>
          </div>
          <div className="surface-muted rounded-lg border p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pending review</div>
            <div className="mt-2 text-sm font-medium">{project.pending_interrupts?.length ? 'Yes' : 'No'}</div>
            <div className="mt-1 text-xs text-muted-foreground">{interruptMessage || 'The graph is actively running or waiting for the next step.'}</div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Progress</span>
            <span className="text-muted-foreground">{progress !== undefined ? `${progress}%` : 'Live stream active'}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${Math.max(progress ?? 8, 8)}%` }}
            />
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Recent events</h3>
            <span className="text-xs text-muted-foreground">Newest first</span>
          </div>

          {recentEvents.length === 0 ? (
            <div className="surface-muted rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              Event messages will appear here once the frontend receives the first runtime update.
            </div>
          ) : (
            <div className="space-y-2">
              {recentEvents.map((event, index) => {
                const Icon = getEventIcon(event.event)
                const rowTone = getEventTone(event, project)

                return (
                  <div
                    key={`${event.timestamp ?? index}-${event.event}-${event.node ?? index}`}
                    className={cn('rounded-lg border p-3', toneClasses(rowTone))}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="mt-0.5 rounded-full bg-background/80 p-1">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium">{EVENT_LABELS[event.event]}</span>
                            {event.node && (
                              <code className="rounded bg-background/70 px-1.5 py-0.5 text-xs text-muted-foreground">
                                {event.node}
                              </code>
                            )}
                            {typeof event.progress === 'number' && (
                              <span className="text-xs text-muted-foreground">{event.progress}%</span>
                            )}
                          </div>
                          <p className="mt-1 text-sm leading-6">
                            {event.message || event.preview || 'Runtime update received.'}
                          </p>
                        </div>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">{formatRelativeTime(event.timestamp)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

