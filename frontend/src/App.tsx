import { useEffect } from 'react'
import { useProjectStore } from './store/projectStore'
import { ProjectSwitcher } from './components/ProjectSwitcher'
import { StageProgress } from './components/StageProgress'
import { RuntimeActivityPanel } from './components/RuntimeActivityPanel'
import { useProjectStream } from './hooks/useProjectStream'
import { ParseStage } from './components/stages/ParseStage'
import { ClarifyStage } from './components/stages/ClarifyStage'
import { SowStage } from './components/stages/SowStage'
import { SprintStage } from './components/stages/SprintStage'
import { JiraStage } from './components/stages/JiraStage'
import { Loader2, AlertCircle } from 'lucide-react'

function App() {
  const { currentProject, isLoading, error, latestStreamEvent, streamEvents, setError } = useProjectStore()
  useProjectStream(currentProject?.id ?? null)

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error, setError])

  const renderStage = () => {
    if (!currentProject) {
      return (
        <div className="flex flex-1 items-center justify-center">
          <div className="surface-muted max-w-xl rounded-2xl border border-dashed p-10 text-center shadow-sm">
            <h2 className="text-2xl font-semibold">No project selected</h2>
            <p className="mt-2 text-muted-foreground">
              Create a project with a transcript to start the graph workflow and watch live activity appear here.
            </p>
          </div>
        </div>
      )
    }

    const stage = currentProject.current_stage

    switch (stage) {
      case 'parse':
        return <ParseStage />
      case 'clarify':
        return <ClarifyStage />
      case 'sow':
        return <SowStage />
      case 'sprint':
        return <SprintStage />
      case 'jira':
      case 'done':
        return <JiraStage />
      default:
        return (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <AlertCircle className="mx-auto h-12 w-12 text-muted-foreground" />
              <h2 className="mt-4 text-xl font-semibold">Unknown stage</h2>
              <p className="mt-2 text-muted-foreground">Stage: {stage}</p>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold">Meeting Intelligence</h1>
            <ProjectSwitcher />
          </div>
          {isLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Loading...</span>
            </div>
          )}
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-3 text-rose-800 dark:border-rose-900/80 dark:bg-rose-950/40 dark:text-rose-200">
          <div className="container mx-auto flex items-center gap-2 text-sm">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-auto hover:underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {currentProject && (
          <div className="mb-6 space-y-4">
            <StageProgress currentStage={currentProject.current_stage} />
            <RuntimeActivityPanel
              project={currentProject}
              latestEvent={latestStreamEvent}
              events={streamEvents}
            />
          </div>
        )}
        <div className="max-w-5xl mx-auto">
          {renderStage()}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t py-6">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          Meeting Intelligence & Project Automation Agent
        </div>
      </footer>
    </div>
  )
}

export default App