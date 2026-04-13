import { useEffect, useState } from 'react'
import { ChevronDown, Plus, Trash2 } from 'lucide-react'
import { useProjectStore } from '@/store/projectStore'
import { listProjects, deleteProject, createProject, getProject } from '@/lib/api'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { Textarea } from './ui/Textarea'

export function ProjectSwitcher() {
  const { projects, currentProject, setProjects, setCurrentProject, addProject, removeProject, setIsLoading, setError } =
    useProjectStore()

  const [isOpen, setIsOpen] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [newTranscript, setNewTranscript] = useState('')

  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    try {
      setIsLoading(true)
      const data = await listProjects()
      setProjects(data)
    } catch (error: any) {
      setError(`Failed to load projects: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateProject = async () => {
    if (!newProjectName.trim() || !newTranscript.trim()) return

    try {
      setIsLoading(true)
      const project = await createProject({ name: newProjectName, transcript: newTranscript })
      addProject(project)
      setIsCreating(false)
      setNewProjectName('')
      setNewTranscript('')
      await loadProjects()
    } catch (error: any) {
      setError(`Failed to create project: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteProject = async (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this project?')) return

    try {
      setIsLoading(true)
      await deleteProject(projectId)
      removeProject(projectId)
      if (currentProject?.id === projectId) {
        setCurrentProject(null)
      }
    } catch (error: any) {
      setError(`Failed to delete project: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSelectProject = async (projectId: string) => {
    try {
      setIsLoading(true)
      const data = await getProject(projectId)
      setCurrentProject(data)
      setIsOpen(false)
    } catch (error: any) {
      setError(`Failed to load project: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="md"
        onClick={() => setIsOpen(!isOpen)}
        className="min-w-[300px] justify-between"
      >
        <span className="truncate">
          {currentProject ? currentProject.name : 'Select a project'}
        </span>
        <ChevronDown className="ml-2 h-4 w-4 shrink-0" />
      </Button>

      {isOpen && (
        <div className="bg-card absolute z-50 mt-2 w-[500px] rounded-md border bg-popover p-4 shadow-md">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Projects</h3>
            <Button size="sm" variant="outline" onClick={() => setIsCreating(!isCreating)}>
              <Plus className="mr-2 h-4 w-4" />
              New Project
            </Button>
          </div>

          {isCreating && (
            <Card className="mb-4 p-4">
              <Input
                placeholder="Project name"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                className="mb-2"
              />
              <Textarea
                placeholder="Paste transcript here..."
                value={newTranscript}
                onChange={(e) => setNewTranscript(e.target.value)}
                className="mb-3 min-h-[150px]"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={handleCreateProject} disabled={!newProjectName || !newTranscript}>
                  Create
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setIsCreating(false)}>
                  Cancel
                </Button>
              </div>
            </Card>
          )}

          <div className="max-h-[300px] space-y-1 overflow-y-auto">
            {projects.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">No projects yet</p>
            ) : (
              projects.map((project) => (
                <div
                  key={project.id}
                  className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent"
                >
                  <button
                    onClick={() => handleSelectProject(project.id)}
                    className="flex-1 text-left"
                  >
                    <div className="font-medium">{project.name}</div>
                    <div className="text-xs text-muted-foreground">Stage: {project.current_stage}</div>
                  </button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => handleDeleteProject(project.id, e)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}