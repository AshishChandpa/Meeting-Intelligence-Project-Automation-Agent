import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useProjectStore } from '@/store/projectStore'
import { getProject, submitSowFeedback, approveSow } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Textarea } from '../ui/Textarea'
import { Badge } from '../ui/Badge'
import { Loader2, Download } from 'lucide-react'

export function SowStage() {
  const { currentProject, setCurrentProject, setIsLoading, setError } = useProjectStore()
  const [feedback, setFeedback] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const sow = currentProject?.sow || ''
  const version = currentProject?.sow_version || 0
  const revisions = currentProject?.sow_revisions || []
  const hasRevisions = revisions.length > 0

  const handleSubmitFeedback = async () => {
    if (!feedback.trim() || !currentProject) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await submitSowFeedback(currentProject.id, { feedback })
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

    if (!hasRevisions) {
      setError('Please provide at least one round of feedback before approving.')
      return
    }

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await approveSow(currentProject.id)
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
    } catch (error: any) {
      setError(`Failed to approve: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const handleDownload = () => {
    if (!sow) return

    const blob = new Blob([sow], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentProject?.name || 'project'}-sow-v${version}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Stage 3: Scope of Work (v{version})</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{revisions.length} revision{revisions.length !== 1 ? 's' : ''}</Badge>
            <Button size="sm" variant="outline" onClick={handleDownload} disabled={!sow}>
              <Download className="mr-2 h-4 w-4" />
              Download
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* SoW Content */}
        <div className="prose max-w-none rounded-md border p-6 dark:prose-invert">
          {sow ? (
            <ReactMarkdown>{sow}</ReactMarkdown>
          ) : (
            <p className="text-muted-foreground">No SoW content yet.</p>
          )}
        </div>

        {/* Changelog */}
        {revisions.length > 0 && (
          <div>
            <h3 className="mb-3 font-semibold">Changelog</h3>
            <div className="space-y-2">
              {revisions.map((revision: any, i: number) => (
                <div key={i} className="rounded-md border p-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">v{revision.version}</Badge>
                    <span className="text-sm text-muted-foreground">
                      {new Date(revision.timestamp || Date.now()).toLocaleString()}
                    </span>
                  </div>
                  <p className="mt-2 text-sm font-medium">Changes:</p>
                  <p className="mt-1 text-sm text-muted-foreground">{revision.changelog}</p>
                  {revision.feedback && (
                    <>
                      <p className="mt-2 text-sm font-medium">Your feedback:</p>
                      <p className="mt-1 text-sm italic">"{revision.feedback}"</p>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-3 border-t pt-4">
          <Textarea
            placeholder="Type your feedback here (e.g., 'Add more details to the timeline section')..."
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
              Submit Feedback & Revise
            </Button>
            <Button onClick={handleApprove} disabled={isSubmitting || !hasRevisions}>
              {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Approve & Continue
            </Button>
          </div>
          {!hasRevisions && (
            <p className="text-center text-sm text-muted-foreground">
              Please provide at least one round of feedback before approving.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}