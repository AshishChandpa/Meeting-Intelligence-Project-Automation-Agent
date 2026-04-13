import { useEffect } from 'react'
import { useProjectStore } from './store/projectStore'
import { ProjectSwitcher } from './components/ProjectSwitcher'
import { StageProgress } from './components/StageProgress'
import { ParseStage } from './components/stages/ParseStage'
import { ClarifyStage } from './components/stages/ClarifyStage'
import { SowStage } from './components/stages/SowStage'
import { SprintStage } from './components/stages/SprintStage'
import { JiraStage } from './components/stages/JiraStage'
import { Loader2, AlertCircle } from 'lucide-react'

function App() {
  const { currentProject, isLoading, error, setError } = useProjectStore()

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
          <div className="text-center">
            <h2 className="text-2xl font-semibold">No project selected</h2>
            <p className="mt-2 text-muted-foreground">Select or create a project to get started</p>
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
        <div className="border-b bg-destructive/10 px-4 py-3">
          <div className="container mx-auto flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-destructive hover:underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {currentProject && (
          <div className="mb-6">
            <StageProgress currentStage={currentProject.current_stage} />
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