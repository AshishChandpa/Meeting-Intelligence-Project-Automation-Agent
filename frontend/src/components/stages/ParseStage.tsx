import { useState } from 'react'
import { useProjectStore } from '@/store/projectStore'
import { getProject, submitStage1Feedback, approveStage1 } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Textarea } from '../ui/Textarea'
import { Badge } from '../ui/Badge'
import { Loader2 } from 'lucide-react'
import type { Extraction, Module, Requirement } from '@/types'

export function ParseStage() {
  const { currentProject, setCurrentProject, setIsLoading, setError } = useProjectStore()
  const [feedback, setFeedback] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (!currentProject?.extraction) return null

  const extraction = currentProject.extraction as Extraction

  const handleSubmitFeedback = async () => {
    if (!feedback.trim() || !currentProject) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await submitStage1Feedback(currentProject.id, { feedback })
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
      await approveStage1(currentProject.id)
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
    } catch (error: any) {
      setError(`Failed to approve: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stage 1: Requirement Extraction</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Project Info */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground">Project Name</label>
            <p className="text-lg">{extraction.project_name || 'Not specified'}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">Client</label>
            <p className="text-lg">{extraction.client_name || 'Not specified'}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">Vendor</label>
            <p className="text-lg">{extraction.vendor_name || 'Not specified'}</p>
          </div>
        </div>

        {/* Modules */}
        <div>
          <h3 className="mb-3 text-lg font-semibold">Modules ({extraction.modules.length})</h3>
          <div className="space-y-2">
            {extraction.modules.map((module: Module, i: number) => (
              <div key={i} className="flex items-start justify-between rounded-md border p-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{module.name}</span>
                    <Badge variant={module.priority.toLowerCase() as any}>{module.priority}</Badge>
                    <Badge variant={module.confidence}>{module.confidence}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{module.description}</p>
                  {module.deadline && (
                    <p className="mt-1 text-xs text-muted-foreground">Deadline: {module.deadline}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Requirements */}
        <div>
          <h3 className="mb-3 text-lg font-semibold">Requirements ({extraction.requirements.length})</h3>
          <div className="space-y-2">
            {extraction.requirements.map((req: Requirement, i: number) => (
              <div key={i} className="rounded-md border p-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{req.module}</span>
                  <Badge variant="outline">{req.type}</Badge>
                  <Badge variant={req.confidence}>{req.confidence}</Badge>
                </div>
                <p className="mt-1 text-sm">{req.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Integrations */}
        {extraction.integrations.length > 0 && (
          <div>
            <h3 className="mb-3 text-lg font-semibold">Integrations ({extraction.integrations.length})</h3>
            <div className="space-y-2">
              {extraction.integrations.map((integration, i: number) => (
                <div key={i} className="rounded-md border p-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{integration.system}</span>
                    <Badge variant={integration.confidence}>{integration.confidence}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{integration.purpose}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Constraints */}
        {extraction.constraints.length > 0 && (
          <div>
            <h3 className="mb-3 text-lg font-semibold">Constraints ({extraction.constraints.length})</h3>
            <div className="space-y-2">
              {extraction.constraints.map((constraint: any, i: number) => (
                <div key={i} className="rounded-md border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm flex-1">{constraint.description}</p>
                    <Badge variant={constraint.confidence || "medium"} className="shrink-0">
                      {constraint.confidence || "medium"} confidence
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Assumptions */}
        {extraction.assumptions && extraction.assumptions.length > 0 && (
          <div>
            <h3 className="mb-3 text-lg font-semibold text-blue-600 dark:text-blue-400">
              Assumptions ({extraction.assumptions.length})
            </h3>
            <div className="space-y-2">
              {extraction.assumptions.map((assumption: any, i: number) => (
                <div key={i} className="rounded-md border border-blue-200 bg-blue-50 p-3 dark:border-blue-900 dark:bg-blue-950">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm flex-1">{assumption.description}</p>
                    <Badge variant={assumption.confidence || "medium"} className="shrink-0">
                      {assumption.confidence || "medium"} confidence
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Unknowns */}
        {extraction.unknowns.length > 0 && (
          <div>
            <h3 className="mb-3 text-lg font-semibold text-yellow-600 dark:text-yellow-400">
              Unknowns ({extraction.unknowns.length})
            </h3>
            <div className="space-y-2">
              {extraction.unknowns.map((unknown, i: number) => (
                <div key={i} className="rounded-md border border-yellow-200 bg-yellow-50 p-3 dark:border-yellow-900 dark:bg-yellow-950">
                  <p className="text-sm">{unknown.description}</p>
                  {unknown.source && <p className="mt-1 text-xs text-muted-foreground">Source: {unknown.source}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-3 border-t pt-4">
          <Textarea
            placeholder="Type corrections here (e.g., 'Add a module for User Authentication')..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
          <div className="flex justify-between gap-3">
            <Button
              onClick={handleSubmitFeedback}
              disabled={!feedback.trim() || isSubmitting}
              variant="secondary"
            >
              {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Submit Correction
            </Button>
            <Button
              onClick={handleApprove}
              disabled={isSubmitting}
            >
              {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Approve & Continue
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}