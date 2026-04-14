import { useState } from 'react'
import { useProjectStore } from '@/store/projectStore'
import { getProject, moveSprintTask, submitSprintFeedback, approveSprintPlan } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Textarea } from '../ui/Textarea'
import { Badge } from '../ui/Badge'
import { Loader2, AlertTriangle } from 'lucide-react'
import type { Task, Sprint } from '@/types'

export function SprintStage() {
  const { currentProject, setCurrentProject, setIsLoading, setError } = useProjectStore()
  const [feedback, setFeedback] = useState('')
  const [taskTargets, setTaskTargets] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const tasks = currentProject?.tasks || []
  const sprints = currentProject?.sprints || []
  const warnings = currentProject?.sprint_warnings || []

  const handleSubmitFeedback = async () => {
    if (!feedback.trim() || !currentProject) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await submitSprintFeedback(currentProject.id, { feedback })
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
      setFeedback('')
    } catch (error: any) {
      setError(`Failed to submit feedback: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const handleApprove = async () => {
    if (!currentProject) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await approveSprintPlan(currentProject.id)
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
    } catch (error: any) {
      setError(`Failed to approve: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const handleMoveTask = async (taskId: string) => {
    if (!currentProject) return
    const targetSprint = taskTargets[taskId]
    if (!targetSprint) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await moveSprintTask(currentProject.id, { task_id: taskId, sprint_name: targetSprint })
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
    } catch (error: any) {
      setError(`Failed to move task: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const getTaskById = (id: string) => tasks.find((t: Task) => t.id === id)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stage 4: Sprint Planning</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="rounded-md border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-900 dark:bg-yellow-950">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-600" />
              <div>
                <p className="font-medium text-yellow-800 dark:text-yellow-200">Warnings</p>
                <ul className="mt-2 list-disc list-inside text-sm text-yellow-700 dark:text-yellow-300">
                  {warnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* Summary */}
        <div className="grid grid-cols-3 gap-4 rounded-md border p-4">
          <div>
            <p className="text-sm text-muted-foreground">Total Tasks</p>
            <p className="text-2xl font-bold">{tasks.length}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Total Sprints</p>
            <p className="text-2xl font-bold">{sprints.length}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Total Points</p>
            <p className="text-2xl font-bold">{sprints.reduce((sum, s: Sprint) => sum + s.total_points, 0)}</p>
          </div>
        </div>

        {/* Sprints */}
        <div className="space-y-4">
          {sprints.map((sprint: Sprint, i: number) => (
            <div key={i} className="rounded-md border p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">{sprint.name}</h3>
                  <p className="text-sm text-muted-foreground">{sprint.goal}</p>
                </div>
                <Badge variant="outline">{sprint.total_points} points</Badge>
              </div>
              <div className="space-y-2">
                {sprint.task_ids.map((taskId) => {
                  const task = getTaskById(taskId)
                  if (!task) return null
                  return (
                    <div key={task.id} className="rounded-md bg-muted p-3">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{task.title}</span>
                            <Badge variant={task.priority.toLowerCase() as any}>{task.priority}</Badge>
                            <Badge variant="outline">{task.story_points} pts</Badge>
                          </div>
                          <p className="mt-1 text-sm text-muted-foreground">{task.description}</p>
                          {task.dependencies.length > 0 && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              Depends on: {task.dependencies.join(', ')}
                            </p>
                          )}
                          <div className="mt-2 flex items-center gap-2">
                            <select
                              className="h-8 rounded-md border bg-background px-2 text-xs"
                              value={taskTargets[task.id] || ''}
                              onChange={(e) => setTaskTargets({ ...taskTargets, [task.id]: e.target.value })}
                            >
                              <option value="">Move to sprint...</option>
                              {sprints
                                .filter((s: Sprint) => s.name !== sprint.name)
                                .map((s: Sprint) => (
                                  <option key={s.name} value={s.name}>
                                    {s.name}
                                  </option>
                                ))}
                            </select>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={!taskTargets[task.id] || isSubmitting}
                              onClick={() => handleMoveTask(task.id)}
                            >
                              Move
                            </Button>
                          </div>
                        </div>
                      </div>
                      {task.acceptance_criteria.length > 0 && (
                        <div className="mt-2">
                          <p className="text-xs font-medium">Acceptance Criteria:</p>
                          <ul className="ml-4 mt-1 list-disc text-xs text-muted-foreground">
                            {task.acceptance_criteria.map((ac, j) => (
                              <li key={j}>{ac}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-3 border-t pt-4">
          <Textarea
            placeholder="Request adjustments (e.g., 'Move task T3 to Sprint 1' or 'Change T5 to 5 points')..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
          <div className="flex justify-between">
            <Button
              onClick={handleSubmitFeedback}
              disabled={!feedback.trim() || isSubmitting}
              variant="secondary"
            >
              {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Request Adjustment
            </Button>
            <Button onClick={handleApprove} disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Approve & Continue to Jira
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}