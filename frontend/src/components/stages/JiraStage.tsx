import { useEffect, useState } from 'react'
import { useProjectStore } from '@/store/projectStore'
import { approveSprintPlan, getProject, getJiraPreview, syncToJiraBatch } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Loader2, ExternalLink, CheckCircle2, XCircle } from 'lucide-react'
import type { JiraBatch, JiraPreview, JiraResult, PendingInterrupt } from '@/types'

function getPendingJiraBatch(interrupts?: PendingInterrupt[]): JiraBatch | null {
  const interrupt = interrupts?.find((item) => item?.stage === 'jira' && typeof item?.batch === 'string')
  if (!interrupt) return null
  const batch = String(interrupt.batch)
  if (batch === 'epics' || batch === 'issues' || batch === 'sprints') return batch
  return null
}

export function JiraStage() {
  const { currentProject, setCurrentProject, setError } = useProjectStore()
  const [isSyncing, setIsSyncing] = useState(false)
  const [isRecovering, setIsRecovering] = useState(false)
  const [preview, setPreview] = useState<JiraPreview | null>(null)
  const [activeBatch, setActiveBatch] = useState<'epics' | 'issues' | 'sprints' | null>(null)

  const jiraResults = currentProject?.jira_results || []
  const jiraConfigStatus = currentProject?.jira_config_status
  const hasDetectedConfig = Boolean(jiraConfigStatus?.has_config)

  useEffect(() => {
    if (!currentProject) return

    void (async () => {
      try {
        const updated = await getProject(currentProject.id)
        setCurrentProject(updated)
        const data = await getJiraPreview(currentProject.id)
        setPreview(data)
      } catch {
        // Keep UI usable even if state refresh fails; manual actions can retry.
      }
    })()
  }, [currentProject?.id, setCurrentProject])

  const formatApiError = (error: any) => {
    const detail = error?.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length > 0) return String(detail[0]?.msg || detail[0])
    if (typeof error?.message === 'string' && error.message.trim()) return error.message
    return String(error)
  }


  const loadPreview = async () => {
    if (!currentProject) return

    try {
      const data = await getJiraPreview(currentProject.id)
      setPreview(data)
    } catch (error: any) {
      setError(`Failed to load preview: ${formatApiError(error)}`)
    }
  }

  const recoverJiraGate = async () => {
    if (!currentProject) return null

    setIsRecovering(true)
    try {
      let refreshed = await getProject(currentProject.id)
      setCurrentProject(refreshed)

      const hasPending = Boolean(getPendingJiraBatch(refreshed.pending_interrupts))
      if (!hasPending && !refreshed.stage5_done) {
        await approveSprintPlan(currentProject.id)
        refreshed = await getProject(currentProject.id)
        setCurrentProject(refreshed)
      }

      const data = await getJiraPreview(currentProject.id)
      setPreview(data)
      return refreshed
    } catch (error: any) {
      setError(`Failed to resume Stage 5: ${formatApiError(error)}`)
      return null
    } finally {
      setIsRecovering(false)
    }
  }

  const handleSyncBatch = async (batch: 'epics' | 'issues' | 'sprints') => {
    if (!currentProject) return

    try {
      setIsSyncing(true)
      setActiveBatch(batch)

      // Refresh graph checkpoint state before triggering a Jira batch write.
      let latest = await getProject(currentProject.id)
      setCurrentProject(latest)
      let expectedBatch = getPendingJiraBatch(latest.pending_interrupts)

      // If Stage 4 is approved but no pending interrupt, trigger graph progression first
      if (!expectedBatch && latest.stage4_approved && !latest.stage5_done && hasTasksAndSprints) {
        setError('Progressing to Stage 5... please wait.')
        await approveSprintPlan(currentProject.id)
        // Wait a moment for graph to progress
        await new Promise(resolve => setTimeout(resolve, 2000))
        latest = await getProject(currentProject.id)
        setCurrentProject(latest)
        expectedBatch = getPendingJiraBatch(latest.pending_interrupts)
      }

      if (expectedBatch !== batch) {
        const nextStep = expectedBatch
          ? `Current Jira review step expects '${expectedBatch}'.`
          : 'Stage 5 is not currently awaiting Jira batch confirmation.'
        setError(`Cannot sync '${batch}' right now. ${nextStep} Refresh project flow and retry.`)
        return
      }

      if (!confirm(`This will create ${batch} in Jira. Continue?`)) return

      await syncToJiraBatch(currentProject.id, batch)
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
      await loadPreview()
    } catch (error: any) {
      const shouldRecover =
        error?.response?.status === 400
        && String(error?.response?.data?.detail || '').toLowerCase().includes('awaiting jira batch confirmation')
      if (shouldRecover) {
        try {
          const refreshed = await recoverJiraGate()
          const expectedAfterRecovery = getPendingJiraBatch(refreshed?.pending_interrupts)
          if (refreshed && expectedAfterRecovery === batch) {
            await syncToJiraBatch(currentProject.id, batch)
            const updated = await getProject(currentProject.id)
            setCurrentProject(updated)
            await loadPreview()
            return
          }
        } catch {
          // Best-effort state refresh after a rejected batch.
        }
      }
      setError(`Failed to sync ${batch}: ${formatApiError(error)}`)
    } finally {
      setIsSyncing(false)
      setActiveBatch(null)
    }
  }

  const batchStatus = currentProject?.jira_batch_status || preview?.batch_status || {}
  const pendingJiraBatch = getPendingJiraBatch(currentProject?.pending_interrupts)
  const epicsDone = batchStatus.epics === 'done'
  const issuesDone = batchStatus.issues === 'done'
  const sprintsDone = batchStatus.sprints === 'done'
  const canRunEpics = pendingJiraBatch === 'epics' && !epicsDone
  const canRunIssues = pendingJiraBatch === 'issues' && epicsDone && !issuesDone
  const canRunSprints = pendingJiraBatch === 'sprints' && issuesDone && !sprintsDone
  const isLocked = !pendingJiraBatch && !currentProject?.stage5_done
  const hasTasksAndSprints = (currentProject?.tasks?.length || 0) > 0 && (currentProject?.sprints?.length || 0) > 0

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Stage 5: Jira Integration</CardTitle>

        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {hasDetectedConfig ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/80 dark:bg-emerald-950/40">
            <div className="flex items-center gap-2">
              <h4 className="font-semibold text-emerald-900 dark:text-emerald-100">Jira configuration detected</h4>
              <Badge variant="success">{jiraConfigStatus?.source || 'project'}</Badge>
            </div>
            <p className="mt-2 text-sm text-emerald-800 dark:text-emerald-200">
              Using <strong>{jiraConfigStatus?.domain}</strong> ({jiraConfigStatus?.project_key}) for this project.
              You can test the connection directly, or save a manual override below.
            </p>
          </div>
        ) : (
          <div className="rounded-md border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
            <h4 className="font-semibold text-blue-900 dark:text-blue-100">Need help setting up Jira?</h4>
            <ul className="mt-2 space-y-1 text-sm text-blue-800 dark:text-blue-200">
              <li>• <strong>Domain:</strong> Your Atlassian URL (e.g., `mycompany.atlassian.net`)</li>
              <li>• <strong>API Token:</strong> Get it from <a href="https://id.atlassian.com/manage-api-tokens" target="_blank" rel="noopener noreferrer" className="underline hover:text-blue-600">id.atlassian.com/manage-api-tokens</a></li>
              <li>• <strong>Project Key:</strong> Check your Jira project URL (e.g., `MIP`, `DEMO`)</li>
              <li>• Project type must be <strong>Scrum</strong> (not Kanban)</li>
            </ul>
          </div>
        )}

        {/* Stage 4 Not Completed Warning */}
        {!hasTasksAndSprints && !preview && (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/80 dark:bg-amber-950/40">
            <h4 className="font-semibold text-amber-900 dark:text-amber-100">⚠️ Stage 4 Not Completed</h4>
            <p className="mt-2 text-sm text-amber-800 dark:text-amber-200">
              Jira sync requires a completed sprint plan with tasks and sprints. Please complete Stage 4 (Sprint Planning) first.
            </p>
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={() => void recoverJiraGate()} disabled={isRecovering || isSyncing} variant="secondary" size="sm">
                {isRecovering ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Resume from Stage 4
              </Button>
              <span className="text-xs text-amber-700 dark:text-amber-300">
                This will approve the sprint plan and prepare Jira preview
              </span>
            </div>
          </div>
        )}


        {/* Preview */}
        {preview && (
          <div className="rounded-md border p-4">
            <h3 className="mb-3 font-semibold">Preview</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Epics</p>
                <p className="text-xl font-bold">{preview.counts.epics}</p>
                <ul className="mt-1 text-xs">
                  {preview.epics.map((epic, i: number) => (
                    <li key={i}>{epic.title}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Issues</p>
                <p className="text-xl font-bold">{preview.counts.issues}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Sprints</p>
                <p className="text-xl font-bold">{preview.counts.sprints}</p>
              </div>
            </div>
          </div>
        )}

        {/* Batch sync controls */}
        {preview && (
          <div className="space-y-3 border-t pt-4">
            <h3 className="font-semibold">Sync Batches (Confirm each step)</h3>
            <div className="rounded-md border border-muted bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
              {pendingJiraBatch
                ? `Awaiting Jira confirmation for '${pendingJiraBatch}'. Run this batch next.`
                : 'Jira batch sync is currently locked. Re-open Stage 5 flow (approve sprint stage if needed) to continue.'}
            </div>
            {isLocked ? (
              <div className="flex justify-start">
                <Button onClick={() => void recoverJiraGate()} disabled={isRecovering || isSyncing} variant="secondary" size="sm">
                  {isRecovering ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Resume Stage 5
                </Button>
              </div>
            ) : null}
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              <Button onClick={() => handleSyncBatch('epics')} disabled={isSyncing || !canRunEpics}>
                {isSyncing && activeBatch === 'epics' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {epicsDone ? 'Epics Created' : 'Create Epics'}
              </Button>
              <Button
                onClick={() => handleSyncBatch('issues')}
                disabled={isSyncing || !canRunIssues}
                variant="secondary"
              >
                {isSyncing && activeBatch === 'issues' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {issuesDone ? 'Issues Created' : 'Create Issues'}
              </Button>
              <Button
                onClick={() => handleSyncBatch('sprints')}
                disabled={isSyncing || !canRunSprints}
                variant="outline"
              >
                {isSyncing && activeBatch === 'sprints' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {sprintsDone ? 'Sprints Created' : 'Create Sprints'}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Current status: epics={batchStatus.epics || 'pending'}, issues={batchStatus.issues || 'pending'}, sprints={batchStatus.sprints || 'pending'}
            </p>
          </div>
        )}

        {/* Results */}
        {jiraResults.length > 0 && (
          <div className="space-y-3">
            <h3 className="font-semibold">Sync Results</h3>
            <div className="space-y-2">
              {jiraResults.map((result: JiraResult, i: number) => (
                <div key={i} className="flex items-center justify-between rounded-md border p-3">
                  <div className="flex items-center gap-3">
                    {result.status === 'created' ? (
                      <CheckCircle2 className="h-5 w-5 text-green-600" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-600" />
                    )}
                    <div>
                      <p className="font-medium">{result.title}</p>
                      <p className="text-sm text-muted-foreground">
                        {result.type}: {result.key}
                      </p>
                      {result.error && (
                        <p className="text-sm text-red-600">{result.error}</p>
                      )}
                    </div>
                  </div>
                  {result.status === 'created' && result.url && (
                    <Button size="sm" variant="outline" asChild>
                      <a href={result.url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="mr-2 h-4 w-4" />
                        View in Jira
                      </a>
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

