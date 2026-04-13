import { useState } from 'react'
import { useProjectStore } from '@/store/projectStore'
import { getProject, setJiraConfig, testJiraConnection, getJiraPreview, syncToJira } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Loader2, ExternalLink, CheckCircle2, XCircle } from 'lucide-react'
import type { JiraConfig, JiraResult } from '@/types'

export function JiraStage() {
  const { currentProject, setCurrentProject, setIsLoading, setError } = useProjectStore()
  const [jiraConfig, setJiraConfigState] = useState<Partial<JiraConfig>>({
    domain: '',
    email: '',
    api_token: '',
    project_key: '',
  })
  const [isTesting, setIsTesting] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [preview, setPreview] = useState<any>(null)

  const jiraResults = currentProject?.jira_results || []

  const handleSetConfig = async () => {
    if (!currentProject || !jiraConfig.domain || !jiraConfig.email || !jiraConfig.api_token || !jiraConfig.project_key) {
      setError('Please fill in all Jira configuration fields')
      return
    }

    try {
      setIsLoading(true)
      await setJiraConfig(currentProject.id, jiraConfig as JiraConfig)
      await loadPreview()
      setTestResult(null)
    } catch (error: any) {
      setError(`Failed to save config: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleTestConnection = async () => {
    if (!currentProject) return

    try {
      setIsTesting(true)
      await testJiraConnection(currentProject.id)
      setTestResult({ success: true, message: 'Connection successful!' })
      await loadPreview()
    } catch (error: any) {
      setTestResult({ success: false, message: `Connection failed: ${error}` })
    } finally {
      setIsTesting(false)
    }
  }

  const loadPreview = async () => {
    if (!currentProject) return

    try {
      const data = await getJiraPreview(currentProject.id)
      setPreview(data)
    } catch (error: any) {
      setError(`Failed to load preview: ${error}`)
    }
  }

  const handleSync = async () => {
    if (!currentProject) return

    if (!confirm('This will create issues in Jira. Are you sure?')) return

    try {
      setIsSyncing(true)
      await syncToJira(currentProject.id)
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
    } catch (error: any) {
      setError(`Failed to sync to Jira: ${error}`)
    } finally {
      setIsSyncing(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Stage 5: Jira Integration</CardTitle>
          <a
            href="https://github.com/your-repo/blob/main/JIRA_SETUP.md"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-primary hover:underline"
          >
            Setup Guide →
          </a>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Help banner */}
        <div className="rounded-md border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
          <h4 className="font-semibold text-blue-900 dark:text-blue-100">Need help setting up Jira?</h4>
          <ul className="mt-2 space-y-1 text-sm text-blue-800 dark:text-blue-200">
            <li>• <strong>Domain:</strong> Your Atlassian URL (e.g., `mycompany.atlassian.net`)</li>
            <li>• <strong>API Token:</strong> Get it from <a href="https://id.atlassian.com/manage-api-tokens" target="_blank" rel="noopener noreferrer" className="underline hover:text-blue-600">id.atlassian.com/manage-api-tokens</a></li>
            <li>• <strong>Project Key:</strong> Check your Jira project URL (e.g., `MIP`, `DEMO`)</li>
            <li>• Project type must be <strong>Scrum</strong> (not Kanban)</li>
          </ul>
        </div>

        {/* Jira Config */}
        <div className="space-y-3">
          <h3 className="font-semibold">Jira Configuration</h3>
          <div className="grid grid-cols-2 gap-3">
            <Input
              placeholder="yourdomain.atlassian.net"
              value={jiraConfig.domain}
              onChange={(e) => setJiraConfigState({ ...jiraConfig, domain: e.target.value })}
            />
            <Input
              placeholder="you@example.com"
              value={jiraConfig.email}
              onChange={(e) => setJiraConfigState({ ...jiraConfig, email: e.target.value })}
            />
            <Input
              placeholder="API Token"
              type="password"
              value={jiraConfig.api_token}
              onChange={(e) => setJiraConfigState({ ...jiraConfig, api_token: e.target.value })}
            />
            <Input
              placeholder="Project Key (e.g., PROJ)"
              value={jiraConfig.project_key}
              onChange={(e) => setJiraConfigState({ ...jiraConfig, project_key: e.target.value.toUpperCase() })}
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSetConfig} size="sm">
              Save Config
            </Button>
            <Button onClick={handleTestConnection} size="sm" variant="secondary" disabled={isTesting}>
              {isTesting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Test Connection
            </Button>
          </div>
          {testResult && (
            <div className={`rounded-md p-3 ${testResult.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
              {testResult.message}
            </div>
          )}
        </div>

        {/* Preview */}
        {preview && (
          <div className="rounded-md border p-4">
            <h3 className="mb-3 font-semibold">Preview</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Epics</p>
                <p className="text-xl font-bold">{preview.epics.length}</p>
                <ul className="mt-1 text-xs">
                  {preview.epics.map((epic: string, i: number) => (
                    <li key={i}>{epic}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Issues</p>
                <p className="text-xl font-bold">{preview.issues}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Sprints</p>
                <p className="text-xl font-bold">{preview.sprints}</p>
              </div>
            </div>
          </div>
        )}

        {/* Sync Button */}
        {preview && jiraResults.length === 0 && (
          <div className="flex justify-end border-t pt-4">
            <Button onClick={handleSync} disabled={isSyncing} size="lg">
              {isSyncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Sync to Jira
            </Button>
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